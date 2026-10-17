"""Team assignment by k-means(2) on shirt colour (plan §6.8). numpy for the maths, cv2 only for HSV.

Per confirmed track per sampled frame: upper 50 % of the box, sides shrunk 20 %, grass-hue pixels dropped,
median colour in a hue-circular space f = [S cos 2πH, S sin 2πH, V] (white/dark kits keep working, unlike a
plain S > 0.25 mask). k-means k=2 fitted on samples from the first 10 s, seeded from --kit-a/--kit-b hex or
k-means++. Assign by nearest centroid once a track has >= 5 samples; lock by majority at 15. Samples farther
than 2x the mean intra-cluster distance -> team 2 (GK / referee).

  python map/team_colour.py --debug <det_dir> [--kit-a "#2f6df6" --kit-b "#e8e8e8"]   # 5-frame debug PNG
"""
import argparse
import colorsys
import os
from collections import Counter, defaultdict

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None


def hsv_to_feat(h, s, v):
    """h, s, v in [0, 1] (arrays ok) -> (..., 3)."""
    a = 2 * np.pi * np.asarray(h, float)
    s = np.asarray(s, float)
    return np.stack([s * np.cos(a), s * np.sin(a), np.asarray(v, float)], axis=-1)


def hex_to_feat(hx):
    hx = hx.lstrip("#")
    r, g, b = (int(hx[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return hsv_to_feat(*colorsys.rgb_to_hsv(r, g, b))


def crop_feature(frame_bgr, box):
    """Median shirt colour feature for one box, or None."""
    H, W = frame_bgr.shape[:2]
    x1, y1, x2, y2 = (int(round(v)) for v in box)
    w = x2 - x1
    x1, x2 = x1 + int(0.2 * w), x2 - int(0.2 * w)
    y2 = y1 + int(0.5 * (y2 - y1))
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(W, x2), min(H, y2)
    if x2 - x1 < 2 or y2 - y1 < 2:
        return None
    hsv = cv2.cvtColor(frame_bgr[y1:y2, x1:x2], cv2.COLOR_BGR2HSV).reshape(-1, 3).astype(float)
    h, s, v = hsv[:, 0] / 180.0, hsv[:, 1] / 255.0, hsv[:, 2] / 255.0
    grass = (hsv[:, 0] >= 33) & (hsv[:, 0] <= 90) & (s > 0.2) & (v > 0.15)
    keep = ~grass
    if keep.sum() < 4:
        return None
    return np.median(hsv_to_feat(h[keep], s[keep], v[keep]), axis=0)


def kmeans2(X, seeds=None, iters=20, rng=None):
    X = np.asarray(X, float)
    rng = rng or np.random.default_rng(0)
    if seeds is not None:
        C = np.asarray(seeds, float).copy()
    else:
        c0 = X[rng.integers(len(X))]
        d = ((X - c0) ** 2).sum(1)
        c1 = X[rng.choice(len(X), p=d / d.sum())] if d.sum() > 0 else X[rng.integers(len(X))]
        C = np.stack([c0, c1])
    for _ in range(iters):
        lab = ((X[:, None, :] - C[None]) ** 2).sum(-1).argmin(1)
        for k in range(2):
            if (lab == k).any():
                C[k] = X[lab == k].mean(0)
    lab = ((X[:, None, :] - C[None]) ** 2).sum(-1).argmin(1)
    intra = np.sqrt(((X - C[lab]) ** 2).sum(1)).mean() if len(X) else 1.0
    return C, float(intra)


class TeamAssigner:
    def __init__(self, kit_a=None, kit_b=None, fit_seconds=10.0, min_samples=5, lock_at=15):
        self.seeds = None
        if kit_a and kit_b:
            self.seeds = np.stack([hex_to_feat(kit_a), hex_to_feat(kit_b)])
        self.fit_seconds, self.min_samples, self.lock_at = fit_seconds, min_samples, lock_at
        self.samples = defaultdict(list)          # track id -> [feat]
        self.fit_buf = []
        self.t_start = None
        self.C, self.intra = None, None
        self.locked = {}

    def add(self, tid, t, feat):
        if feat is None:
            return
        if self.t_start is None:
            self.t_start = t
        self.samples[tid].append(feat)
        if self.C is None:
            self.fit_buf.append(feat)
            if t - self.t_start >= self.fit_seconds and len(self.fit_buf) >= 10:
                self.fit()

    def fit(self):
        if len(self.fit_buf) < 2:
            return
        self.C, self.intra = kmeans2(np.array(self.fit_buf), self.seeds)

    def _label(self, f):
        d = np.sqrt(((self.C - f) ** 2).sum(1))
        k = int(d.argmin())
        return 2 if d[k] > 2 * self.intra else k

    def team(self, tid):
        if tid in self.locked:
            return self.locked[tid]
        s = self.samples.get(tid, [])
        if self.C is None or len(s) < self.min_samples:
            return 2
        labels = [self._label(f) for f in s]
        vote = Counter(labels).most_common(1)[0][0]
        if len(s) >= self.lock_at:
            self.locked[tid] = vote
        return vote

    def finalize(self):
        if self.C is None:
            self.fit()


def debug_png(det_dir, out_png, kit_a=None, kit_b=None, n=5):
    """Run detections -> tracker -> colours on one segment and save n frames side by side."""
    import json
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from track import Tracker
    rows = [json.loads(l) for l in open(os.path.join(det_dir, "detections.jsonl"))]
    by_frame = defaultdict(list)
    for r in rows:
        if r["cls"] == "person":
            by_frame[r["frame"]].append(r)
    meta = json.load(open(os.path.join(det_dir, "meta.json")))
    cap = cv2.VideoCapture(os.path.join(det_dir, "seg.mp4"))
    tr, ta = Tracker(), TeamAssigner(kit_a, kit_b, fit_seconds=min(2.0, meta["n_frames"] / meta["fps"] / 2))
    nf = meta["n_frames"]
    picks = set(np.linspace(nf * 0.3, nf - 1, n).astype(int).tolist())
    shots = []
    for f in range(nf):
        ok, img = cap.read()
        if not ok:
            break
        dets = by_frame.get(f, [])
        out = tr.step(f / meta["fps"], [d["box"] for d in dets], [d["conf"] for d in dets])
        if f % 3 == 0:
            for trk in out:
                ta.add(trk.id, f / meta["fps"], crop_feature(img, trk.box()))
        if f in picks:
            ta.finalize()
            vis = img.copy()
            colours = {0: (246, 109, 47), 1: (232, 232, 232), 2: (128, 128, 128)}
            for trk in out:
                x1, y1, x2, y2 = trk.box().astype(int)
                c = colours[ta.team(trk.id)]
                cv2.rectangle(vis, (x1, y1), (x2, y2), c, 3)
                cv2.putText(vis, str(trk.id), (x1, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.8, c, 2)
            shots.append(cv2.resize(vis, (vis.shape[1] // 2, vis.shape[0] // 2)))
    if shots:
        cv2.imwrite(out_png, np.vstack(shots))
    return out_png


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--debug", required=True, help="det dir with detections.jsonl, meta.json, seg.mp4")
    ap.add_argument("--kit-a")
    ap.add_argument("--kit-b")
    ap.add_argument("--out")
    a = ap.parse_args()
    out = a.out or os.path.join(a.debug, "teams_debug.png")
    print(debug_png(a.debug, out, a.kit_a, a.kit_b))
