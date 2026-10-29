# tools/diagrams

The vendored diagram kit lives here. It builds the diagrams in `docs/architecture/out/` from the YAML specs in `docs/architecture/specs/`.

## Diagram kit (vendored)

`build.py` and `diagram_kit/` are a vendored copy of the shared diagram toolkit, **vol-diagram-kit at commit
`7493b4b`** (`git -C <kit repo> log --oneline -1` printed `7493b4b Fix fifth-review data-safety defects in
--check remedies and adoption`). One YAML spec per diagram becomes `.mmd`, `.svg`, `.png`, `.drawio` and
`.lucid.xml` (sequence diagrams: `.mmd`, `.svg`, `.png`), all from the same computed layout.

- **Specs:** `docs/architecture/specs/*.yaml`, in the kit's schema. The schema is not vendored (the copy step
  below takes only `build.py` and `diagram_kit/`); read it in the kit repo:
  [SCHEMA.md at 7493b4b](https://github.com/rajib2k5/vol-diagram-kit/blob/7493b4b/SCHEMA.md).
- **Output:** `docs/architecture/out/`, including `.diagram-kit-manifest.json`. Commit it with the specs.
- **Dependencies:** the `diagrams` group in `pyproject.toml` (`pyyaml`, `resvg-py`). The kit is tested on
  Python 3.12 only.
- **Do not edit** the vendored files by hand. To update the kit, copy it again, then change the commit above:

  ```bash
  rsync -a --exclude __pycache__ /path/to/vol-diagram-kit/diagram_kit /path/to/vol-diagram-kit/build.py tools/diagrams/
  ```

Run from the repo root:

```bash
# build (the kit refuses to overwrite files it did not write, so out/ must be a fresh folder or the kit's own)
uv run --group diagrams python tools/diagrams/build.py docs/architecture/specs --out docs/architecture/out
# check that out/ is current (exit 1 and a list of files if not); tests/test_diagrams.py runs this with --no-png
uv run --group diagrams python tools/diagrams/build.py docs/architecture/specs --out docs/architecture/out --check
# Mermaid render gate: run before every commit that changes a spec (setup below)
uv run --group diagrams --with playwright==1.64.1 python tools/diagrams/build.py docs/architecture/specs --verify-mermaid
```

The render gate draws every `.mmd` with Mermaid 12.2.0 (the version GitHub renders with, read by the kit on
2026-10-28) in headless Chromium and fails if any spec text is missing, in the wrong element or not as written.
Setup, once per machine; nothing goes into the repo:

```bash
npm install --prefix ~/.cache/diagram-kit mermaid@12.2.0
export DIAGRAM_KIT_MERMAID_JS=~/.cache/diagram-kit/node_modules/mermaid/dist/mermaid.min.js
export DIAGRAM_KIT_CHROMIUM=$HOME/.cache/ms-playwright/chromium-1234/chrome-linux/chrome   # any Chromium; or `uv run playwright install chromium`
```

PNG bytes are verified on aarch64 only (never compared across CPU architectures); on an x86_64 runner use
`--check --no-png`, which still compares every `.mmd`, `.svg`, `.drawio` and `.lucid.xml` byte for byte.
The kit's known limits (no text wrapping, ERDs only left to right, long edge labels, untested Lucid/Figma/FigJam
imports) are in the kit's README under "Known limitations" and summarised in `docs/architecture/README.md`.

## Removed: the interim Mermaid renderer

`render_mermaid.sh` turned the hand-kept `docs/architecture/*.mmd` files into `docs/architecture/rendered/` SVG and PNG, using a toolchain pinned in `package.json` and `package-lock.json` (`@mermaid-js/mermaid-cli`, `mermaid`, `puppeteer`). The kit above replaced it, and on 2026-10-29 the script, `package.json`, `package-lock.json`, the old `.mmd` files and `rendered/` were removed (the history of the M0 commit `9cd2f19` has them). The write-up of its PNG reproducibility measurements went with it. A `node_modules/` folder in this directory, if one is left from its `npm ci`, is git-ignored and unused; delete it.
