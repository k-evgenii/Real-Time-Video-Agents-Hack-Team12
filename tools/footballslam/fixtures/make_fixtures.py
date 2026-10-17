#!/usr/bin/env python3
"""Write the synthetic i24_cam-1 bundle under data/demo/."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "demo"
SCENE = "i24_cam-1"
PENDING = "s3://fixture/pending"
RISK = {
    "collision",
    "near_miss",
    "hard_braking",
    "sudden_stop",
    "wrong_way",
    "reversing",
    "pedestrian_in_road",
    "emergency_vehicle",
}
MANOEUVRE = {"lane_change", "overtaking", "u_turn", "turning"}
FLOW_CODE = {"F": 0, "M": 1, "D": 2, "S": 3}
ENDED_CODE = {"flow_change": 0, "risk_event": 1, "end": 2}
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
LABELS = {
    "duration_s": ("duration", "s"),
    "n_seg": ("segments", "segments"),
    "mean_vehicles": ("mean vehicles", "vehicles"),
    "max_vehicles": ("max vehicles", "vehicles"),
    "mean_peds": ("mean pedestrians", "pedestrians"),
    "n_risk_events": ("risk events", "events"),
    "n_manoeuvres": ("manoeuvres", "manoeuvres"),
    "share_dense_or_stopped": ("dense or stopped share", "share"),
    "flow_code": ("flow code", "code"),
    "ended_by_code": ("ended-by code", "code"),
}


def dump(path, doc):
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def segment(idx, flow, vehicles, peds, events, direction="R", light="D", note=""):
    t0 = idx * 8.0
    return {
        "match_id": SCENE,
        "part": 0,
        "seg_idx": idx,
        "t0": t0,
        "t1": t0 + 8.0,
        "flow": flow,
        "direction": direction,
        "scene": "H",
        "n_vehicles": vehicles,
        "n_peds": peds,
        "light": light,
        "events": events,
        "note": note,
        "source": PENDING,
        "original_video": PENDING,
        "parse_ok": True,
    }


def build_segments():
    """60 segments, 8 s apart. Twelve flow runs, two of them extreme."""
    recipe = []

    def add_run(flow, count, vehicles, peds=0, events=None, direction="R", light="D", note=""):
        for j in range(count):
            ev = events[j] if events else ["none"]
            nt = note if j == count - 1 else ""
            veh = vehicles[j] if isinstance(vehicles, list) else vehicles
            recipe.append((flow, veh, peds if not isinstance(peds, list) else peds[j], ev, direction, light, nt))

    # Nine ordinary runs, alternating free and moderate, one single U gap.
    # Means step by 0.4 and every run peaks at 14, so normals stay one cluster.
    ordinary = [
        ("F", [10, 11, 10, 10, 14], "R"),
        ("M", [10, 11, 11, 10, 14], "R"),
        ("F", [11, 11, 11, 10, 14], "R"),
        ("M", [11, 11, 11, 11, 14], "R"),
        ("F", [11, 12, 11, 11, 14], "L"),
        ("M", [12, 12, 11, 11, 14], "R"),
        ("F", [12, 12, 12, 11, 14], "R"),
        ("M", [12, 12, 12, 12, 14], "R"),
        ("F", [13, 12, 12, 12, 14], "R"),
    ]
    for i, (flow, vehs, direction) in enumerate(ordinary):
        events = [["none"]] * 5
        # Non-scoring events keep the clip plausible without moving the 10 features.
        if i == 2:
            events[2] = ["cyclist"]
        if i == 6:
            events[1] = ["debris"]
        if i == 8:
            events[3] = ["parking"]
        light = "R" if i == 5 else "D"
        add_run(flow, 5, vehs, events=events, direction=direction, light=light)
        if i == 3:
            # Replace the middle segment with one unclear gap. The episode stays open.
            slot = len(recipe) - 3
            recipe[slot] = ("U", 12, 0, ["none"], "U", "D", "")

    # Stopped-queue outlier. Risk labels sit on the closing segment only.
    add_run(
        "S",
        5,
        [50, 48, 52, 47, 49],
        peds=[6, 7, 8, 5, 9],
        events=[
            ["stopped_vehicle"],
            ["stopped_vehicle"],
            ["parking"],
            ["debris"],
            ["hard_braking", "collision", "near_miss"],
        ],
        note="queue collapse after a hard brake",
    )
    # Ordinary free run between the two outliers.
    add_run("F", 5, [13, 13, 12, 12, 14], events=[["none"], ["tailgating"], ["none"], ["none"], ["none"]])
    # Dense manoeuvre outlier, closed by a wrong-way risk.
    add_run(
        "D",
        5,
        [26, 28, 24, 30, 27],
        peds=[11, 12, 10, 14, 13],
        events=[
            ["lane_change", "overtaking"],
            ["u_turn", "turning"],
            ["lane_change", "turning"],
            ["overtaking", "cyclist"],
            ["wrong_way", "pedestrian_in_road", "u_turn"],
        ],
        direction="X",
        note="vehicle turns across dense lanes",
    )
    if len(recipe) != 60:
        raise SystemExit(f"recipe length {len(recipe)}")
    return [segment(i, *row) for i, row in enumerate(recipe)]


def episodes_from(segments):
    found = []
    open_ep = None

    def close(ended_by):
        nonlocal open_ep
        open_ep["ended_by"] = ended_by
        open_ep["t1"] = open_ep["rows"][-1]["t1"]
        found.append(open_ep)
        open_ep = None

    for seg in segments:
        flow = seg["flow"]
        risky = any(ev in RISK for ev in seg["events"])
        if open_ep is None:
            if flow in "FMDS":
                open_ep = {"flow": flow, "rows": [seg], "u_run": 0}
                if risky:
                    close("risk_event")
            continue
        same = flow == open_ep["flow"]
        gap = flow == "U" and open_ep["u_run"] == 0
        if same or gap:
            open_ep["rows"].append(seg)
            open_ep["u_run"] = open_ep["u_run"] + 1 if flow == "U" else 0
            if risky:
                close("risk_event")
            continue
        if flow in "FMDS":
            close("flow_change")
            open_ep = {"flow": flow, "rows": [seg], "u_run": 0}
            if risky:
                close("risk_event")
            continue
        close("flow_change")
    if open_ep is not None:
        close("end")

    attacks = []
    for n, ep in enumerate(found, start=1):
        rows = ep["rows"]
        events = []
        scenes = []
        for row in rows:
            for ev in row["events"]:
                if ev not in events:
                    events.append(ev)
            if row["scene"] not in scenes:
                scenes.append(row["scene"])
        attacks.append(
            {
                "attack_id": f"ep-{n:02d}",
                "team": "A",
                "flow": ep["flow"],
                "t0": rows[0]["t0"],
                "t1": rows[-1]["t1"],
                "n_seg": len(rows),
                "part": 0,
                "scenes": scenes,
                "events": events,
                "ended_by": ep["ended_by"],
                "rows": rows,
            }
        )
    return attacks


def features_of(ep):
    rows = ep["rows"]
    vehicles = [r["n_vehicles"] for r in rows]
    peds = [r["n_peds"] for r in rows]
    n_risk = sum(1 for r in rows for ev in r["events"] if ev in RISK)
    n_man = sum(1 for r in rows for ev in r["events"] if ev in MANOEUVRE)
    share = sum(1 for r in rows if r["flow"] in ("D", "S")) / len(rows)
    return [
        ep["t1"] - ep["t0"],
        len(rows),
        sum(vehicles) / len(rows),
        max(vehicles),
        sum(peds) / len(rows),
        n_risk,
        n_man,
        share,
        FLOW_CODE[ep["flow"]],
        ENDED_CODE[ep["ended_by"]],
    ]


def median(values):
    ys = sorted(values)
    n = len(ys)
    mid = n // 2
    if n % 2:
        return ys[mid]
    return 0.5 * (ys[mid - 1] + ys[mid])


def robust_z(matrix):
    cols = list(zip(*matrix))
    zrows = []
    meds = []
    for col in cols:
        med = median(col)
        mad = 1.4826 * median([abs(v - med) for v in col]) + 1e-6
        meds.append(med)
        zrows.append([max(-5.0, min(5.0, (v - med) / mad)) for v in col])
    return [list(row) for row in zip(*zrows)], meds


def knn_scores(zrows):
    n = len(zrows)
    k = max(3, round(n ** 0.5))
    dists = []
    for i, left in enumerate(zrows):
        order = sorted(
            (sum((a - b) ** 2 for a, b in zip(left, right)) ** 0.5 for j, right in enumerate(zrows) if j != i)
        )
        dists.append(sum(order[:k]) / k)
    med = median(dists) or 1e-6
    return [d / med for d in dists]


def rarity_moment(ep, segments):
    counts = {}
    for seg in segments:
        for ev in seg["events"]:
            if ev != "none":
                counts[ev] = counts.get(ev, 0) + 1
    best = None
    for row in ep["rows"]:
        score = sum(1.0 / counts.get(ev, 1) for ev in row["events"] if ev != "none")
        key = (score, 1 if row["note"] else 0, -row["t0"])
        if best is None or key > best[0]:
            best = (key, row)
    return best[1]


def reason_text(name, z, value, med):
    shown = round(value, 1) if isinstance(value, float) else value
    base = round(med, 1) if isinstance(med, float) else med
    side = "above" if z >= 0 else "below"
    label, unit = LABELS[name]
    return f"{label} {abs(z):.1f}σ {side} camera median ({shown} vs {base} {unit})"


def build_anomalies(attacks, segments):
    matrix = [features_of(ep) for ep in attacks]
    zrows, meds = robust_z(matrix)
    scores = knn_scores(zrows)
    order = sorted(range(len(attacks)), key=lambda i: (-scores[i], attacks[i]["attack_id"]))
    rank_of = {idx: rank for rank, idx in enumerate(order, start=1)}
    rows = []
    for i, ep in enumerate(attacks):
        top = sorted(range(10), key=lambda j: abs(zrows[i][j]), reverse=True)[:3]
        moment = rarity_moment(ep, segments)
        score = round(scores[i], 3)
        rows.append(
            {
                "attack_id": ep["attack_id"],
                "rank": rank_of[i],
                "s_feat": score,
                "s_emb": None,
                "flagged": score >= 2.5,
                "agree": False,
                "features": [round(v, 3) for v in matrix[i]],
                "z": [round(v, 3) for v in zrows[i]],
                "reasons": [reason_text(FEATURE_NAMES[j], zrows[i][j], matrix[i][j], meds[j]) for j in top],
                "moment": {"t": moment["t0"], "seg_idx": moment["seg_idx"], "source": PENDING},
            }
        )
    rows.sort(key=lambda r: r["rank"])
    return rows


def build_map():
    fps = 1
    duration = 480
    lanes = [80, 200, 320, 440, 560]
    classes = [0, 0, 1, 0, 0, 2, 0, 0, 3, 0, 0, 0, 1, 0, 0]
    alerts = [
        {
            "track_id": 4,
            "t0": 80,
            "t1": 88,
            "type": "hard_braking",
            "peak_d2": 18.4,
            "peak_score": 1.6,
            "u": 3,
            "v": 2,
            "tau": 11.2,
            "d2_hist": [4.2, 7.1, 11.4, 15.6, 18.4, 16.2, 11.0, 7.4],
        },
        {
            "track_id": 11,
            "t0": 200,
            "t1": 208,
            "type": "swerve",
            "peak_d2": 16.8,
            "peak_score": 1.85,
            "u": 5,
            "v": 4,
            "tau": 11.2,
            "d2_hist": [3.4, 6.2, 10.8, 14.1, 16.8, 15.0, 9.6, 6.1],
        },
    ]
    alert_at = {(a["track_id"], t): a for a in alerts for t in range(int(a["t0"]), int(a["t1"]) + 1)}
    frames = []
    for t in range(0, duration, fps):
        points = []
        for n in range(1, 16):
            lane = lanes[(n - 1) % 5]
            x = (40 * n + 70 * t) % 1001
            y = lane
            score = 0
            vx = 70
            hit = alert_at.get((n, t))
            if hit and hit["type"] == "hard_braking":
                score = 160
                vx = 12
            elif hit and hit["type"] == "swerve":
                score = 185
                y = min(680, lane + 40)
            points.append([n, classes[n - 1], int(x), int(y), 48 if classes[n - 1] == 1 else 36, 22 if classes[n - 1] else 18, vx, 0, score])
        frames.append({"t": t, "p": points})
    cells = []
    for v in range(8):
        for _u in range(8):
            if 1 <= v <= 5:
                cells.append([1.0, 0.0, 60, 40.0])
            else:
                cells.append([0.0, 0.0, 0, 0.0])
    return {
        "match_id": SCENE,
        "mode": "FLOW",
        "fps": fps,
        "flow": {"cols": 8, "rows": 8, "cells": cells},
        "alerts": alerts,
        "frames": frames,
    }


def main():
    segments = build_segments()
    attacks = episodes_from(segments)
    if len(attacks) != 12:
        summary = [(a["attack_id"], a["flow"], a["n_seg"], a["ended_by"]) for a in attacks]
        raise SystemExit(f"expected 12 episodes, got {summary}")
    anomalies = build_anomalies(attacks, segments)
    top = [r for r in anomalies if r["rank"] <= 2]
    flagged = [r for r in anomalies if r["flagged"]]
    if {r["attack_id"] for r in top} != {"ep-10", "ep-12"} or any(r["s_feat"] < 2.5 for r in top):
        raise SystemExit(f"outliers did not rank 1 and 2: {[(r['attack_id'], r['rank'], r['s_feat']) for r in anomalies]}")
    if {r["attack_id"] for r in flagged} != {"ep-10", "ep-12"}:
        raise SystemExit(f"expected only the two outliers flagged: {flagged}")
    public = []
    for ep in attacks:
        row = dict(ep)
        row.pop("rows")
        public.append(row)
    mp = build_map()
    raw = json.dumps(mp, separators=(",", ":")).encode("utf-8")
    if len(raw) >= 400 * 1024:
        raise SystemExit(f"map.json is {len(raw)} bytes")
    sim = json.loads(raw)
    sim["simulated"] = True
    sim["alerts"] = list(sim["alerts"]) + [
        {
            "track_id": 9,
            "t0": 300,
            "t1": 308,
            "type": "wrong_way",
            "peak_d2": 24.5,
            "peak_score": 1.9,
            "u": 4,
            "v": 3,
            "tau": 11.2,
            "d2_hist": [5.0, 9.4, 14.8, 20.1, 24.5, 22.0, 15.2, 8.8],
            "reason": "unit velocity cos −0.92 against a cell with n=60 for 8 frames → wrong way",
        }
    ]
    for frame in sim["frames"]:
        t = frame["t"]
        if 300 <= t <= 308:
            for point in frame["p"]:
                if point[0] == 9:
                    point[6] = -70
                    point[8] = 210
    track_alerts = []
    for alert, reason in zip(
        mp["alerts"],
        [
            "d²=18.4 vs τ=11.2 for 8 frames; speed ratio 0.31 → hard braking",
            "d²=16.8 vs τ=11.2 for 8 frames; heading change 74° → swerve",
        ],
    ):
        row = dict(alert)
        row["reason"] = reason
        track_alerts.append(row)

    OUT.mkdir(parents=True, exist_ok=True)
    dump(OUT / "segments.json", {"match_id": SCENE, "segments": segments})
    dump(OUT / "attacks.json", {"match_id": SCENE, "attacks": public})
    dump(OUT / "anomalies.json", {"match_id": SCENE, "feature_names": FEATURE_NAMES, "per_team": {"A": anomalies}})
    (OUT / "map.json").write_bytes(raw + b"\n")
    dump(OUT / "track_alerts.json", track_alerts)
    dump(OUT / "map_sim.json", sim)
    print(f"wrote {OUT}")
    print(f"segments {len(segments)} episodes {len(public)} map_bytes {len(raw) + 1}")
    print("ranks", [(r["attack_id"], r["rank"], r["s_feat"], r["flagged"]) for r in anomalies[:4]])


if __name__ == "__main__":
    main()
