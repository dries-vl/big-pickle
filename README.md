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

From your PC, publish the current game and small maps with one command:

```sh
python deploy.py
```

Requires Python 3.11+, Pillow and OpenSSH on your PC, and Python 3 on the Linux
server. This builds `resources.bin` from the repository's `heights.png` and
`ground_types.png`, verifies all packed texels, and publishes **only `index.html`
and `resources.bin`** to <https://game.driesvl.com>. It publishes the working tree;
no Git commit, push, or GitHub credentials are required.

### Private machine configuration (once per PC)

Configure an SSH alias in your own `~/.ssh/config`. Put only its name in
`~/.config/big-pickle/deploy.json` (or `$XDG_CONFIG_HOME/big-pickle/deploy.json`):

```json
{"ssh_host":"your-ssh-alias"}
```

This file lives **outside Git**. Server addresses, usernames and SSH keys stay in
your SSH configuration/agent. The script stores no passwords or tokens and does
not disable SSH host-key checks or HTTPS certificate verification. An encrypted
SSH key may prompt for its passphrase unless already loaded in your SSH agent.

Alternatively: `python deploy.py --host your-ssh-alias`.

### What publication does

- Uploads to a new release directory and verifies SHA-256 checksums before activation.
- Switches both public file paths through one atomic `.current` symlink change.
  Existing flat-file deployments are migrated while preserving their original files.
- Fetches both files over public HTTPS and checks their hashes. If that fails,
  restores the previous release, unless another deployment has since taken over.
- Retains earlier releases in `.releases/` for recovery; no automatic deletion.
  Caddy only serves `/`, `/index.html`, and `/resources.bin`, so release directories
  are not exposed as additional public routes.

Routine updates run as your SSH user, need **no sudo**, and do not reload Caddy.
If the website directory needs initial setup, the command stages the two public
files plus `deploy/activate.sh` and `deploy/Caddyfile.game`, then prompts for sudo
in your terminal. Setup validates and backs up Caddy's config before reloading it.
Use `python deploy.py --setup` to explicitly reconfigure an existing installation.
DNS must already point at the server; Caddy handles HTTPS certificates and redirects.

For a local-only rehearsal:

```sh
python deploy.py --dry-run
```

The server uses cache revalidation; reload an already-open page to load a new
release. Python's development HTTP server is not needed in production.

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
4. Publish both runtime files using the same deployment command:

   ```sh
   python deploy.py
   ```

   Reload the site to see the new map. The server's `no-cache` policy revalidates
   the binary. An already-open page keeps its existing GPU map until reloaded.

The deployment command always rebuilds from the repository's default input pair
and default calibration. Commit the public source PNGs with their generated pack
to keep map changes reproducible.

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

`python -m unittest test_deploy.py` exercises publication, migration, upload
validation and rollback in local temporary directories, without contacting a server.

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
