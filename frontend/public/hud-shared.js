/* Shared by hud.html, hud-boot.js (the boot animation) and the optional hud-local.js. Loaded first, in <head>.
   Everything the scripts share lives here under window.JarvisHud, so the contract is written down in one place:

   JarvisHud.layout(W, H)      the HUD's panel layout for a window size (hud.html draws it, hud-boot.js reveals it)
   JarvisHud.panels(layout)    the nine panel rectangles {id, x, y, w, h}, in the boot reveal order
   JarvisHud.wings(layout, ringR)  the two graph wings left and right of the core ring (ringR: the ring's current radius)
   JarvisHud.mapArea(panel, u) where the world map sits inside the network panel
   JarvisHud.helperUrl(path)   the hardware helper's address: direct on this PC, /helper through the LAN gateway (port 8443)

   JarvisHud.capture           hand-over of the HUD's first frame to the boot animation:
     texts    Map "x,y" -> TextRecord while hud-boot.js collects the texts the HUD draws, else null
     active   true while hud-boot.js copies the HUD canvas: the HUD then draws its panels without texts and map dots
     mapDots  the world map's dots ([lon, lat]) while active
   TextRecord = {text, x, y, size, color, align, alpha}

   JarvisHud.brain             the neural-core point cloud {pts, E}, made by hud.html, replayed by hud-boot.js
   JarvisHud.brainPose         its current rotation {rot, ...}, updated by hud.html every frame
   JarvisHud.drawWear(ctx, W, H)  paints the HUD's scratches and dust over another canvas (set by hud.html)

   Extension hooks (used by the private hud-local.js; any number of handlers):
   JarvisHud.onAsk(fn)         fn(text) runs before a chat message is sent; returning true means "handled, do not send"
   JarvisHud.onLogLine(fn)     fn(className) runs after every log line that is not the user's own (answers and status lines)
*/
(function () {
  'use strict';
  const askHandlers = [];
  const logLineHandlers = [];
  const MAP_LAT_TOP = 84;      // the world map shows latitudes 84 N ... 58 S (no Antarctica)
  const MAP_LAT_BOTTOM = -58;

  function layout(W, H) {
    const cmp = W / H < 2.8;   // compact: screens narrower than 2.8:1 get wider panels and no wing graphs
    const pw = W * (cmp ? 0.16 : 0.11), gap = W * (cmp ? 0.008 : 0.01), m = W * (cmp ? 0.01 : 0.015);
    const top = H * 0.07, h1 = H * 0.56, y2 = top + h1 + H * 0.02, h2 = H * 0.93 - y2;
    const L1 = m, L2 = m + pw + gap, R2 = W - m - pw, R1 = W - m - 2 * pw - gap;
    const h3 = H * 0.26, hcs = h3 * 0.88, wy = top + hcs + H * 0.02, wh = 2 * h3 - hcs, my0 = wy + wh + H * 0.02, mh0 = H * 0.93 - my0;
    const cx = W / 2, cy = H * 0.40, coreR = Math.min(H * 0.115, W * 0.06);   // the core: its centre and resting radius
    return { W, H, u: H / 1440, cmp, pw, gap, m, top, h1, y2, h2, L1, L2, R1, R2, h3, hcs, wy, wh, my0, mh0, cx, cy, coreR };
  }

  function wings(L, ringR) {
    const u = L.u;
    const xl = L.L2 + L.pw + 30 * u, xr = L.R1 - 30 * u;                  // outer ends of the wings
    const gl = L.cx - ringR - 60 * u, gr2 = L.cx + ringR + 60 * u;        // inner ends, next to the ring
    const x0 = xl + 50 * u, wl = L.cx - ringR - 130 * u - x0;              // left graphs: start and width
    const rh = 62 * u, y0 = L.cy - 3 * rh;                                 // row height, first row (6 rows around the centre line)
    const x1 = L.cx + ringR + 130 * u, wr = xr - 50 * u - x1;              // right bars: start and width
    return { xl, xr, gl, gr2, x0, wl, rh, y0, x1, wr };
  }

  function panels(L) {
    return [
      { id: 'hardware', x: L.L1, y: L.top, w: L.pw, h: L.h1 },
      { id: 'diagnostics', x: L.L2, y: L.top, w: L.pw, h: L.h1 },
      { id: 'core', x: L.L1, y: L.y2, w: L.pw, h: L.h2 },
      { id: 'biometric', x: L.L2, y: L.y2, w: L.pw, h: L.h2 },
      { id: 'chrono', x: L.R1, y: L.top, w: L.pw, h: L.hcs },
      { id: 'atmospherics', x: L.R1, y: L.wy, w: L.pw, h: L.wh },
      { id: 'network', x: L.R1, y: L.my0, w: 2 * L.pw + L.gap, h: L.mh0 },
      { id: 'stream', x: L.R2, y: L.top, w: L.pw, h: L.hcs },
      { id: 'neural', x: L.R2, y: L.wy, w: L.pw, h: L.wh },
    ];
  }

  function mapArea(panel, u) {
    const left = panel.x + 28 * u, width = panel.w - 56 * u;
    const h = Math.min(panel.h - 60 * u, width * (MAP_LAT_TOP - MAP_LAT_BOTTOM) / 360);
    const w = h * 360 / (MAP_LAT_TOP - MAP_LAT_BOTTOM);
    return { left, width, x: left + (width - w) / 2, top: panel.y + 50 * u, w, h, latTop: MAP_LAT_TOP, latBottom: MAP_LAT_BOTTOM };
  }

  function helperUrl(path) {
    return (location.port === '8443' ? '/helper' : 'http://127.0.0.1:8765') + (path || '');
  }

  window.JarvisHud = {
    layout, panels, wings, mapArea, helperUrl,
    capture: { texts: null, active: false, mapDots: null },
    brain: null, brainPose: null, drawWear: null,
    onAsk(fn) { askHandlers.push(fn); },
    onLogLine(fn) { logLineHandlers.push(fn); },
    handleAsk(text) { return askHandlers.some((fn) => fn(text) === true); },
    logLineAdded(className) { logLineHandlers.forEach((fn) => fn(className)); },
  };
})();
