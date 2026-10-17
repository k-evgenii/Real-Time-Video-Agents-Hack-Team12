# Traffic Anomaly Detectors — VAST Builders Challenge, Team 12

**Live app:** [team-12-app.thecosmoslabs.com/app](https://team-12-app.thecosmoslabs.com/app/) (or [workshop.thecosmoslabs.com](https://workshop.thecosmoslabs.com) → **App**)

> Traffic cameras produce hours of nothing and seconds that matter. We built two detectors that find those
> seconds with **no labels and no training**, on any camera in the VAST video archive, and explain every flag
> in plain numbers.

---

## Contents
1. [What it does](#1-what-it-does)
2. [How it works](#2-how-it-works)
3. [Results](#3-results)
4. [Using the app](#4-using-the-app)
5. [Data contracts](#5-data-contracts)
6. [Repository layout](#6-repository-layout)
7. [Running everything](#7-running-everything)
8. [Deployment](#8-deployment)
9. [Testing](#9-testing)
10. [Design decisions and deviations](#10-design-decisions-and-deviations)
11. [Limits](#11-limits)
12. [Team, workflow and history](#12-team-workflow-and-history)
13. [Stack](#13-stack)

---

## 1. What it does

Pick a camera in the web app and you get:

- **The video**, streamed from the VAST index, with every vehicle and pedestrian **boxed and tracked**. Boxes go
  green → amber → red as the trajectory anomaly score rises.
- **A flow map**: the camera frame seen from above, with an 8×8 grid of **lane-flow arrows the system learned
  itself**, every vehicle as a dot (red when it is alerting) and its recent trail.
- **Two anomaly timelines** under the video:
  - **Lane A, scene episodes (Cosmos + Embed1):** coarse, segment-level, from what Cosmos3-Reason wrote.
  - **Lane B, trajectory alerts (Kalman):** fine, frame-level, from how each vehicle actually moves.
- **An anomaly panel** with two tabs (*Episodes* / *Trajectories*), and a **"why" card** that explains the selected
  item in σ and units. Clicking an item seeks the video to it.
- **Simulate**: injects a labelled synthetic manoeuvre (e.g. a swerve) into one real vehicle so you can watch the
  trajectory detector fire. Everything simulated is badged as such.
- **Find similar**: searches the archive with the anomaly's phrase across all cameras.

The same code runs on a fixed overhead highway camera (I-24), a fixed residential street camera, and moving
dashcam / GoPro footage. On moving cameras it **switches the physics layer off** (detection boxes only) and keeps
the episode layer, so it knows what it can't claim.

---

## 2. How it works

```
                         VAST VSS pipeline (already running)
 video ──► segmenter (5 s) ──► YOLO11 ──► Cosmos3-Reason ──► Cosmos Embed1 ──► VastDB + S3
                                  │              │                  │
                 per-frame boxes  │   free-text  │   256-d vectors  │
                 (/videos/        │   description│   (vectors_      │
                  detections)     │              │    visual)       │
                                  ▼              ▼                  ▼
  ┌──────────────── Lane B (map/) ───────────┐  ┌──────────── Lane A (events/) ──────────────┐
  │ detect.py   sidecar boxes per segment     │  │ events.py  W&B LLM → fixed traffic grammar │
  │ track.py    SORT-lite + CV Kalman         │  │ attacks.py runs of same FLOW → episodes     │
  │ anomaly_track.py  d², ρ, Δθ, τ, EMA,      │  │ features.py 10 features per episode         │
  │             flow field, wrong_way         │  │ anomaly.py  per-camera robust-z + kNN,      │
  │ build_map.py  two passes → map*.json,     │  │             + Embed1 cosine kNN             │
  │             track_alerts.json, Simulate   │  │ → segments/attacks/anomalies.json           │
  └───────────────────────┬───────────────────┘  └───────────────────┬────────────────────────┘
                          └──────────────┬───────────────────────────┘
                                         ▼
                     app/ (Flask + vanilla JS, deployed on K8s at /app)
                     main.py: /matches, /data/<scene>/<name>.json, /video proxy, /similar
                     app.js (shell) + pitch.js (flow map) + overlay.js (boxes)
```

### 2.1 Lane A: scene episodes (Cosmos + Embed1)

1. **Labels.** Every indexed segment already has a Cosmos3-Reason description. `events.py` sends those
   descriptions to **W&B serverless inference** (`--repair`), which converts the free text into a fixed grammar
   (`events/prompt.txt`):
   `SCENE · FLOW (free/moderate/dense/stopped) · VEHICLES · PEDESTRIANS · DIRECTION · EVENTS (closed vocabulary:
   lane_change, hard_braking, sudden_stop, stopped_vehicle, reversing, wrong_way, pedestrian_in_road, collision,
   near_miss, …) · LIGHT · NOTE`. Native rows in that grammar are parsed with regexes; the result is
   `segments.json` with `parse_ok` per row.
2. **Episodes** (`attacks.py`). Walking segments in time order, a run with the same FLOW state is an episode;
   one UNCLEAR segment is tolerated; a flow change or a risk event (collision, near_miss, hard_braking,
   sudden_stop, wrong_way, reversing, pedestrian_in_road, emergency_vehicle) closes it.
3. **Features** (`features.py`), 10 per episode: `duration_s, n_seg, mean_vehicles, max_vehicles, mean_peds,
   n_risk_events, n_manoeuvres, share_dense_or_stopped, flow_code, ended_by_code`.
4. **Anomaly score** (`anomaly.py`), **per camera**:
   - Robust z per feature: `z = (x − median) / (1.4826 · MAD)`, clipped to ±5.
   - `s_feat` = mean distance to the k nearest neighbours (k = max(3, √n)) ÷ the camera's median of that distance.
     1.0 = typical, ≥ 2.5 = flagged.
   - `s_emb` = the same test on the **mean-pooled Cosmos Embed1 visual vectors** (cosine), a view that never
     saw our labels. When both agree, the app says so.
   - Reasons are rendered with units, e.g. *"flow code 5.0σ above camera median (moderate vs free)"*.
   - Per-camera normalisation is the generalisation argument: a highway isn't anomalous for having 30 cars, and a
     residential street isn't anomalous for having one.

### 2.2 Lane B: trajectory anomalies (YOLO11 + Kalman)

1. **Detections** (`map/detect.py`). The pipeline stores YOLO11 boxes for **every frame** of every segment
   (`GET /api/v1/videos/detections`, 20–30 fps). Fallback: hosted YOLO `/v1/infer`. Classes: car, truck, bus,
   motorcycle, person, bicycle (confidence ≥ 0.35).
2. **Tracking** (`map/track.py`). SORT-lite: constant-velocity Kalman filter per object, state `[px, py, vx, vy]`,
   measurement noise `σ_m = max(2, 0.08·s)` with `s = √(w·h)`. Greedy IoU matching on predicted boxes (gate 0.25),
   plus a second stage that keeps a confirmed track through sharp manoeuvres (nearest leftover detection within
   one box-scale). Confirm at 3 hits, delete after 15 misses.
3. **Signals** (`map/anomaly_track.py`) for each confirmed, matched, warmed-up track:
   - (a) residual `r = ‖y‖ / s`
   - (b) heading change Δθ and speed ratio ρ over 5 frames → `sig_b = max(Δθ/(π/2), |log ρ| / log 2.5)`
   - (c) Mahalanobis `d² = yᵀ S⁻¹ y ~ χ²(2)`
4. **Self-set threshold.** `τ = max(9.21, 99.5th percentile of the scene's own d²)`, learned in a first pass over
   the whole part. A second pass scores with it.
5. **Score and hysteresis.** `inst = max(d²/τ, r/0.5·0.5 + 0.5·sig_b)`, `score ← 0.7·score + 0.3·inst`. An alert
   opens when score ≥ 1 for 9 frames (0.3 s), closes below 0.6 for 5 frames, then a 30-frame cooldown.
6. **Type.** `swerve` if Δθ > 60°, `hard_braking` if ρ < 0.4, `sudden_acceleration` if ρ > 2.5, else
   `unexplained_motion`.
7. **Flow field and wrong way.** An 8×8 grid over the image accumulates unit velocities. A *display* field (for the
   arrows) and a stricter *rule* field are kept. `wrong_way` fires when a track runs against a rule cell with ≥ 50
   samples whose directions agree (resultant ≥ 0.6·n) for 5 consecutive frames.
8. **Simulate** (`build_map.py --inject stop|swerve|reverse`). Picks a fast, close vehicle (or `--track-id`),
   removes every detection overlapping its path (so duplicate YOLO boxes can't carry the track), and inserts one
   clean synthetic path that stops, swerves or reverses at `--at-t`. Output is `map_sim*.json` with
   `"simulated": true`.
9. **Moving cameras** (`--mode NONE`). Same tracking for the boxes; scores are zeroed and no alerts are written.

### 2.3 The app (`tools/footballslam/app/`)

- `main.py` (Flask): logs in to VSS once (re-logs in on 401); serves `/health`, `/matches` (from
  `data/index.json`), `/data/<scene>/<name>.json` (fixed names plus per-part `map_<part>` / `map_sim_<part>`),
  `/video?src=…` (Range-forwarding proxy to `/api/v1/videos/stream`) and `/similar?q=…` (`/api/v1/search`).
- `static/app.js` (C): segment playlist (each part's 5-second segments play back to back), both timelines, tabs,
  why-card, Simulate toggle, Find similar. Loads the selected part's map (`map_<part_id>.json`, falling back to
  `map.json`).
- `static/pitch.js` (B): `drawPitch(canvas, frame, opts)`: flow map in `FLOW` mode (image frame, grid, arrows
  scaled by sample count, dots, red alerting dots, thick red trails), or a football pitch in the original modes.
  Also exports `findFrame` (binary search) and `buildTrails`.
- `static/overlay.js` (B): `drawOverlay(canvas, frame, opts)`: score-coloured boxes, IDs, alert type above red
  boxes, highlight of a selected track; handles both the app's pixel-sized canvas and a letterboxed `<video>`.

---

## 3. Results

### Lane B: trajectory layer (all parts served by the app)

| Scene | Part | Camera | Mode | fps | objects/frame | τ (self-set) | real alerts | Simulate |
|---|---|---|---|---|---|---|---|---|
| I-24 overhead | `20261001_055315_scene1_p1c1_chunk_0001` | fixed | FLOW | 30 | 9.1 | 12.87 | 0 | swerve on vehicle 71 → alert, d² = 42.6 vs τ = 12.9, peak score 2.76 |
| I-24 overhead | `20261008_073802_GX010001_chunk_0003` | NYC GoPro (moving) | NONE | 30 | 7.8 | (88.0) | n/a | none |
| I-24 overhead | `20261008_072948_GOPR0130_chunk_0014` | NYC GoPro (moving) | NONE | 30 | 6.9 | (155.3) | n/a | none |
| I-24 overhead | `20261001_060418_scene1_p1c3_chunk_0007` | fixed | FLOW | 30 | 3.4 | 25.87 | 0 | no suitable vehicle |
| Neighborhood | `20261001_072628_neighborhood_20260901_chunk_0007` | fixed | FLOW | 20 | 3.3 | 9.21 | 0 | vehicle 4 → `hard_braking`, d² = 43.7, score 3.87 |
| Neighborhood | `…_chunk_0006` | fixed | FLOW | 20 | 3.7 | 9.21 | 0 | 1 simulated alert |
| Neighborhood | `…_chunk_0019` | fixed | FLOW | 20 | 2.3 | 9.21 | 0 | 1 simulated alert |
| PIE dashcam | `…set02_video_chunk_0010`, `…set03_video_chunk_0015`, `…_0014` | moving | NONE | 30 | 5.2–8.8 | n/a | n/a | none |

The GoPro τ values (88 and 155, against 9–26 for fixed cameras) come from a diagnostic pass. They are how we know
the camera moves, and why those parts are boxes-only.

Earlier full runs on I-24 `scene1_p1c1` chunks 0000/0001/0002 (kept in `data/i24_cam-1/`): τ = 11.29 / 12.87 /
9.21, at most 1 alert per 30 s. Real alerts: track 153 at t = 19.2 s `sudden_acceleration` (speed ratio 2.59), and
track 61 at t = 66.4 s `unexplained_motion` (d² = 35.1 vs τ = 9.2). Simulated swerve on vehicle 85: d² = 40.4 vs
τ = 11.3 for 21 frames, score 2.99.

### Lane A: episode layer (18 segments per camera, parse rate 1.0)

| Scene | episodes | top episode | s_feat | s_emb | flagged | lead reason |
|---|---|---|---|---|---|---|
| I-24 | 10 | `i24_e007` | 1.00 | 4.92 | yes | max vehicles 0.7σ below camera median (0 vs 4) |
| I-24 | | `i24_e010` | 1.66 | 2.98 | yes | flow code 5.0σ above camera median (moderate vs free) |
| Neighborhood | 7 | `neighborhood_e001` | 1.11 | 1.24 | no | mean vehicles 5.0σ below camera median (0.33 vs 1.00) |
| PIE dashcam | 6 | `pie_e001` | 1.41 | 3.09 | yes | max vehicles 2.0σ above camera median (5 vs 3.5) |

Full tables: `tools/footballslam/data/<scene>/anomaly_report.md`.

---

## 4. Using the app

1. Open the [live app](https://team-12-app.thecosmoslabs.com/app/).
2. **Scene**: I-24 overhead · Neighborhood · PIE dashcam. **Part**: a 30-second parent chunk.
3. The video plays its six 5-second segments back to back; the clock is seconds into the part.
4. **Lane A** bars are episodes, coloured by flow (free → stopped), with flagged ones outlined red. **Lane B**
   ticks are trajectory alerts. Click either to seek.
5. **Simulate** loads the part's `map_sim` file; the injected vehicle turns red with a "simulated" badge.
   For the best demo: I-24 part 1 (vehicle 71 around 0:10) or Neighborhood part 1 (vehicle 4 around 0:10).
6. **Episodes / Trajectories** tabs list the top anomalies; the why card shows z-bars (episodes) or d² vs τ
   (trajectories). **Find similar** searches the archive across cameras.

---

## 5. Data contracts

All times are seconds into the part. Scene folders: `tools/footballslam/data/<scene>/`.

**`index.json`** (C)
```json
{"matches":[{"match_id":"i24","title":"I-24 overhead","map_mode":"FLOW",
  "lanes":{"A":{"name":"Scene episodes (Cosmos)","colour":"#2f6df6"},"B":{"name":"Trajectory alerts (Kalman)","colour":"#f6b02f"}},
  "parts":[{"part_id":"<chunk stem>","original_video":"s3://…/<chunk>.mp4",
            "segments":[{"idx":0,"t0":0.0,"t1":5.0,"source":"s3://…-segments/segments/<chunk>_segment_001_of_006.mp4"}]}]}]}
```

**`segments.json`** (A): `{match_id, segment_len_s, parse_rate, segments:[{seg_id, part_id, idx, t0, t1, source,
flow F|M|D|S|U, direction L|R|T|A|X|U, scene H|S|R|I|C|U, events[], n_vehicles, n_peds, light, note, parse_ok}]}`

**`attacks.json`** (A, episodes): `{match_id, attacks:[{attack_id, team:"A", t0, t1, seg_ids[], n_seg, duration_s,
flow, events[], ended_by flow_change|risk_event|end}]}`

**`anomalies.json`** (A): `{match_id, k, feature_names[10], per_team:{A:[{attack_id, rank, s_feat, s_emb, flagged,
agree, z[10], reasons[3], moment:{seg_id, t, why}}]}}`

**`map.json` / `map_<part>.json` / `map_sim*.json`** (B)
```json
{"match_id":"i24","part_id":"…","mode":"FLOW|NONE","fps":5,"image_size":[1920,1080],"tau":12.87,
 "flow":{"cols":8,"rows":8,"cells":[[ux,uy,n,mean_speed_px_s], …64]},
 "alerts":[{"track_id":71,"t0":10.3,"t1":11.0,"type":"unexplained_motion","peak_d2":42.6,"peak_score":2.76,
            "u":…,"v":…,"d2_hist":[…],"tau":12.87,"n_frames":20,"reason":"d²=42.6 vs τ=12.9 for 20 frames; …"}],
 "frames":[{"t":10.4,"p":[[id, cls, x_dm, y_dm, u, v, w, h, score_x100]],"b":null}],
 "simulated":true}
```
`cls`: 0 vehicle, 1 person/bicycle, 2 other. `(u, v)` = box **centre** in source pixels, `w, h` in pixels.
`x, y` = `((u/W − 0.5)·1050, (v/H − 0.5)·680)`. `score_x100 ≥ 100` means alerting.

**`track_alerts.json`** (B): array of the real (non-simulated) alerts above, sorted by `peak_score`.

---

## 6. Repository layout

> The repo has two trees: Role B's original work at the root, and the integrated app under `tools/footballslam/`
> (where A and C committed). **The deployed app is built only from `tools/footballslam/`.** Root-level copies of
> the map data are kept for reproducibility.

```
.
├── README.md                     ← this file
├── pixi.toml / pixi.lock         Python env (pixi)
├── map/                          Role B — trajectory layer
│   ├── vss.py                    VSS/GPU client (credentials from env or /config, never printed)
│   ├── detect.py                 per-frame detections (stored sidecar → hosted YOLO fallback)
│   ├── track.py                  SORT-lite + constant-velocity Kalman
│   ├── anomaly_track.py          d², ρ, Δθ, τ, EMA, hysteresis, flow field, wrong_way
│   ├── build_map.py              two-pass pipeline → map*.json, track_alerts.json, --inject, --mode NONE
│   ├── calib.py, team_colour.py  football-era homography + k-means kit split (kept, not in the traffic path)
│   ├── dev.html, dev_fixture.json, make_dev_fixture.py   standalone module test page
│   ├── NOTES_FOR_C.md            integration notes
│   └── tests/                    test_track, test_calib, test_track_anomaly (11 tests)
├── app/static/pitch.js, overlay.js   original module copies (served copies are in tools/footballslam/app/static/)
├── data/i24_cam-1/, data/neighborhood_cam-1/   first trajectory runs (scene1_p1c1 0000–0002, neighborhood 0000–0001)
└── tools/footballslam/           integrated project (A + C + B's served files)
    ├── README.md, DEMO_SCRIPT.md, CONTRACTS.md, PIVOT_TRAFFIC.md
    ├── app/                      main.py, requirements.txt, static/{index.html, app.js, style.css, pitch.js, overlay.js}
    ├── events/                   Role A — prompt.txt, events.py, attacks.py, features.py, anomaly.py, tests/
    ├── check/validate.py         JSON validator
    ├── fixtures/make_fixtures.py synthetic data/demo bundle
    ├── deploy/deploy.sh          K8s deploy (ConfigMap + Secret + Deployment/Service/Ingress at /app)
    ├── data/index.json           scenes and parts the app serves
    ├── data/{i24,neighborhood,pie}/   segments, attacks, anomalies, anomaly_report.md, map*.json, track_alerts.json
    ├── data/demo/, data/m1/      fixtures; football-era match data
    ├── recon/                    scene and stream reconnaissance notes
    └── docs/                     QA, recording, submission notes
```

---

## 7. Running everything

**Environment.** On the lab VM credentials and endpoints are already in environment variables (`INGRESS_URL`,
`USERNAME`, `PASSWORD`, `GPU_BEARER_TOKEN`, `S3_*`, `WANDB_*`); never hard-code or print them. The VM has no pip;
we bootstrapped a venv:
```bash
cd ~/vast-builders-challenge && python3 -m venv .venv && curl -sSfL https://bootstrap.pypa.io/get-pip.py | .venv/bin/python
.venv/bin/pip install numpy opencv-python-headless requests pytest flask boto3
PY=~/vast-builders-challenge/.venv/bin/python
cd ~/vast-builders-challenge/tools/footballslam          # repo root
```

**Lane A: episodes** (per scene: `i24`, `neighborhood`, `pie`)
```bash
$PY tools/footballslam/events/events.py  --match i24 --source vastdb --repair   # descriptions → grammar (W&B)
$PY tools/footballslam/events/attacks.py --match i24                            # episodes
$PY tools/footballslam/events/anomaly.py --match i24                            # scores + anomaly_report.md
```

**Lane B: trajectories** (any part listed in `index.json`)
```bash
IDX=tools/footballslam/data/index.json; P=20261001_055315_scene1_p1c1_chunk_0001
$PY map/build_map.py --scene i24 --part $P --index $IDX --mode FLOW  --out tools/footballslam/data/i24/map_$P.json
$PY map/build_map.py --scene i24 --part $P --index $IDX --inject swerve --out tools/footballslam/data/i24/map_sim_$P.json
$PY map/build_map.py --scene pie --part <pie part> --index $IDX --mode NONE --out tools/footballslam/data/pie/map_<pie part>.json
```
Missing detections are fetched automatically into `data/raw/det/<segment>/` (git-ignored). Useful flags:
`--primary` (also write `map.json`), `--warmup 15`, `--persist 9`, `--track-id N --at-t T`, `--sources file`.

**Adding a video.** Add the chunk to `index.json` (its six segment sources and t0/t1), run Lane A on the scene,
run Lane B for the part (FLOW for fixed cameras, NONE for moving ones), redeploy.

**Local app**
```bash
cd tools/footballslam && VSS_URL="$INGRESS_URL" VSS_USERNAME="$USERNAME" VSS_PASSWORD="$PASSWORD" PORT=8081 $PY app/main.py
# open http://localhost:8081/  (forward port 8081 in Cursor's Ports panel)
```

**Module test page** (no backend needed)
```bash
$PY map/make_dev_fixture.py && $PY -m http.server 8090
# http://localhost:8090/map/dev.html?map=dev_fixture.json
# http://localhost:8090/map/dev.html?map=<path to map_sim.json>&mode=FLOW&video=<local mp4>
```

---

## 8. Deployment

```bash
bash tools/footballslam/deploy/deploy.sh
```
- Kubernetes, team namespace `team-12`, public image `python:3.12-slim`, no image build.
- App code and data go in a ConfigMap. Files are stored as `f000…` with a manifest, because keys can't contain
  `/`. The pod copies them to `/code`, `pip install`s `requirements.txt` and runs `main.py`.
- VSS credentials go in a Secret. Inside the pod `VSS_URL` is the in-cluster backend Service.
- The Ingress is `video-lab-team-12.cosmos.vastdata.com`, path `/app(/|$)(.*)`, rewritten to `/`. Users open the
  public link above or the workshop **App** button.
- **Data packing:** only the scenes listed in `index.json` are packed, **gzipped** (≈ 500 KB encoded, under the
  900 KB budget); the start script gunzips them. The original fallback (uploading the data to S3 and setting
  `DATA_URL`) failed with an `SSLError` against the team S3 endpoint, so the gzip path is what's live.
- **Verify:** `kubectl -n team-12 get pods -l app=footballslam`; `curl http://video-lab-team-12.cosmos.vastdata.com/app/health`.

---

## 9. Testing

```bash
$PY -m pytest map/tests -q                          # 11 tests, Role B
$PY -m pytest tools/footballslam/events/tests -q    # Role A
$PY tools/footballslam/check/validate.py            # contract validator (see known noise in §11)
```
Role B tests:
- **Trajectory:** straight motion → no alert; sudden stop → `hard_braking` within 6 frames; 90° swerve → alert;
  opposite-direction car in a trained flow field → `wrong_way`.
- **Tracker:** crossing tracks keep their IDs; a 10-frame gap is re-acquired or cleanly re-created; 22 static
  tracks keep stable IDs.
- **Homography and k-means** (football era): exact DLT recovery; two-kit split; referee → team 2.

**End-to-end checks done:** a fresh clone reproduces the committed I-24 result exactly (τ = 11.29, same alert).
In the local and deployed app, every part shows its own boxes, Simulate fires on I-24 and Neighborhood, PIE and
GoPro parts are boxes-only, and all data routes return 200 (path traversal returns 404).

---

## 10. Design decisions and deviations

| Decision | Why |
|---|---|
| Use the pipeline's stored per-frame YOLO detections | All frames at 20–30 fps, ~0.3 s per segment, no GPU cost; hosted `/v1/infer` (~4.6 s) is the fallback |
| Kalman acceleration term at `q_dt = 0.2 s`, not the frame interval | At 30 fps the plan's `(0.5·s/dt²)²·0.1` allows ~22,000 px/s²: the filter follows everything, mean d² ≈ 0.3, nothing can alert |
| Persistence 9 frames (0.3 s), warm-up 15 | The plan's 3 frames is 0.1 s at 30 fps (detection jitter); with 3/10, I-24 gave 3–7 alerts per 30 s, now ≤ 1 |
| Second-stage matching in the tracker | A sharp manoeuvre loses IoU and would break the track exactly when it should be scored |
| ρ needs only the earlier speed above the gate; alert type from extremes over the whole alert | Otherwise a stop never reads as braking, and types were taken from the wrong frame |
| Two flow fields + coherence ≥ 0.6 for wrong way | Cells straddling opposite carriageways caused false wrong-way alerts |
| Two-pass scoring (learn τ, then score) | τ is the scene's own 99.5th percentile, so no threshold is tuned per camera |
| NONE mode on moving cameras | Image-space physics from a moving vehicle is meaningless (GoPro τ of 88–155 shows it); boxes only |
| Simulate removes overlapping detections and inserts a clean path | Duplicate YOLO boxes otherwise carried the real track and the injection never fired |
| Per-part maps + gzipped ConfigMap deploy | One map per scene drew part 1's boxes on other parts; the S3 offload failed on TLS |

---

## 11. Limits

- **Image-space physics**: no road calibration, so far vehicles are smaller and slower. The per-scene τ absorbs
  most of this.
- **Occlusions** drop boxes, break tracks and thin the flow field.
- **Episode resolution** is the 5-second segment.
- **Moving cameras** (PIE dashcam, NYC GoPro) get detections only; there's no trajectory anomaly layer there.
- **Simulated stop** doesn't cross the alert threshold, so Simulate uses swerve. Simulated reverse alerts as
  `unexplained_motion`, not `wrong_way`. Quiet chunks with no suitable vehicle have no Simulate.
- **New videos and episodes**: the two NYC GoPro clips and I-24 `p1c3_chunk_0007` were added late. They're listed
  under the "I-24 overhead" scene and have trajectory/box maps, but Lane A episodes weren't rerun for them, so the
  episode lane shows the scene's existing episodes.
- **`validate.py` noise**: it expects a different map row layout (`[id, cls, x, y, w, h, vx, vy, score]`) from the
  pivot contract the modules use, treats alert `u,v` as flow-cell indices, and flags some football-era keys in PIE
  files. The app is unaffected.
- `track_alerts.json` only holds real alerts; the Lane B timeline therefore doesn't show simulated ticks, and red
  boxes show "ALERT" rather than the type unless `app.js` passes `alerts` to `drawOverlay`.

---

## 12. Team, workflow and history

**Roles**

| Role | Owns |
|---|---|
| **A**, Events & anomaly | `events/**`, `segments.json`, `attacks.json`, `anomalies.json`, `anomaly_report.md` |
| **B**, Map & trajectories | `map/**`, `pitch.js`, `overlay.js`, `map*.json`, `track_alerts.json` |
| **C**, App, deploy, story | `app/main.py`, `app.js`, `index.html`, `style.css`, `check/`, `fixtures/`, `deploy/`, `index.json`, docs |

**Workflow.** Each person worked on their own branch (`a/…`, `b/…`, `c/…`) and merged through pull requests.
Pull requests: #1 `b/traffic-trajectories`, #2 `a/traffic-episodes`, #3 `c/traffic-site`, #4 and #5
`b/integrate-app`, #6 `b/deploy-gzip`. Pushing from the lab VMs needed a **classic** GitHub token with `repo`
scope (fine-grained tokens can't write to another user's personal repo), plus bypassing Cursor's broken askpass
helper:
```bash
env -u GIT_ASKPASS -u SSH_ASKPASS -u VSCODE_GIT_ASKPASS_MAIN -u VSCODE_GIT_ASKPASS_NODE -u VSCODE_GIT_IPC_HANDLE \
  GIT_TERMINAL_PROMPT=1 git push -u origin <branch>
```

**History.**
- **13:00, FootballSLAM.** The original plan: upload match footage with a custom Cosmos prompt, split it into
  attacks per team, find anomalous attacks, and draw a calibrated tactical map (4-point homography, k-means kit
  colours). The map layer (`calib.py`, `team_colour.py`, football pitch in `pitch.js`) was built and tested. No
  football footage got indexed in time, because ingest was the critical path.
- **14:30, pivot to traffic** (`PIVOT_TRAFFIC.md`). The archive's I-24, neighborhood and PIE cameras were already
  segmented, described, embedded and detected, so there was no upload risk. The football machinery was reused:
  team → camera, attack → episode, pitch → flow map; Kalman trajectory anomalies became the core of Lane B.
- **~16:00, integration.** The merge left Role B's files at the root while the app lived under
  `tools/footballslam/`. B wired the modules and data into the app, added NONE mode for moving cameras, per-part
  maps and three new videos, and fixed the deploy (gzip instead of S3).

---

## 13. Stack

VAST VSS index and VastDB · Cosmos3-Reason (segment descriptions) · Cosmos Embed1 (256-d visual vectors) ·
YOLO11 (per-frame detections) · W&B serverless inference (label extraction) · Kubernetes on the VAST lab cluster
(ConfigMap + Ingress at `/app`) · Flask + vanilla JS (no CDN) · numpy · Cursor and the workshop skills.
