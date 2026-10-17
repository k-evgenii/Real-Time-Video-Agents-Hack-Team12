# Notes from B (map) for C

1. **map.json `p` row `u,v` = box CENTRE** in source pixels (same as ball `b[2..3]`); `w,h` = box size. `overlay.js` draws `(u-w/2, v-h/2, w, h)`. If your fixtures use top-left, please switch to centre.
2. map.json carries one extra key `image_size: [W, H]` (detection pixel size). Please let `validate.py` allow extra keys; pass it to `drawOverlay(..., {imageSize: map.image_size})`.
3. `pitch.js` also exports `findFrame(frames, t)` (binary search) and `buildTrails(frames, i, 2)` so `app.js` doesn't need its own. Canvases need a CSS width/height and `min-width: 0` on a grid/flex parent.
4. Detection source for the map = the stored ingest YOLO sidecar (`/videos/detections`, every frame, 30 fps); fallback = hosted `/v1/infer`. Segments are 5 s.
5. `map_mode` for `index.json`: pending A's Triage Card — default **RELATIVE**, upgrade to FULL if the primary camera is fixed and calibration RMSE < 1.5 m.
