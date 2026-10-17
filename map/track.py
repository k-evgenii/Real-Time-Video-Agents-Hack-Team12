"""SORT-lite tracker with a constant-velocity Kalman filter (plan Appendix A). Pure numpy.

State x = [px, py, vx, vy] (box centre, pixels); box size (w, h) is smoothed separately.
R = sigma_m^2 I with sigma_m = max(2, 0.08 s), s = sqrt(w h);  Q = q * G(dt), q = (0.5 s / dt^2)^2 * 0.1.
Greedy IoU matching on predicted boxes (gate 0.25), confirm at 3 hits, delete after 15 misses.
"""
import numpy as np

H_MAT = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], float)


def iou(a, b):
    """a: (N,4), b: (M,4) boxes [x1,y1,x2,y2] -> (N,M) IoU."""
    a = np.asarray(a, float).reshape(-1, 4)
    b = np.asarray(b, float).reshape(-1, 4)
    if len(a) == 0 or len(b) == 0:
        return np.zeros((len(a), len(b)))
    x1 = np.maximum(a[:, None, 0], b[None, :, 0])
    y1 = np.maximum(a[:, None, 1], b[None, :, 1])
    x2 = np.minimum(a[:, None, 2], b[None, :, 2])
    y2 = np.minimum(a[:, None, 3], b[None, :, 3])
    inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    area_a = (a[:, 2] - a[:, 0]) * (a[:, 3] - a[:, 1])
    area_b = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
    return inter / np.maximum(area_a[:, None] + area_b[None, :] - inter, 1e-9)


class KalmanCV:
    def __init__(self, cx, cy, s):
        self.x = np.array([cx, cy, 0.0, 0.0])
        sig = max(2.0, 0.08 * s)
        self.P = np.diag([sig ** 2, sig ** 2, (2.0 * s) ** 2, (2.0 * s) ** 2])

    def predict(self, dt, s):
        F = np.array([[1, 0, dt, 0], [0, 1, 0, dt], [0, 0, 1, 0], [0, 0, 0, 1]], float)
        q = (0.5 * s / dt ** 2) ** 2 * 0.1
        d4, d3, d2 = dt ** 4 / 4, dt ** 3 / 2, dt ** 2
        Q = q * np.array([[d4, 0, d3, 0], [0, d4, 0, d3], [d3, 0, d2, 0], [0, d3, 0, d2]])
        self.x = F @ self.x
        self.P = F @ self.P @ F.T + Q

    def innovation(self, z, s):
        sig = max(2.0, 0.08 * s)
        R = np.eye(2) * sig ** 2
        y = np.asarray(z, float) - H_MAT @ self.x
        S = H_MAT @ self.P @ H_MAT.T + R
        return y, S

    def update(self, z, s):
        y, S = self.innovation(z, s)
        a, b, c, d = S[0, 0], S[0, 1], S[1, 0], S[1, 1]
        det = a * d - b * c
        S_inv = np.array([[d, -b], [-c, a]]) / det
        K = self.P @ H_MAT.T @ S_inv
        self.x = self.x + K @ y
        self.P = (np.eye(4) - K @ H_MAT) @ self.P
        return float(y @ S_inv @ y)


class Track:
    def __init__(self, tid, box, t, cls="person", conf=1.0):
        x1, y1, x2, y2 = box
        self.id = tid
        self.w, self.h = float(x2 - x1), float(y2 - y1)
        self.kf = KalmanCV((x1 + x2) / 2, (y1 + y2) / 2, self.scale)
        self.hits, self.misses, self.age = 1, 0, 1
        self.t = t
        self.cls, self.conf = cls, conf
        self.confirmed = False
        self.last_d2 = 0.0
        self.matched = True

    @property
    def scale(self):
        return float(np.sqrt(max(self.w * self.h, 1.0)))

    def box(self):
        cx, cy = self.kf.x[0], self.kf.x[1]
        return np.array([cx - self.w / 2, cy - self.h / 2, cx + self.w / 2, cy + self.h / 2])

    def predict(self, t):
        dt = max(t - self.t, 1e-3)
        self.kf.predict(dt, self.scale)
        self.t = t
        self.age += 1

    def update(self, box, conf):
        x1, y1, x2, y2 = box
        s = float(np.sqrt(max((x2 - x1) * (y2 - y1), 1.0)))
        self.last_d2 = self.kf.update(((x1 + x2) / 2, (y1 + y2) / 2), s)
        self.w = 0.7 * self.w + 0.3 * (x2 - x1)
        self.h = 0.7 * self.h + 0.3 * (y2 - y1)
        self.hits += 1
        self.misses = 0
        self.conf = conf
        self.matched = True


class Tracker:
    def __init__(self, iou_gate=0.25, confirm_hits=3, max_misses=15):
        self.iou_gate, self.confirm_hits, self.max_misses = iou_gate, confirm_hits, max_misses
        self.tracks = []
        self.next_id = 1

    def step(self, t, boxes, confs=None):
        """boxes: (N,4) detections at time t. Returns list of confirmed tracks matched this frame."""
        boxes = np.asarray(boxes, float).reshape(-1, 4)
        confs = np.ones(len(boxes)) if confs is None else np.asarray(confs, float)
        for tr in self.tracks:
            tr.predict(t)
            tr.matched = False
        pred = np.array([tr.box() for tr in self.tracks]).reshape(-1, 4)
        M = iou(pred, boxes)
        used_t, used_d = set(), set()
        if M.size:
            order = np.dstack(np.unravel_index(np.argsort(-M, axis=None), M.shape))[0]
            for ti, di in order:
                if M[ti, di] < self.iou_gate:
                    break
                if ti in used_t or di in used_d:
                    continue
                self.tracks[ti].update(boxes[di], confs[di])
                used_t.add(ti)
                used_d.add(di)
        alive = []
        for i, tr in enumerate(self.tracks):
            if i not in used_t:
                tr.misses += 1
            if tr.hits >= self.confirm_hits:
                tr.confirmed = True
            limit = self.max_misses if tr.confirmed else 2
            if tr.misses <= limit:
                alive.append(tr)
        self.tracks = alive
        for di in range(len(boxes)):
            if di not in used_d:
                self.tracks.append(Track(self.next_id, boxes[di], t, conf=confs[di]))
                self.next_id += 1
        return [tr for tr in self.tracks if tr.confirmed and tr.matched]
