"""Trajectory anomalies on top of track.py (PIVOT_TRAFFIC §3.4) + 8x8 flow field / wrong_way. Pure numpy.

Per confirmed track, matched this frame, with >= WARMUP hits:
  (a) r_norm = |y| / s          (innovation relative to box scale)
  (b) heading change dθ and speed ratio ρ between the Kalman velocity now and 5 frames ago, only when both speeds
      exceed 0.15 s/dt;  sig_b = max(dθ/(π/2), |log ρ| / log 2.5)
  (c) d² = yᵀ S⁻¹ y  ~ χ²(2)
  τ = max(9.21, q_0.995 of the scene d² pool (>= 300 samples));  inst = max(d²/τ, 0.5 r_norm/0.5 + 0.5 sig_b)
  score <- 0.7 score + 0.3 inst;  alert enters at score >= 1 for 3 frames, exits < 0.6 for 5, cooldown 30 frames.
  type: ρ < 0.4 hard_braking, ρ > 2.5 sudden_acceleration, dθ > 60° swerve, else unexplained_motion.
Flow field: 8x8 image grid accumulating unit velocities of fast-enough tracks; wrong_way when a track's unit velocity
has cos < -0.5 against a cell with n >= 50 for 5 consecutive frames.
"""
import math
from collections import deque

import numpy as np

CHI2_995 = 9.21
WARMUP = 10
LAG = 5
ENTER, ENTER_N = 1.0, 3
EXIT, EXIT_N = 0.6, 5
COOLDOWN = 30
FLOW_MIN_N = 50
WRONG_COS, WRONG_N = -0.5, 5
D2_HIST_MAX = 60
GATE_DT = 0.0        # speed gate 0.15 s / max(dt, GATE_DT); 0.1 lets slow far cars in and triples false alerts on I-24


class FlowField:
    def __init__(self, W, H, cols=8, rows=8):
        self.W, self.H, self.cols, self.rows = W, H, cols, rows
        self.sum = np.zeros((rows, cols, 2))
        self.n = np.zeros((rows, cols), int)
        self.speed = np.zeros((rows, cols))

    def cell(self, u, v):
        c = min(self.cols - 1, max(0, int(u / self.W * self.cols)))
        r = min(self.rows - 1, max(0, int(v / self.H * self.rows)))
        return r, c

    def add(self, u, v, vx, vy):
        sp = math.hypot(vx, vy)
        if sp <= 0:
            return
        r, c = self.cell(u, v)
        self.sum[r, c] += (vx / sp, vy / sp)
        self.n[r, c] += 1
        self.speed[r, c] += sp

    def direction(self, u, v):
        r, c = self.cell(u, v)
        n = self.n[r, c]
        if n < FLOW_MIN_N:
            return None, n
        d = self.sum[r, c]
        norm = np.hypot(*d)
        if norm < 0.6 * n:          # cell straddles opposite carriageways: no single lane direction to violate
            return None, n
        return d / norm, n

    def to_json(self):
        cells = []
        for r in range(self.rows):
            for c in range(self.cols):
                n = int(self.n[r, c])
                d = self.sum[r, c]
                norm = float(np.hypot(*d))
                ux, uy = (d / norm).tolist() if norm > 0 else (0.0, 0.0)
                cells.append([round(ux, 3), round(uy, 3), n, round(float(self.speed[r, c] / n), 1) if n else 0.0])
        return {"cols": self.cols, "rows": self.rows, "cells": cells}


class TrackState:
    __slots__ = ("vel", "score", "above", "below", "cooldown", "alert", "wrong", "last")

    def __init__(self):
        self.vel = deque(maxlen=LAG + 1)
        self.score = 0.0
        self.above = self.below = self.cooldown = self.wrong = 0
        self.alert = None
        self.last = {}


