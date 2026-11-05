/* hud-brain.js - Jarvis neural core (plain WebGL, no libraries).
   const b = JarvisBrain(canvas, {detail: 1, fps: 30});
   b.setState('idle'|'listening'|'thinking'|'speaking');  b.setLevel(0..1);  b.intro(seconds);  b.destroy();
   Canvas is black + opaque: put it over the HUD with CSS mix-blend-mode: screen (black = see-through). */
(function () {
const COLS = {idle:[60,190,235], listening:[110,215,190], thinking:[235,160,95], speaking:[110,200,235]};   // HUD FDC palette
const ACC = [255,154,61];                                                                                   // HUD orange accent
const SI = {idle:0, listening:1, thinking:2, speaking:3};
//            rot  wobble line  point mist  glow  pulses
const CFG = [ [.07,.006, .30, .60, .085, .17, .60],
              [.12,.010, .33, .66, .090, .21, .75],
              [.50,.003, .27, .52, .050, .50, 1.0],
              [.12,.006, .33, .64, .090, .24, .90] ];

function JarvisBrain(cv, opt) {
  opt = opt || {};
  const D = opt.detail || 1; let FPS = opt.fps || 60;
  const gl = cv.getContext('webgl', {antialias:true, alpha:false, depth:false, powerPreference:'high-performance'});
  if (!gl) return null;

  // ---------- helpers ----------
  const R = Math.random, rnd = (a,b) => a + R()*(b-a), gauss = () => (R()+R()+R()-1.5)*.8;
  const len = v => Math.hypot(v[0],v[1],v[2]), sub = (a,b) => [a[0]-b[0],a[1]-b[1],a[2]-b[2]];
  const norm = v => { const l = len(v) || 1; return [v[0]/l,v[1]/l,v[2]/l]; }, dot = (a,b) => a[0]*b[0]+a[1]*b[1]+a[2]*b[2];
  const dir = () => { const z = rnd(-1,1), a = rnd(0,6.2832), s = Math.sqrt(1-z*z); return [s*Math.cos(a), s*Math.sin(a), z]; };
  const ball = r => { let p; do p = [rnd(-1,1),rnd(-1,1),rnd(-1,1)]; while (len(p) > 1); return p.map(x => x*r); };

  // ---------- cosmic web: particles on the walls and edges of random cells ----------
  const SEEDS = 46, seeds = Array.from({length:SEEDS}, () => ball(1.2));
  const near = p => { const o = []; for (let i = 0; i < SEEDS; i++) o.push([len(sub(p,seeds[i])), i]); return o.sort((u,v) => u[0]-v[0]); };
  const plane = (p,i,j) => { const A = seeds[i], B = seeds[j], n = norm(sub(B,A)), k = dot(sub(p,[(A[0]+B[0])/2,(A[1]+B[1])/2,(A[2]+B[2])/2]), n); return [p[0]-n[0]*k, p[1]-n[1]*k, p[2]-n[2]*k]; };
  const nodes = [], mk = (b,kind,o) => Object.assign({b, kind, k:R(), sp:rnd(.5,1.6), ph:rnd(0,6.2832)}, o);
  const WEB = 7000*D | 0, KNOTS = 420*D | 0, DUST = 900*D | 0, HAIRS = 650*D | 0;
  while (nodes.length < WEB) {
    let p = ball(1); const o = near(p), [a,b,c] = [o[0][1],o[1][1],o[2][1]], edge = R() < .72;
    if (edge) for (let i = 0; i < 6; i++) { p = plane(p,a,b); p = plane(p,a,c); } else p = plane(p,a,b);
    const q = near(p); if (![a,b,c].includes(q[0][1]) || q[1][0]-q[0][0] > .02 || (edge && q[2][0]-q[0][0] > .03)) continue;
    p = p.map(x => x + gauss()*(edge ? .011 : .02)); if (len(p) > 1) continue;
    nodes.push(mk(p, 0, {fly:R() < .26}));
  }
  // neurons: bright knots where several cells meet
  const somas = [];
  for (let tries = 0; somas.length < KNOTS && tries < 30000; tries++) {
    let p = ball(1); const o = near(p), id = o.slice(0,4).map(x => x[1]);
    for (let i = 0; i < 12; i++) { p = plane(p,id[0],id[1]); p = plane(p,id[0],id[2]); p = plane(p,id[0],id[3]); }
    const q = near(p); if (!id.includes(q[0][1]) || q[2][0]-q[0][0] > .03 || len(p) > .97) continue;
    const fly = R() < .26, acc = somas.length % 6 === 0 ? 1 : 0;
    somas.push(nodes.length); nodes.push(mk(p, 0, {fly, soma:1, acc}));
    for (let j = 0, m = 5 + (R()*8|0); j < m; j++) nodes.push(mk(p.map(x => x + gauss()*.016), 0, {fly, star:R() < .3}));
  }
  const WEBN = nodes.length;
  for (let i = 0; i < DUST; i++) nodes.push(mk(dir(), 1, {k:Math.pow(R(),1.6)}));
  const pairs = [], lmax = [], lmul = [];
  for (let i = 0; i < HAIRS; i++) {
    let w; do w = nodes[R()*WEBN|0]; while (len(w.b) < .82);
    const d = norm(w.b), L = rnd(.03,.15);
    pairs.push([nodes.length, nodes.length+1]); lmax.push(9); lmul.push(.9, 0);
    nodes.push(mk(d, 2, {L}), mk(d, 3, {L}));
  }
  // links: nearby web particles (grid lookup)
  const LINK = .075 / Math.cbrt(D), G = new Map(), key = (x,y,z) => (x*73856093) ^ (y*19349663) ^ (z*83492791), cell = p => p.map(v => Math.floor(v/LINK));
  for (let i = 0; i < WEBN; i++) { const kk = key(...cell(nodes[i].b)); (G.get(kk) || G.set(kk, []).get(kk)).push(i); }
  for (let i = 0; i < WEBN; i++) {
    const p = nodes[i].b, c = cell(p), nb = [];
    for (let x=-1;x<=1;x++) for (let y=-1;y<=1;y++) for (let z=-1;z<=1;z++) for (const j of (G.get(key(c[0]+x,c[1]+y,c[2]+z)) || [])) {
      if (j <= i) continue; const d = len(sub(p, nodes[j].b)); if (d < LINK) nb.push([d,j]); }
    nb.sort((u,v) => u[0]-v[0]);
    for (let m = 0, n = R() < .5 ? 2 : 3; m < Math.min(n, nb.length); m++) { pairs.push([i, nb[m][1]]); lmax.push(LINK*2.2); lmul.push(1,1); }
  }
  // axons: each neuron to its 2-3 nearest neurons (the "neural network" lines, carry the signals)
  const axons = [];
  somas.forEach(i => {
    const o = somas.filter(j => j !== i).map(j => [len(sub(nodes[i].b, nodes[j].b)), j]).sort((u,v) => u[0]-v[0]);
    for (let m = 0, n = 3 + (R() < .5); m < n; m++) if (o[m] && o[m][0] < .6 && (m < 2 || i < o[m][1])) {
      axons.push(pairs.length); pairs.push([i, o[m][1]]); lmax.push(1.1); lmul.push(1.1,1.1); }
  });
  // signals running along the axons
  const PULSES = Math.min(axons.length*2, 650*D | 0), PB = nodes.length;
  const pulse = Array.from({length:PULSES}, (_,i) => ({a:axons[R()*axons.length|0], f:R(), v:rnd(.35,.9), acc:i % 5 === 0}));
  // sparks: tiny fast lights hopping along the web lines (from line to line at the junctions)
  const adj = Array.from({length:WEBN}, () => []);
  pairs.forEach(([a,b], i) => { if (a < WEBN && b < WEBN) { adj[a].push(i); adj[b].push(i); } });
  const webLinks = pairs.map((_,i) => i).filter(i => pairs[i][0] < WEBN && pairs[i][1] < WEBN);
  const SPARKS = 1100*D | 0, SB = nodes.length + PULSES;
  const spawn = s => { s.p = webLinks[R()*webLinks.length|0]; s.r = R() < .5; s.f = 0; s.life = 6 + (R()*30|0); return s; };
  const spark = Array.from({length:SPARKS}, () => spawn({v:rnd(1.4,3.2), f:0}));
  const M0 = pairs.length, N = nodes.length + PULSES + SPARKS, M = M0 + SPARKS, fire = new Float32Array(N);

  // ---------- shapes for the four states ----------
  function target(nd, st) {
    const b = nd.b, r = len(b) || 1e-6, d = [b[0]/r, b[1]/r, b[2]/r]; let Rr;
    if (nd.kind === 0) { if (st === 2) { if (!nd.fly) return b.map(x => x*.11); Rr = .3 + Math.pow(nd.k,1.5)*2; } else Rr = [.56+.5*r, .6+.54*r, 0, 1.0*r][st]; }
    else if (nd.kind === 1) { const Q = [[.35,1.9],[.45,2],[.9,2.7],[1.1,2.1]][st]; Rr = Q[0] + nd.k*(Q[1]-Q[0]); }
    else Rr = [1.02,1.1,.09,1.0][st] + (nd.kind === 3 ? nd.L*[1,1.25,4,.45][st] : 0);
    return [d[0]*Rr, d[1]*Rr, d[2]*Rr];
  }
  const NN = nodes.length, TG = [0,1,2,3].map(st => { const a = new Float32Array(NN*3); nodes.forEach((nd,i) => a.set(target(nd,st), i*3)); return a; });
  const cur = new Float32Array(TG[0]), pos = new Float32Array(N*3);
  const start = Float32Array.from({length:NN*3}, () => 0), delay = new Float32Array(NN);
  for (let i = 0; i < NN; i++) { const d = dir(), r = rnd(2,3); start.set([d[0]*r, d[1]*r, d[2]*r], i*3); delay[i] = nodes[i].soma ? R()*.25 : .15 + R()*.5; }

  // ---------- GL programs ----------
  function prog(vs, fs) {
    const p = gl.createProgram();
    [[gl.VERTEX_SHADER,vs],[gl.FRAGMENT_SHADER,fs]].forEach(([t,s]) => { const sh = gl.createShader(t); gl.shaderSource(sh, 'precision mediump float;'+s); gl.compileShader(sh);
      if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(sh)); gl.attachShader(p, sh); });
    gl.linkProgram(p); const u = {}, a = {};
    for (let i = 0, n = gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS); i < n; i++) { const x = gl.getActiveUniform(p,i).name; u[x] = gl.getUniformLocation(p,x); }
    for (let i = 0, n = gl.getProgramParameter(p, gl.ACTIVE_ATTRIBUTES); i < n; i++) { const x = gl.getActiveAttrib(p,i).name; a[x] = gl.getAttribLocation(p,x); }
    return {p, u, a};
  }
  const PROJ = `uniform vec2 uF; uniform float uZ; varying float vE;
    vec4 proj(vec3 p){ float w = uZ - p.z; vec4 c = vec4(p.x*uF.x, p.y*uF.y, 0., w); vE = smoothstep(.98,.7,length(c.xy/w)); return c; }`;
  const PT = prog(`attribute vec3 p; attribute float s, ph, ac, fi; uniform float uPx, uT; varying float vB, vA; ${PROJ}
      void main(){ gl_Position = proj(p); gl_PointSize = min(s*(1.+fi*.9)*uPx/gl_Position.w, 48.); vB = (.6 + .4*sin(uT*2.5 + ph*7.))*(1.+fi*2.); vA = ac; }`,
    `uniform vec3 uC, uA; uniform float uG; varying float vB, vA, vE;
      void main(){ float d = length(gl_PointCoord-.5), a = smoothstep(.5,0.,d); a *= a; float c = smoothstep(.16,0.,d); vec3 col = mix(uC, uA, vA);
        gl_FragColor = vec4((col*a*.8 + mix(col,vec3(1.),.55)*c*.75)*vB*uG*vE, 1.); }`);
  const MI = prog(`attribute vec3 p; attribute float m; uniform float uPx; varying float vF; ${PROJ}
      void main(){ gl_Position = proj(p); gl_PointSize = min(m*uPx/gl_Position.w, 120.); vF = m > 0. ? 1. : 0.; }`,
    `uniform vec3 uC; uniform float uG; varying float vF, vE;
      void main(){ float d = length(gl_PointCoord-.5), a = smoothstep(.5,0.,d); gl_FragColor = vec4(uC*a*a*uG*vF*vE, 1.); }`);
  const LN = prog(`attribute vec3 p; attribute vec3 c; varying vec3 vC; ${PROJ} void main(){ gl_Position = proj(p); vC = c; }`,
    `varying vec3 vC; varying float vE; void main(){ gl_FragColor = vec4(vC*vE, 1.); }`);
  const GW = prog(`attribute vec2 q; varying vec2 vQ; void main(){ vQ = q; gl_Position = vec4(q, 0., 1.); }`,
    `uniform vec3 uC; uniform float uG, uR; varying vec2 vQ; void main(){ float d = length(vQ)/uR; gl_FragColor = vec4(uC*uG*exp(-d*d*3.)*(1.+.8*exp(-d*d*40.)), 1.); }`);

  const buf = (data, usage) => { const b = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, b); gl.bufferData(gl.ARRAY_BUFFER, data, usage || gl.STATIC_DRAW); return b; };
  const all = i => i < NN ? nodes[i] : null;
  const bPos = buf(pos, gl.DYNAMIC_DRAW);
  const bSize = buf(Float32Array.from({length:N}, (_,i) => { const n = all(i); return !n ? (i >= SB ? 1.5 : 3.2) : n.soma ? rnd(3.6,5) : n.kind === 1 ? rnd(.35,.8) : n.kind === 2 ? .4 : n.kind === 3 ? 0 : n.star ? rnd(1.2,2.2) : rnd(.3,.65); }));
  const bPh = buf(Float32Array.from({length:N}, (_,i) => all(i) ? all(i).ph : rnd(0,6.28)));
  const bAc = buf(Float32Array.from({length:N}, (_,i) => { const n = all(i); return n ? (n.acc ? 1 : 0) : (i >= SB ? (i % 9 === 0 ? 1 : 0) : pulse[i-PB].acc ? 1 : 0); }));
  const bFire = buf(fire, gl.DYNAMIC_DRAW);
  const bMist = buf(Float32Array.from({length:N}, (_,i) => { const n = all(i); return n && n.kind === 0 ? (n.soma ? rnd(10,14) : rnd(4,9)) : 0; }));
  const lPos = new Float32Array(M*6), lCol = new Float32Array(M*6), LM = Float32Array.from(lmax), LU = Float32Array.from(lmul);
  const bLPos = buf(lPos, gl.DYNAMIC_DRAW), bLCol = buf(lCol, gl.DYNAMIC_DRAW), bQuad = buf(new Float32Array([-1,-1,1,-1,-1,1,1,1]));
  const attr = (pr, name, b, n) => { const l = pr.a[name]; if (l == null || l < 0) return; gl.bindBuffer(gl.ARRAY_BUFFER, b); gl.enableVertexAttribArray(l); gl.vertexAttribPointer(l, n, gl.FLOAT, false, 0, 0); };
  const off = pr => Object.values(pr.a).forEach(l => gl.disableVertexAttribArray(l));

  // ---------- state ----------
  let st = 0, lvl = 0, ext = 0, extUntil = 0, introT = 9, introLen = 2.4, alive = true, last = performance.now(), acc = 0, rotY = 0;
  const P = CFG[0].slice(), col = COLS.idle.map(x => x/255), tcol = col.slice(), A3 = ACC.map(x => x/255);
  let W = 1, H = 1, pxScale = 10;
  const ro = new ResizeObserver(() => { const dpr = Math.min(devicePixelRatio || 1, 2); W = cv.width = Math.max(1, cv.clientWidth*dpr | 0); H = cv.height = Math.max(1, cv.clientHeight*dpr | 0); pxScale = Math.min(W,H)*.011; });
  ro.observe(cv);
  const sim = t => { let s = Math.max(0, Math.sin(t*9.3)) * (.55 + .45*Math.sin(t*2.1)); if (Math.sin(t*.9) > .75) s *= .1; return s; };
  const ease = x => x <= 0 ? 0 : x >= 1 ? 1 : 1 - Math.pow(1-x, 3);

  function frame(now) {
    if (!alive) return; requestAnimationFrame(frame);
    const step = (now - last)/1000; if (step < 1/FPS - .002) return; const w0 = performance.now();
    const dt = Math.min(.05, step); last = now; const t = now/1000;
    introT += dt;

    const raw = now < extUntil ? ext : st === 3 ? sim(t) : st === 2 ? .3 + .1*Math.sin(t*3) : st === 1 ? .15 + .1*Math.sin(t*2) : 0;
    lvl += (raw - lvl) * (raw > lvl ? .5 : .12);
    const e = 1 - Math.exp(-dt*2); CFG[st].forEach((v,i) => P[i] += (v - P[i])*e); for (let i = 0; i < 3; i++) col[i] += (tcol[i] - col[i])*e;
    const [rot, wob, lg, pg, mg, gg, pact] = P, tg = TG[st], ip = introT/introLen, inIntro = ip < 1.2;
    rotY += dt*rot*(1 + lvl*.5);
    const rx = .25*Math.sin(t*.11), cy = Math.cos(rotY), sy = Math.sin(rotY), cx = Math.cos(rx), sx = Math.sin(rx);

    for (let i = 0; i < NN; i++) {
      const nd = nodes[i], i3 = i*3, k = 1 - Math.exp(-dt*2.2*nd.sp);
      cur[i3] += (tg[i3]-cur[i3])*k; cur[i3+1] += (tg[i3+1]-cur[i3+1])*k; cur[i3+2] += (tg[i3+2]-cur[i3+2])*k;
      let m = 1 + .012*Math.sin(t*.8 + cur[i3+1]*3);
      if (st === 3) m += lvl*.16*(.5 + .5*Math.sin(nd.ph + t*7)); else if (st === 1) m += lvl*.12*Math.sin(cur[i3+1]*6 - t*5);
      let x = cur[i3]*m + wob*Math.sin(t*1.3 + nd.ph), y = cur[i3+1]*m + wob*Math.sin(t*1.7 + nd.ph*1.3), z = cur[i3+2]*m + wob*Math.sin(t*1.1 + nd.ph*1.7);
      if (inIntro) {                                                   // intro: fly in from far away with a spin
        const q = ease((ip - delay[i]) / .55), s = (1-q)*2.4, cs = Math.cos(s), ss = Math.sin(s);
        const ox = start[i3]*cs + start[i3+2]*ss, oz = -start[i3]*ss + start[i3+2]*cs;
        x = ox + (x-ox)*q; y = start[i3+1] + (y-start[i3+1])*q; z = oz + (z-oz)*q;
      }
      const x1 = x*cy + z*sy, z1 = -x*sy + z*cy;                       // rotate (y, then x)
      pos[i3] = x1; pos[i3+1] = y*cx - z1*sx; pos[i3+2] = y*sx + z1*cx;
    }
    for (let i = 0; i < somas.length; i++) fire[somas[i]] *= Math.exp(-dt*3.5);
    const nOn = Math.round(PULSES * Math.min(1, pact + lvl*.4) * (inIntro ? ease(ip - .9) : 1));
    for (let i = 0; i < PULSES; i++) {
      const pu = pulse[i], o = (PB+i)*3;
      pu.f += dt*pu.v*(1 + lvl*1.5 + (st === 2 ? 1.2 : 0));
      if (pu.f > 1) { fire[pairs[pu.a][pu.r ? 0 : 1]] = 1; pu.f = 0; pu.a = axons[R()*axons.length|0]; pu.r = R() < .5; }
      const a = pairs[pu.a][pu.r ? 1 : 0]*3, b = pairs[pu.a][pu.r ? 0 : 1]*3, f = pu.f;
      if (i < nOn) { pos[o] = pos[a]+(pos[b]-pos[a])*f; pos[o+1] = pos[a+1]+(pos[b+1]-pos[a+1])*f; pos[o+2] = pos[a+2]+(pos[b+2]-pos[a+2])*f; }
      else { pos[o] = pos[o+1] = 0; pos[o+2] = -99; }
    }
    const sOn = Math.round(SPARKS * Math.min(1, pact + lvl*.5) * (inIntro ? ease(ip - .9) : 1)), sp3 = st === 2 ? 1.8 : 1 + lvl;
    for (let i = 0; i < SPARKS; i++) {
      const s = spark[i], o = (SB+i)*3, lo = (M0+i)*6;
      let a = pairs[s.p][s.r ? 1 : 0]*3, b = pairs[s.p][s.r ? 0 : 1]*3;
      const L = Math.hypot(pos[b]-pos[a], pos[b+1]-pos[a+1], pos[b+2]-pos[a+2]) || .01;
      s.f += dt*s.v*sp3/Math.max(L, .02);
      if (s.f >= 1) {                                                  // reached a junction: jump onto another line there
        const node = pairs[s.p][s.r ? 0 : 1], nb = adj[node];
        if (--s.life <= 0 || nb.length < 2) spawn(s);
        else { let q; do q = nb[R()*nb.length|0]; while (q === s.p); s.p = q; s.r = pairs[q][1] === node; s.f = 0; }
        a = pairs[s.p][s.r ? 1 : 0]*3; b = pairs[s.p][s.r ? 0 : 1]*3;
      }
      const L2 = Math.hypot(pos[b]-pos[a], pos[b+1]-pos[a+1], pos[b+2]-pos[a+2]) || .01, f = Math.min(1, s.f), t0 = Math.max(0, f - .045/L2);
      if (L2 > .2) spawn(s);                                           // stretched line (state change): hide, start elsewhere
      if (i < sOn && L2 <= .2) {
        pos[o] = pos[a]+(pos[b]-pos[a])*f; pos[o+1] = pos[a+1]+(pos[b+1]-pos[a+1])*f; pos[o+2] = pos[a+2]+(pos[b+2]-pos[a+2])*f;
        lPos[lo] = pos[o]; lPos[lo+1] = pos[o+1]; lPos[lo+2] = pos[o+2];
        lPos[lo+3] = pos[a]+(pos[b]-pos[a])*t0; lPos[lo+4] = pos[a+1]+(pos[b+1]-pos[a+1])*t0; lPos[lo+5] = pos[a+2]+(pos[b+2]-pos[a+2])*t0;
        lCol[lo] = .45 + col[0]*.9; lCol[lo+1] = .45 + col[1]*.9; lCol[lo+2] = .45 + col[2]*.9; lCol[lo+3] = lCol[lo+4] = lCol[lo+5] = 0;
      } else { pos[o] = pos[o+1] = 0; pos[o+2] = -99; lPos.fill(0, lo, lo+6); lCol.fill(0, lo, lo+6); }
    }
    const fade = inIntro ? ease((ip - .45)/.5) : 1, g = lg*(1 + lvl*.7)*fade, cr = col[0]*g, cg = col[1]*g, cb = col[2]*g;
    for (let p = 0; p < M0; p++) {
      const a = pairs[p][0]*3, b = pairs[p][1]*3, o = p*6, dx = pos[a]-pos[b], dy = pos[a+1]-pos[b+1], dz = pos[a+2]-pos[b+2];
      let al = 1 - Math.sqrt(dx*dx+dy*dy+dz*dz)/LM[p]; al = al > 0 ? al : 0;
      lPos[o]=pos[a]; lPos[o+1]=pos[a+1]; lPos[o+2]=pos[a+2]; lPos[o+3]=pos[b]; lPos[o+4]=pos[b+1]; lPos[o+5]=pos[b+2];
      const u = al*LU[p*2], v = al*LU[p*2+1];
      lCol[o]=cr*u; lCol[o+1]=cg*u; lCol[o+2]=cb*u; lCol[o+3]=cr*v; lCol[o+4]=cg*v; lCol[o+5]=cb*v;
    }

    // ---------- draw ----------
    gl.viewport(0, 0, W, H); gl.clearColor(0,0,0,1); gl.clear(gl.COLOR_BUFFER_BIT);
    gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE);
    const f = 2.414, F = W > H ? [f*H/W, f] : [f, f*W/H], Z = 4.2;
    const flash = inIntro ? Math.max(0, 1 - Math.abs(ip - 1)*5) : 0;     // core flash when the intro lands
    gl.useProgram(GW.p); attr(GW, 'q', bQuad, 2);
    gl.uniform3fv(GW.u.uC, col); gl.uniform1f(GW.u.uG, (gg*(.7 + lvl*.6) + flash*.8)*fade); gl.uniform1f(GW.u.uR, st === 2 ? .35 : .9);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4); off(GW);
    gl.bindBuffer(gl.ARRAY_BUFFER, bPos); gl.bufferSubData(gl.ARRAY_BUFFER, 0, pos);
    gl.useProgram(MI.p); attr(MI, 'p', bPos, 3); attr(MI, 'm', bMist, 1);
    gl.uniform2fv(MI.u.uF, F); gl.uniform1f(MI.u.uZ, Z); gl.uniform1f(MI.u.uPx, pxScale); gl.uniform3fv(MI.u.uC, col); gl.uniform1f(MI.u.uG, mg*(1 + lvl*.6)*fade);
    gl.drawArrays(gl.POINTS, 0, NN); off(MI);
    gl.bindBuffer(gl.ARRAY_BUFFER, bLPos); gl.bufferSubData(gl.ARRAY_BUFFER, 0, lPos);
    gl.bindBuffer(gl.ARRAY_BUFFER, bLCol); gl.bufferSubData(gl.ARRAY_BUFFER, 0, lCol);
    gl.useProgram(LN.p); attr(LN, 'p', bLPos, 3); attr(LN, 'c', bLCol, 3); gl.uniform2fv(LN.u.uF, F); gl.uniform1f(LN.u.uZ, Z);
    if (fade > 0) gl.drawArrays(gl.LINES, 0, M*2); off(LN);
    gl.useProgram(PT.p); attr(PT, 'p', bPos, 3); attr(PT, 's', bSize, 1); attr(PT, 'ph', bPh, 1); attr(PT, 'ac', bAc, 1); gl.bindBuffer(gl.ARRAY_BUFFER, bFire); gl.bufferSubData(gl.ARRAY_BUFFER, 0, fire); attr(PT, 'fi', bFire, 1);
    gl.uniform2fv(PT.u.uF, F); gl.uniform1f(PT.u.uZ, Z); gl.uniform1f(PT.u.uPx, pxScale); gl.uniform1f(PT.u.uT, t);
    gl.uniform3fv(PT.u.uC, col); gl.uniform3fv(PT.u.uA, A3); gl.uniform1f(PT.u.uG, pg*(1 + lvl*.5));
    gl.drawArrays(gl.POINTS, 0, N); off(PT);
    api.ms += (performance.now() - w0 - api.ms)*.05;                    // average CPU time per frame
  }
  requestAnimationFrame(frame);

  const api = {
    nodes: N, links: M, ms: 0, canvas: cv,
    setFps(n) { FPS = n || 60; },
    setState(s) { const i = SI[s] != null ? SI[s] : s; if (CFG[i]) { st = i; const c = COLS[Object.keys(SI)[i]]; for (let k = 0; k < 3; k++) tcol[k] = c[k]/255; } },
    setLevel(v) { ext = v; extUntil = performance.now() + 300; },
    intro(sec) { introLen = sec || 2.4; introT = 0; },
    destroy() { alive = false; ro.disconnect(); const x = gl.getExtension('WEBGL_lose_context'); if (x) x.loseContext(); }
  };
  return api;
}
window.JarvisBrain = JarvisBrain;
})();
