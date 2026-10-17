"""Synthetic contract-valid map.json (22 players + referee + ball) for map/dev.html.

  python map/make_dev_fixture.py [--seconds 60] [--fps 5] [--out map/dev_fixture.json]
"""
import argparse
import json
import math
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 1920, 1080


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=60)
    ap.add_argument("--fps", type=float, default=5)
    ap.add_argument("--mode", default="FULL")
    ap.add_argument("--out", default=os.path.join(HERE, "dev_fixture.json"))
    a = ap.parse_args()
    rng = np.random.default_rng(7)
    form = [(-480, 0), (-350, -250), (-350, -80), (-350, 80), (-350, 250), (-150, -200), (-150, 0), (-150, 200),
            (50, -220), (80, 0), (50, 220)]
    base = np.array([[x, y, 0] for x, y in form] + [[-x, -y, 1] for x, y in form] + [[0, 100, 2]], float)
    phase = rng.uniform(0, 2 * math.pi, (len(base), 2))
    frames = []
    n = int(a.seconds * a.fps)
    for i in range(n):
        t = round(i / a.fps, 2)
        shift = 150 * math.sin(t / 8)
        rows = []
        for k, (bx, by, team) in enumerate(base):
            x = bx + shift + 60 * math.sin(t / 3 + phase[k, 0])
            y = by + 50 * math.sin(t / 4 + phase[k, 1])
            u, v = (x + 525) / 1050 * W, (y + 340) / 680 * H
            rows.append([k + 1, int(team), int(x), int(y), int(u), int(v - 35), 30, 70])
        bx, by = 300 * math.sin(t / 5), 200 * math.sin(t / 3.3)
        interp = 1 if (i // 15) % 4 == 3 else 0
        b = [int(bx), int(by), int((bx + 525) / 1050 * W), int((by + 340) / 680 * H), 0.6, interp]
        frames.append({"t": t, "p": rows, "b": b})
    json.dump({"match_id": "demo", "part_id": "demo_p01", "mode": a.mode, "fps": a.fps,
               "pitch": {"length_m": 105, "width_m": 68}, "image_size": [W, H], "frames": frames},
              open(a.out, "w"), separators=(",", ":"))
    print("wrote", a.out, os.path.getsize(a.out) // 1024, "KB")


if __name__ == "__main__":
    main()
