# De Lage Landen

A Dutch Revolt strategy-game terrain study, rendered with WebGPU. Open the
Dutch HTML landing page, then **Verken het landschap**. Returning visits restore
the last camera position with **Verkenning voortzetten**.

## Run locally

```sh
python -m http.server 8000 --bind 127.0.0.1
```

Run this from the repository root. Open <http://localhost:8000> in a WebGPU-capable browser. Remote deployment
needs HTTPS. Deploy just **index.html** and **resources.bin** together.
No JS bundles, fonts, images, CDN resources, or favicon requests are needed.

- Drag or WASD / arrows: pan; wheel: zoom.
- Shift-drag / right-drag: orbit and tilt; Q/E: rotate.
- R: reset; Escape: menu. Touch dragging also pans.
- Camera state is stored locally; this is a terrain viewer, not a saved campaign.
- **Licht: ochtend / avond** changes the sun direction, warmth and atmosphere.
- **Hoogtelijnen** adds subtle antialiased ink contours. **− / +** also works on touchscreens.

### Living miniature landscape

Forest classes now carry seeded, shaded canopy clusters with irregular silhouettes,
drawn as instanced ellipsoid impostors. Cropland receives individual patch tones,
hedgerow-like edges and distance-filtered plough lines. Built-up ground has subtle
terracotta variation. These are illustrative material details, not historical
tree, parcel or building records. The source classifications remain authoritative.

Warm grazing sunlight, short heightfield shadow rays, slowly moving cloud shadows,
distance haze, rippling water and specular highlights give the map depth. The
background is a procedural atmospheric wash. All detail is generated locally:
the original two-file delivery remains intact, with no additional assets.

## Deployment

The public endpoint is `https://game.driesvl.com`. Deployment uses SSH and Caddy.
Keep SSH keys, server addresses, account names, passwords and provider tokens
in your machine's SSH configuration or credential store, outside this repository.
The repository contains only the public virtual-host configuration and deployment
code; it does not provide authentication. Activating the host requires server sudo
access. Configure DNS to the intended server before activation.

Choose your own SSH alias below (configured locally in `~/.ssh/config`):

```sh
DEPLOY_HOST=your-ssh-alias
ssh "$DEPLOY_HOST" 'mkdir -p game-deploy'
scp index.html resources.bin deploy/Caddyfile.game deploy/activate.sh "$DEPLOY_HOST:game-deploy/"
ssh -t "$DEPLOY_HOST" 'sudo bash game-deploy/activate.sh'
```

`deploy/activate.sh` validates a candidate Caddy configuration, installs the two
public files into `/var/www/game.driesvl.com`, backs up the existing configuration,
adds only the game host, and reloads Caddy. It restores the old configuration if
reload fails. Caddy handles certificate issuance/renewal and HTTP→HTTPS redirects.
The host only serves `/`, `/index.html`, and `/resources.bin`; it uses conditional
cache revalidation so a changed HTML/pack is not held behind an arbitrary TTL.

Repeat the upload/activation steps for later full releases. Public files are owned
by the user invoking sudo, so a map-only update can replace the binary without
changing the Caddy configuration (see below).

After activation, check `curl -I https://game.driesvl.com` and open that URL in
a WebGPU-capable browser. A Python development server is not needed in production.

## Build the binary resources

Requires Python and Pillow (`python -m pip install Pillow`). The generated
pack is included, so rebuilding is only necessary when changing the inputs.

```sh
python build_assets.py
python verify_assets.py
```

`heights.png` and `ground_types.png` are build inputs, never requested by the
browser. The pack starts with `REVOLT01`, a little-endian uint32 JSON-header
length, the UTF-8 metadata, then a zlib stream. Decompressed data is row-major
1026×1026 RG8 texture-array layers: height in R, material ID in G. Each layer
covers 1024×1024 source pixels plus one-texel gutters. Edge padding clamps to
the source; internal gutters copy neighboring source pixels. Heights are
bilinear-filtered; categorical materials use integer `textureLoad`.

The RGB palette matches ESA-style classes: dark green woodland, pink cropland,
yellow grassland, red built-up land, blue water, gray barren land, and teal
wetland. Unknown colors fail the build rather than silently misclassify data.
Historical accuracy/georeferencing cannot be inferred from these PNGs alone.

