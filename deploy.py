#!/usr/bin/env python3
"""Build, verify and publish the two-file game using existing SSH authentication."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tarfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parent
FILES = ('index.html', 'resources.bin')
URL = 'https://game.driesvl.com'
CONFIG = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'big-pickle/deploy.json'

# Runs as the SSH user, never root. Streaming upload accepts only the two named
# regular files; no tar extraction, credentials, repository, or source PNGs.
REMOTE = r'''
import fcntl, hashlib, json, os, re, shutil, sys, tarfile, tempfile
from pathlib import Path
root = Path('/var/www/game.driesvl.com')
names = ('index.html', 'resources.bin')
mode = sys.argv[1]
if mode == 'status':
    print('ready' if root.is_dir() and os.access(root, os.W_OK) else 'setup')
    sys.exit(0)
def switch(target):
    temporary = root / '.current.next'
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(target)
    os.replace(temporary, root / '.current')
def release_path(value):
    if not re.fullmatch(r'\.releases/[a-zA-Z0-9_-]+', value):
        raise ValueError('Invalid release path')
    return root / value
with (root / '.deploy.lock').open('a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    current = root / '.current'
    if mode == 'rollback':
        expected, previous = sys.argv[2:]
        release_path(expected)
        old = release_path(previous)
        if not old.is_dir() or os.readlink(current) != expected:
            raise RuntimeError('Rollback refused: release changed or previous release missing')
        switch(previous)
        print('Previous release restored')
        sys.exit(0)
    if mode != 'publish':
        raise ValueError('Unknown operation')
    digests = dict(zip(names, sys.argv[2:]))
    if len(digests) != 2 or not all(re.fullmatch(r'[0-9a-f]{64}', v) for v in digests.values()):
        raise ValueError('Missing or invalid checksums')
    releases = root / '.releases'
    releases.mkdir(mode=0o755, exist_ok=True)
    # Refuse to replace unrelated links or directories during first-run migration.
    if current.exists() and not current.is_symlink():
        raise RuntimeError('.current is not a release symlink')
    for name in names:
        path = root / name
        if path.is_symlink():
            if os.readlink(path) != '.current/' + name:
                raise RuntimeError('Unexpected website symlink: ' + name)
        elif path.exists() and not path.is_file():
            raise RuntimeError('Unexpected website directory: ' + name)
    folder = Path(tempfile.mkdtemp(prefix='release-', dir=releases))
    published = False
    try:
        seen = set()
        with tarfile.open(fileobj=sys.stdin.buffer, mode='r|') as archive:
            for entry in archive:
                if entry.name not in names or not entry.isfile() or entry.name in seen:
                    raise ValueError('Unexpected upload entry')
                seen.add(entry.name)
                with archive.extractfile(entry) as source, (folder / entry.name).open('wb') as dest:
                    digest = hashlib.sha256()
                    while chunk := source.read(1024 * 1024):
                        digest.update(chunk)
                        dest.write(chunk)
                    dest.flush()
                    os.fsync(dest.fileno())
                if digest.hexdigest() != digests[entry.name]:
                    raise ValueError('Upload checksum mismatch: ' + entry.name)
                (folder / entry.name).chmod(0o644)
        if seen != set(names):
            raise ValueError('Incomplete upload')
        folder.chmod(0o755)
        # Preserve a previous flat-file deployment before introducing indirection.
        if not current.is_symlink():
            if not all((root / name).is_file() for name in names):
                raise RuntimeError('Initial website files missing; run with --setup')
            old = Path(tempfile.mkdtemp(prefix='previous-', dir=releases))
            for name in names:
                shutil.copyfile(root / name, old / name)
                (old / name).chmod(0o644)
            old.chmod(0o755)
            switch(str(old.relative_to(root)))
        previous = os.readlink(current)
        release_path(previous)
        for name in names:
            link = root / ('.' + name + '.next')
            link.unlink(missing_ok=True)
            link.symlink_to('.current/' + name)
            os.replace(link, root / name)
        target = str(folder.relative_to(root))
        switch(target)
        published = True
        print(json.dumps({'release': target, 'previous': previous}))
    finally:
        if not published:
            shutil.rmtree(folder)
'''


def run(command, **kwargs):
    return subprocess.run(command, check=True, **kwargs)


def ssh(host, *args, data=None):
    command = 'python3 -c ' + shlex.quote(REMOTE) + ' ' + shlex.join(args)
    # Keep normal host-key checking and SSH-agent/key handling. No stored password.
    return run(['ssh', '-o', 'ConnectTimeout=15', host, command],
               input=data, stdout=subprocess.PIPE).stdout.decode().strip()


def setup(host):
    print('Initial server setup: sudo may ask for your password in the terminal.', flush=True)
    stage = run(['ssh', host, 'mktemp -d "$HOME/.big-pickle-setup.XXXXXXXX"'],
                capture_output=True, text=True).stdout.strip()
    if not re.fullmatch(r'/[a-zA-Z0-9_./-]+/\.big-pickle-setup\.[a-zA-Z0-9]+', stage):
        raise RuntimeError('Unexpected setup staging path')
    run(['scp', '--', *(str(ROOT / name) for name in FILES),
         str(ROOT / 'deploy/Caddyfile.game'), str(ROOT / 'deploy/activate.sh'), f'{host}:{stage}/'])
    run(['ssh', '-t', host, 'sudo bash ' + shlex.quote(stage + '/activate.sh')])
    # Retain failed setup stages for diagnosis; successful stages contain no secrets.
    run(['ssh', host, 'rm -r -- ' + shlex.quote(stage)])


def verify_live(digests):
    for attempt in range(6):
        try:
            for name, expected in digests.items():
                request = urllib.request.Request(URL + '/' + name,
                                                 headers={'Cache-Control': 'no-cache'})
                with urllib.request.urlopen(request, timeout=20) as response:
                    if response.geturl() != URL + '/' + name:
                        raise RuntimeError('Unexpected website redirect')
                    actual = hashlib.file_digest(response, 'sha256').hexdigest()
                if actual != expected:
                    raise RuntimeError('Live checksum mismatch: ' + name)
            return
        except (OSError, RuntimeError) as error:
            if attempt == 5:
                raise RuntimeError(f'HTTPS verification failed: {error}') from error
            time.sleep(3)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', help='SSH alias; otherwise read private deploy.json')
    parser.add_argument('--setup', action='store_true', help='Configure Caddy using interactive sudo')
    parser.add_argument('--dry-run', action='store_true', help='Build and verify locally; no SSH or upload')
    args = parser.parse_args()
    config = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
    if not isinstance(config, dict):
        raise ValueError(f'Expected a JSON object in {CONFIG}')
    host = args.host or config.get('ssh_host')
    if not isinstance(host, str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]*', host):
        parser.error(f'Set an SSH alias with --host or {{"ssh_host":"your-alias"}} in {CONFIG}')
    print('Building the current heights.png and ground_types.png…', flush=True)
    run([sys.executable, str(ROOT / 'build_assets.py')])
    run([sys.executable, str(ROOT / 'verify_assets.py')])
    digests = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in FILES}
    if args.dry_run:
        print(f'Local checks passed. Would publish {", ".join(FILES)} to {URL} using SSH alias {host}.')
        return
    if args.setup or ssh(host, 'status') == 'setup':
        setup(host)
    # The current pack is small; archive exactly the two runtime files in memory.
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode='w') as archive:
        for name in FILES:
            data = (ROOT / name).read_bytes()
            if hashlib.sha256(data).hexdigest() != digests[name]:
                raise RuntimeError(f'{name} changed during deployment; rerun the command')
            entry = tarfile.TarInfo(name)
            entry.size = len(data)
            archive.addfile(entry, io.BytesIO(data))
    print('Uploading and activating a verified release…', flush=True)
    result = json.loads(ssh(host, 'publish', *(digests[name] for name in FILES), data=payload.getvalue()))
    try:
        verify_live(digests)
    except Exception:
        print('Live verification failed; restoring the previous release.', file=sys.stderr)
        ssh(host, 'rollback', result['release'], result['previous'])
        raise
    print(f'Live and verified: {URL}\nRelease: {result["release"]}\nPrevious: {result["previous"]}')


if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError as error:
        sys.exit(f'Deployment failed: {error.cmd[0]} exited with status {error.returncode}; see output above.')
    except (OSError, ValueError, RuntimeError) as error:
        sys.exit(f'Deployment failed: {error}')
