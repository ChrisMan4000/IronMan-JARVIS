/* hud-brain.js - Jarvis vortex brain (plain WebGL + one 2D ink canvas, no libraries).
   const b = JarvisBrain(canvas, {detail: 1, fps: 30});
   b.setState('idle'|'listening'|'thinking'|'speaking');  b.setLevel(0..1);  b.intro(seconds);  b.destroy();
   Canvas is black + opaque: put it over the HUD with CSS mix-blend-mode: screen (black = see-through).

   How it works (the way the old Geiss visualiser did it): every step the last picture is warped (spin + pull)
   and faded, then fresh "ink" is drawn on top: the voice wave, a beating two-lobed core, nerve fibres, dust.
   The pull goes inward (black-hole tunnel) and turns outward while speaking. The engine runs 120 steps per
   second whatever the screen rate is. intro() builds the brain out of single pixels sucked in from the window. */
(function () {
'use strict';
const COLS = {idle:[60,190,235], listening:[110,215,190], thinking:[235,160,95], speaking:[110,200,235]};   // HUD FDC palette
const ACCS = {idle:[235,160,95], listening:[235,160,95], thinking:[60,190,235], speaking:[235,160,95]};     // second ink colour
const SPD  = {idle:.6, listening:.9, thinking:1.7, speaking:1};                                             // spin speed
const HZ = 120, TAU = Math.PI*2, WH = [255,255,255];
const rgba = (c, a) => 'rgba('+(c[0]|0)+','+(c[1]|0)+','+(c[2]|0)+','+a+')';
const ss = (a, b, x) => { x = Math.max(0, Math.min(1, (x-a)/(b-a))); return x*x*(3-2*x); };

const VS = 'attribute vec2 p;varying vec2 v;void main(){v=p*.5+.5;gl_Position=vec4(p,0.,1.);}';
const FB = S => 'precision highp float;varying vec2 v;uniform sampler2D prev,ink;uniform float t,lvl,spd,th,pull,dir;uniform vec3 dec;'+
 'mat2 rot(float x){float s=sin(x),k=cos(x);return mat2(k,-s,s,k);}'+
 'void main(){vec2 c=v-.5;float r=length(c);'+
 'float n1=sin(c.x*7.+t*.5)+sin(c.y*9.-t*.4)+sin((c.x+c.y)*5.+t*.3);'+                 // uneven current instead of clean rings
 'float n2=sin(c.x*11.-t*.6)+sin(c.y*6.+t*.35);'+
 'float fd=1.-.02*smoothstep(.2,.49,r)-.05*max(dir,0.)*smoothstep(.07,0.,r);'+         // rim fades, core swallows light while pulling in
 'c=rot((.015*spd+th*(.012+.012*sin(t*2.6))+.004*spd/(r*6.+.25))*(1.+.3*n1))*c;'+      // spin, faster near the centre, surging while thinking
 'c*=1.+dir*(pull*(1.+.25*n2)+.003*lvl)+th*.003*sin(t*3.1+n1);'+                       // dir 1 = pull inward, -1 = push outward (speaking)
 'c+=.0014*vec2(sin(c.y*11.+t*.7)+sin(c.y*23.-t),cos(c.x*13.-t*.6)+cos(c.x*19.+t*.8));'+
 'vec2 w=c+.5;vec2 e=vec2(1./'+S+'.,0.);'+
 'vec3 p=texture2D(prev,w).rgb*.8+(texture2D(prev,w+e.xy).rgb+texture2D(prev,w-e.xy).rgb+texture2D(prev,w+e.yx).rgb+texture2D(prev,w-e.yx).rgb)*.05;'+
 'p*=step(0.,w.x)*step(w.x,1.)*step(0.,w.y)*step(w.y,1.);'+
 'gl_FragColor=vec4(max(p*dec*fd-.0022,0.)+texture2D(ink,v).rgb,1.);}';
const SHOW = 'precision highp float;varying vec2 v;uniform sampler2D buf;uniform vec3 col;uniform float lvl,th,ii;'+
 'void main(){float r=length(v-.5);vec3 k=pow(texture2D(buf,v).rgb,vec3(.85));'+
 'k*=1.+(.4+.6*lvl)*smoothstep(.2,0.,r);'+                                             // hotter centre
 'k+=mix(col,vec3(1.),.5)*(.06+.16*lvl+.06*th)*exp(-r*r*900.)*ii;'+
 'k*=mix(1.,smoothstep(.5,.2,r),.4)*smoothstep(.5,.44,r);'+                            // soft outer edge, black at the canvas border
 'gl_FragColor=vec4(k,1.);}';

window.JarvisBrain = function (cv, opt) {
  opt = opt || {};
  const detail = opt.detail == null ? 1 : opt.detail, S = detail >= 1 ? 768 : 512, Z = S/768;
  cv.width = cv.height = S;
  const gl = cv.getContext('webgl', {alpha:false, antialias:false});
  if (!gl) return null;
  let fb, show, U = {}, US = {};
  try {
    const prog = fs => { const p = gl.createProgram();
      [[gl.VERTEX_SHADER,VS],[gl.FRAGMENT_SHADER,fs]].forEach(([ty,src]) => { const s = gl.createShader(ty); gl.shaderSource(s,src); gl.compileShader(s);
        if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s)); gl.attachShader(p, s); });
      gl.bindAttribLocation(p,0,'p'); gl.linkProgram(p); return p; };
    fb = prog(FB(S)); show = prog(SHOW);
  } catch (e) { return null; }
  ['prev','ink','t','lvl','spd','th','pull','dir','dec'].forEach(n => U[n] = gl.getUniformLocation(fb,n));
  ['buf','col','lvl','th','ii'].forEach(n => US[n] = gl.getUniformLocation(show,n));
  const tex = () => { const x = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D,x);
    gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,S,S,0,gl.RGBA,gl.UNSIGNED_BYTE,null);
    gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR); gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE); return x; };
  const ic = document.createElement('canvas'); ic.width = ic.height = S; const g = ic.getContext('2d');
  gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1,1,-1,-1,1,1,1]), gl.STATIC_DRAW);
  gl.enableVertexAttribArray(0); gl.vertexAttribPointer(0,2,gl.FLOAT,false,0,0);
  const T = [tex(),tex()], F = [], inkT = tex(); let cur = 0;
  const clearAll = () => { for (let j = 0; j < 2; j++) { gl.bindFramebuffer(gl.FRAMEBUFFER,F[j]); gl.clear(gl.COLOR_BUFFER_BIT); } };
  for (let j = 0; j < 2; j++) { const f = gl.createFramebuffer(); gl.bindFramebuffer(gl.FRAMEBUFFER,f);
    gl.framebufferTexture2D(gl.FRAMEBUFFER,gl.COLOR_ATTACHMENT0,gl.TEXTURE_2D,T[j],0); F.push(f); }
  gl.clearColor(0,0,0,1); clearAll();
  gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL,true); gl.viewport(0,0,S,S);

  // ---------- state ----------
  let state = 'idle', level = 0, fps = opt.fps > 15 ? 120 : (opt.fps || 30);
  let t = 0, lvl = .1, th = 0, spk = 0, hb = 0, hbp = 0, ang = 0, act = 0, rotF = 0, dustK = 1;
  const cc = COLS.idle.slice(), ca = ACCS.idle.slice();                                 // current colours, eased on state change
  // intro: ti = seconds since the build started (in "full length" time, K stretches it); I1 core+lobes, I3 wave, I4 fibres
  let ti = 99, K = 1, I1 = 1, I3 = 1, I4 = 1, IG = 0, PT = null, PTN = [1,1,1,1], arr = [0,0,0,0], ov = null, og = null;
  const inbox = [];
  // nerve fibres growing out of the core
  const FI = []; for (let i = 0; i < 14; i++) FI.push({a0:i*TAU/14+(Math.random()-.5)*.3, ph:Math.random()*TAU, ph2:Math.random()*TAU, sp:.3+Math.random()*.4, L:.13+Math.random()*.1});
  const W = (x, k) => Math.sin(x*7+t*3+k)*.5+Math.sin(x*17-t*5+k*2.3)*.3+Math.sin(x*41+t*9+k*4.1)*.2+(Math.random()-.5)*.1;
  const bend = x => S*(.045*Math.sin(x*3.1+t*.35)+.028*Math.sin(x*6.3-t*.5))*Math.sin(x*Math.PI);   // the wave bends like a nerve
  const fibre = (c, f) => { const a = c.a0+rotF+f*(.5*Math.sin(c.ph+t*.22)+.25*Math.sin(f*4+c.ph2-t*.35)), rr = S*(.02+c.L*(1+.5*lvl+.3*th)*f);
    return [S/2+Math.cos(a)*rr, S/2+Math.sin(a)*rr]; };
  const speck = (x, y, z, style) => { g.fillStyle = style; g.fillRect(x-z/2, y-z/2, z, z); };

  // ---------- one 1/120 s step of the simulation (no drawing) ----------
  function sim() {
    t += 1/HZ;
    let tg;
    if (state === 'idle') tg = Math.max(level, .08+.04*Math.sin(t*.8));
    else if (state === 'thinking') tg = Math.max(level, .26+.2*Math.sin(t*2.2)+.4*Math.pow(Math.abs(Math.sin(t*.9)),8));
    else tg = .1+.9*level;                                                              // listening = microphone, speaking = Jarvis audio
    lvl += (tg-lvl)*.18;
    th += ((state === 'thinking' ? 1 : 0)-th)*.02;
    spk += ((state === 'speaking' ? 1 : 0)-spk)*.03;
    dustK += ((state === 'idle' ? .12 : 1)-dustK)*.02;
    hbp = (hbp+(1+.8*th)/HZ)%1; hb = Math.exp(-hbp*9)+.6*Math.exp(-Math.pow(hbp-.28,2)*90);   // heartbeat, faster while thinking
    ang += th*.009; if (th < .05) ang = (ang%Math.PI)*.985;                             // wave turns while thinking, settles flat after
    act += (.25+1.6*lvl+1.2*th)/HZ; rotF += .0012*SPD[state];
    for (let i = 0; i < 3; i++) { cc[i] += (COLS[state][i]-cc[i])*.03; ca[i] += (ACCS[state][i]-ca[i])*.03; }
    if (PT) { ti += 1/HZ/K; IG = (1-ss(2.2,4.8,ti))*ss(0,.6,ti);                        // each part only shines as much as its pixels have arrived
      I1 += (arr[0]/PTN[0]-I1)*.04; I3 += (arr[1]/PTN[1]-I3)*.04; I4 += (arr[2]/PTN[2]-I4)*.04; }
  }

  // ---------- fresh ink for this frame ----------
  function drawInk() {
    let i, j, k, x, e, boost, amp, c, f, P, pf, gr, rr, al, R;
    g.globalCompositeOperation = 'source-over'; g.fillStyle = '#000'; g.fillRect(0,0,S,S);
    g.globalCompositeOperation = 'lighter'; g.lineJoin = 'round';
    // voice wave through the core
    g.save(); g.translate(S/2,S/2); g.rotate(ang);
    for (k = 0; k < 3; k++) { g.beginPath();
      for (i = 0; i <= 120; i++) { x = i/120; e = Math.pow(Math.sin(x*Math.PI),1.5); boost = 1+1.1*Math.exp(-Math.pow((x-.5)/.11,2));
        amp = S*(.012+.1*lvl)*e*boost*(k === 2 ? 1.5 : 1);
        if (i) g.lineTo(S*.72*(x-.5), bend(x)+W(x,k*3)*amp*I3); else g.moveTo(S*.72*(x-.5), bend(x)+W(x,k*3)*amp*I3); }
      c = k === 0 ? WH : (k === 1 ? ca : cc); al = (k === 0 ? .5 : .3)*I3;
      gr = g.createLinearGradient(-S*.36,0,S*.36,0);
      gr.addColorStop(0,rgba(c,0)); gr.addColorStop(.3,rgba(c,al*.6)); gr.addColorStop(.5,rgba(c,al)); gr.addColorStop(.7,rgba(c,al*.6)); gr.addColorStop(1,rgba(c,0));
      g.strokeStyle = gr; g.lineWidth = (k === 0 ? 1.3 : 1)*Z; g.stroke(); }
    g.restore();
    // hot core
    R = S*(.035+.07*lvl+.02*th); al = (.007+.028*lvl+.01*th+.014*hb)*I1;
    gr = g.createRadialGradient(S/2,S/2,0,S/2,S/2,R);
    gr.addColorStop(0,'rgba(255,255,255,'+al+')'); gr.addColorStop(.35,rgba(cc,al*.6)); gr.addColorStop(1,'rgba(0,0,0,0)');
    g.fillStyle = gr; g.fillRect(S/2-R,S/2-R,R*2,R*2);
    // intro pixels that just arrived become part of the brain
    for (i = 0; i < inbox.length; i += 2) speck(inbox[i], inbox[i+1], 1.4*Z, 'rgba(255,255,255,.95)'); inbox.length = 0;
    // dust that falls in (far less while idle)
    const nd = Math.floor(5*dustK*ss(5.4,6.6,ti)+Math.random());
    for (i = 0; i < nd; i++) { const da = Math.random()*TAU, dr = S*(.14+Math.random()*.34); speck(S/2+Math.cos(da)*dr, S/2+Math.sin(da)*dr, 2*Z, i%3 ? rgba(cc,.7) : 'rgba(255,255,255,.7)'); }
    // two soft lobes that beat
    for (k = -1; k <= 1; k += 2) { x = S/2+k*S*(.045+.01*hb); const y = S/2+S*.008*Math.sin(t*.5+k); rr = S*(.085+.02*hb+.03*lvl);
      gr = g.createRadialGradient(x,y,0,x,y,rr); gr.addColorStop(0,rgba(cc,(.012+.012*hb)*I1)); gr.addColorStop(1,rgba(cc,0)); g.fillStyle = gr; g.fillRect(x-rr,y-rr,rr*2,rr*2); }
    // fibres: smooth curves with a short bright stretch travelling along each one (inward, or outward while speaking)
    g.lineWidth = 1.2*Z;
    for (i = 0; i < FI.length; i++) { c = FI[i]; pf = (act*c.sp+c.ph)%1.6; if (spk < .5) pf = 1.25-pf;
      P = []; for (j = 0; j <= 24; j++) { f = fibre(c, j/24); P.push(f[0], f[1]); }
      g.beginPath(); g.moveTo(P[0],P[1]); for (j = 1; j <= 24; j++) g.lineTo(P[j*2],P[j*2+1]); g.strokeStyle = rgba(i%4 ? cc : ca, .035*I4); g.stroke();
      k = Math.round(pf*24);
      if (I4 > .9 && k >= 1 && k <= 22) { g.beginPath(); g.moveTo(P[k*2-2],P[k*2-1]); g.lineTo(P[k*2],P[k*2+1]); g.lineTo(P[k*2+2],P[k*2+3]); g.lineTo(P[k*2+4],P[k*2+5]);
        g.strokeStyle = 'rgba(255,255,255,'+(.05+.12*lvl+.08*th)+')'; g.stroke(); } }
  }

  // ---------- intro: faint 1 px pixels all over the window, sucked in at random, each landing on its own spot ----------
  // group 0 core+lobes, 1 voice wave, 2 nerve fibres, 3 soft body
  function target(p) {
    if (p.g === 1) { const x = p.p1, px = S*.72*(x-.5), bd = bend(x); return [S/2+px*Math.cos(ang)-bd*Math.sin(ang), S/2+px*Math.sin(ang)+bd*Math.cos(ang)]; }
    if (p.g === 2) return fibre(FI[p.p1], p.p2);
    return [S/2+p.p1*S, S/2+p.p2*S];
  }
  function endIntro() { if (ov) ov.remove(); ov = og = PT = null; ti = 99; I1 = I3 = I4 = 1; IG = 0; }
  function intro(sec) {
    endIntro();
    K = Math.max(4, Math.min(7, sec || 6.6))/6.6; ti = 0; I1 = I3 = I4 = 0; arr = [0,0,0,0]; inbox.length = 0; clearAll();
    ov = document.createElement('canvas'); ov.style.cssText = 'position:fixed;left:0;top:0;width:100vw;height:100vh;pointer-events:none;z-index:102';
    ov.width = window.innerWidth; ov.height = window.innerHeight; document.body.appendChild(ov); og = ov.getContext('2d');
    const N = Math.round(Math.max(1500, Math.min(9000, ov.width*ov.height/900))*(detail >= 1 ? 1 : .5));
    PT = []; PTN = [0,0,0,0];
    const r3 = () => Math.random()+Math.random()+Math.random()-1.5;
    for (let i = 0; i < N; i++) { const q = Math.random(), gp = q < .24 ? 0 : q < .56 ? 1 : q < .88 ? 2 : 3, r = .03+.15*Math.sqrt(Math.random()), a = Math.random()*TAU; PTN[gp]++;
      PT.push({sx:Math.random()*ov.width, sy:Math.random()*ov.height, g:gp,
        p1: gp === 0 ? r3()*.07 : gp === 1 ? .5+(Math.random()+Math.random()-1)*.5 : gp === 2 ? Math.floor(Math.random()*FI.length) : Math.cos(a)*r,
        p2: gp === 0 ? r3()*.055 : gp === 2 ? Math.random() : Math.sin(a)*r,
        d:.5+Math.random()*3.6, du:1+Math.random()*1.1, cu:(Math.random()-.5)*.55, done:false}); }
    for (let k = 0; k < 4; k++) if (!PTN[k]) PTN[k] = 1;
  }
  function drawPT() {
    if (!PT) return;
    og.clearRect(0,0,ov.width,ov.height);
    if (ti > 6.6) { endIntro(); return; }
    const rc = cv.getBoundingClientRect(), fin = ss(0,.6,ti);
    for (let i = 0; i < PT.length; i++) { const p = PT[i]; if (p.done) continue; const u = (ti-p.d)/p.du;
      if (u < 0) { og.fillStyle = rgba(cc,.07*fin); og.fillRect(p.sx,p.sy,1,1); continue; }                 // far out: barely visible
      const T2 = target(p);
      if (u >= 1) { p.done = true; inbox.push(T2[0],T2[1]); arr[p.g]++; continue; }
      const e = u*u*u, dx = rc.left+T2[0]/S*rc.width-p.sx, dy = rc.top+T2[1]/S*rc.height-p.sy, w = Math.sin(u*Math.PI)*p.cu*(1-e);
      og.fillStyle = rgba(cc,.07+.93*e); og.fillRect(p.sx+dx*e-dy*w, p.sy+dy*e+dx*w, 1, 1); }                // lights up as it closes in; always 1 px
  }

  // ---------- frame loop ----------
  let raf = 0, last = 0, acc = 0, dead = false;
  const api = {nodes: FI.length, links: 0, ms: 0, canvas: cv,
    setFps: f => { fps = f > 15 ? 120 : (f || 30); },          // GPU machines: screen rate (up to 120); no-GPU machines keep the HUD's low cap
    setState: s => { if (COLS[s]) state = s; },
    setLevel: v => { level = Math.max(0, Math.min(1, +v || 0)); },
    intro, destroy: () => { dead = true; cancelAnimationFrame(raf); endIntro(); }};
  function frame(ms) {
    if (dead) return; raf = requestAnimationFrame(frame);
    const dt = Math.min(.1, (ms-last)/1000); if (dt < 1/fps-.002) return; last = ms;
    acc += dt*HZ; let n = Math.min(6, Math.floor(acc)); acc -= n; if (acc > 6) acc = 0; if (n < 1) return;
    const t0 = performance.now(), mx = Math.max(cc[0],cc[1],cc[2]), D = .986;
    for (let i = 0; i < n; i++) sim();
    drawInk();
    gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D,inkT); gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,ic);
    gl.useProgram(fb); gl.uniform1i(U.prev,0); gl.uniform1i(U.ink,1);
    gl.uniform1f(U.t,t); gl.uniform1f(U.lvl,lvl); gl.uniform1f(U.spd,SPD[state]); gl.uniform1f(U.th,th);
    gl.uniform1f(U.pull,.0062*(1+.6*IG)); gl.uniform1f(U.dir,1-2*spk);
    gl.uniform3f(U.dec, D-(1-cc[0]/mx)*.0225, D-(1-cc[1]/mx)*.0225, D-(1-cc[2]/mx)*.0225);    // trails age into the state colour
    gl.activeTexture(gl.TEXTURE0);
    for (let i = 0; i < n; i++) { gl.bindTexture(gl.TEXTURE_2D,T[cur]); gl.bindFramebuffer(gl.FRAMEBUFFER,F[1-cur]); gl.drawArrays(gl.TRIANGLE_STRIP,0,4); cur = 1-cur; }
    gl.bindFramebuffer(gl.FRAMEBUFFER,null); gl.bindTexture(gl.TEXTURE_2D,T[cur]); gl.useProgram(show);
    gl.uniform1i(US.buf,0); gl.uniform3f(US.col,cc[0]/255,cc[1]/255,cc[2]/255); gl.uniform1f(US.lvl,lvl); gl.uniform1f(US.th,th); gl.uniform1f(US.ii,I1);
    gl.drawArrays(gl.TRIANGLE_STRIP,0,4);
    drawPT();
    api.ms = performance.now()-t0;
  }
  cv.addEventListener('webglcontextlost', e => { e.preventDefault(); dead = true; cancelAnimationFrame(raf); endIntro(); });
  raf = requestAnimationFrame(ms => { last = ms; raf = requestAnimationFrame(frame); });
  return api;
};
})();
