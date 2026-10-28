#!/usr/bin/env bash
# Render every docs/architecture/*.mmd to SVG and PNG under docs/architecture/rendered/.
#
# Interim renderer: a shared diagram toolkit will replace this later (see README.md).
#
# The renderer is installed from tools/diagrams/package-lock.json with `npm ci`, so the
# mermaid-cli, mermaid and puppeteer versions are the exact ones in the lockfile on every
# machine (npx would resolve mermaid and puppeteer afresh each time).
#
# Usage (from the repo root):  bash tools/diagrams/render_mermaid.sh
#        check PNGs only:      bash tools/diagrams/render_mermaid.sh --check-png FILE...
#
# PNGs are fail-safe. Chromium sometimes screenshots a very large page only partly (blank
# bottom rows) while mmdc still exits 0, so a PNG is accepted only when
#   1. it passes an ink check (see check_png.mjs below: the drawing must reach the edge it
#      should, not stop part-way down), and
#   2. a second, independent render passes the check too and is byte-identical to it.
# Up to PNG_MAX_ATTEMPTS renders are made per PNG; if no two complete renders agree, that
# diagram fails and its previous outputs are left untouched.
#
# Environment overrides (all optional):
#   PNG_SCALE        device scale factor for PNGs, upper bound (default 2)
#   PNG_MAX_WIDTH    cap on PNG width in pixels (default 12000). Chromium truncates large
#                    screenshots at random: measured on the 35-entity ERD, 0 of 60 renders
#                    were cut at 12000 px wide, against about 1 in 4 at 13000 px and 5 of 12
#                    at 16000 px (README.md). The retry loop makes any width safe; a smaller
#                    one just needs fewer retries.
#   PNG_MAX_ATTEMPTS renders tried per PNG before giving up (default 12)
#   PUPPETEER_CONFIG path to a Puppeteer config JSON, e.g. {"executablePath": "..."} or
#                    {"args": ["--no-sandbox"]}; passed to mmdc with -p
#   MMDC_BIN         mmdc executable to run instead of the one `npm ci` installs (used to
#                    test the PNG checks with a wrapper that damages its output)
#
# Exit status: 0 only if every diagram rendered to both SVG and PNG and every PNG passed
# its checks; otherwise 1.

set -euo pipefail

THEME="neutral"
BACKGROUND="white"
PNG_SCALE="${PNG_SCALE:-2}"
PNG_MAX_WIDTH="${PNG_MAX_WIDTH:-12000}"
PNG_MAX_ATTEMPTS="${PNG_MAX_ATTEMPTS:-12}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC_DIR="docs/architecture"
OUT_DIR="docs/architecture/rendered"

DIAGRAMS_DIR="$REPO_ROOT/tools/diagrams"
MMDC_BIN="${MMDC_BIN:-$DIAGRAMS_DIR/node_modules/.bin/mmdc}"

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

# PNG completeness check. Needs no packages beyond Node itself (zlib is built in).
#
# Decodes the PNG and finds the box that contains all non-white pixels. Mermaid pads a
# diagram evenly (about 8 CSS px each side; the sequence diagram's side margins are a bit
# wider and uneven), so a complete PNG has a blank margin of similar size on opposite edges.
# A truncated screenshot (observed: everything below some row is blank) has a huge blank
# margin at the bottom and a tiny one at the top. The rule: the larger of two opposite
# margins may be at most twice the smaller plus 16 px. Complete renders measured 6 to 21 px
# margins; truncated ERDs measured 1,000 px or more at the bottom.
#
# Exits 0 and prints "ok ..." for a complete PNG; exits 1 and prints "INCOMPLETE: ..." for a
# truncated, blank, corrupt or unsupported-format file (anything it cannot vouch for).
CHECK_PNG="$WORK_DIR/check_png.mjs"
cat > "$CHECK_PNG" <<'JS'
import { readFileSync } from 'node:fs';
import { inflateSync } from 'node:zlib';

const INK_BELOW = 250; // a pixel darker than this (0-255) counts as drawn
const MARGIN_SLACK = 16; // px added to twice the smaller of two opposite margins

const fail = (message) => {
  console.log(`INCOMPLETE: ${message}`);
  process.exit(1);
};

const file = process.argv[2];
let buf;
try {
  buf = readFileSync(file);
} catch (error) {
  fail(`cannot read ${file} (${error.code ?? error.message})`);
}
if (buf.length < 8 || !buf.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))) {
  fail('not a PNG file');
}

let header = null;
let sawEnd = false;
const idat = [];
for (let pos = 8; pos + 12 <= buf.length; ) {
  const length = buf.readUInt32BE(pos);
  const type = buf.toString('latin1', pos + 4, pos + 8);
  const data = buf.subarray(pos + 8, pos + 8 + length);
  if (data.length < length) fail(`${type} chunk cut short`);
  if (type === 'IHDR') {
    header = {
      width: data.readUInt32BE(0),
      height: data.readUInt32BE(4),
      depth: data[8],
      colorType: data[9],
      interlace: data[12],
    };
  } else if (type === 'IDAT') {
    idat.push(data);
  } else if (type === 'IEND') {
    sawEnd = true;
    break;
  }
  pos += 12 + length;
}
if (!header) fail('no IHDR chunk');
if (!sawEnd) fail('no IEND chunk (file cut short)');

