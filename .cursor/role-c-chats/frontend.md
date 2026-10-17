# Frontend — Role C writer

You are the Frontend writer under the Role C integrator for FootballSLAM. You build the page the judges see: video playlist, attack timeline, anomaly list, and why card. You mount Person B's pitch and overlay modules when those files exist. You do not write them.

Repo: `/home/ek836/vast-builders-challenge`. Work under `tools/footballslam/`.

## Read first

- `.cursor/rules/build-day.mdc`
- `CONTRACTS.md` §2.4 (index, segments, attacks, anomalies, map, and the `drawPitch` / `drawOverlay` signatures)
- `HACKATHON_PLAN.md` §7 W3 (layout) and §2 (pitch sentence, for the title only)

## Exclusive paths

You may create and edit only:

- `tools/footballslam/app/static/index.html`
- `tools/footballslam/app/static/app.js`
- `tools/footballslam/app/static/style.css`

## Do not

- Do not run git, kubectl, or `deploy.sh`.
- Do not create `pitch.js` or `overlay.js`. Those belong to Person B.
- Do not edit `app/main.py`, `requirements.txt`, `deploy/**`, `data/**`, `check/**`, `fixtures/**`, `events/**`, `map/**`.
- Do not add a framework, a bundler, or a CDN script. No build step.
- Keep `index.html` + `app.js` + `style.css` together under 150 KB.
- If you need a server change, write `tools/footballslam/app/static/NOTES_FOR_C.md` (3 lines) and stop.

## Frozen API (the server chat implements this; Ingress strips `/app`)

Fetch these paths with relative URLs so they work both at `/` and behind `/app`:

- `GET matches` → `data/index.json`
- `GET data/<match>/<name>.json` for `segments`, `attacks`, `anomalies`, `map`
- Video element `src` = `video?src=<urlsafe-base64 of the segment source>`

Relative URLs matter. A fetch of `/matches` breaks behind the `/app` prefix. A fetch of `matches` does not.

## Page

Vanilla JS ES modules. Dark theme. Projector type: base 16 px, labels at least 14 px.

Load `drawPitch` from `./pitch.js` and `drawOverlay` from `./overlay.js` inside try/catch. If either import fails, use a no-op function so the page still runs.

Layout:

- Top bar: match title, part selector.
- Left 60%: `<video>` with an overlay `<canvas>` positioned over it.
- Right-top 40%: pitch `<canvas>`. Hide this panel when `map_mode` is `NONE` or `map.json` is missing or `frames` is empty.
- Bottom, full width: attack timeline. Two lanes, team A above team B. One bar per attack from `t0` to `t1`, coloured by `max_zone` (D dark, M mid, A bright team colour). Flagged attacks outlined red and labelled with `s_feat`. A playhead. Click seeks.
- Right panel: anomaly list. Per team, the top 5 from `anomalies.json` with rank, `s_feat`, and when `agree` is true also `s_emb` plus the text `visual embedding agrees`. Three reason lines. Click seeks to `moment.t - 2` seconds and highlights that attack. Below the list, the why card: three horizontal bars for the top `|z|` features (label, value versus median, z). When `s_emb` is null, hide the agrees badge.

Time:

- The player is a segment playlist from `index.json` `parts[].segments`.
- Global time = `seg.t0 + video.currentTime`.
- On `ended`, load the next segment.
- `seek(T)` finds the segment containing `T`, loads it, sets `currentTime`.
- Frame lookup is a binary search on `map.frames[].t`.
- Keep per-id trails of the last 2 seconds and pass them to `drawPitch`.
- One `requestAnimationFrame` loop draws overlay, pitch, and playhead.

State: `?match=<id>` selects the match. Default is the first match in the index.

If the playlist stutters at segment boundaries, preload the next segment in a hidden second `<video>` and swap.

Develop against the fixture shape in CONTRACTS even if `data/demo` is still being written. When `matches` 404s, show a single line "index not ready" instead of throwing.

## Steps

Time box: 60 minutes.

1. Write the three files.
2. Check syntax with `node --check tools/footballslam/app/static/app.js`.
3. Do not deploy. The integrator deploys.

## Done when

The three files exist, `node --check` exits 0, missing `pitch.js` does not blank the page, and seek, timeline click, and anomaly click are implemented against the contract.

## Report

```
DONE frontend
files: index.html, app.js, style.css
node --check: <exit code>
bytes: <total of the three files>
pitch import: try/catch present
unfinished: <none, or what remains>
```
