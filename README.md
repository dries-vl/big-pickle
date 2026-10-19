# Low Countries

A Dutch Revolt strategy-game terrain study, rendered with WebGPU. Open the
HTML landing page, then **Explore the landscape**. Returning visits restore
the last camera position with **Continue exploring**.

## Run locally

```sh
python -m http.server 8000 --bind 127.0.0.1 --directory /home/dries/apps/dev/big-pickle
```

Open <http://localhost:8000> in a WebGPU-capable browser. Remote deployment
needs HTTPS. Deploy just **index.html** and **resources.bin** together.
No JS bundles, fonts, images, CDN resources, or favicon requests are needed.

- Drag or WASD / arrows: pan; wheel: zoom.
- Shift-drag / right-drag: orbit and tilt; Q/E: rotate.
- R: reset; Escape: menu. Touch dragging also pans.
- Camera state is stored locally; this is a terrain viewer, not a saved campaign.

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
- Height-derived normals, slope-based rock blending, squared directional sun,
  hemispheric skylight, slope occlusion, and distance fog.
- Logarithmic distance-blended detail scales and discrete ground materials.
- Infinite reverse-Z projection (`near / viewZ`), `depth32float`, clear 0,
  and `greater` depth comparison, matching Rome's Vulkan depth convention.

World UVs retain PNG orientation: north at the top at the default camera yaw.
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

Rendering is event-driven (camera input/resize), with no continuous GPU work
while the menu is idle. Performance marks expose download, decode, device,
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
