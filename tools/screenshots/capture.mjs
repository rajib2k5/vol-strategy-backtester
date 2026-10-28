// Screenshots of the built app for the README and the design board.
//
//   node capture.mjs [--url http://127.0.0.1:4173/] [--out ../../docs/images/app]
//
// Without --url it serves app/dist with `vite preview` on a free port, so run `npm run build`
// in app/ first (`npm run capture` here does both). Chromium is Puppeteer's own pinned build;
// WebGL comes from the SwiftShader software renderer, so it needs no GPU.
//
// Writes, from a 1440x900 viewport:
//   about-dark.png, about-light.png   the About page including the 3D hero, full page, 1x
//   architecture-light.png            the Architecture page, full page, 1x
//   hero-3d.png                       the 3D surface and its axis labels cropped tight, dark theme, 2x
//
// The theme is switched with the app's own toggle button, which stores the choice in
// localStorage (the default, dark, needs no click); each shot gets a fresh browser context so
// nothing carries over. The Architecture diagrams animate, so the script waits for the layers
// to finish rising in and for the sequence diagram's loop to reach its "everything drawn" hold.
// Every PNG is then recompressed losslessly with oxipng (WebAssembly build, pinned in
// package.json), which makes the files 25 to 55 percent smaller without changing a pixel.
// It exits non-zero if the app logged a page error, if the hero fell back to the 2D heatmap
// (no WebGL), or if the hero's canvas has no surface pixels in it.

import { spawn } from 'node:child_process';
import { mkdirSync } from 'node:fs';
import { readFile, writeFile } from 'node:fs/promises';
import net from 'node:net';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import optimise, { init as initOxipng } from '@jsquash/oxipng/optimise.js';
import puppeteer from 'puppeteer';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const APP_DIR = path.resolve(HERE, '../../app');
const VIEWPORT = { width: 1440, height: 900 };
const THEME_KEY = 'vol-strategy-backtester:theme'; // `${APP_SLUG}:theme`, see app/src/lib/theme.ts
const HERO_CROP_PADDING = 24; // CSS px kept around the drawn surface and labels

// Software WebGL in headless Chromium: ANGLE on top of SwiftShader (a CPU rasterizer).
const CHROMIUM_ARGS = ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--enable-webgl'];

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function argValue(name) {
  const i = process.argv.indexOf(name);
  return i >= 0 ? process.argv[i + 1] : undefined;
}

function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const { port } = server.address();
      server.close(() => resolve(port));
    });
  });
}

