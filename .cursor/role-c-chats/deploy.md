# Deploy — Role C writer

You are the Deploy writer under the Role C integrator for FootballSLAM. You write `deploy.sh`. You do not execute it, and you do not edit the Flask app.

Repo: `/home/ek836/vast-builders-challenge`. Work under `tools/footballslam/`.

## Read first

- `.cursor/rules/build-day.mdc`
- `.cursor/skills/deployment/deploy-app-no-registry/SKILL.md` (follow it; do not invent a hostname or a Docker build)

Never print, log, or commit credentials, tokens, or `/config` values. The script may read `/config/<team>.config` and the kubeconfig at runtime. It must not echo passwords.

## Exclusive paths

You may create and edit only:

- `tools/footballslam/deploy/deploy.sh`

## Do not

- Do not run `deploy.sh`, kubectl, git, or a local Flask server.
- Do not edit `app/**`, `data/**`, `recon/**`, `check/**`, `fixtures/**`, `events/**`, `map/**`.
- Do not `docker build` or push an image.
- If you need a change outside this file, write the note into a comment block at the top of `deploy.sh` labelled `NOTES_FOR_C` and stop.

## What the script must do

Idempotent. A second run updates the ConfigMap and restarts the rollout.

- `APP_NAME=footballslam`
- Resolve the team the way the skill does: exactly one `/config/*.config`, `NS` from `USERNAME`, `KUBECONFIG=/config/${NS}-k8s.yaml`, `APP_HOST=video-lab-team-<N>.cosmos.vastdata.com` where `<N>` is `USERNAME` with the `team-` prefix removed.
- Public image `python:3.12-slim`. Listen on `PORT=8080`. Working dir `/code`. Install `requirements.txt` if present, then `exec python main.py`.
- Secret `footballslam-vss-creds` with `VSS_URL` (the config's `INGRESS_URL`), `VSS_USERNAME`, `VSS_PASSWORD`. Add `DATA_URL` only when data is offloaded (below).
- Ingress on `$APP_HOST`, path `/app(/|$)(.*)`, rewrite so the container sees `/`. Do not create a new hostname. Do not use path `/`.
- Readiness probe `GET /health` on 8080.

ConfigMap constraint: `kubectl create configmap --from-file` is not recursive, and ConfigMap keys cannot contain `/`. `app/static/` will not appear in the pod if you only pack the top of `app/`. The container start command must materialize `static/` (stage the files into the ConfigMap under flat keys, then have the start script write them back to `static/` before `python main.py`, or an equivalent that still uses the skill's public image and Ingress). Pack `app/main.py`, `app/requirements.txt`, and the static files. Also pack `data/index.json` and `data/<match>/*.json` when the packed JSON is under 900 KB.

If `data/` would push the ConfigMap over 900 KB, do not pack `data/`. Upload `data/` to the team S3 bucket using credentials from `/config` (boto3 or aws cli, without printing the keys) and set `DATA_URL` in the Secret to the prefix the server fetches (`$DATA_URL/<match>/<name>.json`).

The script ends by printing three non-secret lines: namespace, app host, and the kubectl rollout command the integrator should expect. It may include `kubectl rollout status` when the integrator runs it. Do not run it yourself.

## Steps

Time box: 25 minutes.

1. Read the deploy-app-no-registry skill end to end.
2. Write `tools/footballslam/deploy/deploy.sh` as above. `bash -n tools/footballslam/deploy/deploy.sh` must pass.
3. Stop. The integrator runs the script.

## Done when

`bash -n` exits 0, the script name and host match the skill, static files are handled despite the ConfigMap key rule, and you did not apply anything to the cluster.

## Report

```
DONE deploy
files: tools/footballslam/deploy/deploy.sh
bash -n: <exit code>
static staging: <one line on how static/ is recreated in the pod>
data over 900KB: <S3 + DATA_URL, or packed in the ConfigMap>
unfinished: <none, or what remains>
```
