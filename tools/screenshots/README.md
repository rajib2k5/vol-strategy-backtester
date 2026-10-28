# tools/screenshots

Screenshots of the built app for the root README and the design board. They land in
`docs/images/app/`.

| File | What it shows |
|---|---|
| `about-dark.png` | About page, dark theme (the app's default), full page, 1440 px wide |
| `about-light.png` | About page, light theme, full page, 1440 px wide |
| `architecture-light.png` | Architecture page, light theme, full page, 1440 px wide |
| `hero-3d.png` | The 3D volatility surface and its axis labels, cropped tight, dark theme, at 2x |

## Command

Run from the repo root. The app needs its own `npm ci` once, and the first run of the tool
needs `npm ci` here:

```bash
npm ci --prefix tools/screenshots
cd tools/screenshots && npm run capture
```

`npm run capture` builds the app (`npm --prefix ../../app run build`) and then runs
`node capture.mjs`, which serves `app/dist` with `vite preview` on a free port
(`--port <free> --strictPort`), takes the shots and stops the server. To use a server you
already started, or to write elsewhere:

```bash
node capture.mjs --url http://127.0.0.1:4173/ --out /some/dir
```

The capture itself takes about 30 to 35 seconds (most of it waiting for the Architecture
page's animations); `npm run capture` with the build took 50 seconds.

## How it works

- **Browser.** `puppeteer` 25.16.0, the same pin as `tools/diagrams`, driving its own cached
  Chromium (156.0.8078.47 here). Both versions are exact in `package.json` and locked in
  `package-lock.json`.
- **WebGL.** Headless Chromium has no GPU, so it starts with
  `--use-angle=swiftshader --enable-unsafe-swiftshader --ignore-gpu-blocklist`, which gives
  a software WebGL (`ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device ...`; the script prints
  the renderer string). It needs no display and no GPU.
- **Theme.** The script uses the app's own toggle button (`button.theme-toggle`), which stores
  the choice under `vol-strategy-backtester:theme` in localStorage. Each shot opens a fresh
  browser context, so it starts on the default theme (dark), and only the light shots click the toggle.
  No CSS is injected.
- **Animations.** The Architecture diagrams animate. Before the full-page capture the script
  waits until every layer has risen in and the sequence diagram's loop is at its hold, where
  every message is drawn, and checks that this still holds after the capture (otherwise it
  captures again). The dashes on the connectors and the highlighted node of the activity
  diagram at the bottom move continuously, so those differ between runs.
- **Size.** Every PNG is recompressed losslessly by `@jsquash/oxipng` 2.3.0 (oxipng as
  WebAssembly, pinned), 23 to 55 percent smaller. Checked on two files: the decoded pixels
  are identical before and after.

## Checks (the script exits 1 if any fails)

- the browser has WebGL;
- the About page's hero is the canvas, not the 2D heatmap fallback (`.hero-fallback`), and
  every axis label has been placed by the render loop (they stay hidden until the first
  frame is drawn);
- at least 2 percent of the hero stage's pixels are blue, which only the surface's colour
  ramp is (measured: 8.9 percent when drawn, 0.1 percent with the canvas hidden);
- the app logged no page error, no failed request and no HTTP error. The one exception is
  `/favicon.ico`: the app ships no favicon, so Chromium's automatic request for it is a 404.

## Output (measured on the dev box, 2026-10-28)

| File | Pixels | Bytes |
|---|---|---|
| `about-dark.png` | 1440 x 2196 | 248,979 |
| `about-light.png` | 1440 x 2196 | 249,117 |
| `architecture-light.png` | 1440 x 6776 | 664,139 |
| `hero-3d.png` | 994 x 779 | 85,290 |

The About shots came out byte-identical in the captures compared (336,863 and 325,334 bytes
before recompression, each time). The Architecture shot is not: the connector dashes and the
activity diagram's token move, and its size varied by a few hundred bytes across captures
(864,834 to 865,318 bytes before recompression). All of them also show the exported
manifest's `generated_at` and source commit, which change on every re-export. So do not use
a checksum to decide whether the app changed.
