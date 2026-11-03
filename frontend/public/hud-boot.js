/* global hw */  // hw: live hardware stats (let in hud.html), filled when the helper answers
/* J.A.R.V.I.S. boot animation: the HUD's parts fly in from all sides and assemble, the core lights up, then the panels
   of the real HUD are revealed one by one and the overlay fades out (about 6 s; a click skips it).
   Loaded by hud.html (not on phones) right after the HUD's own script. Everything it shares with the HUD goes through
   window.JarvisHud (hud-shared.js): the layout, the captured texts of the HUD's first frame, the brain cloud, the wear overlay.

   Timeline (seconds after start):
     0.0-2.0  pieces fly in (each starts at its own time)      1.5-3.0  status lines        2.4  HUD texts captured
     3.0-4.2  panels unroll (one every 0.12 s), wings at 3.3   3.1-4.1  core flash          4.2  brain assembles
     5.9      fade out (or on click)                                                         */
(function () {
  'use strict';
  const overlay = document.createElement('div');
  overlay.id = 'bootOv';
  overlay.style.cssText = 'position:fixed;inset:0;z-index:100;background:#02080c;cursor:pointer;transition:opacity .9s';
  const canvas = document.createElement('canvas');
  canvas.style.cssText = 'position:absolute;left:0;top:0;width:100%;height:100%';
  overlay.appendChild(canvas);
  document.body.appendChild(overlay);

  const W = canvas.width = innerWidth, H = canvas.height = innerHeight, ctx = canvas.getContext('2d');
  const random = Math.random, PI = Math.PI, TAU = PI * 2;
  const LAYOUT = JarvisHud.layout(W, H), u = LAYOUT.u, compact = LAYOUT.cmp;
  const CX = LAYOUT.cx, CY = LAYOUT.cy, coreR = LAYOUT.coreR, ringR = coreR * 2.1, focal = H * 0.9;
  const WING = JarvisHud.wings(LAYOUT, ringR);
  const PANELS = JarvisHud.panels(LAYOUT);
  const NETWORK = PANELS.findIndex((p) => p.id === 'network'), NEURAL = PANELS.findIndex((p) => p.id === 'neural');
  // the two wing areas (left: core diagnostics graphs, right: fan bars), used to clip, reveal and group texts
  const WING_TOP = WING.y0 - 40 * u, WING_HEIGHT = 6 * WING.rh + 60 * u;
  const WING_LEFT = { x: WING.xl - 12, y: WING_TOP, w: (CX - ringR - 58 * u) - (WING.xl - 12), h: WING_HEIGHT };
  const WING_RIGHT = { x: CX + ringR + 58 * u, y: WING_TOP, w: WING.xr + 12 - (CX + ringR + 58 * u), h: WING_HEIGHT };
  const COLOR = {
    cyan: '#19d3ff', orange: '#ff9a3d', dim: 'rgba(150,215,235,0.6)', sky: '#7fdcff', blue: '#2b9bff', green: '#3dff9a',
    red: '#ff4d4d', yellow: '#ffd24a', steel: 'rgb(200,225,240)', shade: 'rgba(0,8,14,0.55)',
  };
  const FONT = 'px Consolas,monospace';
  const TIME = {
    textFill: 2.4, capture: 2.4, panels: 3.0, panelStagger: 0.12, panelUnroll: 0.45, wings: 3.3, wingTexts: 3.4, logBar: 3.15,
    domText: 3.4, flash: 3.1, burst: 3.4, brainShown: 4.1, brain: 4.2, end: 5.9, last: 6.2,
    status: 1.5, statusStep: 0.3, starsFade: 3.2, gridFade: 0.8,
  };
  const panelStart = (i) => TIME.panels + i * TIME.panelStagger;
  const CAPTURE = { COLLECTING: 'collecting', FREEZING: 'freezing', DONE: 'done' };
  const FREEZE_FRAMES = 6;   // frames the HUD draws its panels without texts before its canvas is copied
  const WINGS = 'wings';     // reveal group of the texts in the wing areas (the others: a panel index)

  const clamp01 = (v) => Math.max(0, Math.min(1, v));
  const easeOut = (p) => 1 - Math.pow(1 - p, 3);
  const randomSign = () => (random() < 0.5 ? -1 : 1);
  const polar = (r, a) => [Math.cos(a) * r, Math.sin(a) * r];
  function arcPoints(r, a0, a1, n) { const out = []; for (let i = 0; i <= n; i++) out.push(polar(r, a0 + (a1 - a0) * i / n)); return out; }
  const circlePoints = (r) => arcPoints(r, 0, TAU, 72);
  const rectPoints = (a, b, w, h) => [[a, b], [a + w, b], [a + w, b + h], [a, b + h]];
  function tickLines(r, n, len, every, len2) {
    const out = [];
    for (let i = 0; i < n; i++) { const a = i * TAU / n, l = (every && i % every == 0) ? len2 : len; out.push([polar(r, a), polar(r + l, a)]); }
    return out;
  }
  const inRect = (r, X, Y, pad) => X >= r.x - pad && X <= r.x + r.w + pad && Y >= r.y - pad && Y <= r.y + r.h + pad;

  /* ---------- pieces: one drawing each (lines, polygons, dots, texts) that flies in on its own path ----------
     lines: point arrays (drawn with the piece's colour) or {points, color, alpha} for a line with its own style */
  const pieces = [], stars = [];
  function addPiece(p) {
    p.lineWidth = p.lineWidth || 1.5; p.alpha = p.alpha == null ? 1 : p.alpha; p.color = p.color || COLOR.cyan; p.spin = p.spin || 0;
    let sx = 0, sy = 0, n = 0;
    const add = (q) => { sx += q[0]; sy += q[1]; n++; };
    (p.lines || []).forEach((l) => (Array.isArray(l) ? l : l.points).forEach(add));
    (p.polys || []).forEach((g) => g.pts.forEach(add));
    (p.dots || []).forEach((g) => add([g.x, g.y]));
    (p.texts || []).forEach((g) => add([g.x, g.y]));
    p.center = n ? [sx / n, sy / n] : [0, 0];
    const dirAngle = random() * TAU, distance = (0.5 + random() * 0.6) * (p.wing ? W * 0.45 : W);
    p.startAt = p.wing ? 0.9 + random() * 0.9 : 0.2 + random() * 1.3; p.flyTime = 1.7;
    p.rotX = randomSign() * (1.5 + random() * 2.2) * TAU; p.rotY = randomSign() * (1.5 + random() * 2.2) * TAU; p.rotZ = randomSign() * (1 + random() * 1.5) * TAU;
    p.fromX = Math.cos(dirAngle) * distance; p.fromY = Math.sin(dirAngle) * distance * 0.7; p.fromZ = focal * (-0.3 + random() * 1.5);
    pieces.push(p);
  }
  for (let i = 0; i < 90; i++) stars.push({ angle: random() * TAU, spread: random(), phase: random() });

  addPiece({ polys: [{ pts: circlePoints(ringR + 20 * u), col: COLOR.shade }] });
  for (let i = 1; i <= 10; i++) addPiece({ lines: [circlePoints(coreR * i * 0.22)], lineWidth: 1, alpha: 0.1 });
  const rays = []; for (let i = 0; i < 24; i++) rays.push([polar(coreR * 0.2, i * PI / 12), polar(ringR, i * PI / 12)]);
  addPiece({ lines: rays, lineWidth: 1, alpha: 0.07 });
  if (!compact) {
    addPiece({ lines: [[[WING.xl - CX, 0], [WING.gl - CX, 0]]], lineWidth: 1, alpha: 0.25, wing: 1 });
    addPiece({ lines: [[[WING.gr2 - CX, 0], [WING.xr - CX, 0]]], lineWidth: 1, alpha: 0.25, wing: 1 });
    const graphs = [['CPU LOAD %', COLOR.sky], ['GPU LOAD %', COLOR.blue], ['GPU POWER W', COLOR.orange], ['GPU TEMP C', COLOR.orange], ['LINK LATENCY', COLOR.green], ['SYNAPSE (SIM)', COLOR.cyan]];
    graphs.forEach(([name, color], k) => {
      const rowY = WING.y0 + k * WING.rh, bars = [], count = Math.floor(WING.wl / (6 * u));
      let v = 0.5;
      for (let i = 0; i < count; i++) {
        v = clamp01(v + (random() - 0.5) * 0.35);
        const bh = v * (WING.rh - 28 * u);
        bars.push({ pts: rectPoints(WING.x0 + i * 6 * u - CX, rowY + 18 * u + (WING.rh - 28 * u) - bh - CY, 3.5 * u, Math.max(1, bh)), col: color, al: 0.3 + 0.65 * v });
      }
      const texts = [{ s: name, x: WING.x0 - CX, y: rowY + 12 * u - CY, sz: 11 * u, col: COLOR.dim, ta: 'left' }];
      if (!k) texts.push({ s: 'CORE DIAGNOSTICS // BREATH', x: WING.x0 - CX, y: WING.y0 - 16 * u - CY, sz: 14 * u, col: COLOR.cyan, ta: 'left' });
      const baseline = { points: [[WING.x0 - CX, rowY + WING.rh - 5 * u - CY], [WING.x0 + WING.wl - CX, rowY + WING.rh - 5 * u - CY]], alpha: 0.3 };
      addPiece({ polys: bars, texts, lines: [baseline], color, lineWidth: 1, wing: 1 });
    });
    ['CPU FAN', 'PUMP FAN', 'GPU FAN', 'SYSTEM FAN #1', 'SYSTEM FAN #2', 'SYSTEM FAN #3'].forEach((name, k) => {
      const rowY = WING.y0 + k * WING.rh, color = k % 2 ? COLOR.orange : COLOR.blue, level = 0.3 + random() * 0.6;
      const texts = [{ s: name, x: WING.x1 - CX, y: rowY + 12 * u - CY, sz: 11 * u, col: COLOR.dim, ta: 'left' }];
      if (!k) texts.push({ s: 'FAN SPEEDS // LIVE', x: WING.x1 - CX, y: WING.y0 - 16 * u - CY, sz: 14 * u, col: COLOR.cyan, ta: 'left' });
      addPiece({ polys: [{ pts: rectPoints(WING.x1 - CX, rowY + 20 * u - CY, WING.wr, 10 * u), col: color, al: 0.25 }, { pts: rectPoints(WING.x1 - CX, rowY + 20 * u - CY, WING.wr * level, 10 * u), col: color, al: 0.9 }], texts, wing: 1 });
    });
  }
  addPiece({ lines: [circlePoints(ringR)], lineWidth: 1.5, glow: 1 }); addPiece({ lines: [circlePoints(ringR + 22 * u)], lineWidth: 1.5, glow: 1 });
  addPiece({ lines: tickLines(ringR, 120, 6 * u, 5, 11 * u), lineWidth: 1.5, spin: 0.15, glow: 1 }); addPiece({ lines: tickLines(ringR, 12, 18 * u, 0, 0), lineWidth: 2, spin: 0.15, glow: 1 });
  ['E', 'S', 'W', 'N'].forEach((ch, k) => { const a = k * PI / 2, q = polar(ringR + 44 * u, a); addPiece({ texts: [{ s: ch, x: q[0], y: q[1] + 5 * u, sz: 16 * u, col: COLOR.cyan, rt: a + PI / 2 }] }); });
  const degrees = [];
  for (let k = 0; k < 12; k++) {
    if (k % 3 == 0) continue;
    const a = k * PI / 6, q = polar(ringR + 40 * u, a);
    degrees.push({ s: String((k * 30 + 90) % 360).padStart(3, '0'), x: q[0], y: q[1] + 4 * u, sz: 11 * u, col: COLOR.dim, rt: a + PI / 2 });
  }
  addPiece({ texts: degrees });
  addPiece({ polys: [{ pts: [[-8 * u, -ringR - 40 * u], [8 * u, -ringR - 40 * u], [0, -ringR - 26 * u]] }], texts: [{ s: 'HDG 000', x: 0, y: -ringR - 52 * u, sz: 15 * u, col: COLOR.cyan }] });
  const bezel = []; for (let i = 0; i < 40; i++) { const a = i * TAU / 40, l = 0.08 + 0.05 * Math.sin(i * 2.3); bezel.push(arcPoints(ringR - 16 * u, a, a + l, 6)); }
  addPiece({ lines: bezel, color: COLOR.steel, lineWidth: 9, alpha: 0.28, spin: -0.22 });
  addPiece({ lines: [circlePoints(ringR - 30 * u)], lineWidth: 1, alpha: 0.5 }); addPiece({ lines: tickLines(ringR - 30 * u, 180, -6 * u, 0, 0), lineWidth: 1, alpha: 0.45, spin: -0.3 });
  for (let i = 0; i < 3; i++) addPiece({ lines: [arcPoints(ringR - 16 * u, i * 2.094, i * 2.094 + 0.35, 8)], lineWidth: 9, alpha: 0.95, glow: 1, spin: 0.5 });
  for (let side = 0; side < 2; side++) {
    for (let k = 0; k < 4; k++) {
      const r0 = coreR * (1.45 + k * 0.12), ticks = [];
      for (let i = 0; i < 44; i++) {
        const a = (i / 43 - 0.5) * 1.7 + side * PI, v = 0.25 + random() * 0.65;
        const color = side ? (v > 0.9 ? COLOR.red : COLOR.orange) : (v > 0.9 ? COLOR.green : COLOR.blue);
        ticks.push({ points: [polar(r0, a), polar(r0 + coreR * 0.015 + v * coreR * 0.085, a)], color });
      }
      addPiece({ lines: ticks, lineWidth: 5 - k * 0.7, dash: [3 * u, 2 * u] });
    }
  }
  // live gauges: GPU load, graphics memory, processor load (from hud.html's hw when the helper answers)
  const gaugeValue = [(s) => s.gpu && s.gpu.load / 100, (s) => s.gpu && s.gpu.mem_used / s.gpu.mem_total, (s) => (s.cpu_load || 0) / 100];
  [['GPU', 0.6, COLOR.orange], ['VRAM', 0.7, COLOR.red], ['CPU', 0.3, COLOR.yellow]].forEach(([label, start, color], k) => {
    const c = polar(coreR * 1.64, PI / 2 + (k - 1) * 0.3), move = (q) => [q[0] + c[0], q[1] + c[1]];
    const ring = { points: arcPoints(15 * u, 0, TAU, 24).map(move), alpha: 0.25 }, arc = arcPoints(15 * u, -PI / 2, -PI / 2 + TAU * start, 18).map(move);
    addPiece({
      update() {
        const stats = (typeof hw !== 'undefined') ? hw : null;
        const live = stats && gaugeValue[k](stats);
        const v = clamp01((live == null || live === false || Number.isNaN(live)) ? start : live);
        this.lines[1] = arcPoints(15 * u, -PI / 2, -PI / 2 + TAU * v, 18).map(move); this.texts[1].s = Math.round(v * 100) + '%';
      },
      lines: [ring, arc], color, lineWidth: 5, glow: 1, dots: [{ x: c[0], y: c[1], r: 5 * u, col: color }],
      texts: [{ s: label, x: c[0], y: c[1] + 34 * u, sz: 10 * u, col: color }, { s: Math.round(start * 100) + '%', x: c[0], y: c[1] + 47 * u, sz: 10 * u, col: COLOR.dim }],
    });
  });
  const chevrons = [];
  for (let k = 0; k < 3; k++) {
    const a = -PI / 2 + (k - 1) * 0.3, c = polar(coreR * 1.64, a), ca = Math.cos(a + PI / 2), sa = Math.sin(a + PI / 2);
    chevrons.push({ pts: [[-7 * u, -6 * u], [7 * u, -6 * u], [0, 8 * u]].map((q) => [c[0] + q[0] * ca - q[1] * sa, c[1] + q[0] * sa + q[1] * ca]), al: 0.8 });
  }
  addPiece({ polys: chevrons });
  addPiece({ lines: [circlePoints(coreR * 1.38)], lineWidth: 2, glow: 1, dash: [6 * u, 10 * u], spin: 0.3 });
  for (let i = 0; i < 3; i++) addPiece({ lines: [arcPoints(coreR * 1.30, i * 2.094, i * 2.094 + 1.3, 10)], lineWidth: 4, glow: 1, spin: 0.5 });
  addPiece({ lines: [circlePoints(coreR * 1.22)], lineWidth: 1, alpha: 0.6 }); addPiece({ lines: tickLines(coreR * 1.22, 90, -5 * u, 0, 0), lineWidth: 1, alpha: 0.7, spin: -0.45 });
  for (let i = 0; i < 3; i++) addPiece({ lines: [arcPoints(coreR * 1.14, i * 2.094, i * 2.094 + 0.9, 8)], lineWidth: 3, glow: 1, spin: -0.6 });
  const spikes = []; for (let i = 0; i < 96; i++) { const a = i / 96 * TAU - PI / 2; spikes.push([polar(coreR * 0.86, a), polar(coreR * 0.86 + coreR * 0.05 + random() * coreR * 0.12, a)]); }
  addPiece({ lines: spikes, lineWidth: 2 }); addPiece({ lines: [circlePoints(coreR * 0.82)], lineWidth: 3, glow: 1 });
  addPiece({ lines: [arcPoints(coreR * 0.74, 0, TAU, 6)], lineWidth: 2, spin: 0.2 }); addPiece({ lines: [arcPoints(coreR * 0.74, PI / 6, PI / 6 + TAU, 6)], lineWidth: 2, spin: -0.2 });
  addPiece({ lines: [arcPoints(coreR * 0.58, 0, TAU, 3)], lineWidth: 1.5, spin: 0.3 }); addPiece({ lines: [arcPoints(coreR * 0.58, PI / 3, PI / 3 + TAU, 3)], lineWidth: 1.5, spin: -0.3 });
  addPiece({ lines: [arcPoints(coreR * 0.66, PI / 4, PI / 4 + TAU, 4)], lineWidth: 1.2, spin: 0.25 }); addPiece({ lines: [circlePoints(coreR * 0.64)], lineWidth: 1.8 }); addPiece({ lines: [arcPoints(coreR * 0.45, 0, 4, 24)], lineWidth: 1.8, spin: 1.2 });
  for (let k = 0; k < 7; k++) {
    const r = coreR * (0.3 + k * 0.07), dir = k % 2 ? -1 : 1, trail = [];
    for (let j = 0; j < 10; j++) { const q = polar(r, -dir * j * 0.07); trail.push({ x: q[0], y: q[1], r: Math.max(0.5, 3.2 - j * 0.25) * u, al: 1 - j / 10, col: k % 3 == 0 ? COLOR.orange : COLOR.cyan }); }
    addPiece({ dots: trail, spin: dir * 1000 / (700 + k * 180) * 0.5 });
  }
  addPiece({ lines: [arcPoints(coreR * 0.26, 0, 2, 14)], color: COLOR.orange, lineWidth: 5, glow: 1, spin: 1.4 }); addPiece({ lines: [arcPoints(coreR * 0.26, PI, PI + 2, 14)], color: COLOR.orange, lineWidth: 5, glow: 1, spin: 1.4 }); addPiece({ lines: [arcPoints(coreR * 0.2, 0, 4, 20)], color: COLOR.red, lineWidth: 3, glow: 1, spin: -1 });
  addPiece({ lines: [circlePoints(coreR * 0.3)], lineWidth: 2, alpha: 0.5 }); addPiece({ lines: [circlePoints(coreR * 0.55)], lineWidth: 2, alpha: 0.3 }); addPiece({ lines: [circlePoints(coreR * 0.8)], lineWidth: 2, alpha: 0.15 });
  addPiece({ lines: [[[-coreR * 0.8, 0], [-coreR * 0.3, 0]], [[coreR * 0.3, 0], [coreR * 0.8, 0]], [[0, -coreR * 0.8], [0, -coreR * 0.3]], [[0, coreR * 0.3], [0, coreR * 0.8]]], lineWidth: 1.5 });

  /* ---------- status lines under the core: what is already running ---------- */
  const status = ['HELPER 8765 ... CHECKING', 'MODEL ... CHECKING', 'SERVER 8000 ... CHECKING', 'GPU ... CHECKING'];
  fetch(JarvisHud.helperUrl()).then((r) => {
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  }).then((j) => {
    status[0] = 'HELPER 8765 ... OK';
    status[1] = j.model ? 'MODEL ' + String(j.model).slice(0, 28) + ' ... LOADED' : 'MODEL ... NONE LOADED';
    status[3] = (j.gpu && j.gpu.name) ? 'GPU ' + String(j.gpu.name).replace('NVIDIA GeForce ', '').slice(0, 24) + ' ... OK' : 'GPU ... NOT FOUND';
  }).catch((e) => {
    // a network error means the helper is not running; anything else (HTTP status, broken JSON) is an error of a running helper
    status[0] = 'HELPER 8765 ... ' + (e instanceof TypeError ? 'OFFLINE' : 'ERROR'); status[1] = 'MODEL ... UNKNOWN'; status[3] = 'GPU ... UNKNOWN';
  });
  fetch('/v1/telemetry/stats').then((r) => { status[2] = 'SERVER 8000 ... ' + (r.ok ? 'OK' : 'ERROR'); }).catch(() => { status[2] = 'SERVER 8000 ... OFFLINE'; });

  /* ---------- drawing ---------- */
  const SCRAMBLE_CHARS = '01ABCDEF#$%&*+<>/=?XYZ';
  function scramble(s, t, t0, dur) {
    // text that "decodes" from random characters to s between t0 and t0 + dur
    s = String(s);
    const p = clamp01((t - t0) / dur);
    if (p >= 1) return s;
    const n = Math.floor(s.length * p);
    let r = s.slice(0, n);
    for (let i = n; i < s.length; i++) r += s.charAt(i) == ' ' ? ' ' : SCRAMBLE_CHARS.charAt(Math.floor(random() * SCRAMBLE_CHARS.length));
    return r;
  }

  function drawPiece(p, t, ghost) {
    // one piece at time t: flies in rotated and far away, then spins in place; a ghost is a faint motion trail
    if (t < p.startAt) return;
    const q = clamp01((t - p.startAt) / p.flyTime), e = easeOut(q), inv = 1 - e, fill = clamp01((t - TIME.textFill) / 1);
    const a = p.rotX * inv, b = p.rotY * inv, c = p.rotZ * inv, ca = Math.cos(a), sa = Math.sin(a), cb = Math.cos(b), sb = Math.sin(b), cc = Math.cos(c), sc = Math.sin(c);
    const spin = p.spin * Math.max(0, t - p.startAt - p.flyTime), cs = Math.cos(spin), ss = Math.sin(spin), c0 = p.center, ox = p.fromX * inv, oy = p.fromY * inv, oz = p.fromZ * inv;
    function project(pt) {
      let X = pt[0], Y = pt[1];
      if (spin) { const X1 = X * cs - Y * ss; Y = X * ss + Y * cs; X = X1; }
      const rx = X - c0[0], ry = Y - c0[1], y1 = ry * ca, z1 = ry * sa, x2 = rx * cb + z1 * sb, z2 = -rx * sb + z1 * cb, x3 = x2 * cc - y1 * sc, y3 = x2 * sc + y1 * cc;
      const k = focal / Math.max(focal * 0.15, focal + z2 + oz);
      return [CX + (c0[0] + x3 + ox) * k, CY + (c0[1] + y3 + oy) * k, k];
    }
    function tracePath(points) { points.forEach((pt, i) => { const s = project(pt); i ? ctx.lineTo(s[0], s[1]) : ctx.moveTo(s[0], s[1]); }); }
    const al = Math.min(1, q * 4) * (0.35 + 0.65 * fill) * (ghost ? 0.2 : 1), widthK = 0.4 + 0.6 * fill;
    ctx.setLineDash(p.dash || []); ctx.lineWidth = p.lineWidth * u * widthK;
    if (p.glow && fill > 0.5 && !ghost) { ctx.shadowColor = p.color; ctx.shadowBlur = 10 * u; } else ctx.shadowBlur = 0;
    const lines = p.lines || [];
    // plain lines in one stroke, then the lines with their own colour or alpha
    ctx.strokeStyle = p.color; ctx.globalAlpha = al * p.alpha; ctx.beginPath();
    let any = false;
    lines.forEach((l) => { if (Array.isArray(l)) { tracePath(l); any = true; } });
    if (any) ctx.stroke();
    lines.forEach((l) => {
      if (Array.isArray(l)) return;
      ctx.strokeStyle = l.color || p.color; ctx.globalAlpha = al * p.alpha * (l.alpha != null ? l.alpha : 1);
      ctx.beginPath(); tracePath(l.points); ctx.stroke();
    });
    ctx.setLineDash([]); ctx.shadowBlur = 0;
    if (ghost) return;
    (p.polys || []).forEach((g) => {
      ctx.beginPath(); tracePath(g.pts); ctx.closePath();
      if (fill > 0) { ctx.globalAlpha = al * (g.al != null ? g.al : p.alpha) * fill; ctx.fillStyle = g.col || p.color; ctx.fill(); }
      if (fill < 1) { ctx.globalAlpha = al * 0.6 * (1 - fill); ctx.strokeStyle = (g.col && g.col.charAt(0) == '#') ? g.col : COLOR.cyan; ctx.lineWidth = u; ctx.stroke(); }
    });
    (p.dots || []).forEach((g) => {
      const s = project([g.x, g.y]);
      ctx.globalAlpha = al * (g.al != null ? g.al : 1); ctx.fillStyle = g.col || p.color;
      ctx.beginPath(); ctx.arc(s[0], s[1], Math.max(0.5, g.r * s[2]), 0, TAU); ctx.fill();
    });
    (p.texts || []).forEach((g) => {
      const s = project([g.x, g.y]);
      ctx.globalAlpha = al * (0.2 + 0.8 * fill); ctx.fillStyle = g.col || p.color; ctx.font = Math.max(4, g.sz * s[2]) + FONT; ctx.textAlign = g.ta || 'center';
      const text = scramble(g.s, t, p.startAt + p.flyTime, 0.9);
      if (g.rt != null) { ctx.save(); ctx.translate(s[0], s[1]); ctx.rotate(g.rt); ctx.fillText(text, 0, 0); ctx.restore(); } else ctx.fillText(text, s[0], s[1]);
    });
  }

  function drawTitle(al) {
    ctx.globalAlpha = al;
    const ty = H * 0.04;
    ctx.font = (36 * u) + FONT; ctx.textAlign = 'center'; ctx.fillStyle = COLOR.orange; ctx.shadowColor = COLOR.orange; ctx.shadowBlur = 14 * u;
    ctx.fillText('J . A . R . V . I . S .', CX, ty); ctx.shadowBlur = 0;
    // "Just A Really Very Intelligent System" with the first letters in bold
    const words = ['Just', 'A', 'Really', 'Very', 'Intelligent', 'System'], size = 9 * u, parts = [];
    words.forEach((w, i) => { parts.push([true, w[0]]); parts.push([false, w.slice(1) + (i < 5 ? ' ' : '')]); });
    const font = (bold) => (bold ? 'bold ' : '') + size + FONT;
    let width = 0;
    parts.forEach(([bold, s]) => { ctx.font = font(bold); width += ctx.measureText(s).width; });
    let px = CX - width / 2;
    ctx.textAlign = 'left'; ctx.fillStyle = 'rgba(255,154,61,.85)';
    parts.forEach(([bold, s]) => { ctx.font = font(bold); ctx.fillText(s, px, ty + 47 * u); px += ctx.measureText(s).width; });
    ctx.textAlign = 'center'; ctx.font = (9 * u) + FONT; ctx.fillStyle = 'rgba(180,230,255,.6)'; ctx.fillText('customized by Chris', CX, ty + 59 * u);
    ctx.globalAlpha = 1;
  }

  /* ---------- hand-over to the real HUD ---------- */
  const capture = JarvisHud.capture;
  let captureState = CAPTURE.COLLECTING, freezeCount = 0, snapshot = null, collected = [], textReveal = [];
  let mapDelays = null, brainSeeds = null, domTexts = null, done = false;
  const log = document.getElementById('log'), bar = document.getElementById('bar');
  capture.texts = new Map();
  [log, bar].forEach((el) => { if (el) { el.style.zIndex = '101'; el.style.clipPath = 'inset(100% 0 0 0)'; } });
  const background = document.createElement('div');   // the page background, faded in behind the panels
  (function copyPageBackground() {
    const b = getComputedStyle(document.body), h = getComputedStyle(document.documentElement), s = (b.backgroundImage != 'none') ? b : h;
    background.style.cssText = 'position:absolute;left:0;top:0;width:100%;height:100%;opacity:0';
    background.style.backgroundColor = (b.backgroundColor == 'rgba(0, 0, 0, 0)') ? h.backgroundColor : b.backgroundColor;
    background.style.backgroundImage = s.backgroundImage; background.style.backgroundSize = s.backgroundSize;
    background.style.backgroundPosition = s.backgroundPosition; background.style.backgroundRepeat = s.backgroundRepeat;
    overlay.insertBefore(background, canvas);
  })();

  function revealGroup(rec) {
    // which panel (index) or wing reveals this text, or null for texts outside all of them
    for (let i = 0; i < PANELS.length; i++) { const p = PANELS[i]; if (rec.x >= p.x - 4 && rec.x <= p.x + p.w + 4 && rec.y >= p.y - 4 && rec.y <= p.y + p.h + 8) return i; }
    if (!compact && (inRect(WING_LEFT, rec.x, rec.y, 0) || inRect(WING_RIGHT, rec.x, rec.y, 0))) return WINGS;
    return null;
  }

  function drawGrid(t) {
    // background glow and grid, outside the panels (the panels come from the HUD snapshot)
    const a = clamp01((t - TIME.panels) / TIME.gridFade);
    background.style.opacity = a;
    if (a <= 0) return;
    ctx.save(); ctx.beginPath(); ctx.rect(0, 0, W, H);
    PANELS.forEach((p) => ctx.rect(p.x - 6, p.y - 6, p.w + 12, p.h + 12));
    if (!compact) [WING_LEFT, WING_RIGHT].forEach((r) => ctx.rect(r.x, r.y, r.w, r.h));
    ctx.clip('evenodd'); ctx.globalAlpha = a;
    const glow = ctx.createRadialGradient(CX, CY, 0, CX, CY, Math.max(W, H) * 0.6);
    glow.addColorStop(0, 'rgba(25,211,255,0.14)'); glow.addColorStop(1, 'rgba(2,6,11,0)'); ctx.fillStyle = glow; ctx.fillRect(0, 0, W, H);
    ctx.strokeStyle = 'rgba(25,211,255,0.045)'; ctx.lineWidth = 1; ctx.beginPath();
    for (let gx = 0; gx < W; gx += 60 * u) { ctx.moveTo(gx, 0); ctx.lineTo(gx, H); }
    for (let gy = 0; gy < H; gy += 60 * u) { ctx.moveTo(0, gy); ctx.lineTo(W, gy); }
    ctx.stroke(); ctx.restore(); ctx.globalAlpha = 1;
  }

  function captureHud(t) {
    // 1. collect the texts the HUD draws; 2. at TIME.capture ask the HUD to draw without texts for a few frames; 3. copy its canvas
    if (captureState == CAPTURE.DONE) return;
    if (captureState == CAPTURE.COLLECTING) {
      if (capture.texts && capture.texts.size) { collected = Array.from(capture.texts.values()); capture.texts.clear(); }
      if (t >= TIME.capture && collected.length) { capture.texts = null; capture.active = true; captureState = CAPTURE.FREEZING; freezeCount = 0; }
      return;
    }
    if (++freezeCount < FREEZE_FRAMES) return;
    const hudCanvas = document.getElementById('cv');
    if (hudCanvas) {
      snapshot = document.createElement('canvas'); snapshot.width = hudCanvas.width; snapshot.height = hudCanvas.height;
      snapshot.getContext('2d').drawImage(hudCanvas, 0, 0);
      textReveal = collected.map((rec) => ({ rec, group: revealGroup(rec) })).filter((q) => q.group !== null);
    }   // no HUD canvas: the panels are not replayed, the HUD shows them itself when the overlay fades
    capture.active = false; captureState = CAPTURE.DONE;
  }

  function drawRevealedTexts(t) {
    // the HUD's texts, decoded line by line while their panel unrolls
    textReveal.forEach(({ rec, group }) => {
      let s = rec.text, shownAt, visible;
      if (group === WINGS) { shownAt = TIME.wingTexts + 0.1 + Math.abs(rec.x - CX) / W * 0.8; visible = true; }
      else {
        const p = PANELS[group], t1 = panelStart(group);
        shownAt = t1 + 0.3 + clamp01((rec.y - p.y) / p.h) * 0.6;
        visible = rec.y < p.y - 6 + (p.h + 12) * easeOut(clamp01((t - t1) / TIME.panelUnroll)) + 4;
      }
      if (t < shownAt || !visible) return;
      if (/^\d\d:\d\d:\d\d$/.test(s)) s = new Date().toLocaleTimeString('en-GB');
      ctx.globalAlpha = Math.min(1, (t - shownAt) * 3) * (rec.alpha == null ? 1 : rec.alpha);
      ctx.fillStyle = rec.color; ctx.font = rec.size + FONT; ctx.textAlign = rec.align;
      ctx.fillText(scramble(s, t, shownAt, 0.9), rec.x, rec.y);
    });
    ctx.globalAlpha = 1;
  }

  function drawBrain(t) {
    // the neural core's point cloud (made by hud.html) flies together inside its panel
    const panel = PANELS[NEURAL], brain = JarvisHud.brain;
    if (!brain || !brain.pts || t < TIME.brainShown) return;
    const nx = panel.x + panel.w / 2, ny = panel.y + panel.h * 0.5, nr = Math.min(panel.h * 0.36, panel.w * 0.44), sc = nr * 1.03;
    if (!brainSeeds) brainSeeds = brain.pts.map(() => [random(), random(), random(), random()]);
    const start = TIME.brain, rot = (JarvisHud.brainPose && JarvisHud.brainPose.rot) || 0, ca = Math.cos(rot), sa = Math.sin(rot), c3 = Math.cos(0.3), s3 = Math.sin(0.3);
    const hx = panel.x + 10 * u, hy = panel.y + 42 * u, hw2 = panel.w - 20 * u, hh2 = panel.h - 68 * u, projected = [];
    ctx.save(); ctx.beginPath(); ctx.rect(hx, hy, hw2, hh2); ctx.clip(); ctx.globalCompositeOperation = 'lighter';
    const ga = clamp01((t - start) / 1.2), glow = ctx.createRadialGradient(nx, ny, 0, nx, ny, sc * 1.3);
    glow.addColorStop(0, 'rgba(25,211,255,' + (0.1 * ga) + ')'); glow.addColorStop(1, 'rgba(25,211,255,0)');
    ctx.globalAlpha = 1; ctx.fillStyle = glow; ctx.fillRect(hx, hy, hw2, hh2);
    ctx.strokeStyle = COLOR.cyan; ctx.lineWidth = u; ctx.beginPath();
    brain.pts.forEach((q, i) => {
      const seed = brainSeeds[i], pg = clamp01((t - start - seed[0] * 0.5) / 0.85), e = easeOut(pg), inv = 1 - e;
      const x1 = q[0] * ca + q[2] * sa, z1 = -q[0] * sa + q[2] * ca, y2 = q[1] * c3 - z1 * s3, z2 = q[1] * s3 + z1 * c3, persp = 1 / (1 + z2 * 0.3), fx = nx + x1 * sc * persp, fy = ny - y2 * sc * persp;
      const an = (seed[3] - 0.5) * 7 * inv, cs = Math.cos(an), sn = Math.sin(an), gx = nx + (fx - nx) * cs - (fy - ny) * sn, gy = ny + (fx - nx) * sn + (fy - ny) * cs;
      const sx = hx + seed[1] * hw2, sy = hy + seed[2] * hh2, X = sx * inv + gx * e, Y = sy * inv + gy * e;
      projected.push([X, Y, pg]);
      if (pg > 0 && pg < 1) { ctx.moveTo(X, Y); ctx.lineTo(X + (sx - X) * 0.12 * inv, Y + (sy - Y) * 0.12 * inv); }
    });
    ctx.globalAlpha = 0.5; ctx.stroke();
    const edgeAlpha = clamp01((t - start - 0.8) / 0.6) * 0.3;
    if (edgeAlpha > 0) {
      ctx.globalAlpha = edgeAlpha; ctx.beginPath();
      brain.E.forEach(([i, j]) => { const a = projected[i], b = projected[j]; if (a && b) { ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); } });
      ctx.stroke();
    }
    ctx.fillStyle = COLOR.cyan;
    projected.forEach((q, i) => {
      if (q[2] <= 0) return;
      const inner = i >= 180, s = (inner ? 2.6 : 2.2) * u;   // the last 40 points are the inner core
      ctx.globalAlpha = Math.min(1, q[2] * 4) * (inner ? 1 : 0.75); ctx.fillRect(q[0] - s / 2, q[1] - s / 2, s, s);
    });
    ctx.restore(); ctx.globalAlpha = 1;
  }

  function drawPanels(t) {
    // the copied HUD panels unroll from the top, one after the other, with a bright edge
    const r = snapshot.width / W;
    PANELS.forEach((p, i) => {
      const w = easeOut(clamp01((t - panelStart(i)) / TIME.panelUnroll));
      if (w <= 0) return;
      const sw = p.w + 12, sh = p.h + 12;
      ctx.globalAlpha = 1;
      if (i == NEURAL) {   // its inner area stays open: the brain is drawn there live
        ctx.save(); ctx.beginPath(); ctx.rect(p.x - 6, p.y - 6, sw, sh * w); ctx.rect(p.x + 10 * u, p.y + 42 * u, p.w - 20 * u, p.h - 68 * u); ctx.clip('evenodd');
        ctx.drawImage(snapshot, (p.x - 6) * r, (p.y - 6) * r, sw * r, sh * w * r, p.x - 6, p.y - 6, sw, sh * w); ctx.restore();
      } else ctx.drawImage(snapshot, (p.x - 6) * r, (p.y - 6) * r, sw * r, sh * w * r, p.x - 6, p.y - 6, sw, sh * w);
      if (w < 1) { ctx.globalAlpha = 0.9 * (1 - w); ctx.fillStyle = COLOR.cyan; ctx.fillRect(p.x, p.y + p.h * w, p.w, 2 * u); }
    });
    if (!compact) {
      const wt = easeOut(clamp01((t - TIME.wings) / 0.7));
      if (wt > 0) {   // the wings open sideways from the core
        const L = WING_LEFT, R = WING_RIGHT;
        ctx.globalAlpha = 1;
        ctx.drawImage(snapshot, (L.x + L.w * (1 - wt)) * r, L.y * r, L.w * wt * r, L.h * r, L.x + L.w * (1 - wt), L.y, L.w * wt, L.h);
        ctx.drawImage(snapshot, R.x * r, R.y * r, R.w * wt * r, R.h * r, R.x, R.y, R.w * wt, R.h);
      }
    }
  }

  function drawMapDots(t) {
    // the world map's dots appear west to east while the network panel unrolls
    const dots = capture.mapDots;
    if (!dots || !dots.length) return;
    if (!mapDelays) { mapDelays = new Float32Array(dots.length); for (let j = 0; j < dots.length; j++) mapDelays[j] = (dots[j][0] + 180) / 360 * 0.9 + random() * 0.4; }
    const p = PANELS[NETWORK], area = JarvisHud.mapArea(p, u), shown = easeOut(clamp01((t - panelStart(NETWORK)) / TIME.panelUnroll));
    const start = panelStart(NETWORK) + 0.3, size = 1.7 * u, limit = p.y - 6 + (p.h + 12) * shown;
    ctx.globalAlpha = 0.38; ctx.fillStyle = COLOR.cyan; ctx.beginPath();
    for (let j = 0; j < dots.length; j++) {
      if (t < start + mapDelays[j]) continue;
      const qy = area.top + (area.latTop - dots[j][1]) / (area.latTop - area.latBottom) * area.h;
      if (qy > limit) continue;
      ctx.rect(area.x + (dots[j][0] + 180) / 360 * area.w, qy, size, size);
    }
    ctx.fill();
  }

  function revealChatAndBar(t) {
    // the real chat log and input bar unroll too, their texts decoding like the panels'
    const p1 = easeOut(clamp01((t - TIME.panels) / TIME.panelUnroll)), p2 = easeOut(clamp01((t - TIME.logBar) / 0.4));
    if (log) log.style.clipPath = 'inset(' + (100 * (1 - p1)).toFixed(1) + '% 0 0 0)';
    if (bar) bar.style.clipPath = 'inset(' + (100 * (1 - p2)).toFixed(1) + '% 0 0 0)';
    if (t <= TIME.wings) return;
    if (!domTexts) {
      domTexts = [];
      [log, bar].forEach((el) => {
        if (!el) return;
        const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
        let node;
        while ((node = walker.nextNode())) if (node.nodeValue.trim()) domTexts.push({ node, text: node.nodeValue, placeholder: false });
      });
      const input = bar && bar.querySelector('input[type=text]');
      if (input && input.placeholder) domTexts.push({ node: input, text: input.placeholder, placeholder: true });
    }
    domTexts.forEach((d) => { const s = scramble(d.text, t, TIME.domText, 1.0); if (d.placeholder) d.node.placeholder = s; else d.node.nodeValue = s; });
  }

  function drawHandOver(t) {
    captureHud(t);
    if (captureState != CAPTURE.DONE) return;
    if (snapshot) drawPanels(t);
    drawMapDots(t);
    drawBrain(t);
    drawRevealedTexts(t);
    if (!done) revealChatAndBar(t);
    ctx.globalAlpha = 1;
  }

  function restoreHud() {
    capture.active = false; capture.texts = null;
    if (domTexts) domTexts.forEach((d) => { if (d.placeholder) d.node.placeholder = d.text; else d.node.nodeValue = d.text; });
    domTexts = [];
    [log, bar].forEach((el) => { if (el) el.style.clipPath = ''; });
    setTimeout(() => [log, bar].forEach((el) => { if (el) el.style.zIndex = ''; }), 600);
  }

  function drawFrame(t) {
    ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.shadowBlur = 0; ctx.globalAlpha = 1; ctx.clearRect(0, 0, W, H);
    drawGrid(t);
    const starFade = 1 - clamp01((t - TIME.starsFade) / 0.6);
    if (starFade > 0) {   // star tunnel
      ctx.fillStyle = COLOR.cyan;
      stars.forEach((s) => {
        const z = (s.phase + t * 0.25) % 1, rr = z * z * W * 0.45 * (0.3 + s.spread);
        ctx.globalAlpha = starFade * 0.7 * z; ctx.fillRect(CX + Math.cos(s.angle) * rr, CY + Math.sin(s.angle) * rr * 0.6, u * (2 + z * 4), u * (2 + z * 4));
      });
    }
    ctx.save();
    const zoom = 1.08 - 0.08 * easeOut(clamp01((t - TIME.starsFade) / 0.8));
    ctx.translate(CX, CY); ctx.scale(zoom, zoom); ctx.translate(-CX, -CY);
    pieces.forEach((p) => {
      if (p.wing) return;   // the wings come from the HUD snapshot
      if (p.update) p.update();
      if (t < p.startAt + p.flyTime) { drawPiece(p, t - 0.1, true); drawPiece(p, t - 0.05, true); }
      drawPiece(p, t, false);
    });
    ctx.restore(); ctx.shadowBlur = 0; ctx.setLineDash([]);
    if (t > TIME.flash) {   // the core lights up and pulses
      const ca2 = clamp01((t - TIME.flash) / 0.4), pulse = 0.5 + 0.5 * Math.sin((t - TIME.burst) * 7), gr = ctx.createRadialGradient(CX, CY, 0, CX, CY, coreR * 0.46);
      gr.addColorStop(0, 'rgba(255,255,255,' + (0.6 + 0.2 * pulse) * ca2 + ')'); gr.addColorStop(0.4, 'rgba(25,211,255,' + 0.4 * ca2 + ')'); gr.addColorStop(1, 'rgba(25,211,255,0)');
      ctx.globalAlpha = 1; ctx.fillStyle = gr; ctx.beginPath(); ctx.arc(CX, CY, coreR * 0.46, 0, TAU); ctx.fill();
    }
    if (t > TIME.burst) {   // white flash and an orange shock ring
      const b = clamp01((t - TIME.burst) / 0.7);
      ctx.globalAlpha = (1 - b) * 0.9; ctx.fillStyle = '#fff'; ctx.beginPath(); ctx.arc(CX, CY, coreR * 0.35 * (1 + b * 2), 0, TAU); ctx.fill();
      ctx.globalAlpha = 1 - b; ctx.strokeStyle = COLOR.orange; ctx.lineWidth = 3 * u; ctx.beginPath(); ctx.arc(CX, CY, coreR * (0.4 + b * 5), 0, TAU); ctx.stroke();
    }
    const fs = Math.round(14 * u);
    ctx.font = fs + FONT; ctx.textAlign = 'center'; ctx.fillStyle = COLOR.cyan;
    status.forEach((s, i) => {
      const tm = TIME.status + i * TIME.statusStep;
      if (t > tm) { ctx.globalAlpha = clamp01((t - tm) / 0.2) * (1 - clamp01((t - TIME.panels) / 0.3)); ctx.fillText('> ' + s, CX, CY + ringR + 90 * u + i * fs * 1.5); }
    });
    if (JarvisHud.drawWear) JarvisHud.drawWear(ctx, W, H);
    drawTitle(clamp01(t / 0.5));
    drawHandOver(t);
    ctx.globalAlpha = 1;
  }

  const t0 = performance.now();
  function finish() {
    if (done) return;
    done = true; restoreHud();
    overlay.style.transition = 'opacity .4s'; overlay.style.pointerEvents = 'none'; overlay.style.opacity = '0';
    setTimeout(() => overlay.remove(), 500);
  }
  function tick(now) {
    if (!overlay.isConnected) return;
    const t = (now - t0) / 1000;
    try { drawFrame(Math.min(t, TIME.last)); }
    catch (e) { console.error('boot animation stopped:', e); finish(); return; }   // never leave the HUD covered
    if (t >= TIME.end && !done) finish();
    requestAnimationFrame(tick);
  }
  overlay.addEventListener('click', finish);
  requestAnimationFrame(tick);
})();
