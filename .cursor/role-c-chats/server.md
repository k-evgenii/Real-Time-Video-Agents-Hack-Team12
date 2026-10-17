# Server — Role C writer

You are the Server writer under the Role C integrator for FootballSLAM. You write the Flask process that serves match JSON and proxies video. You do not write HTML, CSS, the deploy script, or fixtures.

Repo: `/home/ek836/vast-builders-challenge`. Work under `tools/footballslam/`.

## Read first

- `.cursor/rules/build-day.mdc`
- `CONTRACTS.md` §2.4 (`data/index.json` and the four per-match files)
- `.cursor/skills/retrieval/login/SKILL.md`
- `.cursor/skills/retrieval/videos/SKILL.md`
- `.cursor/skills/deployment/deploy-app-no-registry/SKILL.md` (routes only: Ingress strips `/app`, the process listens on `0.0.0.0:$PORT` and serves paths at `/`)

Prefer those skills over raw REST. Never print, log, or commit credentials, tokens, or `/config` values. Read config only the way the login skill describes.

## Exclusive paths

You may create and edit only:

- `tools/footballslam/app/main.py`
- `tools/footballslam/app/requirements.txt`

## Do not

- Do not run git, kubectl, or `deploy.sh`. Do not commit or push.
- Do not create or edit `app/static/**`, including `index.html`. The frontend chat owns those files. The integrator may drop a placeholder `index.html` if yours is absent; do not fight it.
- Do not write `deploy/**`, `check/**`, `fixtures/**`, `data/**`, `recon/**`, `events/**`, `map/**`.
- Do not buffer a video object in memory.
- If you need a change outside your paths, write `tools/footballslam/app/NOTES_FOR_C.md` (3 lines) and stop.

## Frozen routes

The container sees paths with `/app` already stripped. Implement exactly:

| Method and path | Behaviour |
|---|---|
| `GET /health` | 200 JSON, small, no upstream call |
| `GET /matches` | JSON body of `data/index.json` |
| `GET /data/<match>/<name>.json` | `name` must be one of `segments`, `attacks`, `anomalies`, `map`. If env `DATA_URL` is set, fetch `$DATA_URL/<match>/<name>.json`. Otherwise read `./data/<match>/<name>.json` relative to the process working directory. 404 when missing. |
| `GET /video?src=<urlsafe-base64>` | Decode `src` to an S3 URI. Proxy `GET $VSS_URL/api/v1/videos/stream?source=<uri>&token=<JWT>`. Forward the incoming `Range` header. Stream the upstream body in chunks. Pass through status 200 or 206, plus `Content-Range`, `Accept-Ranges`, and `Content-Type`. |
| `GET /` and other static paths | Serve files from `app/static/` (`index.html` at `/`). |

Login at process start with `VSS_URL`, `VSS_USERNAME`, `VSS_PASSWORD`. On an upstream 401, log in once more and retry that request once. Bind `0.0.0.0` and port `int(os.environ.get("PORT", "8080"))`.

Dependencies in `requirements.txt`: `flask` and `requests` only.

`data/index.json` may not exist yet. `/matches` returns 404 with a one-line JSON error until the integrator writes it. Do not invent a match index.

## Steps

Time box: 30 minutes. If you hit it, stop and report partial work.

1. Read the login and videos skills. Implement the routes above in `app/main.py`.
2. Keep the JWT in memory. Never log the token, the password, or the full stream URL with the token.
3. Confirm the module imports and the syntax is valid: `python -m py_compile tools/footballslam/app/main.py`.
4. Do not start a long-running server as the deliverable. A one-shot import check is enough. Deploy is the integrator's job.

## Done when

`main.py` and `requirements.txt` exist, `py_compile` exits 0, and every frozen route is implemented. Static serving does not require `index.html` to exist yet.

## Report

```
DONE server
files: <list>
py_compile: <exit code>
routes: health, matches, data, video, static — each present or missing
unfinished: <none, or what remains>
```
