"""Build the sole runtime resource pack. Requires Pillow; no runtime dependencies."""
import argparse
import json
import struct
import zlib
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent
# ESA-style RGB classes in the supplied image → compact material IDs.
CLASSES = {(0, 100, 0): 1, (240, 150, 255): 2, (255, 255, 76): 3,
           (250, 0, 0): 4, (0, 100, 200): 5, (180, 180, 180): 6,
           (0, 150, 160): 7, (255, 187, 34): 8, (255, 255, 255): 9}


def build():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--heights', type=Path, default=ROOT / 'heights.png')
    parser.add_argument('--cover', type=Path, default=ROOT / 'ground_types.png')
    parser.add_argument('--output', type=Path, default=ROOT / 'resources.bin')
    parser.add_argument('--width-m', type=float, default=81920)
    parser.add_argument('--height-scale-m', type=float, default=1250)
    args = parser.parse_args()
    height = Image.open(args.heights).convert('RGB')
    cover = Image.open(args.cover).convert('RGB')
    if height.size != cover.size or min(height.size) < 2:
        raise ValueError('Height and cover dimensions must match and be at least 2×2')
    if args.width_m <= 0 or args.height_scale_m <= 0:
        raise ValueError('Physical dimensions must be positive')
    colors = cover.getcolors(height.width * height.height)
    unknown = [rgb for _, rgb in colors if rgb not in CLASSES]
    if unknown:
        raise ValueError(f'Unknown ground-cover colors (add explicit mappings): {unknown[:20]}')
    # Exact categorical translation: never interpolate IDs or interpret red as height.
    palette = Image.new('P', (1, 1))
    palette.putpalette([v for rgb in CLASSES for v in rgb] + [0] * (768 - len(CLASSES) * 3))
    indexed = cover.quantize(palette=palette, dither=Image.Dither.NONE)
    ids = indexed.point(list(CLASSES.values()) + [0] * (256 - len(CLASSES)), 'L')
    height = height.getchannel('R')
    tile = 1024
    columns = (height.width + tile - 1) // tile
    rows = (height.height + tile - 1) // tile
    if columns * rows > 256:
        raise ValueError('Pack exceeds portable 256 texture-array layers')
    meta = dict(version=1, width=height.width, height=height.height, tile=tile,
                columns=columns, rows=rows, widthMeters=args.width_m,
                heightScale=args.height_scale_m, heightBase=height.getextrema()[0] / 255)
    header = json.dumps(meta, separators=(',', ':')).encode()
    compressor = zlib.compressobj(9)
    output = args.output
    with output.open('wb') as stream:
        stream.write(b'REVOLT01' + struct.pack('<I', len(header)) + header)
        # One-texel gutters preserve bilinear sampling and normals across tile seams.
        for y in range(rows):
            for x in range(columns):
                box = (x * tile - 1, y * tile - 1, (x + 1) * tile + 1, (y + 1) * tile + 1)
                channels = []
                for image in (height, ids):
                    left, top, right, bottom = box
                    crop = image.crop((max(0, left), max(0, top), min(image.width, right), min(image.height, bottom)))
                    padded = Image.new('L', (tile + 2, tile + 2))
                    ox, oy = max(0, -left), max(0, -top)
                    padded.paste(crop, (ox, oy))
                    if ox:
                        padded.paste(crop.crop((0, 0, 1, crop.height)), (0, oy))
                    ex = ox + crop.width
                    if ex < tile + 2:
                        padded.paste(padded.crop((ex - 1, oy, ex, oy + crop.height)).resize((tile + 2 - ex, crop.height)), (ex, oy))
                    if oy:
                        padded.paste(padded.crop((0, oy, tile + 2, oy + 1)), (0, 0))
                    ey = oy + crop.height
                    if ey < tile + 2:
                        padded.paste(padded.crop((0, ey - 1, tile + 2, ey)).resize((tile + 2, tile + 2 - ey)), (0, ey))
                    channels.append(padded)
                stream.write(compressor.compress(Image.merge('LA', channels).tobytes()))
        stream.write(compressor.flush())
    print(f'{output.name}: {output.stat().st_size:,} bytes; {height.width}×{height.height}, {columns * rows} RG8 tiles')


if __name__ == '__main__':
    build()
