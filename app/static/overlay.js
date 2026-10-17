// overlay.js — draws map.json boxes over a <video> (role B). No dependencies.
// Usage (C's app.js): put a <canvas> absolutely positioned exactly over the <video> (same box), then per rAF:
//   import { drawOverlay } from './overlay.js';
//   drawOverlay(canvas, map.frames[i] || null, videoEl, { teams: { A: '#2f6df6', B: '#e8e8e8' }, showIds: true,
//               imageSize: map.image_size });   // [W,H] of the detection pixels; defaults to video.videoWidth/Height
// Row p = [id, team, x_dm, y_dm, u, v, w, h] with (u, v) = box centre in source pixels; ball b = [x, y, u, v, conf, interp].
// Handles object-fit: contain letterboxing. Idempotent: clears and redraws each call.

const GREY = '#8a8f98';

export function drawOverlay(canvas, frame, videoEl, opts = {}) {
  const dpr = window.devicePixelRatio || 1;
  const cw = Math.max(1, Math.round(videoEl.clientWidth * dpr));
  const ch = Math.max(1, Math.round(videoEl.clientHeight * dpr));
  if (canvas.width !== cw) canvas.width = cw;
  if (canvas.height !== ch) canvas.height = ch;
  const ctx = canvas.getContext('2d');
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, cw, ch);
  if (!frame) return;

  const sw = (opts.imageSize && opts.imageSize[0]) || videoEl.videoWidth || cw;
  const sh = (opts.imageSize && opts.imageSize[1]) || videoEl.videoHeight || ch;
  const vw = videoEl.videoWidth || sw, vh = videoEl.videoHeight || sh;
  const s = Math.min(cw / vw, ch / vh);                 // contain-fit of the displayed video
  const ox = (cw - vw * s) / 2, oy = (ch - vh * s) / 2;
  const sx = s * vw / sw, sy = s * vh / sh;             // detection pixels -> canvas pixels

  const teams = opts.teams || { A: '#2f6df6', B: '#e8e8e8' };
  const showIds = opts.showIds !== false;
  const lw = Math.max(2, 2.5 * dpr);
  const fs = Math.round(14 * dpr);
  ctx.lineWidth = lw;
  ctx.font = `bold ${fs}px system-ui, sans-serif`;
  ctx.textBaseline = 'bottom';
  ctx.textAlign = 'left';
  for (let n = 0; n < frame.p.length; n++) {
    const p = frame.p[n];
    const c = p[1] === 0 ? teams.A : p[1] === 1 ? teams.B : GREY;
    const w = p[6] * sx, h = p[7] * sy;
    const x = ox + p[4] * sx - w / 2, y = oy + p[5] * sy - h / 2;
    ctx.strokeStyle = c;
    ctx.strokeRect(x, y, w, h);
    if (showIds) {
      ctx.fillStyle = 'rgba(0,0,0,0.6)';
      const label = String(p[0]);
      const tw = ctx.measureText(label).width + 6 * dpr;
      ctx.fillRect(x, y - fs - 2 * dpr, tw, fs + 2 * dpr);
      ctx.fillStyle = c;
      ctx.fillText(label, x + 3 * dpr, y);
    }
  }
  const b = frame.b;
  if (b) {
    const r = Math.max(8 * dpr, 10 * s);
    const x = ox + b[2] * sx, y = oy + b[3] * sy;
    ctx.strokeStyle = '#fff';
    if (b[5]) ctx.setLineDash([4 * dpr, 4 * dpr]);
    ctx.strokeRect(x - r, y - r, 2 * r, 2 * r);
    ctx.setLineDash([]);
  }
}
