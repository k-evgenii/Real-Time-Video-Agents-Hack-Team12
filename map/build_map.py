"""detections -> tracker -> team colour -> ground point -> homography -> data/<match>/map.json (CONTRACTS §2.4).

  python map/build_map.py --match m1 --part m1_h1_p01 --mode FULL|RELATIVE|NONE [--calib data/m1/calib.json]
         [--sources sources.txt | --index data/index.json] [--fps 5] [--max-seconds 120] [--kit-a HEX --kit-b HEX]

Segment list: --index (uses parts[].segments[] t0/source of --part) or --sources (lines "s3uri [t0_global]";
missing t0 is derived from "..._chunk_NNNN_segment_SSS_of_MMM" with --chunk-len, plus --t-offset).
Missing detections are fetched with detect.py. Row p = [track_id, team, x_dm, y_dm, u, v, w, h]
with (u, v) = box CENTRE in source pixels; b = [x_dm, y_dm, u, v, conf, interp] or null.
"""
import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from calib import project  # noqa: E402
from team_colour import TeamAssigner, crop_feature  # noqa: E402
from track import Tracker  # noqa: E402

ROOT = os.path.dirname(HERE)
DET_ROOT = os.path.join(ROOT, "data", "raw", "det")
SEG_RE = re.compile(r"chunk_(\d+)_segment_(\d+)_of_(\d+)")
BALL = ("sports ball", "ball")
PITCH_X, PITCH_Y, MARGIN = 52.5, 34.0, 3.0


def seg_id_of(source):
    return os.path.splitext(os.path.basename(source))[0]


def load_segments(a):
    segs = []
    if a.index:
        idx = json.load(open(a.index))
        for m in idx["matches"]:
            if m["match_id"] != a.match:
                continue
            for p in m["parts"]:
                if p["part_id"] == a.part:
                    segs = [(s["source"], float(s["t0"])) for s in p["segments"]]
        if not segs:
            sys.exit(f"part {a.part} not found in {a.index}")
    else:
        for line in open(a.sources):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            src = parts[0]
            if len(parts) > 1:
                t0 = float(parts[1])
            else:
                m = SEG_RE.search(src)
                if not m:
                    sys.exit(f"cannot derive t0 for {src}; give it as a 2nd column")
                chunk, seg, of = (int(x) for x in m.groups())
                t0 = a.t_offset + chunk * a.chunk_len + (seg - 1) * a.chunk_len / of
            segs.append((src, t0))
    return sorted(segs, key=lambda s: s[1])


def ensure_detections(segs):
    missing = [s for s, _ in segs if not os.path.exists(os.path.join(DET_ROOT, seg_id_of(s), "meta.json"))]
    if missing:
        from detect import detect
        from vss import VSS
        vss = VSS().login()
        for s in missing:
            m = detect(vss, s, os.path.join(DET_ROOT, seg_id_of(s)))
            print(f"  detect {seg_id_of(s)} engine={m['engine']} {m['seconds']}s")


def to_pitch_dm(points, mode, H, W, Hpx):
    pts = np.asarray(points, float).reshape(-1, 2)
    if mode == "FULL":
        xy = project(H, pts)
        inside = (np.abs(xy[:, 0]) <= PITCH_X + MARGIN) & (np.abs(xy[:, 1]) <= PITCH_Y + MARGIN)
        return np.round(xy * 10).astype(int), inside
    xy = np.c_[(pts[:, 0] / W - 0.5) * 1050, (pts[:, 1] / Hpx - 0.5) * 680]
    return np.round(xy).astype(int), np.ones(len(pts), bool)


def ball_at(t, balls, fps):
    """balls: sorted list of (t, u, v, conf). Returns (u, v, conf, interp) or None."""
    if not balls:
        return None
    ts = np.fromiter((b[0] for b in balls), float)
    i = int(np.searchsorted(ts, t))
    half = 0.5 / fps
    near = [j for j in (i - 1, i) if 0 <= j < len(balls) and abs(ts[j] - t) <= half]
    if near:
        j = max(near, key=lambda j: balls[j][3])
        return balls[j][1], balls[j][2], balls[j][3], 0
    if 0 < i < len(balls) and ts[i] - ts[i - 1] <= 1.0:
        a, b = balls[i - 1], balls[i]
        w = (t - a[0]) / (b[0] - a[0])
        return a[1] + w * (b[1] - a[1]), a[2] + w * (b[2] - a[2]), min(a[3], b[3]), 1
    return None


