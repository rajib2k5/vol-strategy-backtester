# tools/diagrams

Interim Mermaid renderer for the architecture diagrams.

A shared diagram toolkit (YAML spec to `.mmd`, `.svg`, `.png`, `.drawio` and
`.lucid.xml`) will be vendored into this directory later. It will consume
`docs/architecture/specs/*.yaml`. Until then, `render_mermaid.sh` turns the
checked-in `.mmd` files into SVG and PNG, and nothing else. When the toolkit
lands, this script and this README are expected to be replaced.

## Command

Run from the repo root:

```bash
bash tools/diagrams/render_mermaid.sh
```

The first thing it does is `npm ci --prefix tools/diagrams` (a few seconds once npm's cache is warm).

It renders every `docs/architecture/*.mmd` to `docs/architecture/rendered/<name>.svg`
and `docs/architecture/rendered/<name>.png`, where `<name>` is the `.mmd` file name
without the extension. It prints each output path, and exits non-zero if any diagram
fails to render. A failed diagram does not stop the others, and its previous outputs
(if any) are left untouched rather than deleted. Outputs are only replaced after both
the SVG and the PNG of that diagram succeed.

A PNG is only accepted after two checks (see "Are the outputs reproducible?" below for why):
it must pass an ink check, and a second render must pass it too and be byte-identical.
The script renders each PNG up to `PNG_MAX_ATTEMPTS` (12) times and prints every rejected attempt.
If no two complete renders agree, that diagram fails (exit 1) and its committed files stay as they were.

To run only the ink check on existing PNGs (no npm, no rendering; exit 1 if any is incomplete):

```bash
bash tools/diagrams/render_mermaid.sh --check-png docs/architecture/rendered/*.png
```

Environment variables, all optional: `PNG_SCALE` (2), `PNG_MAX_WIDTH` (12000), `PNG_MAX_ATTEMPTS` (12),
`PUPPETEER_CONFIG`, and `MMDC_BIN` (run another `mmdc` instead of the installed one; the tests below use it
with wrappers that damage the output).

The script resolves the repo root from its own location, so it also works from other
working directories.

## Pinned versions

The whole toolchain is pinned in `tools/diagrams/package.json` and locked in
`tools/diagrams/package-lock.json`:

| Package | Version |
|---|---|
| `@mermaid-js/mermaid-cli` | 11.17.0 |
| `mermaid` | 11.17.2 |
| `puppeteer` | 25.16.0 (drives Chromium; the browser build it needs is cached under `~/.cache/puppeteer`) |

`mermaid` and `puppeteer` are listed as direct dependencies and repeated under `overrides`, so
no nested package can pull in a different copy. The script runs `npm ci --prefix tools/diagrams`
(which installs exactly the lockfile and fails if `package.json` and the lock disagree) and then
calls the local `node_modules/.bin/mmdc`. It no longer uses `npx -y`, which resolved mermaid and
puppeteer afresh on every machine. `tools/diagrams/node_modules/` is git-ignored.

To change a version: edit `package.json`, run `npm install --prefix tools/diagrams`, review the
lockfile diff, re-render, and compare the images.

Requirements: Node 22 with `npm`, and network access on the first run (npm packages, and
Puppeteer's Chromium if it is not already cached).

### Are the outputs reproducible?

Yes, for all ten files, because the script now refuses to accept a PNG it cannot vouch for. Measured
on the aarch64 dev box on 2026-10-28 (pinned toolchain, Puppeteer's cached Chromium).

**What was wrong.** Chromium sometimes screenshots a very large page only partly, and `mmdc` still
exits 0. With the old 16,000 px cap, `data-model.erd.png` (16,001 x 4,676) came out truncated in 5 of 12
sequential ERD-only renders; the rest was identical to the complete render (checksum `56fb346f`).
The truncated renders are fine down to some row and blank below it. The cut rows seen were 3,041, 3,295, 3,549,
3,803 and 4,311 (3,041 plus multiples of 254): five different truncated variants over about 50 renders (the other four showed up in
runs done four at a time, with the Chromium flags below). The SVG was identical every time. Byte-identity alone is therefore not enough: two
consecutive truncated renders can have the same checksum (renders 5 and 6 of the 12 did).

**What decides it is page size.** ERD-only renders, counting complete ones (all truncated ones were cut at the bottom):

| PNG width cap | Pixels | Complete renders |
|---|---|---|
| 8,000 px | 8,000 x 2,338 | 20 of 20 |
| 12,000 px | 12,000 x 3,507 (42.1 M) | 60 of 60 |
| 13,000 px | 13,000 x 3,799 (49.4 M) | 15 of 20 |
| 14,000 px | 14,000 x 4,092 | 11 of 20 |
| 15,000 px | 15,001 x 4,384 | 11 of 20 |
| 16,000 px | 16,001 x 4,676 (74.8 M) | 7 of 12 |

(These ran sequentially or two to four at a time. The cause, probably Chromium not having painted all of a very
large page's raster tiles when the screenshot is taken, was not isolated. Chromium flags `--disable-gpu`,
`--disable-gpu-compositing`/`-rasterization`, `--disable-dev-shm-usage` and `--enable-gpu-rasterization`
did not help: 4 to 7 of 10 renders were still truncated with each.)

**What the script does about it.**

1. The default PNG width cap is 12,000 px instead of 16,000. Only the ERD is affected: its scale drops from
   0.89 to 0.67, so text is about 11 px instead of 14 px at 100% zoom, still legible (checked on a 100% crop).
   `PNG_MAX_WIDTH=16000` restores the old size, and the checks below still make that safe.
2. Ink check. The PNG is decoded and the box around its non-white pixels is measured. Mermaid pads a diagram evenly, so
   opposite blank margins must be alike (the larger at most 2x the smaller + 16 px). Complete renders measured top and
   bottom margins of 4 to 21 px, and left and right margins of 4 to 100 px (the sequence diagram's are wider and uneven, 75
   and 100). Truncated ERDs measured 364, 872 and 1,634 px at the bottom (three variants checked), and the 40%-blanked
   test images in the simulations below measured 1,403 to 2,812 px.
3. Two renders that pass the check must be byte-identical, within `PNG_MAX_ATTEMPTS` renders.

**Measured with the new script.**

- 8 consecutive runs of `render_mermaid.sh` (each starting with `npm ci`): all exited 0, and `sha256sum` of all 10
  outputs gave the same list in all 8 runs. A ninth run, after the failure tests below, gave that list again. At
  12,000 px no ERD render was rejected in any of the 8 runs (0 of 16).
- The 5 SVGs and 4 of the PNGs (`architecture`, `data-flow`, `engine-daily-loop.sequence`, `process`) are also
  byte-identical to the files committed before this change. Only `data-model.erd.png` changed, because of the narrower width.
- With `PNG_MAX_WIDTH=16000`, where Chromium really does truncate, 3 runs all exited 0 and wrote the same complete ERD
  (`56fb346f`, identical to the old committed one). In one of them 3 truncated renders in a row were rejected (the same
  1,634 px blank bottom margin and ink count each, so a comparison between renders alone could have accepted a matching pair)
  before two complete ones matched. In the other two, no render was rejected.
- `--check-png` on saved real renders: the complete ERD gave `ok`; three different real truncated ERDs gave `INCOMPLETE`
  with exit 1.
- Simulated failures, using `MMDC_BIN` wrappers (kept outside the repo):
  - every PNG has its bottom 40% blanked, `PNG_MAX_ATTEMPTS=3`: all 5 diagrams reject all 3 attempts, the script
    exits 1, and `sha256sum` of `docs/architecture/rendered/*` is unchanged;
  - every PNG is complete but 64 random bytes are appended to each render, so none matches another,
    `PNG_MAX_ATTEMPTS=3`: exits 1, outputs unchanged;
  - the first 2 PNG renders of each diagram are blanked, then the real ones: exits 0 after 4 attempts per diagram, and the
    outputs are byte-identical to the clean run.

Not covered: the ink check only sees the edges, so a PNG with a blank band in the middle but intact top and bottom
would pass it and rely on the byte-identity check. Whether the checksums also match on another machine (other fonts, another
Chromium build) was not checked.

Why the SVGs are stable: Mermaid draws box outlines with random curves, and without a fixed seed
`architecture`, `data-flow` and `data-model.erd` differed between two renders (the control below; their labels were
identical, and `process` and `engine-daily-loop.sequence` were already stable). The script therefore sets Mermaid's
`handDrawnSeed` to 1. As a control, rendering each of the five twice to SVG with the same renderer and no seed gave
different bytes for those three, and rendering twice with the seed gave identical bytes for all five.

## Rendering choices

- Theme `neutral`, background `white`, so the images read on both GitHub light and dark.
- `useMaxWidth: false` for flowchart, ER and sequence diagrams (the script writes this
  config to a temp file). Mermaid then emits SVGs at their natural pixel size instead of
  `width="100%"`, and the PNG is not squeezed to the viewport width. Without this, the
  35-entity ERD (about 17,900 px wide) came out at 2,000 px wide with unreadable text.
- PNG device scale is 2, capped so the PNG is at most 12,000 px wide (see "What decides it is page size" above for
  why not 16,000). Only the ERD hits the cap, rendering at about 0.67x. Override with `PNG_SCALE` and `PNG_MAX_WIDTH`.

## Puppeteer / Chromium

On the aarch64 dev box, Puppeteer's own cached Chromium works as-is, so no Puppeteer
config file is committed. If Chromium fails to launch (missing browser, or a sandbox
error as root or in a container), point Puppeteer at a config JSON:

```bash
PUPPETEER_CONFIG=path/to/puppeteer-config.json bash tools/diagrams/render_mermaid.sh
```

For example `{"executablePath": "/home/<user>/.cache/ms-playwright/chromium-1234/chrome-linux/chrome"}`
to use a Playwright Chromium, or `{"args": ["--no-sandbox"]}` where the sandbox is
unavailable.

## Known limits

- The ERD (`data-model.erd`) is very wide (12,000 x 3,507 px as PNG, 17,891 x 5,229 as SVG). Text is
  legible at 100% zoom, but it is not readable fit-to-screen, and the relationship lines
  span most of the width. Fixing that needs changes to the diagram or its layout, not to
  this script.
- In `engine-daily-loop.sequence`, the autonumber badge overlaps the lifeline and part of the label
  on self-messages (steps 6, 7, 8 and 20) in the rendered output. Cosmetic; the text is still
  readable (checked on a zoomed crop of the PNG).
- The ink check is not proof of a complete image (see "Not covered" above).
