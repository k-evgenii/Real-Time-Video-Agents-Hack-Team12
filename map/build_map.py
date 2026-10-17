"""detections -> tracker -> trajectory anomalies -> data/<scene>/map_<part>.json (+ track_alerts.json). PIVOT_TRAFFIC §2, §3.4.

  python map/build_map.py --scene i24_cam-1 --part 20261001_055249_scene1_p1c1_chunk_0000 --mode FLOW [--fps 5] [--primary]
  python map/build_map.py ... --inject stop|swerve|reverse [--track-id N] [--at-t T]     # writes map_sim_<part>.json

Segments of --part come from --index (parts[].segments[]), --sources (lines "s3uri [t0]"), or are derived from the part
stem: s3://$S3_SEGMENTS_BUCKET/segments/<part>_segment_KKK_of_NNN.mp4. Derived t0 = chunk*--chunk-len + (k-1)*seg_len.
Two passes: pass 1 tracks the whole part to learn the scene τ (q_0.995 of d², floor 9.21); pass 2 scores with that τ.
Row p = [track_id, cls(0 vehicle, 1 person/bicycle, 2 other), x_dm, y_dm, u, v, w, h, score_x100] with (u, v) = box
centre in source pixels and x,y the RELATIVE formula. --primary also writes map.json / map_sim.json.
"""
import argparse
import json
import math
import os
import re
import sys
import time
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from anomaly_track import CHI2_995, SceneAnomaly  # noqa: E402
from track import Tracker  # noqa: E402

ROOT = os.path.dirname(HERE)
DET_ROOT = os.path.join(ROOT, "data", "raw", "det")
SEG_RE = re.compile(r"chunk_(\d+)_segment_(\d+)_of_(\d+)")
VEHICLES = {"car", "truck", "bus", "motorcycle"}
PEOPLE = {"person", "bicycle"}
Q_DT = 0.2


def seg_id_of(source):
    return os.path.splitext(os.path.basename(source))[0]


def derive_t0(src, a):
    m = SEG_RE.search(src)
    if not m:
        sys.exit(f"cannot derive t0 for {src}; give it as a 2nd column in --sources")
    chunk, seg, of = (int(x) for x in m.groups())
    return a.t_offset + chunk * a.chunk_len + (seg - 1) * a.chunk_len / of


def load_segments(a):
    if a.index and os.path.exists(a.index):
        idx = json.load(open(a.index))
        for m in idx.get("matches", []):
            if m["match_id"] != a.scene:
                continue
            for p in m["parts"]:
                if a.part in (p["part_id"], os.path.splitext(os.path.basename(p.get("original_video", "")))[0]):
                    return sorted(((s["source"], float(s["t0"])) for s in p["segments"]), key=lambda s: s[1])
    if a.sources:
        segs = []
        for line in open(a.sources):
            parts = line.split()
            if not parts or parts[0].startswith("#") or a.part not in parts[0]:
                continue
            segs.append((parts[0], float(parts[1]) if len(parts) > 1 else derive_t0(parts[0], a)))
        if segs:
            return sorted(segs, key=lambda s: s[1])
    bucket = os.environ.get("S3_SEGMENTS_BUCKET")
    if not bucket:
        sys.exit("no segments found: give --index, --sources, or set S3_SEGMENTS_BUCKET")
    n = a.n_seg
    srcs = [f"s3://{bucket}/segments/{a.part}_segment_{k:03d}_of_{n:03d}.mp4" for k in range(1, n + 1)]
    return [(s, derive_t0(s, a)) for s in srcs]


def ensure_detections(segs):
    missing = [s for s, _ in segs if not os.path.exists(os.path.join(DET_ROOT, seg_id_of(s), "meta.json"))]
    if missing:
        from detect import detect
        from vss import VSS
        vss = VSS().login()
        for s in missing:
            m = detect(vss, s, os.path.join(DET_ROOT, seg_id_of(s)))
            print(f"  detect {seg_id_of(s)} engine={m['engine']} {m['seconds']}s")