class SceneAnomaly:
    def __init__(self, W, H, tau=None, flow=None, warmup=WARMUP, enter_n=ENTER_N):
        self.W, self.H = W, H
        self.warmup, self.enter_n = warmup, enter_n
        self.fixed_tau = tau
        self.pool = []
        self.flow = flow or FlowField(W, H)          # display field (slower tracks too, fills both carriageways)
        self.rule_flow = FlowField(W, H)             # wrong_way field: only tracks above the full speed gate
        self.states = {}
        self.alerts = []

    @property
    def tau(self):
        if self.fixed_tau is not None:
            return self.fixed_tau
        if len(self.pool) >= 300:
            return max(CHI2_995, float(np.quantile(self.pool, 0.995)))
        return CHI2_995

    def _open(self, st, tid, t, typ, u, v):
        st.alert = {"track_id": int(tid), "t0": round(t, 2), "t1": round(t, 2), "type": typ, "peak_d2": 0.0,
                    "peak_score": 0.0, "u": int(u), "v": int(v), "d2_hist": [], "dtheta_deg": None,
                    "n_frames": 0, "tau": round(self.tau, 2)}

    def _close(self, st):
        a = st.alert
        if a is not None:
            self.alerts.append(a)
        st.alert = None
        st.cooldown = COOLDOWN
        st.above = st.below = 0

    def step(self, t, dt, tracks):
        """tracks: confirmed tracks matched this frame. Returns {track_id: score} for all of them."""
        scores = {}
        live = set()
        for tr in tracks:
            tid = tr.id
            live.add(tid)
            st = self.states.get(tid)
            if st is None:
                st = self.states[tid] = TrackState()
            px, py, vx, vy = tr.kf.x
            st.vel.append((vx, vy))
            if tr.hits < self.warmup:
                scores[tid] = 0.0
                continue
            s = tr.scale
            d2 = tr.last_d2
            self.pool.append(d2)
            tau = self.tau
            r_norm = tr.last_r
            vmin = 0.15 * s / max(dt, GATE_DT)
            sig_b, rho, dth = 0.0, None, None
            if len(st.vel) > LAG:
                v0 = st.vel[0]
                s0, s1 = math.hypot(*v0), math.hypot(vx, vy)
                if s0 > vmin:
                    # ρ only needs the earlier speed above the gate, so a stop still reads as braking
                    rho = max(s1, 1e-3) / s0
                    sig_b = abs(math.log(rho)) / math.log(2.5)
                    if s1 > vmin:
                        cosang = (v0[0] * vx + v0[1] * vy) / (s0 * s1)
                        dth = math.acos(max(-1.0, min(1.0, cosang)))
                        sig_b = max(sig_b, dth / (math.pi / 2))
                elif s1 > vmin:
                    rho = s1 / max(s0, 1e-3)
                    sig_b = min(abs(math.log(rho)) / math.log(2.5), 3.0)
            inst = max(d2 / tau, 0.5 * r_norm / 0.5 + 0.5 * sig_b)
            st.score = 0.7 * st.score + 0.3 * inst
            st.last = {"rho": rho, "dth": dth, "d2": d2}

            # flow field + wrong way
            speed = math.hypot(vx, vy)
            wrong_now = False
            if speed > vmin:
                d, n = self.rule_flow.direction(px, py)
                if d is not None and (vx * d[0] + vy * d[1]) / speed < WRONG_COS:
                    wrong_now = True
                if st.alert is None:
                    self.rule_flow.add(px, py, vx, vy)
            if speed > vmin / 3 and st.alert is None:
                self.flow.add(px, py, vx, vy)
            st.wrong = st.wrong + 1 if wrong_now else 0

            if st.cooldown > 0:
                st.cooldown -= 1
            if st.alert is None and st.cooldown == 0:
                st.above = st.above + 1 if st.score >= ENTER else 0
                if st.wrong >= WRONG_N:
                    self._open(st, tid, t, "wrong_way", px, py)
                elif st.above >= self.enter_n:
                    self._open(st, tid, t, classify(rho, dth), px, py)
            if st.alert is not None:
                a = st.alert
                a["t1"] = round(t, 2)
                a["n_frames"] += 1
                if len(a["d2_hist"]) < D2_HIST_MAX:
                    a["d2_hist"].append(round(d2, 1))
                if st.score > a["peak_score"]:
                    a["peak_score"] = round(st.score, 2)
                    a["u"], a["v"] = int(px), int(py)
                if rho is not None:
                    a["rho_min"] = round(min(a.get("rho_min", rho), rho), 2)
                    a["rho_max"] = round(max(a.get("rho_max", rho), rho), 2)
                if dth is not None:
                    a["dtheta_deg"] = round(max(a["dtheta_deg"] or 0.0, math.degrees(dth)), 1)
                if a["type"] != "wrong_way":
                    a["type"] = classify_alert(a)
                a["peak_d2"] = max(a["peak_d2"], round(d2, 1))
                st.below = st.below + 1 if (st.score < EXIT and st.wrong == 0) else 0
                if st.below >= EXIT_N:
                    self._close(st)
            scores[tid] = st.score
        for tid, st in self.states.items():
            if tid not in live and st.alert is not None and st.alert["t1"] < t - 1.0:
                self._close(st)
        return scores

    def finish(self):
        for st in self.states.values():
            if st.alert is not None:
                self._close(st)
        for a in self.alerts:
            a["reason"] = reason(a)
        return sorted(self.alerts, key=lambda a: -a["peak_score"])


def classify(rho, dth):
    if rho is not None and rho < 0.4:
        return "hard_braking"
    if rho is not None and rho > 2.5:
        return "sudden_acceleration"
    if dth is not None and dth > math.radians(60):
        return "swerve"
    return "unexplained_motion"


def classify_alert(a):
    if a.get("dtheta_deg") is not None and a["dtheta_deg"] > 60:
        return "swerve"
    if a.get("rho_min") is not None and a["rho_min"] < 0.4:
        return "hard_braking"
    if a.get("rho_max") is not None and a["rho_max"] > 2.5:
        return "sudden_acceleration"
    return "unexplained_motion"


def reason(a):
    bits = [f"d²={a['peak_d2']:.1f} vs τ={a['tau']:.1f} for {a['n_frames']} frames"]
    if a["type"] == "wrong_way":
        bits.append("moving against the learned lane flow → wrong way")
    elif a["type"] == "hard_braking":
        bits.append(f"speed ratio {a['rho_min']:.2f} → hard braking")
    elif a["type"] == "sudden_acceleration":
        bits.append(f"speed ratio {a['rho_max']:.2f} → sudden acceleration")
    elif a.get("dtheta_deg") is not None and a["type"] == "swerve":
        bits.append(f"heading change {a['dtheta_deg']:.0f}° → swerve")
    else:
        bits.append("motion the constant-velocity model can't explain")
    return "; ".join(bits)
