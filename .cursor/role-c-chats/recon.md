# Recon — Role C writer

You are the Recon writer under the Role C integrator for FootballSLAM. You find one real indexed segment and test whether the video proxy can stream it. You do not change the app, the fixtures, or the match index.

Repo: `/home/ek836/vast-builders-challenge`. Work under `tools/footballslam/`.

## Read first

- `.cursor/rules/build-day.mdc`
- `.cursor/skills/retrieval/login/SKILL.md`
- `.cursor/skills/retrieval/videos/SKILL.md`

Use those skills for login, explore, and stream. Do not hand-roll auth. Never print, log, or commit credentials, tokens, or `/config` values. A JWT may be used in a request. It must not appear in `recon/**` or in your report.

## Exclusive paths

You may create and edit only:

- `tools/footballslam/recon/**`

## Do not

- Do not run git, kubectl, or `deploy.sh`.
- Do not edit `app/**`, `data/**`, `deploy/**`, `check/**`, `fixtures/**`, `events/**`, `map/**`.
- Do not upload video. Person A owns uploads.
- If you need a code change, write `tools/footballslam/recon/NOTES_FOR_C.md` (3 lines) and stop.

## Steps

Time box: 15 minutes. Recon that is still running at 15 minutes stops and reports what it has.

1. Log in with the retrieval login skill.
2. `GET /api/v1/videos/explore` and pick one indexed segment that has a playable `source`. Prefer a short segment. Record its `source` and, if the explore or metadata payload includes it, the parent `original_video`.
3. Probe streaming with the videos skill, using the token as the skill describes (`?token=` on `/api/v1/videos/stream`). Send a `Range: bytes=0-1023` request.
   - Probe the segment `source`.
   - Probe the parent `original_video` when you have one.
   - Record HTTP status, whether `Content-Range` / `Accept-Ranges` came back, and `Content-Type`. Do not download the object.
4. Write `tools/footballslam/recon/source.json`:

```json
{
  "source": "s3://…",
  "original_video": "s3://… or null",
  "segment_stream_ok": true,
  "parent_stream_ok": false
}
```

`segment_stream_ok` is true only for a 200 or 206 with a video content type. Same rule for `parent_stream_ok`.

5. Write `tools/footballslam/recon/STREAM_RECON.md` in under 30 lines: the two probe results, and one recommendation for the integrator, either "playlist of segment sources" or "parent original_video also streams". The playlist contract stays either way. This file only tells the integrator which URI to put in `data/index.json`.

## Done when

`recon/source.json` has a real `source` (not `s3://fixture/pending`) and both booleans are set from actual responses.

## Report

```
DONE recon
files: tools/footballslam/recon/source.json, tools/footballslam/recon/STREAM_RECON.md
segment_stream_ok: <true|false> status=<code>
parent_stream_ok: <true|false|no parent> status=<code>
recommendation: playlist | parent also streams
unfinished: <none, or what remains>
```

Do not paste the S3 URI into the report if it is very long; the integrator reads `source.json`. Do not paste the token.
