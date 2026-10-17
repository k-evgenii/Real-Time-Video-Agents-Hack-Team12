// overlay.js — draws map.json boxes over a <video> (role B). No dependencies.
// Usage (C's app.js): put a <canvas> absolutely positioned exactly over the <video> (same box), then per rAF:
//   import { drawOverlay } from './overlay.js';
//   drawOverlay(canvas, map.frames[i] || null, videoEl, { showIds: true, imageSize: map.image_size,
//               alerts: map.alerts, highlight: trackIdOrNull });
// Row p = [id, cls, x, y, u, v, w, h, score_x100] with (u, v) = box centre in source pixels. With a 9th column (traffic)
// boxes go green -> amber -> red by score_x100 and an active alert prints its type above the box; without it
// (football) boxes use opts.teams by p[1]. Handles object-fit: contain letterboxing. Idempotent.

const GREY = '#8a8f98';

function scoreColour(s) {
  if (s >= 100) return '#ff4d4f';
  if (s >= 50) return '#f6b02f';
  return '#3fb950';
}

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
  const alerts = opts.alerts || [];
  const fs = Math.round(14 * dpr);
  ctx.font = `bold ${fs}px system-ui, sans-serif`;
  ctx.textBaseline = 'bottom';
  ctx.textAlign = 'left';
  for (let n = 0; n < frame.p.length; n++) {
    const p = frame.p[n];
    const traffic = p.length > 8;
    const score = traffic ? p[8] : 0;
    const c = traffic ? scoreColour(score) : p[1] === 0 ? teams.A : p[1] === 1 ? teams.B : GREY;
    const hl = opts.highlight != null && opts.highlight === p[0];
    const w = p[6] * sx, h = p[7] * sy;
    const x = ox + p[4] * sx - w / 2, y = oy + p[5] * sy - h / 2;
    ctx.lineWidth = (hl || score >= 100 ? 4 : 2) * dpr;
    ctx.strokeStyle = hl ? '#ffffff' : c;
    ctx.strokeRect(x, y, w, h);
    let label = showIds ? String(p[0]) : '';
    if (traffic && score >= 100) {
      for (let j = 0; j < alerts.length; j++) {
        const a = alerts[j];
        if (a.track_id === p[0] && frame.t >= a.t0 - 0.5 && frame.t <= a.t1 + 0.5) {
          label += (label ? ' ' : '') + a.type.replace(/_/g, ' ').toUpperCase();
          break;
        }
      }
    }
    if (label) {
      const tw = ctx.measureText(label).width + 6 * dpr;
      ctx.fillStyle = 'rgba(0,0,0,0.65)';
      ctx.fillRect(x, y - fs - 2 * dpr, tw, fs + 2 * dpr);
      ctx.fillStyle = hl ? '#ffffff' : c;
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
