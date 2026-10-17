import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from anomaly_track import SceneAnomaly  # noqa: E402
from track import Tracker  # noqa: E402

FPS = 30.0
DT = 1 / FPS
BW, BH = 60, 40
SIG = 0.08 * math.sqrt(BW * BH)


def box(cx, cy):
    return [cx - BW / 2, cy - BH / 2, cx + BW / 2, cy + BH / 2]


def run(path_fn, n_frames, rng, scene=None, noise=SIG * 0.5):
    tr = Tracker(q_dt=0.2)
    sc = scene or SceneAnomaly(1920, 1080)
    d2s, first_alert_frame = [], None
    for f in range(n_frames):
        cx, cy = path_fn(f)
        jx, jy = rng.normal(0, noise, 2)
        active = tr.step(f * DT, [box(cx + jx, cy + jy)])
        sc.step(f * DT, DT, active)
        for t_ in active:
            if t_.hits >= 10:
                d2s.append(t_.last_d2)
        if first_alert_frame is None and any(st.alert for st in sc.states.values()):
            first_alert_frame = f
    return sc, d2s, first_alert_frame


def test_straight_motion_no_alert():
    rng = np.random.default_rng(0)
    sc, d2s, first = run(lambda f: (100 + 12 * f, 500), 140, rng)
    alerts = sc.finish()
    assert 0.3 < np.mean(d2s) < 3.5, np.mean(d2s)
    assert alerts == [] and first is None


def test_sudden_stop_alerts_quickly():
    rng = np.random.default_rng(1)
    stop = 60
    sc, _, first = run(lambda f: (100 + 12 * min(f, stop), 500), 110, rng)
    alerts = sc.finish()
    assert first is not None and first - stop <= 6, first
    assert alerts[0]["type"] == "hard_braking"


def test_swerve_alerts():
    rng = np.random.default_rng(2)
    turn = 60

    def path(f):
        if f < turn:
            return 100 + 12 * f, 500
        return 100 + 12 * turn, 500 + 12 * (f - turn)
    sc, _, first = run(path, 110, rng)
    alerts = sc.finish()
    assert first is not None and first - turn <= 8, first
    assert alerts[0]["type"] in ("swerve", "unexplained_motion", "hard_braking")


def test_wrong_way_in_trained_flow():
    rng = np.random.default_rng(3)
    sc = SceneAnomaly(1920, 1080)
    for k in range(6):                                   # train: six cars driving right along y=500
        run(lambda f, k=k: (50 + 12 * f, 500 + 3 * k), 150, rng, scene=sc)
    sc.alerts.clear()
    sc.states.clear()
    tr = Tracker(q_dt=0.2)
    tr.next_id = 1000
    wrong = None
    for f in range(120):                                 # one car driving left in the same lane
        active = tr.step(f * DT, [box(1800 - 12 * f + rng.normal(0, 1), 500 + rng.normal(0, 1))])
        sc.step(f * DT, DT, active)
        if wrong is None and any(st.alert and st.alert["type"] == "wrong_way" for st in sc.states.values()):
            wrong = f
    assert wrong is not None
    assert any(a["type"] == "wrong_way" for a in sc.finish())
