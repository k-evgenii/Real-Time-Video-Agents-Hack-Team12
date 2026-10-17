# Notes from B (trajectories + flow map) for C — traffic pivot

Files (scene `i24_cam-1`, 3 parent chunks, match-global t = chunk_index*30 + seconds in chunk):
- `data/i24_cam-1/map.json` = primary part `20261001_055249_scene1_p1c1_chunk_0000` (t 0–30). Per part: `map_<part>.json`
  for `..._chunk_0001` (t 30–60) and `..._chunk_0002` (t 60–90). Set `t_offset_s = chunk_index*30` in index.json.
- `data/i24_cam-1/map_sim.json` = same part with an injected swerve on track 85 at t≈10.4 s; top-level `"simulated": true`,
  every alert has `"simulated": true`. Show a "SIMULATED" label when the toggle is on.
- `data/i24_cam-1/track_alerts.json` = `{"scene","tau":{part:τ},"alerts":[…]}` sorted by `peak_score` (real alerts only).

map.json (FLOW): `p` row = `[id, cls(0 vehicle,1 person/bicycle,2 other), x_dm, y_dm, u, v, w, h, score_x100]`, `(u,v)` = box
CENTRE in source pixels; `b` always null. Top level: `image_size [W,H]`, `tau`, `flow {cols,rows,cells:[[ux,uy,n,mean_speed_px_s]]}`
(row-major), `alerts [{track_id,t0,t1,type,peak_d2,peak_score,u,v,d2_hist,tau,n_frames,rho_min,rho_max,dtheta_deg,reason,part_id,scene}]`.
`d2_hist` = d² per frame during the alert (≤ 60 values) for the sparkline; draw `tau` as the threshold line.

Calls:
- `drawPitch(canvas, frame, {mode:'FLOW', flow: map.flow, imageSize: map.image_size, trails: buildTrails(map.frames, i, 2), teams:{B:'#f6b02f'}})`
- `drawOverlay(canvas, frame, video, {imageSize: map.image_size, alerts: map.alerts, highlight: trackIdOrNull})` — boxes green/amber/red
  by score, alert type printed above red boxes, `highlight` draws that id white (use on alert click).
- `findFrame(map.frames, t)` / `buildTrails` exported from pitch.js. Canvases need CSS size + `min-width:0` on grid parents.
