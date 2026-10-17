# Traffic detectors

## Pitch

Traffic cameras produce hours of nothing and seconds that matter.

Two detectors find those seconds with no labels and no training, on any camera in this archive.

## Two layers

**Episodes (lane A).** Cosmos3-Reason already described every segment. A W&B inference pass turns that free text into a fixed grammar: flow, vehicle count, pedestrians, direction, events, light. A run of segments in the same flow state is an episode. Per camera, ten plain features are robust-z-scored and episodes are ranked by k-nearest-neighbour distance. A second rank mean-pools Cosmos Embed1 visual vectors; that view never sees the labels. Scores use that camera's own median, so a highway is ordinary for having many cars and a residential street is ordinary for having one.

**Trajectory alerts (lane B).** On a fixed camera, each confirmed vehicle is a constant-velocity Kalman filter in the image. Innovation, a short-window heading and speed change, and Mahalanobis distance against a threshold taken from that scene's own residual pool become a score. An 8×8 flow field stores the lane direction those tracks accumulate, and a track against a well-filled cell is a wrong-way alert. This layer is off on the dashcam.

## Scenes

| Scene | Camera | Map |
|---|---|---|
| I-24 overhead | `i24_cam-1` | `FLOW` |
| Neighborhood | `neighborhood_cam-1` | `FLOW` |
| PIE dashcam | `pie_cam-3` | `NONE` |

`FLOW` draws the frame, the flow arrows, and the vehicle dots. `NONE` hides the flow panel. The episode timeline still runs on all three.

Find-similar searches the archive with the alert phrase and the camera filter off, so a hit on one camera can surface the same kind of moment on another.

## How to run

From the repo root:

```bash
python3 tools/footballslam/fixtures/make_fixtures.py
python3 tools/footballslam/check/validate.py
bash tools/footballslam/deploy/deploy.sh
```

Then open https://workshop.thecosmoslabs.com and click App.

## Episode table

TODO(episode-table)

## Trajectory table

TODO(trajectory-table)

## Screenshots

TODO(screenshots)

## Stack

VAST VSS index, Cosmos3-Reason labels, Cosmos Embed1 vectors, YOLO11, W&B inference, Cursor skills.

## Limits

- Physics is image-space. x and y on the flow map are image-normalised.
- Occlusions drop boxes, break tracks, and thin the flow field.
- Episode resolution is the segment length. A manoeuvre inside one segment is one row, not its own episode.
- The PIE dashcam is a moving camera. Kalman and the flow field stay off; only the episode layer runs.
- If the two demo chunks are not re-ingested in time, the labels are the repaired reading of the descriptions already in the index, and the demo says so.