def load_frames(segs, stride):
    """-> list of (t, [det rows]), W, H, fps"""
    frames, W, H, fps = [], None, None, 30.0
    for src, t0 in segs:
        d = os.path.join(DET_ROOT, seg_id_of(src))
        meta = json.load(open(os.path.join(d, "meta.json")))
        W, H, fps = meta["width"], meta["height"], meta["fps"] or 30.0
        by_frame = defaultdict(list)
        for line in open(os.path.join(d, "detections.jsonl")):
            r = json.loads(line)
            if r["cls"] in VEHICLES or r["cls"] in PEOPLE:
                by_frame[r["frame"]].append(r)
        n = meta["n_frames"] or (max(by_frame) + 1 if by_frame else 0)
        for f in range(0, n, stride):
            frames.append((t0 + f / fps, by_frame.get(f, [])))
    return frames, W, H, fps / stride


WARMUP, PERSIST = 10, 3


def run_pass(frames, W, H, dt, tau=None, record=False):
    tracker = Tracker(q_dt=Q_DT)
    scene = SceneAnomaly(W, H, tau=tau, warmup=WARMUP, enter_n=PERSIST)
    out, assigns, life = [], [], {}
    for t, dets in frames:
        active = tracker.step(t, [d["box"] for d in dets], [d["conf"] for d in dets], [d["cls"] for d in dets])
        scores = scene.step(t, dt, active)
        if record:
            assigns.append(dict(tracker.last_assign))
            for trk in active:
                c = (float(trk.kf.x[0]), float(trk.kf.x[1]))
                lt = life.setdefault(trk.id, [t, t, trk, c, c])
                lt[1], lt[4] = t, c
        out.append((t, [(trk.id, trk.cls, trk.box().copy(), scores.get(trk.id, 0.0)) for trk in active]))
    return out, scene, assigns, life


def pick_track(life, at_t, frames_t):
    """Vehicle alive around at_t moving fastest relative to its own size (a near, clearly moving car)."""
    best, best_v = None, 0.0
    for tid, (t0, t1, trk, c0, c1) in life.items():
        if t0 > at_t - 1.0 or t1 < at_t + 2.0 or trk.cls not in VEHICLES:
            continue
        v = math.hypot(c1[0] - c0[0], c1[1] - c0[1]) / max(t1 - t0, 1e-3) / trk.scale
        if v > best_v:
            best, best_v = tid, v
    return best


