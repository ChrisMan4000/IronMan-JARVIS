/* IronMan J.A.R.V.I.S. HUD settings panel (gear top left). Settings live in
   window.HUDS, a copy in localStorage 'jvHudS' (read before the HUD starts) and the
   real file ~/.openjarvis/hud-settings.json through /v1/speech/hud-settings. */
(function () {
  'use strict';
  const DEF = { fps: 30, brain: 'HIGH', wear: true, compact: false, intro: true, voice: '', speed: 1, vol: 100,
    exaggeration: 0.5, temperature: 0.6, wake: true, stt_language: 'auto', mic: '', tokens: false, conf: true,
    reply_language: 'auto', tts_language: 'auto', tts_model: 'v3' };
  const S = window.HUDS = Object.assign({}, DEF, window.HUDS || {});
  const LANGS = { ar: 'Arabic', da: 'Danish', de: 'German', el: 'Greek', en: 'English', es: 'Spanish', fi: 'Finnish', fr: 'French',
    he: 'Hebrew', hi: 'Hindi', it: 'Italian', ja: 'Japanese', ko: 'Korean', ms: 'Malay', nl: 'Dutch', no: 'Norwegian', pl: 'Polish',
    pt: 'Portuguese', ru: 'Russian', sv: 'Swedish', sw: 'Swahili', tr: 'Turkish', zh: 'Chinese' };
  const NAME = c => LANGS[c] || ({ uk: 'Ukrainian', cs: 'Czech', ro: 'Romanian', hu: 'Hungarian', id: 'Indonesian', vi: 'Vietnamese', th: 'Thai', fa: 'Persian' })[c] || c;
  let tSave = 0;
  function save() {
    try { localStorage.setItem('jvHudS', JSON.stringify(S)) } catch (e) { /* private mode */ }
    clearTimeout(tSave);
    tSave = setTimeout(() => {
      fetch('/v1/speech/hud-settings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(S) })
        .then(r => flash(r.ok ? 'SAVED · KEPT AFTER RESTART' : 'NOT SAVED (server)')).catch(() => flash('NOT SAVED (server offline)'));
    }, 300);
  }
  function flash(t) { const s = document.getElementById('jvsSaved'); if (s) { s.textContent = t; s.classList.add('on'); setTimeout(() => s.classList.remove('on'), 900) } }

  /* ---------- hooks used by hud.html ---------- */
  const voiceLang = () => (window.jvAskLang && Date.now() - (window.jvAskT || 0) < 90000) ? window.jvAskLang : null;   // language of the last spoken question (90 s)
  window.jvLangHint = function () {
    if (S.reply_language === 'en') return ' Always reply in English.';
    const l = voiceLang();
    if (l && l !== 'en') return ' The user spoke ' + NAME(l) + '. Reply in ' + NAME(l) + ' (keep the NN% confidence start).';
    return ' Reply in the same language the user used.';
  };
  window.jvSpeakLang = function (text) {
    if (S.tts_language && S.tts_language !== 'auto') return S.tts_language;
    if (S.reply_language === 'en') return 'en';
    const l = voiceLang();
    if (l && l !== 'en' && l !== 'de') return LANGS[l] ? l : 'en';
    const w = (' ' + String(text).toLowerCase() + ' ');   // typed question: German or English by common words
    const de = (w.match(/\s(der|die|das|und|ist|nicht|ich|sie|ein|eine|zu|mit|auf|für|es|sind|wird|heute)\s/g) || []).length;
    const en = (w.match(/\s(the|and|is|not|you|a|to|with|on|for|it|are|will|today|of)\s/g) || []).length;
    return de > en ? 'de' : 'en';
  };
  let tokEl = null, tokT = 0;
  window.jvTok = function (u, ms) {
    if (!S.tokens || !u) { if (tokEl) tokEl.style.display = 'none'; return }
    const log = document.getElementById('log'); if (!log) return;
    if (!tokEl) { tokEl = document.createElement('div'); tokEl.id = 'jvTok'; document.body.appendChild(tokEl) }
    const n = u.completion_tokens || 0, all = u.total_tokens || (n + (u.prompt_tokens || 0)), tps = ms > 0 ? n / (ms / 1000) : 0;
    const t0 = performance.now(); cancelAnimationFrame(tokT); tokEl.style.display = 'block';
    const place = () => { const r = log.getBoundingClientRect(); tokEl.style.left = (r.right - tokEl.offsetWidth - 10) + 'px'; tokEl.style.top = (r.bottom - tokEl.offsetHeight - 8) + 'px' };
    const step = () => { const k = Math.min(1, (performance.now() - t0) / 700), e = 1 - Math.pow(1 - k, 3);
      tokEl.innerHTML = '<b>' + Math.round(n * e) + '</b> tok · <b>' + Math.round(tps * e) + '</b> tok/s · ctx <b>' + Math.round(all * e).toLocaleString('en') + '</b>';
      place(); if (k < 1) tokT = requestAnimationFrame(step) };
    step();
  };

  /* ---------- rugged box (same look as the HUD boxes, style E) ---------- */
  const C = 'rgb(60,190,235)', R = Math.random;
  function rug(el) {
    let c = el.querySelector(':scope>canvas.jvbx'); if (!c) { c = document.createElement('canvas'); c.className = 'jvbx'; el.prepend(c) }
    const W = el.offsetWidth, H = el.offsetHeight, d = devicePixelRatio || 1; if (!W || !H) return;
    c.width = W * d; c.height = H * d; const x = c.getContext('2d'); x.scale(d, d);
    const cs = Math.min(12, H / 4), P = o => [[cs + o, o], [W - o, o], [W - o, H - cs - o], [W - cs - o, H - o], [o, H - o], [o, cs + o]];
    const poly = p => { x.beginPath(); p.forEach((q, i) => i ? x.lineTo(q[0], q[1]) : x.moveTo(q[0], q[1])); x.closePath() };
    poly(P(1)); let g = x.createLinearGradient(0, 0, 0, H); g.addColorStop(0, 'rgba(16,36,50,.94)'); g.addColorStop(1, 'rgba(4,11,17,.96)'); x.fillStyle = g; x.fill();
    x.save(); x.clip(); g = x.createLinearGradient(0, 0, 0, H * .35); g.addColorStop(0, 'rgba(255,255,255,.05)'); g.addColorStop(1, 'rgba(255,255,255,0)'); x.fillStyle = g; x.fillRect(0, 0, W, H * .35);
    x.fillStyle = 'rgba(255,255,255,.025)'; for (let y = 0; y < H; y += 3) x.fillRect(0, y, W, 1);
    for (let i = 0, n = W * H / 260; i < n; i++) { x.fillStyle = R() < .5 ? 'rgba(200,235,255,' + (R() * .1) + ')' : 'rgba(0,0,0,' + (R() * .25) + ')'; x.fillRect(R() * W, R() * H, R() * 1.6, R() * 1.6) }
    for (let i = 0, n = R() * 3 | 0; i <= n; i++) { const sx = R() * W, sy = R() * H, r = 20 + R() * 60, s = x.createRadialGradient(sx, sy, 0, sx, sy, r); s.addColorStop(0, 'rgba(150,190,210,.05)'); s.addColorStop(1, 'rgba(0,0,0,0)'); x.fillStyle = s; x.fillRect(sx - r, sy - r, 2 * r, 2 * r) }
    x.strokeStyle = 'rgba(190,225,240,.12)'; x.lineWidth = .6; for (let i = 0, n = R() * 3 | 0; i < n; i++) { const a = R() * W, b = R() * H, l = 15 + R() * 50, t = R() * 6.3; x.beginPath(); x.moveTo(a, b); x.lineTo(a + Math.cos(t) * l, b + Math.sin(t) * l * .3); x.stroke() }
    x.restore();
    x.lineWidth = 1; x.strokeStyle = 'rgba(255,255,255,.08)'; x.beginPath(); x.moveTo(3, H - 4); x.lineTo(3, cs + 3); x.lineTo(cs + 3, 3); x.lineTo(W - 4, 3); x.stroke();
    x.strokeStyle = 'rgba(0,0,0,.6)'; x.beginPath(); x.moveTo(W - 3, 4); x.lineTo(W - 3, H - cs - 3); x.lineTo(W - cs - 3, H - 3); x.lineTo(4, H - 3); x.stroke();
    x.strokeStyle = 'rgba(60,190,235,.16)'; x.save(); x.translate(3, -2); poly(P(1)); x.stroke(); x.restore();
    x.strokeStyle = C; x.globalAlpha = .85; x.lineWidth = 1.1; const p = P(.5);
    for (let i = 0; i < p.length; i++) { const a = p[i], b = p[(i + 1) % p.length], L = Math.hypot(b[0] - a[0], b[1] - a[1]), n = Math.max(1, L / 7 | 0); x.beginPath(); let pen = 0;
      for (let k = 0; k <= n; k++) { const t = k / n, px = a[0] + (b[0] - a[0]) * t + (R() - .5) * .9, py = a[1] + (b[1] - a[1]) * t + (R() - .5) * .9; if (R() < .03 && k) { pen = 0; continue } pen ? x.lineTo(px, py) : x.moveTo(px, py); pen = 1 } x.stroke() }
    x.globalAlpha = .22; poly(P(5)); x.stroke(); x.globalAlpha = 1;
    if (H > 140) { x.fillStyle = 'rgba(60,190,235,.4)'; for (let y = cs + 14; y < H - cs - 10; y += 11) x.fillRect(6, y, y % 55 < 11 ? 6 : 3, 1) }
    if (W > 260 && H > 60) { x.fillStyle = 'rgba(60,190,235,.3)'; let bx = W - cs - 120; for (let i = 0; i < 34; i++) { const w = R() < .4 ? 2 : 1; x.fillRect(bx, H - 12, w, 6); bx += w + 1 + (R() * 2 | 0) }
      x.font = '7px Consolas'; x.fillStyle = 'rgba(60,190,235,.4)'; x.fillText('AOI-' + (1000 + R() * 9000 | 0) + ' // CFG', W - cs - 120, H - 16) }
  }
  const rugAll = () => document.querySelectorAll('.jvrug').forEach(rug);
  window.jvRug = rug;

  /* ---------- panel ---------- */
  const css = `
#jvGear{position:fixed;left:14px;top:12px;width:40px;height:40px;display:grid;place-items:center;cursor:pointer;z-index:60;color:rgb(60,190,235)}
#jvGear svg{width:22px;height:22px;transition:transform .6s}#jvGear:hover svg{transform:rotate(90deg)}#jvGear.on{color:#8fe6b8}
.jvrug{position:relative;isolation:isolate}.jvrug>canvas.jvbx{position:absolute;left:0;top:0;width:100%;height:100%;z-index:-1;pointer-events:none}
#jvSet,#jvFly{position:fixed;z-index:59;color:rgb(60,190,235);font:12px/1.4 Consolas,"Segoe UI Mono",monospace;letter-spacing:.06em;transition:opacity .25s,transform .25s}
#jvSet{left:14px;top:60px;width:520px}#jvFly{width:330px}
#jvSet.hide,#jvFly.hide{opacity:0;transform:translateX(-16px);pointer-events:none}
#jvSet .scr{max-height:calc(100vh - 80px);overflow:auto;padding:4px 6px 22px;scrollbar-width:thin;scrollbar-color:rgba(60,190,235,.35) transparent}
.jvph{display:flex;justify-content:space-between;align-items:baseline;padding:12px 14px 8px}.jvph h1{margin:0;font-size:14px;letter-spacing:.3em;font-weight:normal}.jvph small{opacity:.45;font-size:9px}
.jvln{height:1px;margin:0 14px;background:linear-gradient(90deg,rgb(60,190,235),transparent)}
.jvsec{padding:10px 14px 6px}.jvsec h2{margin:0 0 8px;font-size:10px;letter-spacing:.35em;font-weight:normal;color:rgb(235,160,95)}.jvsec h2:before{content:"// ";opacity:.6}
.jvv{display:grid;grid-template-columns:36px 1fr auto;gap:12px;align-items:center;padding:9px 13px;margin-bottom:6px;cursor:pointer}.jvv.sel{color:#8fe6b8}
.jvplay{width:34px;height:34px;border-radius:50%;border:1px solid currentColor;background:rgba(0,0,0,.3);color:inherit;cursor:pointer;font-size:11px}.jvplay.on{background:currentColor}.jvplay.on span{color:#02060a}
.jvvn{font-size:14px;letter-spacing:.22em}.jvvd{font-size:9px;opacity:.55;letter-spacing:.04em}
.jvwave{display:flex;gap:2px;height:12px;align-items:center;margin-top:3px}.jvwave i{width:3px;height:2px;background:currentColor;opacity:.35}
.playing .jvwave i{animation:jvwv .45s ease-in-out infinite alternate;opacity:.85}@keyframes jvwv{to{height:12px}}
.jvbadge{font-size:9px;padding:3px 7px;border:1px solid currentColor;opacity:.6}.sel .jvbadge{opacity:1}
.jvrow{display:grid;grid-template-columns:150px 1fr 54px;gap:12px;align-items:center;margin:7px 0}.jvrow label{font-size:11px;opacity:.85}.jvrow .val{text-align:right;font-size:10px;opacity:.7}
#jvSet input[type=range]{-webkit-appearance:none;appearance:none;width:100%;height:3px;background:rgba(60,190,235,.35);outline:none}
#jvSet input[type=range]::-moz-range-thumb{width:8px;height:16px;background:rgb(60,190,235);border:0;border-radius:0}
.jvseg{display:flex}.jvseg button{flex:1;padding:4px 0;border:1px solid rgba(60,190,235,.35);background:rgba(0,0,0,.25);color:rgb(60,190,235);font:inherit;font-size:10px;cursor:pointer;margin-left:-1px}.jvseg button.on{background:rgba(60,190,235,.75);color:#02060a}
.jvtg{width:42px;height:18px;border:1px solid rgba(60,190,235,.35);position:relative;cursor:pointer;justify-self:start;background:rgba(0,0,0,.3)}
.jvtg:after{content:"";position:absolute;top:3px;left:3px;width:10px;height:10px;background:rgba(60,190,235,.35);transition:.2s}.jvtg.on{border-color:#8fe6b8}.jvtg.on:after{left:27px;background:#8fe6b8}
#jvSet select,#jvFly select{width:100%;background:#061520;color:rgb(60,190,235);border:1px solid rgba(60,190,235,.35);font:inherit;font-size:10px;padding:3px}
.jvhint{font-size:9px;opacity:.45;margin:-3px 0 6px 162px}
.jvft{display:flex;justify-content:space-between;align-items:center;padding:10px 14px 4px}.jvft small{font-size:9px;opacity:.45;transition:.3s}.jvft small.on{opacity:1;color:#8fe6b8}
.jvbtn{padding:6px 14px;border:1px solid rgb(60,190,235);background:rgba(0,0,0,.3);color:rgb(60,190,235);font:inherit;font-size:10px;letter-spacing:.2em;cursor:pointer}
#jvLink{position:fixed;height:1px;background:linear-gradient(90deg,#8fe6b8,rgb(60,190,235));z-index:58;display:none}
#jvTok{position:fixed;z-index:30;display:none;padding:3px 8px;border:1px solid rgba(60,190,235,.35);background:rgba(0,0,0,.55);color:rgb(60,190,235);font:10px Consolas,monospace;font-variant-numeric:tabular-nums;pointer-events:none}#jvTok b{color:#cfeefa;font-weight:normal}`;
  const st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);
  const seg = (k, opts, lab) => '<div class="jvseg" data-k="' + k + '">' + opts.map((o, i) => '<button data-v="' + o + '">' + (lab ? lab[i] : o) + '</button>').join('') + '</div>';
  const tg = k => '<div class="jvtg" data-k="' + k + '"></div>';
  const rng = (k, min, max, f) => '<input type="range" data-k="' + k + '" data-f="' + f + '" min="' + min + '" max="' + max + '">';
  const row = (l, c, v) => '<div class="jvrow"><label>' + l + '</label>' + c + '<span class="val">' + (v || '') + '</span></div>';
  const hint = t => '<div class="jvhint">' + t + '</div>';
  const gear = document.createElement('div'); gear.id = 'jvGear'; gear.className = 'jvrug'; gear.title = 'Settings';
  gear.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="3.2"/><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M5.3 18.7l2.1-2.1M16.6 7.4l2.1-2.1"/><circle cx="12" cy="12" r="6.5"/></svg>';
  const pn = document.createElement('div'); pn.id = 'jvSet'; pn.className = 'jvrug hide';
  pn.innerHTML = '<div class="scr"><div class="jvph"><h1>SYSTEM SETTINGS</h1><small>J.A.R.V.I.S. // CFG</small></div><div class="jvln"></div>' +
    '<div class="jvsec"><h2>DISPLAY</h2>' + row('FRAME RATE', seg('fps', ['30', '60', '120']), 'FPS') + hint('Lower = faster voice replies (less GPU)') +
    row('BRAIN DETAIL', seg('brain', ['LOW', 'MED', 'HIGH'])) + hint('Applies after reload (F5)') + row('WORN LOOK', tg('wear')) + row('COMPACT MODE', tg('compact')) + hint('Off = automatic by screen shape') + row('INTRO ANIMATION', tg('intro')) + '</div>' +
    '<div class="jvsec"><h2>VOICE</h2><div id="jvMain"></div><div class="jvv jvrug" id="jvCb"><span style="font-size:15px;opacity:.7">&#9638;</span><div><div class="jvvn">CHATTERBOX</div><div class="jvvd" id="jvCbSub">More voices</div></div><span id="jvCbArr" style="font-size:15px;opacity:.7">&#9656;</span></div>' +
    row('SPEAKING PACE', rng('speed', 70, 130, 'x')) + row('VOICE VOLUME', rng('vol', 0, 100, '%')) + row('EXAGGERATION', rng('exaggeration', 25, 200, 'd')) + hint('Neutral = 0.5, extreme values can be unstable') +
    row('TEMPERATURE', rng('temperature', 5, 150, 'd')) + hint('0.6 = steady (Jarvis default) \u00b7 higher = more varied') + '</div>' +
    '<div class="jvsec"><h2>LISTENING</h2>' + row('WAKE WORD', tg('wake')) + row('RECOGNITION LANGUAGE', seg('stt_language', ['auto', 'en', 'de'], ['AUTO', 'EN', 'DE'])) + hint('Auto = detects any language you speak') +
    row('MICROPHONE', '<select data-k="mic" id="jvMic"><option value="">System default</option></select>') + '</div>' +
    '<div class="jvsec"><h2>CHAT</h2>' + row('SHOW TOKENS', tg('tokens')) + hint('Token counter, lower right of the chat box') + row('SHOW CONFIDENCE', tg('conf')) + hint('"95% confidence" in each reply') +
    row('REPLY LANGUAGE', seg('reply_language', ['auto', 'en'], ['SAME AS ME', 'ALWAYS EN'])) + '</div>' +
    '<div class="jvln"></div><div class="jvft"><small id="jvsSaved">SAVED \u00b7 KEPT AFTER RESTART</small><button class="jvbtn" id="jvReset">RESET</button></div></div>';
  const fly = document.createElement('div'); fly.id = 'jvFly'; fly.className = 'jvrug hide';
  fly.innerHTML = '<div class="jvph"><h1>CHATTERBOX</h1><small>VOICES</small></div><div class="jvln"></div><div class="jvsec"><div id="jvCbList"></div><div id="jvOwn"></div>' +
    '<div class="jvhint" style="margin:4px 0 6px">Add a voice: put a clean 10-20 s .wav of one speaker into C:\\Users\\&lt;you&gt;\\.openjarvis\\voices</div></div><div class="jvln"></div>' +
    '<div class="jvsec"><h2>MODEL</h2>' + row('VERSION', seg('tts_model', ['v3', 'v2', 'turbo'], ['MULTILINGUAL V3', 'V2', 'TURBO (EN)'])) + hint('Turbo: lighter and faster, English only') + '<h2 style="margin-top:10px">LANGUAGE</h2>' +
    row('VOICE LANGUAGE', '<select data-k="tts_language"><option value="auto">AUTO (same as reply)</option>' + Object.keys(LANGS).sort((a, b) => LANGS[a] < LANGS[b] ? -1 : 1).map(c => '<option value="' + c + '">' + LANGS[c] + '</option>').join('') + '</select>') +
    '<div class="jvhint" style="margin:2px 0 8px">23 languages built in, no packs needed. A language Chatterbox cannot speak is answered in that language, spoken with the English voice.</div></div>';
  const link = document.createElement('div'); link.id = 'jvLink';
  document.body.append(gear, pn, fly, link);

  /* ---------- controls ---------- */
  const fmt = r => { const v = +r.value; return r.dataset.f === 'x' ? (v / 100).toFixed(2) + 'x' : r.dataset.f === 'd' ? (v / 100).toFixed(2) : v + '%' };
  const toVal = r => r.dataset.f === '%' ? +r.value : +r.value / 100;
  const fromVal = (r, v) => r.dataset.f === '%' ? v : Math.round(v * 100);
  function sync() {
    pn.querySelectorAll('input[type=range]').forEach(r => { r.value = fromVal(r, S[r.dataset.k]); r.nextElementSibling.textContent = fmt(r) });
    document.querySelectorAll('#jvSet .jvseg,#jvFly .jvseg').forEach(s => s.querySelectorAll('button').forEach(b => b.classList.toggle('on', String(S[s.dataset.k]) === b.dataset.v)));
    pn.querySelectorAll('.jvtg').forEach(t => { t.classList.toggle('on', !!S[t.dataset.k]); const v = t.nextElementSibling; if (v) v.textContent = S[t.dataset.k] ? 'ON' : 'OFF' });
    document.querySelectorAll('#jvSet select,#jvFly select').forEach(s => { s.value = S[s.dataset.k] || s.options[0].value });
    document.querySelectorAll('.jvv[data-id]').forEach(v => { const on = v.dataset.id === S.voice; v.classList.toggle('sel', on); const b = v.querySelector('.jvbadge'); if (b) b.textContent = on ? 'ACTIVE' : 'SELECT' });
    const inCb = !!document.querySelector('#jvFly .jvv.sel'); document.getElementById('jvCb').classList.toggle('sel', inCb);
    const sel = document.querySelector('#jvFly .jvv.sel .jvvn'); document.getElementById('jvCbSub').textContent = inCb && sel ? 'Active: ' + sel.textContent : 'More voices · male and female';
  }
  const set = (k, v) => { S[k] = v; save(); sync(); apply(k) };
  pn.querySelectorAll('input[type=range]').forEach(r => { r.oninput = () => { r.nextElementSibling.textContent = fmt(r) }; r.onchange = () => set(r.dataset.k, toVal(r)) });
  document.querySelectorAll('#jvSet .jvseg,#jvFly .jvseg').forEach(s => s.querySelectorAll('button').forEach(b => b.onclick = () => set(s.dataset.k, s.dataset.k === 'fps' ? +b.dataset.v : b.dataset.v)));
  pn.querySelectorAll('.jvtg').forEach(t => t.onclick = () => set(t.dataset.k, !S[t.dataset.k]));
  document.querySelectorAll('#jvSet select,#jvFly select').forEach(s => s.onchange = () => set(s.dataset.k, s.value));
  document.getElementById('jvReset').onclick = () => { Object.keys(S).forEach(k => delete S[k]); Object.assign(S, DEF); save(); sync(); apply('all') };
  function apply(k) {
    if (k === 'tokens' && !S.tokens && document.getElementById('jvTok')) document.getElementById('jvTok').style.display = 'none';
    if (k === 'conf' || k === 'all') document.documentElement.classList.toggle('jvNoConf', S.conf === false);
  }
  const st2 = document.createElement('style'); st2.textContent = 'html.jvNoConf .jvConf{display:none}'; document.head.appendChild(st2);
  apply('conf');

  /* ---------- voices ---------- */
  let au = null, cur = null;
  const stopSample = () => { if (!au) return; au.pause(); cur.classList.remove('playing'); const b = cur.querySelector('.jvplay'); b.classList.remove('on'); b.firstChild.innerHTML = '&#9654;'; au = null; cur = null };
  function card(v) {
    const d = document.createElement('div'); d.className = 'jvv jvrug'; d.dataset.id = v.id;
    d.innerHTML = '<button class="jvplay"' + (v.sample ? '' : ' disabled style="opacity:.3"') + '><span>&#9654;</span></button><div><div class="jvvn"></div><div class="jvvd"></div><div class="jvwave">' + '<i></i>'.repeat(24) + '</div></div><span class="jvbadge">SELECT</span>';
    d.querySelector('.jvvn').textContent = v.label || v.id.toUpperCase(); d.querySelector('.jvvd').textContent = v.desc || '';
    d.querySelectorAll('.jvwave i').forEach(i => i.style.animationDelay = (R() * .45) + 's');
    d.querySelector('.jvplay').onclick = e => { e.stopPropagation(); const was = cur; stopSample(); if (was === d || !v.sample) return;
      au = new Audio('/v1/speech/voice-sample/' + encodeURIComponent(v.id)); au.volume = (S.vol ?? 100) / 100; cur = d; au.play().catch(() => {}); d.classList.add('playing');
      const b = d.querySelector('.jvplay'); b.classList.add('on'); b.firstChild.innerHTML = '&#9632;'; au.onended = stopSample };
    d.onclick = () => set('voice', v.id);
    return d;
  }
  fetch('/v1/speech/voices').then(r => r.json()).then(j => {
    const vs = j.voices || [], main = document.getElementById('jvMain'), cb = document.getElementById('jvCbList'), own = document.getElementById('jvOwn');
    vs.filter(v => v.group === 'main').forEach(v => main.appendChild(card(v)));
    vs.filter(v => v.group === 'chatterbox').forEach(v => cb.appendChild(card(v)));
    const o = vs.filter(v => v.group !== 'main' && v.group !== 'chatterbox');
    o.push({ id: 'default', label: 'BUILT-IN', desc: 'Chatterbox own voice', group: 'own', sample: true });
    if (o.length) { const h = document.createElement('h2'); h.textContent = 'OWN CLIPS'; h.style.margin = '10px 0 8px'; own.appendChild(h); o.forEach(v => own.appendChild(card(v))) }
    sync(); requestAnimationFrame(rugAll);
  }).catch(() => { document.getElementById('jvMain').textContent = 'Voice list not available (server offline?)' });
  function micList() { if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) return;
    navigator.mediaDevices.enumerateDevices().then(ds => { const s = document.getElementById('jvMic'); s.length = 1;
      ds.filter(d => d.kind === 'audioinput' && d.deviceId && d.deviceId !== 'default').forEach((d, i) => { const o = document.createElement('option'); o.value = d.deviceId; o.textContent = d.label || ('Microphone ' + (i + 1)); s.appendChild(o) }); sync() }).catch(() => {}) }

  /* ---------- open / close ---------- */
  const cbBtn = document.getElementById('jvCb');
  function place() { const r = cbBtn.getBoundingClientRect(), pr = pn.getBoundingClientRect(); fly.style.left = (pr.right + 24) + 'px';
    fly.style.top = Math.max(12, Math.min(r.top - 60, innerHeight - fly.offsetHeight - 12)) + 'px';
    link.style.left = r.right + 'px'; link.style.top = (r.top + r.height / 2) + 'px'; link.style.width = (pr.right + 24 - r.right) + 'px' }
  const flyOpen = o => { fly.classList.toggle('hide', !o); link.style.display = o ? 'block' : 'none'; document.getElementById('jvCbArr').innerHTML = o ? '&#9666;' : '&#9656;'; if (o) { place(); requestAnimationFrame(rugAll) } };
  cbBtn.onclick = () => flyOpen(fly.classList.contains('hide'));
  pn.querySelector('.scr').onscroll = () => { if (!fly.classList.contains('hide')) place() };
  gear.onclick = () => { const open = pn.classList.contains('hide'); pn.classList.toggle('hide', !open); gear.classList.toggle('on', open);
    if (open) { micList(); sync(); requestAnimationFrame(rugAll) } else { flyOpen(false); stopSample() } };
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && !pn.classList.contains('hide')) gear.onclick() });
  addEventListener('resize', () => { rugAll(); if (!fly.classList.contains('hide')) place() });

  /* ---------- load the saved file (server wins over the local copy) ---------- */
  fetch('/v1/speech/hud-settings').then(r => r.json()).then(j => { if (j && typeof j === 'object' && Object.keys(j).length) { Object.assign(S, j); try { localStorage.setItem('jvHudS', JSON.stringify(S)) } catch (e) { /* */ } } else save(); sync(); apply('all') }).catch(() => {});
  sync(); requestAnimationFrame(rugAll);
})();
