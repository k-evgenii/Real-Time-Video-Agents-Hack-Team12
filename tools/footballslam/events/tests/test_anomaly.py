import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from anomaly import build


def episode(team, i, duration, events, flow="M", vehicles=8, peds=0, ended_by="flow_change", n_seg=2):
    segs = []
    seg_ids = []
    t0 = i * 100
    step = duration / n_seg
    for n in range(n_seg):
        sid = f"{team}{i}_{n}"
        seg_ids.append(sid)
        segs.append({
            "seg_id": sid,
            "flow": flow,
            "scene": "H",
            "events": [events[min(n, len(events) - 1)]],
            "n_vehicles": vehicles,
            "n_peds": peds,
            "note": "",
            "t0": t0 + n * step,
            "t1": t0 + (n + 1) * step,
        })
    row = {
        "attack_id": f"{team}_{i:03d}",
        "team": team,
        "flow": flow,
        "t0": t0,
        "t1": t0 + duration,
        "seg_ids": seg_ids,
        "n_seg": n_seg,
        "duration_s": duration,
        "zones": ["H"] * n_seg,
        "events": events,
        "ended_by": ended_by,
    }
    return row, segs


def pack(rows):
    attacks, segments = [], []
    for row, segs in rows:
        attacks.append(row)
        segments.extend(segs)
    return attacks, segments


def test_three_outliers_are_in_top_five():
    rows = []
    for team in ("A", "B"):
        for i in range(40):
            rows.append(episode(team, i, 12, ["none"]))
        base = 40
        rows.append(episode(team, base, 80, ["hard_braking", "collision"], flow="S", vehicles=40, ended_by="risk_event", n_seg=8))
        rows.append(episode(team, base + 1, 3, ["lane_change", "u_turn"], flow="F", vehicles=2))
        rows.append(episode(team, base + 2, 25, ["pedestrian_in_road"], flow="D", vehicles=4, peds=6, ended_by="risk_event", n_seg=1))
    attacks, segments = pack(rows)
    doc = build("syn", attacks, segments)
    for team in ("A", "B"):
        ids = [row["attack_id"] for row in doc["per_team"][team]]
        for outlier in (40, 41, 42):
            assert f"{team}_{outlier:03d}" in ids


def test_longer_team_is_not_flagged_for_being_longer():
    rows = []
    for i in range(20):
        rows.append(episode("A", i, 12, ["none"], vehicles=8))
        rows.append(episode("B", i, 24, ["none"], vehicles=20))
    attacks, segments = pack(rows)
    doc = build("syn", attacks, segments)
    flagged = [row for row in doc["per_team"]["B"] if row["flagged"]]
    assert flagged == []
