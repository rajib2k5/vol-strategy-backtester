# Vol Strategy Backtester: app

React 19 + TypeScript + Vite viewer for the results of the Python backtester in the repository
root. It also draws an illustrative implied-vol surface with three.js (`@react-three/fiber`).

**The app never computes results.** It renders the JSON files in `public/data/`, which are written
by `tools/export_app_data.py` in the repository root:

```bash
# from the repository root
uv run python tools/export_app_data.py   # writes app/public/data/manifest.json + datasets
```

On load the app fetches `./data/manifest.json` and the datasets it lists, validates each file
against the contract in `src/lib/contract.ts` (schema version, required keys, grid shape, finite
numbers) and refuses anything that does not match.

## Run

```bash
cd app
npm ci
npm run dev        # local dev server
npm run verify     # lint + tests with coverage thresholds + production build
```

`npm run verify` is the gate. Coverage thresholds (85% lines and functions, 75% branches on
`src/lib/**`) are enforced in `vite.config.ts`. Dependencies are pinned to exact versions.

## Layout

| Path | What lives there |
|---|---|
| `src/lib/` | Pure code (no I/O, DOM or clock): contract parsers, surface geometry, colour ramp, plus the shell, diagrams and chart components |
| `src/data/` | The only code that touches the network: the loader and its React hook |
| `src/content/` | Typed copy for the About and Architecture pages |
| `src/views/` | Pages and the 3D hero |
| `src/test/fixtures/` | Small JSON fixtures used by the tests (tests never read `public/data/`) |