def inject(frames, out1, tid, at_t, kind, dur=4.0):
    """Replace vehicle `tid` (pass-1 path) with one clean synthetic box path that does stop | swerve | reverse at at_t.
    Every detection overlapping the original path is removed first, so duplicate YOLO boxes can't carry the track."""
    from track import iou
    path = {}
    for i, (t, entries) in enumerate(out1):
        for e in entries:
            if e[0] == tid:
                path[i] = np.asarray(e[2], float)
    idx = sorted(path)
    after = [i for i in idx if at_t <= frames[i][0] <= at_t + dur]
    if len(after) < 6:
        sys.exit(f"track {tid} not visible enough after t={at_t}")
    i0, i5 = after[0], after[min(5, len(after) - 1)]
    c = {i: ((path[i][0] + path[i][2]) / 2, (path[i][1] + path[i][3]) / 2) for i in idx}
    dt5 = frames[i5][0] - frames[i0][0]
    v = ((c[i5][0] - c[i0][0]) / dt5, (c[i5][1] - c[i0][1]) / dt5) if dt5 > 0 else (0.0, 0.0)
    sp = math.hypot(*v) or 1.0
    nrm = (-v[1] / sp, v[0] / sp)
    w0, h0 = path[i0][2] - path[i0][0], path[i0][3] - path[i0][1]
    s = math.sqrt(w0 * h0)
    t_i0 = frames[i0][0]
    new = []
    for i, (t, dets) in enumerate(frames):
        dets = [dict(d) for d in dets]
        in_window = t_i0 <= t <= t_i0 + dur
        if i not in path and not in_window:
            new.append((t, dets))
            continue
        tau = t - t_i0
        ref = path[i] if i in path else None
        if in_window:
            co = (c[i0][0] + v[0] * tau, c[i0][1] + v[1] * tau)      # where the car would have been
            ref_box = np.array([co[0] - w0 / 2, co[1] - h0 / 2, co[0] + w0 / 2, co[1] + h0 / 2])
            dets = [d for d in dets if iou([ref_box], [d["box"]])[0, 0] < 0.2]
        if ref is not None:
            dets = [d for d in dets if iou([ref], [d["box"]])[0, 0] < 0.3]
        if t < t_i0 and ref is not None:
            dets.append({"box": ref.tolist(), "conf": 0.9, "cls": "car"})
        elif in_window:
            if kind == "stop":
                T = 0.15
                disp = tau - tau * tau / (2 * T) if tau < T else T / 2
                tgt = (c[i0][0] + v[0] * disp, c[i0][1] + v[1] * disp)
            elif kind == "swerve":
                off = 3.0 * s * min(1.0, tau / 0.3)
                tgt = (co[0] + nrm[0] * off, co[1] + nrm[1] * off)
            else:
                tgt = (c[i0][0] - v[0] * tau, c[i0][1] - v[1] * tau)
            dets.append({"box": [tgt[0] - w0 / 2, tgt[1] - h0 / 2, tgt[0] + w0 / 2, tgt[1] + h0 / 2],
                         "conf": 0.9, "cls": "car"})
        new.append((t, dets))
    return new


def to_rows(entries, W, H):
    rows = []
    for tid, cls, b, score in entries:
        cu, cv = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        if cu < 0 or cv < 0:
            continue
        code = 0 if cls in VEHICLES else 1 if cls in PEOPLE else 2
        rows.append([int(tid), code, int(round((cu / W - 0.5) * 1050)), int(round((cv / H - 0.5) * 680)),
                     int(round(cu)), int(round(cv)), int(round(b[2] - b[0])), int(round(b[3] - b[1])),
                     int(round(min(score, 9.99) * 100))])
    return rows


def sample(out, fps_out):
    frames, next_t = [], None
    for t, entries in out:
        if next_t is None:
            next_t = t
        if t + 1e-6 >= next_t:
            frames.append((t, entries))
            next_t += 1.0 / fps_out
    return frames