def build(a):
    t_start = time.time()
    segs = load_segments(a)
    if a.max_seconds:
        t_first = segs[0][1]
        segs = [s for s in segs if s[1] < t_first + a.max_seconds]
    print(f"segments={len(segs)}  t={segs[0][1]:.1f}..{segs[-1][1]:.1f}s")
    ensure_detections(segs)
    H = None
    if a.mode == "FULL":
        if not a.calib or not os.path.exists(a.calib):
            sys.exit("FULL mode needs --calib (or use --mode RELATIVE)")
        H = np.array(json.load(open(a.calib))["H"], float)

    tracker = Tracker(confirm_hits=a.confirm_hits)
    teams = TeamAssigner(a.kit_a, a.kit_b, fit_seconds=a.fit_seconds)
    out_frames = []          # (t, [(tid, box)], W, H)
    balls = []
    W = Hpx = None
    next_out = None
    colour_every = 1.0 / a.colour_fps
    next_colour = None
    for src, t0 in segs:
        d = os.path.join(DET_ROOT, seg_id_of(src))
        meta = json.load(open(os.path.join(d, "meta.json")))
        W, Hpx, fps = meta["width"], meta["height"], meta["fps"] or 30.0
        by_frame = defaultdict(list)
        for line in open(os.path.join(d, "detections.jsonl")):
            r = json.loads(line)
            by_frame[r["frame"]].append(r)
        mp4 = os.path.join(d, "seg.mp4")
        cap = None
        if not a.no_colour and os.path.exists(mp4):
            import cv2
            cap = cv2.VideoCapture(mp4)
        n = meta["n_frames"] or (max(by_frame) + 1 if by_frame else 0)
        for f in range(0, n):
            t = t0 + f / fps
            img = None
            want_colour = cap is not None and (next_colour is None or t >= next_colour)
            if cap is not None:
                if want_colour:
                    ok, img = cap.read()
                    if not ok:
                        cap, img = None, None
                else:
                    cap.grab()
            if f % a.track_stride:
                continue
            rows = by_frame.get(f, [])
            persons = [r for r in rows if r["cls"] not in BALL]
            for r in rows:
                if r["cls"] in BALL:
                    x1, y1, x2, y2 = r["box"]
                    balls.append((t, (x1 + x2) / 2, (y1 + y2) / 2, r["conf"]))
            active = tracker.step(t, [r["box"] for r in persons], [r["conf"] for r in persons])
            if img is not None:
                for trk in active:
                    teams.add(trk.id, t, crop_feature(img, trk.box()))
                next_colour = t + colour_every
            if next_out is None:
                next_out = t
            if t + 1e-6 >= next_out:
                out_frames.append((round(t, 2), [(trk.id, trk.box().copy()) for trk in active]))
                next_out += 1.0 / a.fps
    teams.finalize()
    balls.sort()

    team_of = {}
    frames_json, n_players, n_ball, split = [], [], 0, [0, 0, 0]
    for t, plist in out_frames:
        rows = []
        if plist:
            boxes = np.array([b for _, b in plist])
            ground = np.c_[(boxes[:, 0] + boxes[:, 2]) / 2, boxes[:, 3]]
            xy, inside = to_pitch_dm(ground, a.mode, H, W, Hpx)
            for (tid, b), (x, y), ok in zip(plist, xy, inside):
                if not ok:
                    continue
                if tid not in team_of:
                    team_of[tid] = teams.team(tid)
                tm = team_of[tid]
                split[tm] += 1
                rows.append([int(tid), int(tm), int(x), int(y), int(round((b[0] + b[2]) / 2)),
                             int(round((b[1] + b[3]) / 2)), int(round(b[2] - b[0])), int(round(b[3] - b[1]))])
        bb = ball_at(t, balls, a.fps)
        bj = None
        if bb is not None:
            (bx, by), ok = (lambda r: (r[0][0], r[1][0]))(to_pitch_dm([[bb[0], bb[1]]], a.mode, H, W, Hpx))
            if ok:
                bj = [int(bx), int(by), int(round(bb[0])), int(round(bb[1])), round(float(bb[2]), 2), int(bb[3])]
                n_ball += 1
        n_players.append(len(rows))
        frames_json.append({"t": t, "p": rows, "b": bj})

    out = {"match_id": a.match, "part_id": a.part, "mode": a.mode, "fps": a.fps,
           "pitch": {"length_m": 105, "width_m": 68}, "image_size": [W, Hpx], "frames": frames_json}
    path = a.out or os.path.join(ROOT, "data", a.match, "map.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    size = os.path.getsize(path)
    nf = max(1, len(frames_json))
    print(f"wrote {path}  mode={a.mode} frames={len(frames_json)} size={size/1024:.0f} KB "
          f"mean players/frame={np.mean(n_players) if n_players else 0:.1f} ball frames={100*n_ball/nf:.0f}% "
          f"team split A/B/?={split} tracks={len(team_of)} ({time.time()-t_start:.0f}s)")
    if size > 1.5 * 1024 * 1024:
        print("WARNING: map.json > 1.5 MB, rerun with --fps 4")
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--match", required=True)
    ap.add_argument("--part", required=True)
    ap.add_argument("--mode", default="RELATIVE", choices=["FULL", "RELATIVE", "NONE"])
    ap.add_argument("--calib")
    ap.add_argument("--sources")
    ap.add_argument("--index")
    ap.add_argument("--t-offset", type=float, default=0.0)
    ap.add_argument("--chunk-len", type=float, default=30.0)
    ap.add_argument("--fps", type=float, default=5)
    ap.add_argument("--max-seconds", type=float, default=0)
    ap.add_argument("--track-stride", type=int, default=1, help="use every Nth detector frame for tracking")
    ap.add_argument("--confirm-hits", type=int, default=3)
    ap.add_argument("--colour-fps", type=float, default=5)
    ap.add_argument("--fit-seconds", type=float, default=10)
    ap.add_argument("--no-colour", action="store_true")
    ap.add_argument("--kit-a")
    ap.add_argument("--kit-b")
    ap.add_argument("--out")
    a = ap.parse_args()
    if not a.index and not a.sources:
        default_index = os.path.join(ROOT, "data", "index.json")
        if os.path.exists(default_index):
            a.index = default_index
        else:
            sys.exit("give --sources or --index")
    build(a)


if __name__ == "__main__":
    main()
