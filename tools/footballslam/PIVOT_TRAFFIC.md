# PIVOT → TRAFFIC (14:30 BST). Delta on top of ROLE_A/B/C files. Roles, paths, contracts and code stay; semantics change.

**Clock:** 14:30 pivot sync (15 min, everyone reads this) · 14:45–15:20 build · **15:20 CP-T1** · 15:20–15:45 integrate + deploy · **15:45 freeze** · 15:50–16:08 record · 16:08–16:20 submit · 16:30 demo.

## 0. What changed and what it buys us
- **No uploads.** Pack A (I-24 overhead highway, `i24_cam-1`), Pack D (neighborhood cam), Pack B (PIE dashcam, `pie_cam-3`) are already segmented, described, embedded, and have YOLO sidecars. A1's upload chat is closed. The ingest critical path is gone.
- **Two anomaly layers, one per owner — this is now the original project brief plus the football machinery:**
  - **A — scene/episode anomalies (unsupervised, from Cosmos labels + Embed1 vectors)** = the football attacks pipeline with a traffic grammar. "Team" → **camera**. "Attack" → **episode** (run of segments with the same FLOW state).
  - **B — trajectory anomalies (Kalman residuals per tracked vehicle)** = v1 plan §4 on top of B's existing `track.py`. The "pitch" becomes a **flow map** (same `drawPitch` signature).
