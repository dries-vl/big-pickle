"""Exercise release publication in a temporary directory; never contacts a server."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

import deploy


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.remote = deploy.REMOTE.replace('/var/www/game.driesvl.com', str(self.root))
        self.old = {'index.html': b'old html', 'resources.bin': b'old terrain'}
        self.new = {'index.html': b'new html', 'resources.bin': b'new terrain'}
        for name, data in self.old.items():
            (self.root / name).write_bytes(data)

    def run_remote(self, *args, data=None):
        return subprocess.run([sys.executable, '-c', self.remote, *args],
                              input=data, capture_output=True)

    def publish(self, files=None, digests=None):
        files = self.new if files is None else files
        digests = digests or [hashlib.sha256(self.new[name]).hexdigest() for name in deploy.FILES]
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode='w') as archive:
            for name, data in files.items():
                entry = tarfile.TarInfo(name)
                entry.size = len(data)
                archive.addfile(entry, io.BytesIO(data))
        return self.run_remote('publish', *digests, data=stream.getvalue())

    def assert_content(self, expected):
        self.assertEqual({name: (self.root / name).read_bytes() for name in deploy.FILES}, expected)

    def test_migration_and_atomic_release_switch(self):
        result = self.publish()
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        state = json.loads(result.stdout)
        self.assert_content(self.new)
        for name, data in self.old.items():
            self.assertTrue((self.root / name).is_symlink())
            self.assertEqual((self.root / state['previous'] / name).read_bytes(), data)
        self.assertEqual(str((self.root / '.current').readlink()), state['release'])

    def test_wrong_checksum_preserves_live_release(self):
        self.assertEqual(self.publish().returncode, 0)
        before = (self.root / '.current').readlink()
        result = self.publish(digests=['0' * 64, '0' * 64])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.root / '.current').readlink(), before)
        self.assert_content(self.new)

    def test_incomplete_upload_preserves_flat_files(self):
        self.assertNotEqual(self.publish({'index.html': self.new['index.html']}).returncode, 0)
        self.assert_content(self.old)
        self.assertFalse((self.root / '.current').exists())

    def test_unexpected_archive_path_is_rejected(self):
        result = self.publish({'../outside': b'not allowed'})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'Unexpected upload entry', result.stderr)
        self.assert_content(self.old)

    def test_rollback_restores_both_files(self):
        state = json.loads(self.publish().stdout)
        result = self.run_remote('rollback', state['release'], state['previous'])
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assert_content(self.old)

    def test_stale_rollback_cannot_overwrite_newer_deployment(self):
        first = json.loads(self.publish().stdout)
        second = json.loads(self.publish().stdout)
        result = self.run_remote('rollback', first['release'], first['previous'])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(str((self.root / '.current').readlink()), second['release'])


if __name__ == '__main__':
    unittest.main()
