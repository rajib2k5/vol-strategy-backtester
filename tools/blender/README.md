# tools/blender

Blender scripts that turn the app's JSON into pictures for the docs.

**Status: render pending — Blender not reachable on this machine (aarch64, no bpy wheel).**
The script has not been run inside Blender yet, so `docs/images/blender/surface_hero.png`
does not exist. Only the pure-Python half has been exercised (see "What has been checked").

## render_surface_hero.py

Renders a hero image of an implied-vol surface:

- x = log-moneyness `k`, y = days to expiry, z = implied vol, each axis scaled to a box.
- The surface is coloured by IV with viridis (perceptually uniform, so equal IV steps
  look like equal colour steps) and drawn with a thin wireframe on top.
- Axis titles ("log-moneyness k", "days to expiry", "implied vol") with the min and max
  value at the ends of each axis, and a caption read from the file's `label`
  ("Illustrative SSVI surface — not market data" for the illustrative file).
- Three suns (key, fill, rim) and a 3/4 camera whose distance is fitted so the whole
  box and its labels fit in the frame.

Run it from the repo root, with Blender's own Python:

```bash
blender --background --python tools/blender/render_surface_hero.py -- \
    --data app/public/data/illustrative_surface.json \
    --out docs/images/blender/surface_hero.png
```

Everything after the lone `--` goes to the script; Blender ignores it.

| Option | Default | Meaning |
|---|---|---|
| `--data` | `app/public/data/illustrative_surface.json` | Surface JSON: `moneyness`, `dte`, `iv[i_dte][j_k]`. |
| `--out` | `docs/images/blender/surface_hero.png` | Output file; must end in `.png`. Parent folders are created. |
| `--samples` | `64` | Render samples (Cycles, or EEVEE's render samples). |
| `--resolution` | `1920x1080` | Image size as `WIDTHxHEIGHT`. |

Blender exits with status 0 even when a script raises. To make a failed render fail the
command (CI, a Makefile), add `--python-exit-code 1` before `--python`.

Cycles is tried first, even when this Blender's engine list does not show it (the list
under-reports); if assigning Cycles fails, EEVEE is used. The EEVEE identifiers are read from
the running Blender because EEVEE's name changed between versions.

### How the file is organised

- Top half: plain Python, no `bpy` import. Checks the JSON (keys, rectangular grid,
  increasing axes, finite numbers), builds vertices, quad faces and per-vertex colours,
  and does the camera maths. Import it from normal Python to test it.
- Bottom half: the Blender side. Each function imports `bpy` itself.

Vertex `i_dte * n_k + j_k` is `iv[i_dte][j_k]`. Min IV maps to z = 0 and max IV to z = 1
before the display scale (4 x 4 x 1.8) is applied. The same axes will hold for the real SPY
surfaces later, so this script should work on them unchanged.

### What has been checked

On this machine, in plain Python and a mock `bpy` (not real Blender):

- The grid-to-mesh functions: a 2x2 grid gives 4 vertices and one quad `(0, 1, 3, 2)`,
  min and max IV land on z = 0 and 1, the real file gives 20 x 26 = 520 vertices and
  19 x 25 = 475 quads, all faces face up, bad input is rejected with a clear message.
- The camera maths: the fitted camera keeps every box corner and label inside the frame.
- The Blender-side control flow, run against a fake `bpy`. That shows the calls happen in
  order with the right arguments. It does **not** show that real Blender accepts them.

Not checked: any real Blender API call, the look of the image, the wireframe offset, label
sizes and the caption position. Expect to tweak the constants at the top of the script
(`WIRE_THICKNESS`, `CAMERA_*`, `LIGHT_RIG`, `FRAME_MARGIN`) after the first real render.

Written against the Blender 4.x Python API (needs 3.2+ for per-vertex colour attributes).
