#!/usr/bin/env bash
# Run on the server: sudo bash game-deploy/activate.sh
# Caddy obtains/renews HTTPS automatically; existing virtual hosts are retained.
set -euo pipefail
cd -- "$(dirname -- "$0")"
if [[ $EUID != 0 ]]; then
    printf 'Voer dit script uit met sudo.\n' >&2
    exit 1
fi
owner=${SUDO_USER:-root}
group=$(id -gn "$owner")
for file in index.html resources.bin Caddyfile.game; do
    test -s "$file"
done
config=/etc/caddy/Caddyfile
candidate=$(mktemp /etc/caddy/Caddyfile.game.XXXXXX)
trap 'rm -f "$candidate"' EXIT
python3 - "$config" "$candidate" <<'PY'
from pathlib import Path
import re
import sys

source, target = map(Path, sys.argv[1:])
text = source.read_text()
block = Path('Caddyfile.game').read_text()
pattern = r'(?ms)^# BEGIN low-countries-game\n.*?^# END low-countries-game\n?'
if re.search(pattern, text):
    text = re.sub(pattern, lambda _: block, text)
else:
    # Never silently overwrite an independently configured host.
    if re.search(r'(?m)^\s*(?:https?://)?game\.driesvl\.com\s*\{', text):
        raise SystemExit('game.driesvl.com bestaat al; controleer de configuratie eerst.')
    text += '\n' + block
target.write_text(text)
PY
caddy validate --config "$candidate" --adapter caddyfile
install -d -m 755 -o "$owner" -g "$group" /var/www/game.driesvl.com
# Later --setup runs only reconfigure Caddy; deploy.py manages existing releases.
if [[ ! -L /var/www/game.driesvl.com/.current ]]; then
    install -m 644 -o "$owner" -g "$group" index.html resources.bin /var/www/game.driesvl.com/
fi
backup="${config}.before-game.$(date +%Y%m%d-%H%M%S)"
cp -p "$config" "$backup"
install -m 644 -o root -g root "$candidate" "$config"
if ! systemctl reload caddy; then
    cp -p "$backup" "$config"
    systemctl reload caddy || true
    printf 'Herladen mislukt; de vorige Caddy-configuratie is teruggezet.\n' >&2
    exit 1
fi
printf 'Geactiveerd: https://game.driesvl.com (certificaatuitgifte kan even duren).\n'
printf 'Vorige configuratie: %s\n' "$backup"
