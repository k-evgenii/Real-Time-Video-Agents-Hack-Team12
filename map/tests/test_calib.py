import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from calib import dlt, project, rmse  # noqa: E402
from team_colour import TeamAssigner, hex_to_feat, kmeans2  # noqa: E402

PITCH = np.array([[-52.5, -34], [52.5, -34], [52.5, 34], [-52.5, 34], [0, 0], [-36, -20.16], [36, 20.16]])


def test_dlt_recovers_known_homography():
    H_true = np.array([[0.08, 0.01, -60.0], [0.002, 0.15, -50.0], [0.00001, 0.0009, 1.0]])
    img = project(np.linalg.inv(H_true), PITCH)
    H = dlt(img, PITCH)
    assert rmse(H, img, PITCH) < 1e-6
    noisy = img + np.random.default_rng(1).normal(0, 1.0, img.shape)
    assert rmse(dlt(noisy, PITCH), noisy, PITCH) < 1.5


def test_kmeans_splits_two_kits():
    rng = np.random.default_rng(0)
    a, b = hex_to_feat("#2f6df6"), hex_to_feat("#e8e8e8")
    X = np.vstack([a + rng.normal(0, 0.03, (40, 3)), b + rng.normal(0, 0.03, (40, 3))])
    C, intra = kmeans2(X)
    lab = ((X[:, None] - C[None]) ** 2).sum(-1).argmin(1)
    assert len(set(lab[:40])) == 1 and len(set(lab[40:])) == 1 and lab[0] != lab[40]


def test_assigner_locks_and_flags_referee():
    rng = np.random.default_rng(2)
    a, b, ref = hex_to_feat("#2f6df6"), hex_to_feat("#e8e8e8"), hex_to_feat("#ffd400")
    ta = TeamAssigner("#2f6df6", "#e8e8e8", fit_seconds=1.0)
    for i in range(20):
        t = i * 0.2
        for tid in range(1, 6):
            ta.add(tid, t, a + rng.normal(0, 0.02, 3))
        for tid in range(6, 11):
            ta.add(tid, t, b + rng.normal(0, 0.02, 3))
        ta.add(99, t, ref + rng.normal(0, 0.02, 3))
    assert {ta.team(t) for t in range(1, 6)} == {0}
    assert {ta.team(t) for t in range(6, 11)} == {1}
    assert ta.team(99) == 2
