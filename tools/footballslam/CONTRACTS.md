# Traffic contract

Scene files keep the football names. The values are traffic. `match_id` is one camera, not a match. Person A writes episode files. Person B writes the flow map and `track_alerts.json`. The integrator writes `data/index.json`. Fixtures live in `data/demo/` and are not a live scene.

`python3 tools/footballslam/check/validate.py` checks this file. Stdlib only. A missing `data/index.json` is skipped. Exit 0 is clean. Exit 1 prints a list of violations.

## 2. File shapes

Paths:

| File | Owner | Required |
|---|---|---|
| `data/index.json` | integrator | no — validator skips it when missing |
| `data/<scene>/segments.json` | A | yes for a scene the site plays |
| `data/<scene>/attacks.json` | A | yes — episodes, filename unchanged |
| `data/<scene>/anomalies.json` | A | yes — lane A only |
| `data/<scene>/map.json` | B | yes when `map_mode` is `FLOW` |
| `data/<scene>/track_alerts.json` | B | optional — checked when present |
| `data/<scene>/map_sim.json` | B | optional — checked when present |

`<scene>` is the `camera_id` (`i24_cam-1`, `neighborhood_cam-1`, `pie_cam-3`, or another live id). The synthetic bundle is the directory `data/demo/` with `match_id` `i24_cam-1`.

### 2.1 `index.json`

```json
{
  "matches": [
    {
      "match_id": "i24_cam-1",
      "title": "I-24 overhead",
      "lanes": {
        "A": {"name": "Scene episodes (Cosmos)", "colour": "#2f6df6"},
        "B": {"name": "Trajectory alerts (Kalman)", "colour": "#f6b02f"}
      },
      "map_mode": "FLOW",
      "parts": [
        {
          "original_video": "s3://…",
          "segments": [{"idx": 0, "t0": 0, "t1": 8, "source": "s3://…"}]
        }
      ]
    }
  ]
}
```

- `match_id` is one camera.
- `lanes.A` is scene episodes. `lanes.B` is trajectory alerts. Names and colours above are exact.
- `map_mode` is `FLOW` (fixed camera) or `NONE` (dashcam). `FULL` and `RELATIVE` are violations.
- At most 3 `parts`, and the segment durations on a scene sum to at most 600 seconds.
- The key `teams` is a violation.

### 2.2 `segments.json`

```json
{
  "match_id": "i24_cam-1",
  "segments": [
    {
      "match_id": "i24_cam-1",
      "part": 0,
      "seg_idx": 0,
      "t0": 0,
      "t1": 8,
      "flow": "F",
      "direction": "R",
      "scene": "H",
      "n_vehicles": 12,
      "n_peds": 0,
      "light": "D",
      "events": ["none"],
      "note": "",
      "source": "s3://…",
      "original_video": "s3://…",
      "parse_ok": true
    }
  ]
}
```

| Field | Values |
|---|---|
| `flow` | `F` free, `M` moderate, `D` dense, `S` stopped, `U` unclear |
| `direction` | `L` left, `R` right, `T` toward, `A` away, `X` mixed, `U` unclear |
| `scene` | `H` highway, `S` street, `R` residential, `I` intersection, `C` dashcam, `U` unclear |
| `n_vehicles`, `n_peds` | integers ≥ 0 |
| `light` | `D` day, `N` night, `R` rain, `U` unclear |
| `events` | closed list below; `none` only by itself |
| `parse_ok` | true exactly when `flow` and `scene` are both in their enums |

Events: `lane_change`, `hard_braking`, `sudden_stop`, `stopped_vehicle`, `reversing`, `wrong_way`, `u_turn`, `overtaking`, `tailgating`, `pedestrian_crossing`, `pedestrian_in_road`, `jaywalking`, `cyclist`, `emergency_vehicle`, `collision`, `near_miss`, `debris`, `parking`, `turning`, `none`.

Football keys that fail the validator: `possession`, `zone`, `n_players`, `tempo`, `ball`, `teams`.

### 2.3 `attacks.json`

Filename stays. Each object is one episode (a run of one flow state). `team` is always `"A"`.

```json
{
  "match_id": "i24_cam-1",
  "attacks": [
    {
      "attack_id": "ep-01",
      "team": "A",
      "flow": "F",
      "t0": 0,
      "t1": 40,
      "n_seg": 5,
      "part": 0,
      "scenes": ["H"],
      "events": ["none"],
      "ended_by": "flow_change"
    }
  ]
}
```