async function startPreview() {
  const port = await freePort();
  const viteBin = path.join(APP_DIR, 'node_modules/vite/bin/vite.js');
  const child = spawn(process.execPath, [viteBin, 'preview', '--host', '127.0.0.1', '--port', String(port), '--strictPort'], {
    cwd: APP_DIR,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  let log = '';
  child.stdout.on('data', (d) => (log += d));
  child.stderr.on('data', (d) => (log += d));
  const url = `http://127.0.0.1:${port}/`;
  for (let i = 0; i < 100; i++) {
    if (child.exitCode !== null) throw new Error(`vite preview exited early (code ${child.exitCode}):\n${log}`);
    try {
      if ((await fetch(url)).ok) return { url, stop: () => child.kill('SIGTERM') };
    } catch {
      /* not listening yet */
    }
    await sleep(100);
  }
  child.kill('SIGTERM');
  throw new Error(`vite preview did not answer at ${url} within 10 s:\n${log}`);
}

/**
 * Decode a PNG inside the page (no image library needed) and report on it. `blueFraction` is the
 * share of blue-dominant pixels: the surface's colour ramp is all blue, and nothing else in the
 * hero stage is. With `cropPadding` it also returns the PNG cropped to the pixels that differ
 * from the corner colour, plus that many pixels of margin.
 */
async function analysePng(page, png, cropPadding) {
  return page.evaluate(
    async (b64, pad) => {
      const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
      const bitmap = await createImageBitmap(new Blob([bytes], { type: 'image/png' }));
      const { width, height } = bitmap;
      const ctx = new OffscreenCanvas(width, height).getContext('2d');
      ctx.drawImage(bitmap, 0, 0);
      const { data } = ctx.getImageData(0, 0, width, height);
      const [bgR, bgG, bgB] = data;
      let blue = 0;
      let x0 = width;
      let y0 = height;
      let x1 = -1;
      let y1 = -1;
      for (let i = 0, p = 0; i < data.length; i += 4, p++) {
        const [r, g, b] = [data[i], data[i + 1], data[i + 2]];
        if (b - r > 60 && b - g > 30) blue++;
        if (Math.max(Math.abs(r - bgR), Math.abs(g - bgG), Math.abs(b - bgB)) > 16) {
          const x = p % width;
          const y = (p - x) / width;
          if (x < x0) x0 = x;
          if (x > x1) x1 = x;
          if (y < y0) y0 = y;
          if (y > y1) y1 = y;
        }
      }
      const result = { width, height, blueFraction: blue / (width * height) };
      if (pad !== null && x1 >= 0) {
        const left = Math.max(0, x0 - pad);
        const top = Math.max(0, y0 - pad);
        const w = Math.min(width, x1 + 1 + pad) - left;
        const h = Math.min(height, y1 + 1 + pad) - top;
        const crop = new OffscreenCanvas(w, h);
        crop.getContext('2d').drawImage(bitmap, left, top, w, h, 0, 0, w, h);
        const blob = await crop.convertToBlob({ type: 'image/png' });
        const dataUrl = await new Promise((resolve) => {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result);
          reader.readAsDataURL(blob);
        });
        result.crop = { width: w, height: h, base64: dataUrl.split(',')[1] };
      }
      return result;
    },
    Buffer.from(png).toString('base64'),
    cropPadding,
  );
}

/** Open the About page in a fresh context, switch to `theme` with the app's toggle, and wait for the hero to draw. */
async function openAbout(browser, baseUrl, theme, scale, problems) {
  const context = await browser.createBrowserContext();
  const page = await context.newPage();
  await page.setViewport({ ...VIEWPORT, deviceScaleFactor: scale });
  page.on('pageerror', (e) => problems.push(`page error: ${e.message}`));
  page.on('requestfailed', (r) => problems.push(`request failed: ${r.url()}`));
  // The app ships no favicon, so Chromium's automatic /favicon.ico request is a harmless 404.
  page.on('response', (r) => r.status() >= 400 && !r.url().endsWith('/favicon.ico') && problems.push(`HTTP ${r.status()}: ${r.url()}`));

  await page.goto(`${baseUrl}#/about`, { waitUntil: 'networkidle0' });
  await page.waitForSelector('.hero-stage');

  // A fresh context starts on the app's default theme (dark) with nothing stored; any other
  // theme is reached by clicking the toggle, which also stores the choice.
  const current = await page.evaluate(() => document.documentElement.getAttribute('data-theme'));
  if (current !== theme) {
    await page.click('button.theme-toggle');
    await page.waitForFunction((t) => document.documentElement.getAttribute('data-theme') === t, {}, theme);
    const stored = await page.evaluate((k) => localStorage.getItem(k), THEME_KEY);
    if (stored !== theme) throw new Error(`expected the toggle to store theme ${theme}, found ${stored}`);
  }

  // Canvas present, no 2D fallback, and every axis label placed by the render loop (they stay
  // hidden until the first frame is drawn).
  await page.waitForSelector('.hero-stage canvas', { timeout: 20000 });
  await page.waitForFunction(
    () => {
      const labels = [...document.querySelectorAll('.hero-axis')];
      return labels.length > 0 && labels.every((l) => l.style.visibility === 'visible');
    },
    { timeout: 20000 },
  );
  if (await page.$('.hero-fallback')) throw new Error('the hero fell back to the 2D heatmap: WebGL is not available');
  await page.evaluate(() => document.fonts.ready);
  await page.mouse.move(5, 5); // keep the pointer off the toggle (hover border)
  await sleep(500);
  return page;
}

/** Architecture page, fully drawn: layers risen in, and no sequence step still pending. Retries if the loop restarts mid-capture. */
async function shootArchitecture(page) {
  await page.click('a[href="#/architecture"]');
  await page.waitForSelector('section.architecture svg');
  await page.mouse.move(5, 5);
  // Runs in the page: layers risen in, and no sequence step still waiting to be drawn.
  const settled = () => {
    const layers = [...document.querySelectorAll('.vsb-arch-layer')];
    return (
      layers.length > 0 &&
      layers.every((l) => getComputedStyle(l).opacity === '1') &&
      document.querySelectorAll('.vsb-seq-line.pending, .vsb-seq-label.pending').length === 0
    );
  };
  for (let attempt = 1; attempt <= 5; attempt++) {
    await page.waitForFunction(settled, { timeout: 60000, polling: 50 });
    const png = await page.screenshot({ fullPage: true });
    if (await page.evaluate(settled)) return png; // still fully drawn after the capture, so the capture was too
    console.log(`architecture: the sequence loop restarted during the capture (attempt ${attempt}); retrying`);
  }
  throw new Error('could not capture the Architecture page with every sequence step drawn');
}

async function main() {
  const out = path.resolve(argValue('--out') ?? path.join(HERE, '../../docs/images/app'));
  mkdirSync(out, { recursive: true });

  const given = argValue('--url');
  const preview = given ? null : await startPreview();
  const baseUrl = given ?? preview.url;

  const browser = await puppeteer.launch({ headless: true, args: CHROMIUM_ARGS });
  const problems = [];
  await initOxipng(await readFile(path.join(HERE, 'node_modules/@jsquash/oxipng/codec/pkg/squoosh_oxipng_bg.wasm')));
  const save = async (name, png) => {
    const smaller = Buffer.from(await optimise(png, { level: 3 }));
    await writeFile(path.join(out, name), smaller);
    console.log(`wrote ${name}: ${png.length} -> ${smaller.length} bytes`);
  };

  try {
    const gl = await (await browser.newPage()).evaluate(() => {
      const c = document.createElement('canvas').getContext('webgl2') ?? document.createElement('canvas').getContext('webgl');
      const info = c?.getExtension('WEBGL_debug_renderer_info');
      return c ? c.getParameter(info ? info.UNMASKED_RENDERER_WEBGL : c.RENDERER) : null;
    });
    console.log(`browser: ${await browser.version()}\nWebGL renderer: ${gl ?? 'NONE'}`);
    if (!gl) throw new Error('this Chromium has no WebGL; try other CHROMIUM_ARGS');

    const dark = await openAbout(browser, baseUrl, 'dark', 1, problems);
    await save('about-dark.png', await dark.screenshot({ fullPage: true }));
    await dark.browserContext().close();

    const light = await openAbout(browser, baseUrl, 'light', 1, problems);
    await save('about-light.png', await light.screenshot({ fullPage: true }));
    await save('architecture-light.png', await shootArchitecture(light));
    await light.browserContext().close();

    // The hero alone, at 2x so the mesh lines and 10 px labels stay crisp, cropped to its content.
    const hero = await openAbout(browser, baseUrl, 'dark', 2, problems);
    const stage = await (await hero.$('.hero-stage')).screenshot();
    const stats = await analysePng(hero, stage, HERO_CROP_PADDING * 2);
    console.log(`hero stage: ${stats.width}x${stats.height}, ${(stats.blueFraction * 100).toFixed(1)}% surface-blue pixels`);
    if (stats.blueFraction < 0.02) throw new Error('the hero canvas shows no surface (no blue ramp pixels)');
    if (!stats.crop) throw new Error('the hero stage is empty');
    console.log(`hero crop: ${stats.crop.width}x${stats.crop.height}`);
    await save('hero-3d.png', Buffer.from(stats.crop.base64, 'base64'));
    await hero.browserContext().close();
  } finally {
    await browser.close();
    preview?.stop();
  }

  if (problems.length > 0) throw new Error(`the app reported problems:\n  ${[...new Set(problems)].join('\n  ')}`);
}

main().catch((error) => {
  console.error(error.stack ?? error);
  process.exit(1);
});
