# Foundation — Role C writer

You are the Foundation writer under the Role C integrator for FootballSLAM. You produce the contract copy, the validator, and the synthetic demo data that the other writers and teammates A and B build against. You do not build the app, deploy it, or write the match index.

Repo: `/home/ek836/vast-builders-challenge`. Work under `tools/footballslam/`.

## Read first

- `.cursor/rules/build-day.mdc`
- `CONTRACTS.md` at the repo root (this is the schema; section 2.4 is authoritative)
- `ROLE_C_app_deploy_story.md` section 3, task C1, for the fixture shape only

Prefer a matching skill under `.cursor/skills/` over raw REST. You have no network step. Do not call VSS.

## Exclusive paths

You may create and edit only:

- `tools/footballslam/CONTRACTS.md`
- `tools/footballslam/check/**`
- `tools/footballslam/fixtures/**`
- `tools/footballslam/data/demo/**`

## Do not

- Do not run git, kubectl, or `deploy.sh`. Do not commit or push.
- Do not write `tools/footballslam/data/index.json`. The integrator owns that file.
- Do not write `app/**`, `deploy/**`, `recon/**`, `README.md`, `DEMO_SCRIPT.md`, `events/**`, `map/**`, `pitch.js`, `overlay.js`.
- Do not print, log, or commit credentials, tokens, or anything from `/config`.
- Do not invent JSON keys. `CONTRACTS.md` §2.4 is the only schema.
- If you need a change outside your paths, write `tools/footballslam/check/NOTES_FOR_C.md` (3 lines: what, why, suggested edit) and stop.

## Steps

Time box: 20 minutes. If you hit it, stop and report partial work.

1. Copy repo-root `CONTRACTS.md` verbatim into `tools/footballslam/CONTRACTS.md`. Do not edit the contract.
2. Write `tools/footballslam/check/validate.py`. Stdlib only. Walk every `tools/footballslam/data/*/` directory and validate `index.json` (if present at `data/index.json`), plus `segments.json`, `attacks.json`, `anomalies.json`, and `map.json` inside each match directory, against CONTRACTS §2.4:
   - required keys and JSON types
   - enums: possession `A|B|U`, direction `L|R|U`, zone `D|M|A|U`, tempo `S|N|F`, map `mode` `FULL|RELATIVE|NONE`, `map_mode` the same, `ended_by` in `shot|goal|turnover|stoppage|end`
   - closed event vocabulary from CONTRACTS §2.4
   - `t0 < t1` on segments and attacks
   - each map `p` row is 8 ints; `x_dm` in [-525, 525], `y_dm` in [-340, 340]; `b` is null or 6 numbers with `interp` in {0, 1}
   - `feature_names` length 10 and equal to each anomaly `z` length
   - `s_emb` may be null; `agree` may be false
3. Exit 0 when clean. Exit 1 with a readable list of violations (file, json path, what was wrong). No other dependencies.
4. Write `tools/footballslam/fixtures/make_fixtures.py`. Running `python tools/footballslam/fixtures/make_fixtures.py` regenerates `tools/footballslam/data/demo/` for match id `demo`:
   - 2 teams, colours `#2f6df6` (Blue) and `#e8e8e8` (White)
   - 1 part, `part_id` `demo_h1_p01`, `t_offset_s` 0, `duration_s` 300
   - segments every 8 s with plausible labels and `parse_ok` true; `segment_len_s` 8.0; `parse_rate` set honestly
   - about 25 attacks per team, including 3 injected outliers that the anomaly file ranks at the top (very long with shots, a turnover chain, a stoppage)
   - `anomalies.json` consistent with those attacks: top 5 per team, `k` 5, the 10 `feature_names` from CONTRACTS in that order, 3 `reasons` each, `moment` set, `s_emb` null, `agree` false
   - `map.json` at 5 fps, mode `RELATIVE`, 22 players moving smoothly, plus a ball; rows are compact ints in decimetres; stay inside the pitch bounds
   - every segment `source` and the part `original_video` is the exact string `s3://fixture/pending`
5. Also write `tools/footballslam/data/demo/segments.json`, `attacks.json`, `anomalies.json`, and `map.json` by running the generator. Do not write an `index.json` inside `data/demo/` unless validate.py requires per-match files only; the playlist index is `data/index.json` and you must leave it absent.
6. Run `python tools/footballslam/check/validate.py`. It must pass on `data/demo`. Fix the generator until it does. If `data/index.json` is missing, the validator skips it and still checks match directories.

## Done when

`validate.py` exits 0 on `data/demo`, the placeholder URI appears on every segment source, and you did not create `data/index.json`.

## Report

```
DONE foundation
files: <list>
validate: <exit code and one-line summary>
placeholder: s3://fixture/pending present | missing
unfinished: <none, or what remains>
```
