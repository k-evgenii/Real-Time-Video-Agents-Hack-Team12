#!/usr/bin/env python3
"""Episode features from PIVOT_TRAFFIC §3.3."""

from __future__ import annotations

FEATURE_NAMES = [
    "duration_s",
    "n_seg",
    "mean_vehicles",
    "max_vehicles",
    "mean_peds",
    "n_risk_events",
    "n_manoeuvres",
    "share_dense_or_stopped",
    "flow_code",
    "ended_by_code",
]
FLOW = {"F": 0, "M": 1, "D": 2, "S": 3, "U": 0}
ENDED = {"flow_change": 0, "risk_event": 1, "end": 2}
RISK = {
    "collision", "near_miss", "hard_braking", "sudden_stop", "wrong_way",
    "reversing", "pedestrian_in_road", "emergency_vehicle",
}
MANOEUVRE = {"lane_change", "overtaking", "u_turn", "turning"}


def feature_vector(attack: dict, segments_by_id: dict[str, dict]) -> list[float]:
    segs = [segments_by_id[sid] for sid in attack["seg_ids"] if sid in segments_by_id]
    vehicles = [int(s.get("n_vehicles") or 0) for s in segs] or [0]
    peds = [int(s.get("n_peds") or 0) for s in segs] or [0]
    flows = [s.get("flow") or attack.get("flow") or "U" for s in segs] or [attack.get("flow") or "U"]
    events = attack.get("events") or []
    return [
        float(attack["duration_s"]),
        float(attack["n_seg"]),
        sum(vehicles) / len(vehicles),
        float(max(vehicles)),
        sum(peds) / len(peds),
        float(sum(1 for e in events if e in RISK)),
        float(sum(1 for e in events if e in MANOEUVRE)),
        sum(1 for f in flows if f in {"D", "S"}) / len(flows),
        float(FLOW.get(attack.get("flow") or "U", 0)),
        float(ENDED.get(attack.get("ended_by") or "end", 2)),
    ]
