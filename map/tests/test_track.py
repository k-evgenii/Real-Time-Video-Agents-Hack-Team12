import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from track import Tracker, iou  # noqa: E402

FPS = 30.0
W, H = 30, 70


def box_at(cx, cy):
    return [cx - W / 2, cy - H / 2, cx + W / 2, cy + H / 2]


def test_iou_basic():
    assert abs(iou([[0, 0, 10, 10]], [[0, 0, 10, 10]])[0, 0] - 1) < 1e-9
    assert iou([[0, 0, 10, 10]], [[20, 20, 30, 30]])[0, 0] == 0


def test_crossing_tracks_no_swap():
    """Two players run towards each other on lines separated by more than one box height."""
    tr = Tracker()
    ids_a, ids_b = [], []
    for f in range(90):
        t = f / FPS
        a = box_at(100 + 8 * f, 300)
        b = box_at(820 - 8 * f, 300 + 1.2 * H)
        out = tr.step(t, [a, b])
        for trk in out:
            cy = trk.box()[1] + H / 2
            (ids_a if abs(cy - 300) < H / 2 else ids_b).append(trk.id)
    assert len(set(ids_a)) == 1 and len(set(ids_b)) == 1
    assert set(ids_a) != set(ids_b)


def test_gap_reacquired_or_recreated():
    tr = Tracker()
    seen = []
    for f in range(60):
        t = f / FPS
        dets = [] if 20 <= f < 30 else [box_at(100 + 3 * f, 200)]
        out = tr.step(t, dets)
        seen.append([trk.id for trk in out])
    before = {i for s in seen[10:20] for i in s}
    after = {i for s in seen[40:60] for i in s}
    assert len(before) == 1 and len(after) == 1
    # either the same id (re-acquired) or a fresh one with the old track gone
    if before != after:
        assert all(trk.id not in before for trk in tr.tracks)


def test_static_many_players_stable_ids():
    rng = np.random.default_rng(0)
    centres = rng.uniform([100, 100], [1800, 1000], size=(22, 2))
    tr = Tracker()
    last = None
    for f in range(45):
        jitter = rng.normal(0, 1.0, size=centres.shape)
        out = tr.step(f / FPS, [box_at(*c) for c in centres + jitter])
        last = {trk.id for trk in out}
    assert len(last) == 22