- `flow` is the episode state: `F|M|D|S` (not `U`).
- `ended_by` is `flow_change`, `risk_event`, or `end`.
- `t0` is the first segment start, `t1` the last segment end.

### 2.4 `anomalies.json`

Lane A only. B does not write this file. `s_emb` may be null. `agree` is true only when both `s_feat` and `s_emb` are numbers ≥ 2.5.

```json
{
  "match_id": "i24_cam-1",
  "feature_names": [
    "duration_s",
    "n_seg",
    "mean_vehicles",
    "max_vehicles",
    "mean_peds",
    "n_risk_events",
    "n_manoeuvres",
    "share_dense_or_stopped",
    "flow_code",
    "ended_by_code"
  ],
  "per_team": {
    "A": [
      {
        "attack_id": "ep-10",
        "rank": 1,
        "s_feat": 4.2,
        "s_emb": null,
        "flagged": true,
        "agree": false,
        "features": [40, 5, 49, 52, 7, 3, 0, 1, 3, 1],
        "z": [0, 0, 5, 5, 5, 5, 0, 5, 3.4, 5],
        "reasons": ["mean vehicles 5.0σ above camera median (49 vs 12)"],
        "moment": {"t": 392, "seg_idx": 49, "source": "s3://…"}
      }
    ]
  }
}
```

`feature_names` is exactly those 10 strings, in that order. `per_team` has the key `"A"` and no other key. `rank` 1 is the most anomalous. `z` has 10 numbers in `[-5, 5]`, aligned with `feature_names`. `flagged` is true when `s_feat ≥ 2.5` or `s_emb ≥ 2.5`.

Feature codes: `flow_code` is F0 M1 D2 S3. `ended_by_code` is flow_change 0, risk_event 1, end 2. `n_manoeuvres` counts `lane_change`, `overtaking`, `u_turn`, `turning`. `share_dense_or_stopped` is the share of segments whose `flow` is `D` or `S`.

### 2.5 `map.json`

`mode` is `FLOW` or `NONE`. There is no homography. `x` and `y` are image-normalised onto a 1050 by 680 decimetre frame (105 m by 68 m).

Each `p` row is 9 ints: the 8 tracking ints, then `score_x100` (Kalman score times 100, 0 while warming up, 0–999).

| Index | Name | Meaning |
|---|---|---|
| 0 | `track_id` | int ≥ 0 |
| 1 | `cls` | 0 car, 1 truck, 2 bus, 3 motorcycle, 4 person, 5 bicycle |
| 2 | `x` | 0–1050 decimetres across the frame |
| 3 | `y` | 0–680 decimetres down the frame |
| 4 | `w` | box width in decimetres, 1–400 |
| 5 | `h` | box height in decimetres, 1–400 |
| 6 | `vx` | decimetres per second, may be negative |
| 7 | `vy` | decimetres per second, may be negative |
| 8 | `score_x100` | 0–999; draw the dot red when ≥ 100 |

```json
{
  "match_id": "i24_cam-1",
  "mode": "FLOW",
  "fps": 1,
  "flow": {
    "cols": 8,
    "rows": 8,
    "cells": [[1.0, 0.0, 60, 40.0]]
  },
  "alerts": [
    {
      "track_id": 4,
      "t0": 80,
      "t1": 88,
      "type": "hard_braking",
      "peak_d2": 18.4,
      "peak_score": 1.6,
      "u": 3,
      "v": 2
    }
  ],
  "frames": [{"t": 0, "p": [[4, 0, 120, 200, 36, 18, 80, 0, 0]]}]
}
```

`FLOW` requires `flow.cols = 8`, `flow.rows = 8`, and 64 `cells` in row-major order (`v * 8 + u`). A cell is `[ux, uy, n, mean_speed]`: unit velocity in image space (`+ux` right, `+uy` down), sample count `n`, and `mean_speed`. `NONE` omits the grid; `alerts` may be empty.

Alert `type` is one of `hard_braking`, `hard_braking/stop`, `stop`, `sudden_acceleration`, `swerve`, `unexplained_motion`, `wrong_way`. `u` and `v` are grid indices 0–7. Optional `tau`, `d2_hist`, and `reason` are passed through.

### 2.6 Optional files

`track_alerts.json` is an array. Each object has the `map.alerts` fields plus a one-line `reason` string.

`map_sim.json` is a `map.json` object plus `"simulated": true`.

## 3. Fixture

`python3 tools/footballslam/fixtures/make_fixtures.py` rewrites `data/demo/` for `i24_cam-1`. Every `source` and `original_video` is `s3://fixture/pending`. `map.json` stays under 400 KB.