- **Scenes:** primary = **I-24 overhead** (fixed camera → clean Kalman + flow field). Secondary = **neighborhood cam** (fixed; stopped/reversing vehicles). Tertiary = **PIE dashcam** (moving camera → A's layer only; **B does not run Kalman on dashcam**).

## 1. Tools from the stack we use (and nothing else)
| Need | Skill / endpoint | Owner |
|---|---|---|
| JWT | `retrieval/login` | all |
| Which cameras/values exist | `retrieval/list-metadata` (`camera_id`, `location`, `capture_type`) | A, C |
| All segment rows + descriptions + **visual embeddings** in bulk | `vast-database/vastdb-read` (`query.py --include-vectors`, columns `source, original_video, reasoning_content, vectors_visual, camera_id, timing…`) | A |
| Fallback per-segment rows | `retrieval/videos` `/videos/metadata`, `/videos/explore` | A, C |
| Structured labels from existing free-text descriptions | **W&B serverless inference** (OpenAI-compatible, `WANDB_*` env) — A's `--repair` becomes the primary labeller | A |
| Clean structured labels for the 2 demo chunks | `ingest/reingest-chunk` (or `reingest-videos`, `chunk_count 1–2`) with the traffic prompt below | A (only A re-ingests) |
| Per-frame boxes | `retrieval/videos` `/videos/detections` sidecar or `$YOLO_URL/v1/infer include_frames` (`gpu/README`) — whichever B1 found | B |
| Segment video | `/videos/stream?source&token` via C's proxy | C |
| Candidate hunting + "find similar" | `retrieval/search` (`metadata_filters {"camera_id": …}`, `min_similarity 0.3`) | A, C |
| One-sentence explanation of a flagged moment (stretch) | Cosmos3-Reason `/v1/chat/completions` with `video_url` | C |
| Deploy | `deployment/deploy-app-no-registry` | C |
| Stretch: persist alerts | `vast-database/vastdb-write` → `hackathon.traffic_anomalies` | A |
Not used: `upload-video`, Canary, Embed1 direct calls (vectors already stored), `deploy`/`build-yamls`.

## 2. Contract deltas (C applies to `CONTRACTS.md`, `validate.py`, fixtures in the first 15 min)
- `index.json`: `match_id` → still the key, but it is a **scene** = one `camera_id` (`i24_cam-1`, `neighborhood_cam-1`, `pie_cam-3`). `teams` → `lanes: {"A": {"name":"Scene episodes (Cosmos)","colour":"#2f6df6"}, "B": {"name":"Trajectory alerts (Kalman)","colour":"#f6b02f"}}`. `map_mode`: `FLOW` (fixed cams) or `NONE` (dashcam). `parts` = parent chunks (`original_video`) of that camera that we chose (≤ 3 per scene, ≤ 10 min total).
- `segments.json`: fields renamed, same shape: `possession`→`flow` ∈ `F|M|D|S|U` (free/moderate/dense/stopped/unclear), `direction` ∈ `L|R|T|A|X|U` (left/right/toward/away/mixed/unclear), `zone`→`scene` ∈ `H|S|R|I|C|U` (highway/street/residential/intersection/dashcam/unclear), `n_players`→`n_vehicles`, add `n_peds`, `tempo`→`light` ∈ `D|N|R|U`. `events` vocabulary (closed): `lane_change hard_braking sudden_stop stopped_vehicle reversing wrong_way u_turn overtaking tailgating pedestrian_crossing pedestrian_in_road jaywalking cyclist emergency_vehicle collision near_miss debris parking turning none`. `parse_ok` = flow and scene parsed.
- `attacks.json` → **keep the filename and shape**, `team` = `"A"` always for episodes (the lane), add `flow` (the episode's state) and `ended_by` ∈ `flow_change|risk_event|end`.
- `anomalies.json`: `per_team` keys = `"A"` (episodes, from A) and `"B"` (trajectory alerts, **written by B into the same file? No** — B writes `data/<scene>/track_alerts.json`, C merges at render time). `feature_names` (10, new): `duration_s, n_seg, mean_vehicles, max_vehicles, mean_peds, n_risk_events, n_manoeuvres, share_dense_or_stopped, flow_code, ended_by_code`.
- `map.json`: `mode` ∈ `FLOW|NONE`; `p` rows get a 9th int: `score_x100` (Kalman anomaly score ×100, 0 if warming up); add top-level `flow: {"cols":8,"rows":8,"cells":[[ux,uy,n,mean_speed],…]}` (unit mean-velocity per grid cell, image space) and `alerts: [{track_id,t0,t1,type,peak_d2,peak_score,u,v}]`. x,y are the RELATIVE formula (image-normalised) — there is no homography now.
- `pitch.js`'s `drawPitch(canvas, frame, opts)` keeps its signature; `opts.mode==='FLOW'` draws a frame rectangle, grid arrows from `opts.flow`, dots coloured by lane colour and **red when `score_x100 ≥ 100`**, trails as before.

## 3. The maths (replaces plan v2 §6; Appendix A of v2 is now primary for B)

### 3.1 Traffic grammar (A owns `events/prompt.txt`; ≤ 800 chars; also the JSON schema for the W&B repair call)
```
You are a traffic analyst. Describe this clip using EXACTLY these lines:
SCENE: HIGHWAY | URBAN_STREET | RESIDENTIAL | INTERSECTION | DASHCAM | UNCLEAR
FLOW: FREE | MODERATE | DENSE | STOPPED | UNCLEAR
VEHICLES: <integer>
PEDESTRIANS: <integer>
DIRECTION: LEFT | RIGHT | TOWARD | AWAY | MIXED | UNCLEAR (dominant travel direction)
EVENTS: comma-separated subset of [lane_change, hard_braking, sudden_stop, stopped_vehicle, reversing, wrong_way, u_turn, overtaking, tailgating, pedestrian_crossing, pedestrian_in_road, jaywalking, cyclist, emergency_vehicle, collision, near_miss, debris, parking, turning, none]
LIGHT: DAY | NIGHT | RAIN | UNCLEAR
NOTE: one short sentence on anything unusual.
```
Two sources, same parser: (i) **repair-as-labeller**: feed every *existing* `reasoning_content` of the chosen cameras to the W&B LLM with "Convert this traffic description into the grammar; use UNCLEAR when not stated; never invent events." → covers hundreds of segments in minutes, no re-ingest; (ii) `reingest-chunk` of the 2 demo chunks with the prompt → clean native labels for the moments we narrate. If (ii) isn't indexed by 15:20, (i) alone ships.

### 3.2 Episodes (replaces attacks, §6.1)
```
walk segments of one parent chunk in time order
RISK = {collision, near_miss, hard_braking, sudden_stop, wrong_way, reversing, pedestrian_in_road, emergency_vehicle}
new episode when flow ∈ {F,M,D,S} and (no open episode or flow ≠ open.flow)
continue when flow == open.flow, or flow == U and previous was open.flow (≤ 1 U gap)
close when flow changes (ended_by=flow_change) or events ∩ RISK ≠ ∅ (ended_by=risk_event; segment stays in the episode) or chunk ends
```

### 3.3 Episode features (10) and anomaly score (unchanged algorithm: robust z + kNN, per **camera**)
`duration_s, n_seg, mean_vehicles, max_vehicles, mean_peds, n_risk_events, n_manoeuvres (lane_change+overtaking+u_turn+turning), share_dense_or_stopped, flow_code (F0 M1 D2 S3), ended_by_code (flow_change0 risk1 end2)`. `s_feat`, `s_emb` (mean-pooled `vectors_visual`, cosine kNN), `rank`, `flagged ≥ 2.5`, `agree` exactly as before. **Moment** = segment in the episode with the rarest events multiset over that camera (ties → non-empty NOTE). Reasons rendered with units ("mean vehicles 2.9σ above camera median (31 vs 12)").
Per-camera normalisation is the generalisability argument: a highway is not "anomalous" for having 30 cars; a residential street is not anomalous for having 1.

### 3.4 Trajectory anomalies (B; v1 plan §4 verbatim, condensed)
State `x=[px,py,vx,vy]`, CV model; `s=√(wh)`, `σ_m=max(2,0.08s)`, `R=σ_m²I`, `Q=q·[[dt⁴/4,0,dt³/2,0],[0,dt⁴/4,0,dt³/2],[dt³/2,0,dt²,0],[0,dt³/2,0,dt²]]`, `q=(0.5s/dt²)²·0.1`; innovation `y`, `S=HP⁻Hᵀ+R`, `d²=yᵀS⁻¹y ~ χ²(2)`.
Signals (confirmed tracks, age ≥ 10, matched this frame): (a) `r_norm=‖y‖/s`; (b) heading change `Δθ` and speed ratio `ρ` over 5 frames, only when speed > `0.15·s/dt`, `sig_b=max(Δθ/(π/2), |log ρ|/log 2.5)`; (c) `d²`.
Threshold `τ=max(9.21, quantile_0.995(scene d² pool, ≥300 samples))`. `inst=max(d²/τ, 0.5·r_norm/0.5 + 0.5·sig_b)`; `score←0.7·score+0.3·inst`; alert enters at `score ≥ 1` for 3 frames, exits `< 0.6` for 5, cooldown 30. Type: `ρ<0.4 → hard_braking/stop`, `ρ>2.5 → sudden_acceleration`, `Δθ>60° → swerve`, else `unexplained_motion`.
**Flow field (new, cheap, demo gold on I-24):** 8×8 grid over the image; each cell accumulates unit velocity vectors of confirmed tracks with speed > v_min; `wrong_way` alert when a track's unit velocity has `cos < −0.5` against a cell with `n ≥ 50` for 5 consecutive frames. Displayed as arrows on the flow map.
Unit tests (B2, synthetic): straight motion → mean d²≈2, no alerts; sudden stop → alert ≤ 4 frames; 90° swerve → alert; opposite-direction track in a trained flow field → `wrong_way`. **Simulate toggle stays** (inject stop/swerve into a real track; labelled on screen) — ship it, the highway may be boring.

## 4. Role deltas and new chat prompts (paste the §2.6 header from your role file above each)

### A — Events & Anomaly
Closed: A1 upload. **New A1-T (20 min): scene selection + labelling.**
```
Owned: events/**, data/<scene>/segments.json, attacks.json, anomalies.json, anomaly_report.md, events/prompt.txt. Read PIVOT_TRAFFIC.md §1–3.
1. list-metadata → confirm camera_id values for I-24, neighborhood, PIE. With vastdb-read (query.py conventions) pull for those three
   camera_ids: source, original_video, camera_id, reasoning_content, timing columns, and vectors_visual (--include-vectors) → cache to
   data/raw/rows_<camera>.parquet (or .json). Report counts per camera and per parent chunk; pick ≤ 3 parent chunks per camera (≤ 10 min
   total) preferring chunks whose existing descriptions mention braking/stopping/pedestrians (grep) — list them for C's index.json.
2. Replace events/prompt.txt with the traffic grammar (PIVOT §3.1). Repoint events.py: --labeller repair runs the W&B LLM over every
   cached reasoning_content of the chosen chunks (temperature 0, JSON schema = grammar keys, batch 10 per call, cache by source), parse,
   write segments.json with the renamed fields (PIVOT §2). Target parse_ok ≥ 0.8. Keep the regex path for native-grammar rows.
3. Start reingest-chunk for the 2 primary I-24 chunks with the traffic prompt (ask me to confirm the targets as the skill requires), poll;
   when indexed, re-run events.py on them (native rows override repaired ones).
```
A2 → rename logic only: `attacks.py` implements PIVOT §3.2 (episodes); tests updated (flow flip; one U gap; collision ends episode). A3 → feature list PIVOT §3.3; per-camera normalisation; everything else unchanged. Report tables per camera into `anomaly_report.md`.

### B — Map & Tracking → **Trajectory anomalies + flow map**
B1 unchanged (point `--batch` at the I-24 and neighborhood segment sources A posts; classes `{car, truck, bus, motorcycle, person, bicycle}`; conf ≥ 0.35). **B2 becomes the core of the original brief:**
```
Owned: map/**, data/<scene>/map.json, track_alerts.json, app/static/pitch.js, overlay.js. Read PIVOT_TRAFFIC.md §3.4 and §2 (map.json delta).
1. map/anomaly_track.py: implement §3.4 exactly on top of track.py (signals a/b/c, adaptive τ with a per-scene d² pool, EMA, persistence,
   hysteresis, cooldown, type labels) + the 8×8 flow field and wrong_way rule. tests/test_track_anomaly.py: the four synthetic tests.
2. build_map.py --scene <camera> --part <chunk> --mode FLOW --fps 5: detections → tracker → anomaly_track → map.json rows with
   score_x100, top-level flow cells and alerts[] (PIVOT §2). Drop calib/team_colour from the path (keep files, don't delete). Add
   --inject {stop,swerve,reverse} --track-id --at-t writing map_sim.json with "simulated": true.
3. Write data/<scene>/track_alerts.json = the alerts[] of all parts, sorted by peak_score, each with a one-line reason
   ("d²=18.4 vs τ=11.2 for 9 frames; speed ratio 0.31 → hard braking"). Print τ per scene and alert counts; aim for ≤ 1 alert / 30 s on
   a boring chunk — raise WARMUP to 15 or persistence to 4 if noisier.
4. Run on the first I-24 chunk as soon as B1 has detections; then neighborhood. Never on pie_cam-3.
```
B3 (pitch/overlay): add `FLOW` mode (frame rectangle, grid arrows from `opts.flow` scaled by `n`, dots red when `score_x100 ≥ 100`, trail of alerting tracks thicker), `overlay.js` colours boxes green→amber→red by `score_x100` and prints the alert type above the box. 25 minutes, then stop.

### C — App, Deploy, Story
C1-T (15 min, first): contract/validator/fixture deltas from §2 (fixtures: 60 segments with flow states, 12 episodes with 2 outliers, map.json with 15 cars, flow cells, 2 alerts). `index.json` scenes from A's chunk list; `map_mode FLOW` for I-24/neighborhood, `NONE` for PIE.
C3-T: timeline lane A = episodes coloured by `flow` (F light → S dark), flagged outlined red; **lane B = B's `track_alerts.json`** as short red ticks (type on hover), click → seek and highlight the track id in the overlay; anomaly panel gets two tabs **Episodes (Cosmos+Embed1)** / **Trajectories (Kalman)**; why card for episodes = z-bars as before, for trajectories = d² sparkline vs τ line (read `d2_hist` from `alerts[]` if B includes it; else just the numbers). Simulate toggle loads `map_sim.json`. Hide the flow panel when `map_mode==='NONE'`.
C4-T: README + DEMO_SCRIPT rewritten for traffic (§5 below); "find similar" button = `/api/v1/search` with the alert type phrase, `metadata_filters {camera_id}` off so it crosses cameras — that is the cross-pack payoff the organisers' own reference doc calls out. Submission text names: VAST VSS index, Cosmos3-Reason labels, Cosmos Embed1 vectors, YOLO11, W&B inference, Cursor skills.

## 5. Demo script (2:30) — replaces v2 §9
**[0:00]** "Traffic cameras produce hours of nothing and seconds that matter. We built two detectors that find those seconds with no labels and no training, on any camera in this archive."
**[0:20 Trajectories, I-24]** *(overlay + flow map)* "Every vehicle gets a constant-velocity Kalman filter; the arrows are the lane flow the system learned in 20 seconds. Green = physics agrees. There — vehicle 14: predicted here, actually here; Mahalanobis 18 against a threshold this camera set for itself at 11; three frames → *hard braking*." *(Simulate toggle if the real clip is quiet: "and here's an injected wrong-way track — the flow field catches it in five frames; it's labelled simulated.")*
**[1:05 Episodes]** *(timeline + tab)* "Second layer, coarser: Cosmos Reason already described every segment; a small LLM pass converts that to a fixed grammar — flow, vehicles, events. Runs of the same flow state become episodes. Per camera we robust-z-score ten plain features and rank episodes by nearest-neighbour distance. Episode 9: vehicles 2.9σ above this camera's median, two risk events, ended in a stop. Independently, in Cosmos's visual-embedding space, the same episode is the furthest from its neighbours — that view never saw our labels."
**[1:50 Generalise]** *(switch scene to the neighborhood cam, then dashcam tab)* "Same code, residential street: the thresholds re-learn themselves — nothing is tuned per camera. On the moving dashcam we switch the physics layer off and keep the episode layer; the system knows what it can't claim."
**[2:15 Close]** "Limits: image-space physics, occlusions, and segment-length resolution. But today: two unsupervised anomaly detectors over the whole archive, explainable to the sigma, 'find more like this' across cameras. Thank you."

## 6. What we keep, cut, and risk
**Keep (reuse as-is):** repo, contracts machinery, validate.py, fixtures generator, Flask proxy + deploy, frontend shell, `track.py`, k-NN anomaly code, parser + repair path, W&B client.
**Cut now:** uploads, homography/calib, team colour, football prompt, "attacks" wording in UI (rename to episodes), Kalman on dashcam, VastDB write (unless A is idle at 15:30).
**Risks:** (1) W&B repair over hundreds of rows is slow → batch 10 descriptions per call, cap at 300 segments per camera; (2) reingest-chunk not back by 15:20 → repaired labels only, say so; (3) I-24 clips have no real trajectory anomaly → Simulate toggle, labelled; (4) `vectors_visual` read fails → `s_emb=null`; (5) time → CP-T1 at 15:20 is the only gate: real episodes for ≥ 1 camera in the deployed app + track alerts on ≥ 1 chunk. Everything not visible at 15:45 is cut from the script, not fixed.
