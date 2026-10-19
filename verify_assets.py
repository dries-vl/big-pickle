"""Check every packed texel, including tile gutters, against the source images."""
import argparse
import json
import struct
import zlib
from pathlib import Path
from PIL import Image, ImageChops
from build_assets import CLASSES, ROOT

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--pack', type=Path, default=ROOT / 'resources.bin')
parser.add_argument('--heights', type=Path, default=ROOT / 'heights.png')
parser.add_argument('--cover', type=Path, default=ROOT / 'ground_types.png')
args = parser.parse_args()
pack = args.pack.read_bytes()
assert pack[:8] == b'REVOLT01'
length, = struct.unpack_from('<I', pack, 8)
meta = json.loads(pack[12:12 + length])
raw = zlib.decompress(pack[12 + length:])
size = meta['tile'] + 2
assert len(raw) == size * size * 2 * meta['rows'] * meta['columns']
heights = Image.open(args.heights).convert('RGB').getchannel('R')
cover = Image.open(args.cover).convert('RGB')
assert heights.size == cover.size == (meta['width'], meta['height'])
reverse = {value: key for key, value in CLASSES.items()}
palette = [component for i in range(256) for component in reverse.get(i, (0, 0, 0))]
for ty in range(meta['rows']):
    for tx in range(meta['columns']):
        offset = (ty * meta['columns'] + tx) * size * size * 2
        tile = Image.frombytes('LA', (size, size), raw[offset:offset + size * size * 2])
        h, ids = tile.split()
        rgb = Image.frombytes('P', ids.size, ids.tobytes())
        rgb.putpalette(palette)
        rgb = rgb.convert('RGB')
        # Independent reference: each row is clamped to the source, including corners.
        for row in range(size):
            y = max(0, min(heights.height - 1, ty * meta['tile'] + row - 1))
            for source, actual in ((heights, h), (cover, rgb)):
                reference = Image.new(source.mode, (size, 1))
                reference.putdata([source.getpixel((max(0, min(source.width - 1, tx * meta['tile'] + x - 1)), y)) for x in range(size)])
                assert ImageChops.difference(reference, actual.crop((0, row, size, row + 1))).getbbox() is None, (tx, ty, row)
print(f'PASS: {meta["width"]}×{meta["height"]}; all elevations, material IDs and gutters match')