### Change which map is displayed

The browser always loads `resources.bin`; it never reads the source PNGs.
Replacing a PNG alone does **not** update the displayed map.

1. Replace the repository's `heights.png` and `ground_types.png` with the new
   paired exports. They must have identical pixel dimensions, orientation, and
   geographic extent. The pipeline does not reproject or align them for you.
2. Build and check the new runtime pack:

   ```sh
   python build_assets.py
   python verify_assets.py
   ```

3. Reload the local preview. Use **Beginbeeld** to reset a camera position saved
   while viewing the previous map. No HTML changes are required for new dimensions.
4. Publish the generated binary. After initial deployment, upload to a temporary
   name and rename it so visitors cannot download a partially uploaded pack:

   ```sh
   scp resources.bin "$DEPLOY_HOST:/var/www/game.driesvl.com/resources.bin.next"
   ssh "$DEPLOY_HOST" 'mv /var/www/game.driesvl.com/resources.bin.next /var/www/game.driesvl.com/resources.bin'
   ```

   Reload the site to see the new map. The server's `no-cache` policy revalidates
   the binary. An already-open page keeps its existing GPU map until reloaded.

Alternatively, build directly from files outside the repository:

```sh
python build_assets.py --heights /path/to/export/heights.png --cover /path/to/export/ground_types.png
python verify_assets.py --heights /path/to/export/heights.png --cover /path/to/export/ground_types.png
```

Both commands use the repository's `resources.bin` by default. If changing
`--output` on the builder, pass that same path with `--pack` to the verifier.
Record the source export/version and build parameters alongside any published
pack so it can be reproduced. Commit public source PNGs together with their
generated pack when using the repository's default input pair.

**Input format:** elevation must be 8-bit grayscale (or RGB/RGBA with identical
R/G/B channels). The current builder reads its red channel; 16-bit/float DEMs
need an explicit calibrated conversion first. Cover must use exact class colors:

| Material | RGB |
| --- | --- |
| Woodland | 0, 100, 0 |
| Cropland | 240, 150, 255 |
| Grassland | 255, 255, 76 |
| Built-up land | 250, 0, 0 |
| Water | 0, 100, 200 |
| Barren land | 180, 180, 180 |
| Wetland | 0, 150, 160 |
| Shrubland | 255, 187, 34 |
| Snow/ice | 255, 255, 255 |

Resample cover with **nearest-neighbor**, never bilinear/JPEG/antialiasing, which
would invent invalid class colors. Different palettes need an explicit mapping
in `CLASSES` in `build_assets.py`; new material types also need shader support.

### Store the full-resolution master maps

Keep large originals outside the public Git repository and the website root:

```text
~/.local/share/big-pickle/basemaps/
  low-countries-v1/
    source/       # untouched 40k originals, original precision and metadata
    exports/      # aligned height/cover crops or reduced-resolution runtime inputs
    provenance.md # origin, license, CRS, bounds, vertical units/datum and export steps
```

For remote backup, use a **private object-storage bucket** (for example Hetzner
Object Storage) with versioned object names. Keep access keys in a local credential
store, not Git, HTML, or the binary. Only intentionally published, licensed runtime
resources belong on the game website. Compression is not encryption: both source
PNGs committed here and terrain packed into `resources.bin` are publicly readable.

A 100 MB compressed source image is not a 100 MB GPU allocation. A 40,000² map
would occupy 1,600 current-size tiles and about **3.14 GiB** of RG8 GPU storage,
before CPU decoding and other resources; the current 256-layer renderer does
**not** support loading that full map. The exact limit also depends on height,
not just width. For now, export a matching crop or downsampled pair (e.g. 4,096²).
Keep the originals untouched for the future tiled-streaming pipeline described
below. Storing originals in object storage alone does not add streaming support.

### Elevation assumptions

The supplied height PNG is grayscale stored in RGBA, with only 22 distinct
8-bit elevations (68–89). It contains no physical scale or sea-level metadata.
Defaults borrow Rome's 81,920 m map width and 1,250 m full height range; the
minimum elevation is subtracted to keep coordinates near the origin. The
HTML's named `relief` constant applies 6× visual exaggeration. The original
height bytes are preserved in the pack. A four-texel normal stencil reduces
quantization banding. Override physical calibration when it is known:

