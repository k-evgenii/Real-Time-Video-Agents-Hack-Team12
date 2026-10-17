"""Manual 4+ point homography image -> pitch (plan §6.7). Hartley-normalised DLT, pure numpy.

  python map/calib.py --frame frame.png --points "u1,v1:X1,Y1;u2,v2:X2,Y2;..." --match m1 [--camera cam1]
  python map/calib.py --frame frame.png --click --match m1       # needs a display + matplotlib
  python map/calib.py --frame frame.png --match m1 --grid        # writes frame_grid.png to read pixels off
  (frame: ffmpeg -i data/raw/det/<seg_id>/seg.mp4 -frames:v 1 data/raw/det/<seg_id>/frame.png)

Pitch metres, origin at centre, x in [-52.5, 52.5] (along touchline), y in [-34, 34].
Writes data/<match>/calib.json {"H","rmse_m","points","image_size"}; refuses if rmse_m > 1.5.
Useful landmarks: corners (+-52.5,+-34), halfway/touchline (0,+-34), centre spot (0,0),
penalty-box corners (+-36,+-20.16), goal-area corners (+-47,+-9.16), penalty spots (+-41.5,0).
"""
import argparse
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_RMSE = 1.5


def _normaliser(pts):
    pts = np.asarray(pts, float)
    c = pts.mean(axis=0)
    d = np.sqrt(((pts - c) ** 2).sum(axis=1)).mean()
    s = np.sqrt(2) / max(d, 1e-12)
    return np.array([[s, 0, -s * c[0]], [0, s, -s * c[1]], [0, 0, 1]])


def dlt(img_pts, pitch_pts):
    img_pts = np.asarray(img_pts, float)
    pitch_pts = np.asarray(pitch_pts, float)
    if len(img_pts) < 4:
        raise ValueError("need >= 4 point pairs")
    Ti, Tp = _normaliser(img_pts), _normaliser(pitch_pts)
    ih = np.c_[img_pts, np.ones(len(img_pts))] @ Ti.T
    ph = np.c_[pitch_pts, np.ones(len(pitch_pts))] @ Tp.T
    rows = []
    for (u, v, _), (X, Y, _) in zip(ih, ph):
        rows.append([-u, -v, -1, 0, 0, 0, u * X, v * X, X])
        rows.append([0, 0, 0, -u, -v, -1, u * Y, v * Y, Y])
    _, _, Vt = np.linalg.svd(np.asarray(rows))
    Hn = Vt[-1].reshape(3, 3)
    H = np.linalg.inv(Tp) @ Hn @ Ti
    return H / H[2, 2]


def project(H, pts):
    pts = np.asarray(pts, float).reshape(-1, 2)
    p = np.c_[pts, np.ones(len(pts))] @ np.asarray(H, float).T
    return p[:, :2] / p[:, 2:3]


def rmse(H, img_pts, pitch_pts):
    err = project(H, img_pts) - np.asarray(pitch_pts, float)
    return float(np.sqrt((err ** 2).sum(axis=1).mean()))


def parse_points(s):
    img, pitch = [], []
    for pair in s.strip().strip(";").split(";"):
        a, b = pair.split(":")
        u, v = (float(x) for x in a.split(","))
        X, Y = (float(x) for x in b.split(","))
        img.append([u, v])
        pitch.append([X, Y])
    return img, pitch


def click_points(frame):
    import matplotlib.pyplot as plt
    img = plt.imread(frame)
    plt.imshow(img)
    plt.title("click >=4 landmarks, then Enter; you will be asked their pitch coords")
    pts = plt.ginput(n=-1, timeout=0)
    plt.close()
    img_pts, pitch_pts = [], []
    for (u, v) in pts:
        X, Y = (float(x) for x in input(f"pitch X,Y for pixel ({u:.0f},{v:.0f}): ").split(","))
        img_pts.append([u, v])
        pitch_pts.append([X, Y])
    return img_pts, pitch_pts


def image_size(frame):
    try:
        import cv2
        im = cv2.imread(frame)
        return [int(im.shape[1]), int(im.shape[0])]
    except Exception:
        return None


def grid_png(frame, out=None, step=100):
    """Copy of the frame with a labelled pixel grid, to read landmark coordinates without a display."""
    import cv2
    im = cv2.imread(frame)
    h, w = im.shape[:2]
    for x in range(0, w, step):
        cv2.line(im, (x, 0), (x, h), (0, 255, 255), 1)
        cv2.putText(im, str(x), (x + 2, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
    for y in range(0, h, step):
        cv2.line(im, (0, y), (w, y), (0, 255, 255), 1)
        cv2.putText(im, str(y), (2, y - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
    out = out or os.path.splitext(frame)[0] + "_grid.png"
    cv2.imwrite(out, im)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frame", required=True)
    ap.add_argument("--grid", action="store_true", help="only write <frame>_grid.png with pixel gridlines")
    ap.add_argument("--points")
    ap.add_argument("--click", action="store_true")
    ap.add_argument("--match", required=True)
    ap.add_argument("--camera", default="cam1")
    ap.add_argument("--out")
    ap.add_argument("--force", action="store_true", help="save even if rmse > 1.5 m")
    a = ap.parse_args()
    if a.grid:
        print(grid_png(a.frame))
        return
    if a.click:
        img_pts, pitch_pts = click_points(a.frame)
    elif a.points:
        img_pts, pitch_pts = parse_points(a.points)
    else:
        sys.exit("give --points or --click")
    H = dlt(img_pts, pitch_pts)
    err = rmse(H, img_pts, pitch_pts)
    back = project(np.linalg.inv(H), pitch_pts)
    px_err = float(np.sqrt(((back - np.asarray(img_pts)) ** 2).sum(axis=1).mean()))
    print(f"points={len(img_pts)} reprojection RMSE = {err:.3f} m (inverse check {px_err:.2f} px)")
    for (u, v), (X, Y), (pX, pY) in zip(img_pts, pitch_pts, project(H, img_pts)):
        print(f"  ({u:.0f},{v:.0f}) -> ({pX:6.2f},{pY:6.2f})  target ({X:6.2f},{Y:6.2f})")
    if err > MAX_RMSE and not a.force:
        sys.exit(f"RMSE {err:.2f} m > {MAX_RMSE} m: re-click (not saved)")
    out = a.out or os.path.join(ROOT, "data", a.match, "calib.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump({"camera": a.camera, "H": [[round(x, 10) for x in r] for r in H.tolist()], "rmse_m": round(err, 3),
               "points": [{"img": i, "pitch": p} for i, p in zip(img_pts, pitch_pts)],
               "image_size": image_size(a.frame)}, open(out, "w"), indent=1)
    print("saved", out)


if __name__ == "__main__":
    main()
