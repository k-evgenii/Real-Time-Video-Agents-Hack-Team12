// pitch.js — top-down pitch renderer for map.json frames (role B). No dependencies.
// Usage (C's app.js):
//   import { drawPitch, findFrame, buildTrails } from './pitch.js';
//   const i = findFrame(map.frames, globalT);                 // binary search on frames[].t (-1 if none)
//   const trails = buildTrails(map.frames, i, 2);              // Map<id, [[x_dm,y_dm],…]> over the last 2 s
//   drawPitch(canvas, map.frames[i] || null, { teams: { A: '#2f6df6', B: '#e8e8e8' }, trails, mode: map.mode });
//   Traffic: drawPitch(canvas, frame, { mode: 'FLOW', flow: map.flow, imageSize: map.image_size, trails,
//            teams: { B: '#f6b02f' } })  -> image frame, 8×8 lane-flow arrows, dots red when score_x100 (p[8]) >= 100.
// Idempotent: clears and redraws the whole canvas each call; sizes the backing store to clientWidth × devicePixelRatio,
// so give the canvas a CSS width/height and `min-width: 0` on a grid/flex parent (else it grows every frame).

const L = 1050, Wd = 680, M = 20;           // pitch length/width and margin, decimetres
const GREY = '#8a8f98';
const bgCache = new WeakMap();               // canvas -> {key, img}

function geom(canvas) {
  const dpr = window.devicePixelRatio || 1;
  const cw = Math.max(1, Math.round((canvas.clientWidth || canvas.width) * dpr));
  const ch = Math.max(1, Math.round((canvas.clientHeight || canvas.height) * dpr));
  if (canvas.width !== cw) canvas.width = cw;
  if (canvas.height !== ch) canvas.height = ch;
  const k = Math.min(cw / (L + 2 * M), ch / (Wd + 2 * M));
  const ox = (cw - (L + 2 * M) * k) / 2 + M * k + (L / 2) * k;
  const oy = (ch - (Wd + 2 * M) * k) / 2 + M * k + (Wd / 2) * k;
  return { cw, ch, k, ox, oy, dpr };
}

function drawLines(ctx, g) {
  const { k, ox, oy, dpr } = g;
  const X = (x) => ox + x * k, Y = (y) => oy + y * k;
  ctx.fillStyle = '#0f3d24';
  ctx.fillRect(0, 0, g.cw, g.ch);
  // mowing stripes
  ctx.fillStyle = '#124a2b';
  for (let i = 0; i < 10; i += 2) ctx.fillRect(X(-L / 2 + i * L / 10), Y(-Wd / 2), (L / 10) * k, Wd * k);
  ctx.strokeStyle = 'rgba(255,255,255,0.85)';
  ctx.lineWidth = Math.max(2, 2.5 * dpr);
  ctx.beginPath();
  ctx.rect(X(-L / 2), Y(-Wd / 2), L * k, Wd * k);
  ctx.moveTo(X(0), Y(-Wd / 2)); ctx.lineTo(X(0), Y(Wd / 2));
  ctx.moveTo(X(91.5), Y(0)); ctx.arc(X(0), Y(0), 91.5 * k, 0, Math.PI * 2);
  for (const s of [-1, 1]) {
    const gx = s * L / 2;
    ctx.rect(Math.min(X(gx), X(gx - s * 165)), Y(-201.6), 165 * k, 403.2 * k);   // penalty area
    ctx.rect(Math.min(X(gx), X(gx - s * 55)), Y(-91.6), 55 * k, 183.2 * k);      // goal area
    ctx.moveTo(X(gx - s * 110) + 91.5 * k, Y(0));
    const a = Math.acos(55 / 91.5);                                              // penalty arc outside the box
    if (s < 0) { ctx.moveTo(X(gx - s * 110) + Math.cos(-a) * 91.5 * k, Y(0) + Math.sin(-a) * 91.5 * k); ctx.arc(X(gx - s * 110), Y(0), 91.5 * k, -a, a); }
    else { ctx.moveTo(X(gx - s * 110) + Math.cos(Math.PI - a) * 91.5 * k, Y(0) + Math.sin(Math.PI - a) * 91.5 * k); ctx.arc(X(gx - s * 110), Y(0), 91.5 * k, Math.PI - a, Math.PI + a); }
  }
  ctx.stroke();
  ctx.fillStyle = 'rgba(255,255,255,0.9)';
  for (const x of [0, -415, 415]) { ctx.beginPath(); ctx.arc(X(x), Y(0), Math.max(2, 0.4 * dpr * 3), 0, Math.PI * 2); ctx.fill(); }
  // goals
  ctx.lineWidth = Math.max(3, 4 * dpr);
  ctx.beginPath();
  ctx.moveTo(X(-L / 2), Y(-36.6)); ctx.lineTo(X(-L / 2 - 15), Y(-36.6)); ctx.lineTo(X(-L / 2 - 15), Y(36.6)); ctx.lineTo(X(-L / 2), Y(36.6));
  ctx.moveTo(X(L / 2), Y(-36.6)); ctx.lineTo(X(L / 2 + 15), Y(-36.6)); ctx.lineTo(X(L / 2 + 15), Y(36.6)); ctx.lineTo(X(L / 2), Y(36.6));
  ctx.stroke();
}