def build(a):
    t_start = time.time()
    segs = load_segments(a)
    if a.max_seconds:
        segs = [s for s in segs if s[1] < segs[0][1] + a.max_seconds]
    print(f"scene={a.scene} part={a.part} segments={len(segs)} t={segs[0][1]:.1f}..{segs[-1][1]:.1f}s")
    ensure_detections(segs)
    frames, W, H, fps = load_frames(segs, a.track_stride)
    dt = 1.0 / fps

    out1, scene1, assigns, life = run_pass(frames, W, H, dt, record=True)
    pool = scene1.pool
    tau = max(CHI2_995, float(np.quantile(pool, 0.995))) if len(pool) >= 300 else CHI2_995
    simulated = None
    if a.inject:
        at_t = a.at_t if a.at_t is not None else frames[len(frames) // 3][0]
        tid = a.track_id or pick_track(life, at_t, [f[0] for f in frames])
        if tid is None:
            sys.exit("no suitable track to inject into; pass --track-id/--at-t")
        frames = inject(frames, out1, tid, at_t, a.inject)
        simulated = {"kind": a.inject, "track_id_pass1": int(tid), "at_t": round(at_t, 2)}
        print(f"injected {a.inject} into pass-1 track {tid} at t={at_t:.1f}s")
    out2, scene2, _, _ = run_pass(frames, W, H, dt, tau=tau)
    alerts = scene2.finish()
    if a.mode == "NONE":
        # moving camera: image-space physics is meaningless, keep boxes only
        alerts = []
        out2 = [(t, [(tid, cls, b, 0.0) for tid, cls, b, _ in entries]) for t, entries in out2]
    for al in alerts:
        al["part_id"] = a.part
        al["scene"] = a.scene
        if simulated:
            al["simulated"] = True

    frames_json, n_obj = [], []
    for t, entries in sample(out2, a.fps):
        rows = to_rows(entries, W, H)
        n_obj.append(len(rows))
        frames_json.append({"t": round(t, 2), "p": rows, "b": None})
    out = {"match_id": a.scene, "part_id": a.part, "mode": a.mode, "fps": a.fps,
           "pitch": {"length_m": 105, "width_m": 68}, "image_size": [W, H], "tau": round(tau, 2),
           "flow": scene2.flow.to_json() if a.mode == "FLOW" else None,
           "alerts": alerts, "frames": frames_json}
    if simulated:
        out["simulated"] = True
        out["simulation"] = simulated
    d = os.path.join(ROOT, "data", a.scene)
    os.makedirs(d, exist_ok=True)
    stem = "map_sim" if simulated else "map"
    paths = [a.out or os.path.join(d, f"{stem}_{a.part}.json")]
    if a.primary:
        paths.append(os.path.join(d, f"{stem}.json"))
    for p in paths:
        with open(p, "w") as f:
            json.dump(out, f, separators=(",", ":"))
    if not simulated:
        merge_track_alerts(d, a.scene, a.part, tau, alerts)
    size = os.path.getsize(paths[0])
    dur = frames[-1][0] - frames[0][0] if frames else 0
    print(f"wrote {', '.join(os.path.relpath(p, ROOT) for p in paths)}  size={size/1024:.0f} KB  tau={tau:.2f} "
          f"(pool {len(pool)})  frames={len(frames_json)}  mean objects/frame={np.mean(n_obj) if n_obj else 0:.1f}  "
          f"alerts={len(alerts)} ({len(alerts) / max(dur, 1) * 30:.2f} per 30 s)  {time.time() - t_start:.0f}s")
    for al in alerts[:8]:
        print(f"  t={al['t0']:.1f}-{al['t1']:.1f} track {al['track_id']} {al['type']:<20} score {al['peak_score']:.2f}  {al['reason']}")
    return out


def merge_track_alerts(d, scene, part, tau, alerts):
    path = os.path.join(d, "track_alerts.json")
    cur = json.load(open(path)) if os.path.exists(path) else {"scene": scene, "tau": {}, "alerts": []}
    cur["tau"][part] = round(tau, 2)
    cur["alerts"] = [x for x in cur["alerts"] if x.get("part_id") != part] + alerts
    cur["alerts"].sort(key=lambda x: -x["peak_score"])
    json.dump(cur, open(path, "w"), separators=(",", ":"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", "--match", dest="scene", required=True)
    ap.add_argument("--part", required=True)
    ap.add_argument("--mode", default="FLOW", choices=["FLOW", "NONE"])
    ap.add_argument("--sources")
    ap.add_argument("--index", default=os.path.join(ROOT, "data", "index.json"))
    ap.add_argument("--t-offset", type=float, default=0.0)
    ap.add_argument("--chunk-len", type=float, default=30.0)
    ap.add_argument("--n-seg", type=int, default=6)
    ap.add_argument("--fps", type=float, default=5)
    ap.add_argument("--max-seconds", type=float, default=0)
    ap.add_argument("--track-stride", type=int, default=1)
    ap.add_argument("--inject", choices=["stop", "swerve", "reverse"])
    ap.add_argument("--track-id", type=int)
    ap.add_argument("--at-t", type=float)
    ap.add_argument("--warmup", type=int, default=15, help="hits before a track is scored")
    ap.add_argument("--persist", type=int, default=9, help="frames above 1.0 before an alert opens (0.3 s at 30 fps)")
    ap.add_argument("--primary", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args()
    global WARMUP, PERSIST
    WARMUP, PERSIST = a.warmup, a.persist
    build(a)


if __name__ == "__main__":
    main()
