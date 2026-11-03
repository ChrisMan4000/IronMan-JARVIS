/* global hw */  // hw: live hardware stats (let in hud.html), filled when the helper answers
/* J.A.R.V.I.S. boot animation, part 1: the scene. Builds every piece of the HUD drawing that flies in (core rings, ticks,
   gauges, wing graphs) and the star tunnel. hud-boot.js (part 2) animates and draws them.
   window.JarvisBootScene(env) -> {pieces, stars}, called once; env = {W, u, compact, CX, CY, coreR, ringR, focal, WING, COLOR, random}.
   The order of the random() calls decides the look: keep it when changing the scene. */
window.JarvisBootScene = function (env) {
  'use strict';
  const { W, u, compact, CX, CY, coreR, ringR, focal, WING, COLOR, random } = env;
  const PI = Math.PI, TAU = PI * 2;
  const clamp01 = (v) => Math.max(0, Math.min(1, v));
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
  return { pieces, stars };
};