function background(canvas, g) {
  const key = `${g.cw}x${g.ch}`;
  let c = bgCache.get(canvas);
  if (!c || c.key !== key) {
    const off = document.createElement('canvas');
    off.width = g.cw; off.height = g.ch;
    drawLines(off.getContext('2d'), g);
    c = { key, img: off };
    bgCache.set(canvas, c);
  }
  return c.img;
}

function textOn(hex) {
  const h = (hex || '#888').replace('#', '');
  const r = parseInt(h.slice(0, 2), 16), gg = parseInt(h.slice(2, 4), 16), b = parseInt(h.slice(4, 6), 16);
  return (0.299 * r + 0.587 * gg + 0.114 * b) > 150 ? '#111' : '#fff';
}

// FLOW mode (traffic): the "pitch" is the camera image normalised to x∈[-525,525], y∈[-340,340].
function drawFlow(canvas, ctx, g, frame, opts) {
  const { k, ox, oy, dpr } = g;
  const X = (x) => ox + x * k, Y = (y) => oy + y * k;
  const [iw, ih] = opts.imageSize || [1920, 1080];
  const dotColour = (opts.teams && (opts.teams.B || opts.teams.A)) || '#f6b02f';
  ctx.fillStyle = '#0d1117';
  ctx.fillRect(0, 0, g.cw, g.ch);
  ctx.fillStyle = '#161b22';
  ctx.fillRect(X(-L / 2), Y(-Wd / 2), L * k, Wd * k);
  ctx.strokeStyle = 'rgba(255,255,255,0.6)';
  ctx.lineWidth = Math.max(2, 2 * dpr);
  ctx.strokeRect(X(-L / 2), Y(-Wd / 2), L * k, Wd * k);

  const flow = opts.flow;
  if (flow && flow.cells) {
    const cw = L / flow.cols, chh = Wd / flow.rows;
    ctx.strokeStyle = 'rgba(255,255,255,0.08)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let c = 1; c < flow.cols; c++) { ctx.moveTo(X(-L / 2 + c * cw), Y(-Wd / 2)); ctx.lineTo(X(-L / 2 + c * cw), Y(Wd / 2)); }
    for (let r = 1; r < flow.rows; r++) { ctx.moveTo(X(-L / 2), Y(-Wd / 2 + r * chh)); ctx.lineTo(X(L / 2), Y(-Wd / 2 + r * chh)); }
    ctx.stroke();
    ctx.strokeStyle = 'rgba(120,200,255,0.75)';
    ctx.fillStyle = 'rgba(120,200,255,0.75)';
    ctx.lineWidth = Math.max(2, 2.5 * dpr);
    for (let i = 0; i < flow.cells.length; i++) {
      const [ux, uy, n] = flow.cells[i];
      if (!n || (ux === 0 && uy === 0)) continue;
      let dx = ux * L / iw, dy = uy * Wd / ih;
      const nrm = Math.hypot(dx, dy) || 1;
      dx /= nrm; dy /= nrm;
      const len = Math.min(cw, chh) * 0.42 * Math.min(1, n / 50);
      const cx = X(-L / 2 + ((i % flow.cols) + 0.5) * cw), cy = Y(-Wd / 2 + (Math.floor(i / flow.cols) + 0.5) * chh);
      const ex = cx + dx * len * k, ey = cy + dy * len * k;
      ctx.beginPath(); ctx.moveTo(cx - dx * len * k, cy - dy * len * k); ctx.lineTo(ex, ey); ctx.stroke();
      const hl = Math.max(6 * dpr, len * k * 0.35), a = Math.atan2(dy, dx);
      ctx.beginPath(); ctx.moveTo(ex, ey);
      ctx.lineTo(ex - hl * Math.cos(a - 0.45), ey - hl * Math.sin(a - 0.45));
      ctx.lineTo(ex - hl * Math.cos(a + 0.45), ey - hl * Math.sin(a + 0.45));
      ctx.closePath(); ctx.fill();
    }
  }
  if (!frame) return;
  const alerting = new Set();
  for (const p of frame.p) if ((p[8] || 0) >= 100) alerting.add(p[0]);
  if (opts.trails) {
    ctx.lineCap = 'round';
    for (const [id, pts] of opts.trails) {
      if (pts.length < 2) continue;
      const hot = alerting.has(id);
      ctx.strokeStyle = hot ? '#ff4d4f' : dotColour;
      ctx.lineWidth = (hot ? 5 : 2) * dpr;
      for (let i = 1; i < pts.length; i++) {
        ctx.globalAlpha = (hot ? 0.9 : 0.5) * i / pts.length;
        ctx.beginPath(); ctx.moveTo(X(pts[i - 1][0]), Y(pts[i - 1][1])); ctx.lineTo(X(pts[i][0]), Y(pts[i][1])); ctx.stroke();
      }
    }
    ctx.globalAlpha = 1;
  }
  const r = Math.max(8 * k, 7 * dpr);
  ctx.font = `bold ${Math.round(14 * dpr)}px system-ui, sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'bottom';
  for (const p of frame.p) {
    const x = X(p[2]), y = Y(p[3]);
    const hot = (p[8] || 0) >= 100;
    ctx.fillStyle = hot ? '#ff4d4f' : p[1] === 1 ? '#7ee787' : dotColour;
    ctx.beginPath(); ctx.arc(x, y, hot ? r * 1.5 : (p[1] === 1 ? r * 0.7 : r), 0, Math.PI * 2); ctx.fill();
    if (hot) {
      ctx.strokeStyle = '#fff'; ctx.lineWidth = 2 * dpr; ctx.stroke();
      ctx.fillStyle = '#fff';
      ctx.fillText(String(p[0]), x, y - r * 1.7);
    }
  }
}

export function drawPitch(canvas, frame, opts = {}) {
  const ctx = canvas.getContext('2d');
  const g = geom(canvas);
  if (opts.mode === 'FLOW') {
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    drawFlow(canvas, ctx, g, frame, opts);
    return;
  }
  const { k, ox, oy, dpr } = g;
  const teams = opts.teams || { A: '#2f6df6', B: '#e8e8e8' };
  const colours = [teams.A, teams.B, GREY];
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.drawImage(background(canvas, g), 0, 0);

  // trails: fading polylines (oldest transparent)
  if (opts.trails && frame) {
    const team = new Map();
    for (const p of frame.p) team.set(p[0], p[1]);
    ctx.lineWidth = Math.max(2, 3 * dpr);
    ctx.lineCap = 'round';
    for (const [id, pts] of opts.trails) {
      if (pts.length < 2) continue;
      ctx.strokeStyle = colours[team.has(id) ? team.get(id) : 2];
      for (let i = 1; i < pts.length; i++) {
        ctx.globalAlpha = 0.6 * i / pts.length;
        ctx.beginPath();
        ctx.moveTo(ox + pts[i - 1][0] * k, oy + pts[i - 1][1] * k);
        ctx.lineTo(ox + pts[i][0] * k, oy + pts[i][1] * k);
        ctx.stroke();
      }
    }
    ctx.globalAlpha = 1;
  }

  if (frame) {
    const r = Math.max(12 * k, 11 * dpr);
    ctx.font = `bold ${Math.round(Math.max(14 * dpr, r * 1.05))}px system-ui, sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.lineWidth = Math.max(1.5, 2 * dpr);
    for (const p of frame.p) {
      const x = ox + p[2] * k, y = oy + p[3] * k, c = colours[p[1]] || GREY;
      ctx.fillStyle = c;
      ctx.strokeStyle = '#000';
      ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
      ctx.fillStyle = textOn(c);
      ctx.fillText(String(p[0] % 100), x, y + 0.5);
    }
    const b = frame.b;
    if (b) {
      const x = ox + b[0] * k, y = oy + b[1] * k, rb = Math.max(7 * k, 7 * dpr);
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = Math.max(2, 3 * dpr);
      if (b[5]) ctx.setLineDash([4 * dpr, 4 * dpr]);
      ctx.beginPath(); ctx.arc(x, y, rb, 0, Math.PI * 2); ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = '#fff';
      ctx.beginPath(); ctx.arc(x, y, Math.max(2.5 * dpr, rb * 0.35), 0, Math.PI * 2); ctx.fill();
    }
  }

  if (opts.mode === 'RELATIVE') {
    const fs = Math.round(16 * dpr);
    ctx.font = `bold ${fs}px system-ui, sans-serif`;
    const msg = 'UNCALIBRATED — relative positions';
    const w = ctx.measureText(msg).width + fs;
    ctx.fillStyle = 'rgba(180,120,0,0.85)';
    ctx.fillRect((g.cw - w) / 2, 6 * dpr, w, fs * 1.6);
    ctx.fillStyle = '#fff';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(msg, g.cw / 2, 6 * dpr + fs * 0.8);
  }
}

// Index of the last frame with frames[i].t <= t, or -1.
export function findFrame(frames, t) {
  let lo = 0, hi = frames.length - 1, ans = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (frames[mid].t <= t) { ans = mid; lo = mid + 1; } else hi = mid - 1;
  }
  return ans;
}

// Trails for frame i over the previous `seconds`: Map<track_id, [[x_dm, y_dm], …]> (oldest first).
export function buildTrails(frames, i, seconds = 2) {
  const trails = new Map();
  if (i < 0 || !frames[i]) return trails;
  const tEnd = frames[i].t;
  let j = i;
  while (j > 0 && tEnd - frames[j - 1].t <= seconds) j--;
  for (; j <= i; j++) {
    for (const p of frames[j].p) {
      let a = trails.get(p[0]);
      if (!a) { a = []; trails.set(p[0], a); }
      a.push([p[2], p[3]]);
    }
  }
  return trails;
}
