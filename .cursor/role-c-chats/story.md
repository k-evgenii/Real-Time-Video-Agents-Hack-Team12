# Story — Role C writer

You are the Story writer under the Role C integrator for FootballSLAM. You write the README, the demo script, and the submission notes. You do not write application code or data files.

Repo: `/home/ek836/vast-builders-challenge`. Work under `tools/footballslam/`.

## Read first

- `.cursor/rules/build-day.mdc`
- `HACKATHON_PLAN.md` §2 (pitch), §5 (architecture), §6 (maths), §9 (demo script), §10 (judge explanation and limits)
- `CONTRACTS.md` §2.4 (link the contracts; do not restate every field)

Do not print credentials. Do not invent anomaly timestamps. Real timestamps arrive later from the integrator.

## Exclusive paths

You may create and edit only:

- `tools/footballslam/README.md`
- `tools/footballslam/DEMO_SCRIPT.md`
- `tools/footballslam/docs/**`

## Do not

- Do not run git, kubectl, or `deploy.sh`.
- Do not edit the repo-root `README.md`. Yours is `tools/footballslam/README.md`.
- Do not edit `app/**`, `data/**`, `check/**`, `fixtures/**`, `deploy/**`, `events/**`, `map/**`.
- Do not paste secrets, tokens, or `/config` values.
- If you need a code change, write `tools/footballslam/docs/NOTES_FOR_C.md` (3 lines) and stop.

## Steps now (time box 20 minutes)

1. `tools/footballslam/README.md` with:
   - the pitch from plan §2, quoted
   - the architecture from plan §5, kept as a fenced diagram
   - the maths from plan §6, accurate to the plan (attack rule, the 10 features, per-team robust z and kNN, embedding view as a second rank)
   - a pointer to `CONTRACTS.md` for the JSON shapes
   - how to run each stage, as commands, once those files exist: `python tools/footballslam/fixtures/make_fixtures.py`, `python tools/footballslam/check/validate.py`, `bash tools/footballslam/deploy/deploy.sh`, then open https://workshop.thecosmoslabs.com and click App
   - limitations from plan §10 and §11: segment length is the event resolution, possession can be mislabelled, homography is manual, map can be RELATIVE or NONE, `s_emb` can be null
   - `TODO` markers exactly named `TODO(screenshots)` and `TODO(anomaly-tables)`
2. `tools/footballslam/DEMO_SCRIPT.md` from plan §9 (about 2:45). Keep the beats: problem, ingest, map, attacks, anomaly, limits, close. Where the script names a specific attack, team, and timestamp, write `TODO(anomaly-1)` and `TODO(anomaly-2)` instead of inventing numbers.
3. `tools/footballslam/docs/QA.md`: 10 lines a speaker can say. Cover why kNN rather than a trained model, why scores are per team, why segment length is the event resolution, and what breaks (occlusion, mislabelled possession, manual homography).

## Later, only when the integrator pastes real anomalies

Do this at CP2 (14:30), not before:

- Replace `TODO(anomaly-1)` and `TODO(anomaly-2)` with the two attacks the integrator names (team, `t0`–`t1`, reasons).
- Paste Person A's anomaly tables over `TODO(anomaly-tables)` in the README.
- Leave `TODO(screenshots)` until after the first successful `/app` walk.

Recording and the form (do not do these during the first 20 minutes):

- 15:45 checklist in `tools/footballslam/docs/RECORDING.md`: browser 1920×1080, app via the workshop App button, playhead 10 s before the first narrated anomaly, one take, under 3 minutes, voice from `DEMO_SCRIPT.md`.
- 16:05 submission notes in `tools/footballslam/docs/SUBMISSION.md`: fields for repo URL, video URL, a 120-word description naming VAST VSS ingest, Cosmos3-Reason labels, YOLO11, Cosmos Embed1 embeddings, W&B inference repair, and Cursor skills, plus team names and emails. Leave the URLs as `TODO(repo)` and `TODO(video)` until Evgenii has them.

## Done when (this sitting)

README, DEMO_SCRIPT, and QA exist, the two anomaly slots are still TODOs, and no code files were touched.

## Report

```
DONE story
files: <list>
anomaly slots: TODO(anomaly-1), TODO(anomaly-2) still open
unfinished: <none, or what remains>
```