```sh
python build_assets.py --width-m 81920 --height-scale-m 1250
```

`--width-m` is the horizontal extent in meters. `--height-scale-m` is the height
span represented by the **entire 0–255 encoding**, not the highest observed pixel
minus the lowest. Rendered relative height is
`(pixel - minimum_pixel) / 255 × height_scale × relief`. Adjust calibration when
changing geographic extent or elevation encoding. Square ground pixels are assumed;
the map's north–south extent follows its pixel aspect ratio.

Water is selected from ground-cover classes and shaded in Rome's shallow/deep
palette. It follows the supplied height surface: a global sea plane would be
incorrect without calibrated elevation/sea-level data. Surface detail is
procedural rather than borrowing Rome's external detail textures.

## Relationship to Rome

Inspected `../rome/shaders.slang`, `shaders.c`, `main.c`, and `vk_texture.h`.
The renderer translates the relevant terrain techniques rather than the
unit simulation and Vulkan-specific indirect-draw machinery:

- Procedural indexed grids displaced by the height texture in the vertex shader.
- Instanced terrain patches, adaptive quadtree subdivision, and edge skirts.
- Height-derived normals, slope-based rock blending, directional sunlight,
  ambient skylight, slope occlusion, and distance fog (now artistically extended).
- Logarithmic distance-blended detail scales and discrete ground materials.
- Infinite reverse-Z projection (`near / viewZ`), `depth32float`, clear 0,
  and `greater` depth comparison, matching Rome's Vulkan depth convention.

World UVs retain PNG orientation: north at the top when camera yaw is zero.
No invented city positions, province borders, or coastlines are overlaid.

## Startup / two-file delivery

All CSS, UI, JavaScript, and WGSL are inline in `index.html`. The landing page
and historical-setting dialog work without the binary or GPU. A preload and
matching fetch request begin the **single** binary download. Adapter/device
initialization starts independently. Once the device is available, asynchronous
pipeline compilation overlaps pack decompression/upload. A completed first
frame is prepared behind the menu. An early click waits on the same readiness
promise; later clicks reveal the prepared canvas. GPU loss or load failure
returns to the HTML menu with an explanation.

The open landscape animates at up to 24 fps; input can request additional frames.
Only one GPU frame is allowed in flight, coalescing newer camera updates on slow
devices. The menu and hidden tabs do no continuous GPU work. Reduced-motion
preferences disable ambient animation. Performance marks expose download, decode, device,
pipeline, upload-queued, GPU-first-frame-complete, renderer-ready, click, and
playing milestones. GPU completion and animation-frame callbacks are not
claims of a physically displayed frame timestamp.

## Larger basemaps

Dimensions come from the pack. Use `--heights`, `--cover`, and optionally
`--output` to build other inputs. Texture arrays avoid relying on a 10k-wide
GPU texture, while fixed 32×32-cell patches decouple mesh size from raster
size. Mixed LODs are skirted. The default 256-layer limit supports square maps
up to 16,384×16,384, subject to GPU memory; rectangular maps also work.

A 10,240² map uses 100 layers, about **201 MiB of GPU terrain storage**, plus
temporary decompression/upload memory. The current implementation downloads
and uploads the entire pack; it is not a virtual-texture streaming system.
For substantially larger datasets, the next step is an indexed, independently
compressed tile directory inside the **same binary file**, HTTP Range support,
and a bounded GPU tile cache. Python's basic server suffices for this build;
range streaming would require an appropriate server. No extra resource URLs
are necessary for that extension.

## Verification

`verify_assets.py` independently compares every packed height/material texel
and gutter against the PNGs. Browser checks during implementation use Chromium
WebGPU (software Vulkan), checking shader/pipeline validation, actual frames,
controls, resize, menu behavior, and the two-request network contract.
Also exercised: early entry during delayed download, missing binary,
unavailable WebGPU, camera persistence, and a synthetic 10,241×1,025 raster
with 22 texture layers (including non-power-of-two edges). Its packed texels
and gutters passed the same independent source comparison, and it rendered
successfully in WebGPU. This is a large-dimension correctness check, not a
10k-square performance benchmark.
