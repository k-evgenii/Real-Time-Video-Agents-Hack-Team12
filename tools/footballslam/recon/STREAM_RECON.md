# Stream recon

Picked the shortest explore timeline segment (0.71s, segment 5 of 5 on `20261008_075622_GX050001_chunk_0023.mp4`). Parent `original_video` came from the same explore chunk. Probe was `GET /api/v1/videos/stream` with `Range: bytes=0-1023` only.

## Segment source

- HTTP 206 Partial Content
- `Content-Range: bytes 0-1023/1388726`
- `Accept-Ranges: bytes`
- `Content-Type: binary/octet-stream`
- `segment_stream_ok`: false (206, but not a video content type)

## Parent original_video

- HTTP 206 Partial Content
- `Content-Range: bytes 0-1023/32338705`
- `Accept-Ranges: bytes`
- `Content-Type: binary/octet-stream`
- `parent_stream_ok`: false (206, but not a video content type)

## Recommendation

playlist of segment sources

Both URIs are range-capable and returned 1024 bytes, but neither response used a video content type, so do not treat the parent as stream-ok. Keep segment `source` URIs in `data/index.json`.