const { width, height, depth, colorType, interlace } = header;
const channels = { 0: 1, 2: 3, 4: 2, 6: 4 }[colorType];
if (!channels || depth !== 8 || interlace !== 0) {
  fail(`unsupported PNG format (color type ${colorType}, depth ${depth}, interlace ${interlace})`);
}

let raw;
try {
  raw = inflateSync(Buffer.concat(idat));
} catch (error) {
  fail(`image data is corrupt (${error.code ?? error.message})`);
}
const stride = width * channels;
if (raw.length !== height * (stride + 1)) {
  fail(`image data is ${raw.length} bytes, expected ${height * (stride + 1)} for ${width}x${height}`);
}

// Undo the PNG row filters, one row at a time, and track where the ink is.
let previous = new Uint8Array(stride);
let current = new Uint8Array(stride);
let firstRow = -1;
let lastRow = -1;
let firstCol = width;
let lastCol = -1;
let inkPixels = 0;
for (let y = 0; y < height; y++) {
  const start = y * (stride + 1);
  const filter = raw[start];
  for (let i = 0; i < stride; i++) {
    const x = raw[start + 1 + i];
    const left = i >= channels ? current[i - channels] : 0;
    const up = previous[i];
    let predicted;
    switch (filter) {
      case 0:
        predicted = 0;
        break;
      case 1:
        predicted = left;
        break;
      case 2:
        predicted = up;
        break;
      case 3:
        predicted = (left + up) >> 1;
        break;
      case 4: {
        const upLeft = i >= channels ? previous[i - channels] : 0;
        const p = left + up - upLeft;
        const pa = Math.abs(p - left);
        const pb = Math.abs(p - up);
        const pc = Math.abs(p - upLeft);
        predicted = pa <= pb && pa <= pc ? left : pb <= pc ? up : upLeft;
        break;
      }
      default:
        fail(`row ${y} has unknown filter type ${filter}`);
    }
    current[i] = x + predicted; // Uint8Array wraps modulo 256, as the PNG spec requires
  }

  let rowInk = false;
  for (let px = 0; px < width; px++) {
    const o = px * channels;
    let v;
    if (channels === 1) v = current[o];
    else if (channels === 2) v = current[o + 1] === 0 ? 255 : current[o];
    else {
      v = Math.min(current[o], current[o + 1], current[o + 2]);
      if (channels === 4 && current[o + 3] === 0) v = 255;
    }
    if (v < INK_BELOW) {
      rowInk = true;
      inkPixels++;
      if (px < firstCol) firstCol = px;
      if (px > lastCol) lastCol = px;
    }
  }
  if (rowInk) {
    if (firstRow < 0) firstRow = y;
    lastRow = y;
  }
  [previous, current] = [current, previous];
}

if (inkPixels === 0) fail('image is blank');

const margin = {
  top: firstRow,
  bottom: height - 1 - lastRow,
  left: firstCol,
  right: width - 1 - lastCol,
};
const summary = `${width}x${height}, ${inkPixels} ink px, blank margin top ${margin.top} bottom ${margin.bottom} left ${margin.left} right ${margin.right}`;
for (const [a, b] of [['top', 'bottom'], ['left', 'right']]) {
  const small = Math.min(margin[a], margin[b]);
  const large = Math.max(margin[a], margin[b]);
  if (large > 2 * small + MARGIN_SLACK) {
    fail(`drawing stops short: ${summary} (${a} and ${b} margins should be alike; ${large} > 2 x ${small} + ${MARGIN_SLACK})`);
  }
}
console.log(`ok ${summary}`);
JS

