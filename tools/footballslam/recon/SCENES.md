# Scenes

Fallback parent list until Person A posts one. When A posts a chunk list, A's list wins.

Live `camera_id` values from `GET /api/v1/metadata/values` match the expected ids: `i24_cam-1`, `neighborhood_cam-1`, `pie_cam-3`. Explore `scope=all` (613 parents) filtered to those ids. Archive counts: I-24 30, neighborhood 52, PIE 180.

| camera_id | map_mode | parents | segments | duration |
|---|---|---|---|---|
| i24_cam-1 | FLOW | 3 | 18 | 90s |
| neighborhood_cam-1 | FLOW | 3 | 18 | 90s |
| pie_cam-3 | NONE | 3 | 18 | 90s |

Each parent is 30s (6 segments × 5s). `duration_s` is the sum of segment spans. `idx` is explore `segment_number` minus 1 (the API numbers segments from 1).

Parents (titles and metadata match the pack):

- `i24_cam-1` FLOW: `scene1_p1c1` chunks 0000, 0001, 0002. location `nashville`, capture_type `traffic`. Same overhead camera. Also under this id: `scene1_p1c2` and `scene1_p1c3` (10 chunks each).
- `neighborhood_cam-1` FLOW: `neighborhood_20260901` chunks 0000 (parked vehicles), 0002 (SUV driving), 0006 (person on the sidewalk). location `neighborhood`, capture_type `streets`.
- `pie_cam-3` NONE: `set01_video` chunks 0000, 0001, 0002. location `toronto`, capture_type `streets`. Chunk 0000 is a stop with brake lights. Dashcam, so no flow map.

Probe: `GET /api/v1/videos/stream` with `Range: bytes=0-1023` on segment 001 of the first parent. 1024 bytes read and discarded. All three sent `Content-Range`.

- i24_cam-1 `20261001_055249_scene1_p1c1_chunk_0000_segment_001_of_006.mp4`: 206, `binary/octet-stream`, `Content-Range: bytes 0-1023/5646068`
- neighborhood_cam-1 `20261001_072331_neighborhood_20260901_chunk_0000_segment_001_of_006.mp4`: 206, `binary/octet-stream`, `Content-Range: bytes 0-1023/5053678`
- pie_cam-3 `20261001_060529_set01_video_chunk_0000_segment_001_of_006.mp4`: 206, `binary/octet-stream`, `Content-Range: bytes 0-1023/4216465`
