// Tests for frontend/public/hud-shared.js and the contract between hud.html, hud-boot.js and hud-local.js.
// No packages needed (Node 22 or newer):   node --test "tests/hud/*.test.mjs"
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import vm from 'node:vm';

const pub = new URL('../../frontend/public/', import.meta.url);
const read = (name) => readFileSync(new URL(name, pub), 'utf8');

function loadShared(port = '5173') {
  const window = { location: { port } };
  vm.runInNewContext(read('hud-shared.js'), { window, location: window.location });
  return window.JarvisHud;
}

test('layout matches the HUD formulas for a 16:9 screen (compact)', () => {
  const L = loadShared().layout(1600, 900);
  assert.equal(L.cmp, true);
  assert.equal(L.u, 900 / 1440);
  assert.equal(L.pw, 1600 * 0.16);
  assert.equal(L.R1, 1600 - L.m - 2 * L.pw - L.gap);
  assert.equal(L.mh0, 900 * 0.93 - L.my0);
  assert.deepEqual([L.cx, L.cy, L.coreR], [800, 360, Math.min(900 * 0.115, 1600 * 0.06)]);
});

test('wide screens are not compact and get narrower panels', () => {
  const L = loadShared().layout(3440, 1000);
  assert.equal(L.cmp, false);
  assert.equal(L.pw, 3440 * 0.11);
});

test('nine panels in reveal order, the network panel spans two columns', () => {
  const H = loadShared(), L = H.layout(1600, 900), P = H.panels(L);
  assert.deepEqual(Array.from(P, (p) => p.id), ['hardware', 'diagnostics', 'core', 'biometric', 'chrono', 'atmospherics', 'network', 'stream', 'neural']);
  const net = P.find((p) => p.id === 'network');
  assert.equal(net.w, 2 * L.pw + L.gap);
  for (const p of P) assert.ok(p.x >= 0 && p.y >= 0 && p.x + p.w <= 1600 + 1e-9 && p.y + p.h <= 900 + 1e-9, p.id + ' inside the window');
});

test('the world map fits inside the network panel and keeps its aspect ratio', () => {
  const H = loadShared(), L = H.layout(1600, 900), net = H.panels(L).find((p) => p.id === 'network'), A = H.mapArea(net, L.u);
  assert.ok(A.x >= net.x && A.x + A.w <= net.x + net.w);
  assert.ok(A.top >= net.y && A.top + A.h <= net.y + net.h);
  assert.ok(Math.abs(A.w / A.h - 360 / (A.latTop - A.latBottom)) < 1e-9);
});

test('wings sit between the inner panels and the core ring', () => {
  const H = loadShared(), L = H.layout(3440, 1000), ringR = L.coreR * 2.1, Wg = H.wings(L, ringR);
  assert.ok(Wg.xl < Wg.gl && Wg.gl < L.cx && L.cx < Wg.gr2 && Wg.gr2 < Wg.xr);
  assert.ok(Wg.wl > 0 && Wg.wr > 0);
});

test('helper address: direct on this PC, through /helper behind the LAN gateway', () => {
  assert.equal(loadShared('5173').helperUrl('/x'), 'http://127.0.0.1:8765/x');
  assert.equal(loadShared('8443').helperUrl('/x'), '/helper/x');
});

test('ask handlers: any handler returning true consumes the message; log line handlers all run', () => {
  const H = loadShared();
  assert.equal(H.handleAsk('hi'), false);
  const seen = [];
  H.onAsk((t) => { seen.push('a:' + t); return false; });
  H.onAsk((t) => t === 'mine');
  assert.equal(H.handleAsk('mine'), true);
  assert.equal(H.handleAsk('other'), false);
  let lines = 0; H.onLogLine(() => lines++); H.onLogLine(() => lines++); H.logLineAdded('sys');
  assert.equal(lines, 2);
  assert.deepEqual(seen, ['a:mine', 'a:other']);
});

test('hud.html loads hud-shared.js before every other script', () => {
  const html = read('hud.html');
  const first = html.search(/<script[\s>]/);
  assert.equal(html.indexOf('<script src="hud-shared.js"></script>'), first);
});

test('hud-boot.js and hud-local.js only use JarvisHud members that hud-shared.js defines', () => {
  const H = loadShared(), known = new Set(Object.keys(H));
  for (const file of ['hud-boot.js', 'hud-local.js', 'hud.html']) {
    if (!existsSync(new URL(file, pub))) continue;   // hud-local.js is private (not in the public repo)
    const used = new Set([...read(file).matchAll(/JarvisHud\.([A-Za-z]+)/g)].map((m) => m[1]));
    for (const name of used) assert.ok(known.has(name), file + ' uses JarvisHud.' + name);
  }
  const capture = new Set(Object.keys(H.capture));
  for (const m of read('hud-boot.js').matchAll(/capture\.([A-Za-z]+)/g)) assert.ok(capture.has(m[1]), 'capture.' + m[1]);
});

test('hud.html records captured texts with the documented TextRecord fields', () => {
  const m = read('hud.html').match(/CAP\.texts\.set\(.*?,\{([^}]*)\}\)/);
  assert.ok(m, 'text recorder found');
  const fields = m[1].split(',').map((f) => f.split(':')[0].trim()).sort();
  assert.deepEqual(fields, ['align', 'alpha', 'color', 'size', 'text', 'x', 'y']);
});

test('home world commands (private hud-local.js, skipped when it is missing)', (t) => {
  if (!existsSync(new URL('hud-local.js', pub))) return t.skip('hud-local.js not present');
  const el = () => ({ style: {}, appendChild() {}, setAttribute() {}, firstChild: null });
  const window = {};
  const document = { createElement: el, head: { appendChild() {} }, body: { append() {} }, documentElement: { classList: { add() {}, remove() {}, contains: () => false } } };
  const H = loadShared();
  vm.runInNewContext(read('hud-local.js'), { window, document, JarvisHud: H, addEventListener() {}, location: { origin: 'http://x' }, add() {} });
  const parse = window.homeWorld.parseCommand;
  assert.equal(parse('show my home'), 'open');
  assert.equal(parse('Please open the house world.'), 'open');
  assert.equal(parse('close home'), 'close');
  assert.equal(parse('hide my flat'), 'close');
  assert.equal(parse('what is the weather at home'), null);
  assert.equal(parse('show me my home office plans'), null);
  assert.equal(H.handleAsk('show my home'), true);
  assert.equal(H.handleAsk('turn on the kitchen lights'), false);
});