# --check-png FILE...: run only the completeness check (no npm, no rendering). Exit 1 if any
# file is incomplete.
if [[ "${1:-}" == "--check-png" ]]; then
  shift
  [[ $# -gt 0 ]] || { echo "usage: render_mermaid.sh --check-png FILE..." >&2; exit 2; }
  check_status=0
  for png in "$@"; do
    if message="$(node "$CHECK_PNG" "$png")"; then
      echo "$png: $message"
    else
      echo "$png: $message" >&2
      check_status=1
    fi
  done
  exit "$check_status"
fi

cd "$REPO_ROOT"

# `npm ci` installs exactly what package-lock.json says (and fails if package.json and the lock
# disagree), unlike `npm install`, which may move versions. It wipes node_modules first, so a
# stale or hand-edited install can never leak into a render.
npm ci --prefix "$DIAGRAMS_DIR" --no-audit --no-fund --silent
[[ -x "$MMDC_BIN" ]] || { echo "mmdc not found at $MMDC_BIN after npm ci" >&2; exit 1; }

# useMaxWidth=false makes mermaid emit the SVG at its natural pixel size instead of
# width="100%". Without it the PNG is squeezed into the viewport width, which turns the
# 35-entity ERD (about 17,900 px wide) into unreadable 3 px text.
# handDrawnSeed=1 fixes the seed of mermaid's shape-outline randomness, so re-rendering an
# unchanged diagram gives byte-identical output and a changed file means a changed diagram.
MERMAID_CONFIG="$WORK_DIR/mermaid-config.json"
cat > "$MERMAID_CONFIG" <<'JSON'
{
  "handDrawnSeed": 1,
  "flowchart": { "useMaxWidth": false },
  "er": { "useMaxWidth": false },
  "sequence": { "useMaxWidth": false }
}
JSON

mmdc() {
  local args=(-q -c "$MERMAID_CONFIG" -t "$THEME" -b "$BACKGROUND")
  if [[ -n "${PUPPETEER_CONFIG:-}" ]]; then
    args+=(-p "$PUPPETEER_CONFIG")
  fi
  "$MMDC_BIN" "${args[@]}" "$@"
}

# Print the width (3rd viewBox value) of the root <svg> of the given file.
svg_width() {
  grep -o -m1 'viewBox="[^"]*"' "$1" | head -n1 | sed 's/viewBox="//; s/"$//' | awk '{print $3}'
}

# Render $src to $stage/$name.png at scale $3 until two complete renders are byte-identical.
# A render that fails the ink check is discarded. A complete render that differs from the
# previous complete render replaces it as the one to match. Returns 1 if no two complete
# renders agree within PNG_MAX_ATTEMPTS.
render_png() {
  local src="$1" name="$2" stage="$3" scale="$4"
  local attempt rejected=0 previous="" candidate message
  for ((attempt = 1; attempt <= PNG_MAX_ATTEMPTS; attempt++)); do
    candidate="$stage/$name.attempt-$attempt.png"
    mmdc -i "$src" -o "$candidate" -s "$scale" || return 1
    if ! message="$(node "$CHECK_PNG" "$candidate")"; then
      echo "    $name.png attempt $attempt rejected: $message" >&2
      rejected=$((rejected + 1))
      rm -f "$candidate"
      continue
    fi
    if [[ -n "$previous" ]] && cmp -s "$previous" "$candidate"; then
      mv -f "$candidate" "$stage/$name.png"
      rm -f "$previous"
      echo "    $name.png: attempt $attempt matches the previous complete render ($rejected of $attempt rejected as incomplete); $message"
      return 0
    fi
    if [[ -n "$previous" ]]; then
      echo "    $name.png attempt $attempt is complete but differs from the previous complete render" >&2
      rm -f "$previous"
    fi
    previous="$candidate"
  done
  echo "    $name.png: no two identical complete renders in $PNG_MAX_ATTEMPTS attempts ($rejected rejected as incomplete)" >&2
  return 1
}

render_one() {
  local src="$1" name="$2" stage="$3"
  mkdir -p "$stage"
  mmdc -i "$src" -o "$stage/$name.svg" || return 1
  [[ -s "$stage/$name.svg" ]] || { echo "empty SVG for $name" >&2; return 1; }

  local width scale
  width="$(svg_width "$stage/$name.svg")"
  [[ -n "$width" ]] || { echo "no viewBox width in $name.svg" >&2; return 1; }
  scale="$(awk -v w="$width" -v max="$PNG_MAX_WIDTH" -v s="$PNG_SCALE" \
    'BEGIN { r = max / w; if (r > s) r = s; printf "%.4f", r }')"

  render_png "$src" "$name" "$stage" "$scale" || return 1
  [[ -s "$stage/$name.png" ]] || { echo "empty PNG for $name" >&2; return 1; }
}

shopt -s nullglob
sources=("$SRC_DIR"/*.mmd)
if [[ ${#sources[@]} -eq 0 ]]; then
  echo "no .mmd files found in $SRC_DIR" >&2
  exit 1
fi

mkdir -p "$OUT_DIR"
failed=()

for src in "${sources[@]}"; do
  name="$(basename "$src" .mmd)"
  stage="$WORK_DIR/out/$name"
  echo "rendering $src"
  if render_one "$src" "$name" "$stage"; then
    # Only replace the committed outputs once both formats succeeded.
    mv -f "$stage/$name.svg" "$OUT_DIR/$name.svg"
    mv -f "$stage/$name.png" "$OUT_DIR/$name.png"
    echo "  $OUT_DIR/$name.svg"
    echo "  $OUT_DIR/$name.png"
  else
    echo "  FAILED: $src" >&2
    failed+=("$src")
  fi
done

if [[ ${#failed[@]} -gt 0 ]]; then
  echo "${#failed[@]} of ${#sources[@]} diagram(s) failed: ${failed[*]}" >&2
  exit 1
fi
echo "ok: ${#sources[@]} diagram(s) rendered to $OUT_DIR"
