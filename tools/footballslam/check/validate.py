#!/usr/bin/env python3
"""Validate traffic scene JSON. Stdlib only. Exit 1 with a readable list."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

FLOWS = set("FMDSU")
EPISODE_FLOWS = set("FMDS")
DIRECTIONS = set("LRTAXU")
SCENES = set("HSRICU")
LIGHTS = set("DNRU")
EVENTS = {
    "lane_change",
    "hard_braking",
    "sudden_stop",
    "stopped_vehicle",
    "reversing",
    "wrong_way",
    "u_turn",
    "overtaking",
    "tailgating",
    "pedestrian_crossing",
    "pedestrian_in_road",
    "jaywalking",
    "cyclist",
    "emergency_vehicle",
    "collision",
    "near_miss",
    "debris",
    "parking",
    "turning",
    "none",
}
ENDED = {"flow_change", "risk_event", "end"}
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
ALERT_TYPES = {
    "hard_braking",
    "hard_braking/stop",
    "stop",
    "sudden_acceleration",
    "swerve",
    "unexplained_motion",
    "wrong_way",
}
FOOTBALL_KEYS = {
    "possession",
    "teams",
    "zone",
    "n_players",
    "tempo",
    "ball",
    "max_zone",
    "outcome",
}
LANE_A = {"name": "Scene episodes (Cosmos)", "colour": "#2f6df6"}
LANE_B = {"name": "Trajectory alerts (Kalman)", "colour": "#f6b02f"}
PENDING = "s3://fixture/pending"
MAP_LIMIT = 400 * 1024


def load_json(path, errors):
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"{path}: {exc}")
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        errors.append(f"{path}: invalid JSON ({exc})")
        return None


def walk_keys(node, path, errors):
    if isinstance(node, dict):
        for key, value in node.items():
            if key in FOOTBALL_KEYS:
                errors.append(f"{path}: football-only key {key}")
            here = f"{path}.{key}" if path else key
            if key in ("map_mode", "mode") and value in ("FULL", "RELATIVE"):
                errors.append(f"{here}: {value} is football-only; use FLOW or NONE")
            walk_keys(value, here, errors)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            walk_keys(value, f"{path}[{i}]", errors)


def is_num(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def require(cond, errors, message):
    if not cond:
        errors.append(message)


def check_segment(seg, path, errors):
    if not isinstance(seg, dict):
        errors.append(f"{path}: segment must be an object")
        return
    flow = seg.get("flow")
    scene = seg.get("scene")
    require(flow in FLOWS, errors, f"{path}: flow {flow!r} not in F|M|D|S|U")
    require(seg.get("direction") in DIRECTIONS, errors, f"{path}: direction invalid")
    require(scene in SCENES, errors, f"{path}: scene {scene!r} not in H|S|R|I|C|U")
    require(seg.get("light") in LIGHTS, errors, f"{path}: light invalid")
    require(is_int(seg.get("n_vehicles")) and seg["n_vehicles"] >= 0, errors, f"{path}: n_vehicles must be an int ≥ 0")
    require(is_int(seg.get("n_peds")) and seg["n_peds"] >= 0, errors, f"{path}: n_peds must be an int ≥ 0")
    events = seg.get("events")
    require(isinstance(events, list) and events, errors, f"{path}: events must be a non-empty list")
    if isinstance(events, list):
        bad = [e for e in events if e not in EVENTS]
        require(not bad, errors, f"{path}: unknown events {bad}")
        if "none" in events:
            require(events == ["none"], errors, f"{path}: none must be the only event")
    t0, t1 = seg.get("t0"), seg.get("t1")
    require(is_num(t0) and is_num(t1) and t1 > t0, errors, f"{path}: need t0 < t1")
    parsed = flow in FLOWS and scene in SCENES
    require(seg.get("parse_ok") is parsed, errors, f"{path}: parse_ok must be {parsed} (flow and scene parsed)")
    require(isinstance(seg.get("source"), str) and seg["source"].startswith("s3://"), errors, f"{path}: source must be an s3 URI")
    require(
        isinstance(seg.get("original_video"), str) and seg["original_video"].startswith("s3://"),
        errors,
        f"{path}: original_video must be an s3 URI",
    )


def check_segments(doc, path, errors):
    require(isinstance(doc, dict), errors, f"{path}: object required")
    if not isinstance(doc, dict):
        return []
    rows = doc.get("segments")
    require(isinstance(rows, list) and rows, errors, f"{path}: segments must be a non-empty list")
    if not isinstance(rows, list):
        return []
    for i, seg in enumerate(rows):
        check_segment(seg, f"{path} segments[{i}]", errors)
    return rows


def check_attacks(doc, path, errors):
    require(isinstance(doc, dict), errors, f"{path}: object required")
    if not isinstance(doc, dict):
        return []
    rows = doc.get("attacks")
    require(isinstance(rows, list) and rows, errors, f"{path}: attacks must be a non-empty list")
    if not isinstance(rows, list):
        return []
    for i, row in enumerate(rows):
        where = f"{path} attacks[{i}]"
        if not isinstance(row, dict):
            errors.append(f"{where}: object required")
            continue
        require(row.get("team") == "A", errors, f"{where}: team must be \"A\"")
        require(row.get("flow") in EPISODE_FLOWS, errors, f"{where}: flow must be F|M|D|S")
        require(row.get("ended_by") in ENDED, errors, f"{where}: ended_by invalid")
        require(isinstance(row.get("attack_id"), str) and row["attack_id"], errors, f"{where}: attack_id required")
        require(is_int(row.get("n_seg")) and row["n_seg"] >= 1, errors, f"{where}: n_seg must be an int ≥ 1")
        require(is_num(row.get("t0")) and is_num(row.get("t1")) and row["t1"] > row["t0"], errors, f"{where}: need t0 < t1")
    return rows


def check_anomalies(doc, path, errors, attacks):
    require(isinstance(doc, dict), errors, f"{path}: object required")
    if not isinstance(doc, dict):
        return []
    require(doc.get("feature_names") == FEATURE_NAMES, errors, f"{path}: feature_names must be the 10 traffic features in order")
    per = doc.get("per_team")
    require(isinstance(per, dict), errors, f"{path}: per_team object required")
    if not isinstance(per, dict):
        return []
    extra = set(per) - {"A"}
    require(not extra, errors, f"{path}: per_team keys {sorted(extra)} are not lane A")
    rows = per.get("A")
    require(isinstance(rows, list) and rows, errors, f"{path}: per_team.A must be a non-empty list")
    if not isinstance(rows, list):
        return []
    attack_ids = [a.get("attack_id") for a in attacks if isinstance(a, dict)]
    seen = []
    for i, row in enumerate(rows):
        where = f"{path} per_team.A[{i}]"
        if not isinstance(row, dict):
            errors.append(f"{where}: object required")
            continue
        require(isinstance(row.get("attack_id"), str), errors, f"{where}: attack_id required")
        require(is_int(row.get("rank")) and row["rank"] >= 1, errors, f"{where}: rank must be an int ≥ 1")
        require(is_num(row.get("s_feat")), errors, f"{where}: s_feat must be a number")
        s_emb = row.get("s_emb")
        require(s_emb is None or is_num(s_emb), errors, f"{where}: s_emb must be a number or null")
        require(isinstance(row.get("flagged"), bool), errors, f"{where}: flagged must be a bool")
        require(isinstance(row.get("agree"), bool), errors, f"{where}: agree must be a bool")
        if row.get("agree") is True:
            require(
                is_num(row.get("s_feat")) and row["s_feat"] >= 2.5 and is_num(s_emb) and s_emb >= 2.5,
                errors,
                f"{where}: agree requires s_feat and s_emb ≥ 2.5",
            )
        z = row.get("z")
        require(isinstance(z, list) and len(z) == 10 and all(is_num(v) and -5 <= v <= 5 for v in z), errors, f"{where}: z must be 10 numbers in [-5, 5]")
        features = row.get("features")
        if features is not None:
            require(isinstance(features, list) and len(features) == 10 and all(is_num(v) for v in features), errors, f"{where}: features must be 10 numbers")
        reasons = row.get("reasons")
        require(isinstance(reasons, list) and reasons and all(isinstance(r, str) and r for r in reasons), errors, f"{where}: reasons must be non-empty strings")
        moment = row.get("moment")
        require(isinstance(moment, dict) and is_num(moment.get("t")), errors, f"{where}: moment.t required")
        if isinstance(moment, dict) and isinstance(moment.get("source"), str):
            require(moment["source"].startswith("s3://"), errors, f"{where}: moment.source must be an s3 URI")
        if is_num(row.get("s_feat")) and isinstance(row.get("flagged"), bool):
            expect = row["s_feat"] >= 2.5 or (is_num(s_emb) and s_emb >= 2.5)
            require(row["flagged"] is expect, errors, f"{where}: flagged must be {expect}")
        seen.append(row.get("rank"))
    if attack_ids:
        got = [r.get("attack_id") for r in rows if isinstance(r, dict)]
        require(sorted(got) == sorted(attack_ids), errors, f"{path}: anomaly attack_ids must match attacks.json")
    if len(seen) == len(rows) and all(is_int(r) for r in seen):
        require(sorted(seen) == list(range(1, len(rows) + 1)), errors, f"{path}: ranks must be 1..n")
    return rows


def check_alert(row, path, errors, need_reason):
    if not isinstance(row, dict):
        errors.append(f"{path}: object required")
        return
    require(is_int(row.get("track_id")) and row["track_id"] >= 0, errors, f"{path}: track_id must be an int ≥ 0")
    require(is_num(row.get("t0")) and is_num(row.get("t1")) and row["t1"] > row["t0"], errors, f"{path}: need t0 < t1")
    require(row.get("type") in ALERT_TYPES, errors, f"{path}: type {row.get('type')!r} invalid")
    require(is_num(row.get("peak_d2")) and is_num(row.get("peak_score")), errors, f"{path}: peak_d2 and peak_score required")
    require(is_int(row.get("u")) and 0 <= row["u"] <= 7, errors, f"{path}: u must be an int 0..7")
    require(is_int(row.get("v")) and 0 <= row["v"] <= 7, errors, f"{path}: v must be an int 0..7")
    if need_reason:
        require(isinstance(row.get("reason"), str) and row["reason"].strip(), errors, f"{path}: reason string required")
    hist = row.get("d2_hist")
    if hist is not None:
        require(isinstance(hist, list) and all(is_num(v) for v in hist), errors, f"{path}: d2_hist must be a list of numbers")
    if "tau" in row:
        require(is_num(row.get("tau")), errors, f"{path}: tau must be a number")


def check_point(row, path, errors):
    require(isinstance(row, list) and len(row) == 9 and all(is_int(v) for v in row), errors, f"{path}: p row must be 9 ints")
    if not (isinstance(row, list) and len(row) == 9 and all(is_int(v) for v in row)):
        return
    track_id, cls, x, y, w, h, _vx, _vy, score = row
    require(track_id >= 0, errors, f"{path}: track_id ≥ 0")
    require(0 <= cls <= 5, errors, f"{path}: cls must be 0..5")
    require(0 <= x <= 1050 and 0 <= y <= 680, errors, f"{path}: x,y outside the relative decimetre frame")
    require(1 <= w <= 400 and 1 <= h <= 400, errors, f"{path}: w,h out of range")
    require(0 <= score <= 999, errors, f"{path}: score_x100 must be 0..999")


def check_flow(flow, path, errors):
    require(isinstance(flow, dict), errors, f"{path}: flow object required")
    if not isinstance(flow, dict):
        return
    require(flow.get("cols") == 8 and flow.get("rows") == 8, errors, f"{path}: flow cols and rows must be 8")
    cells = flow.get("cells")
    require(isinstance(cells, list) and len(cells) == 64, errors, f"{path}: flow.cells must have 64 entries")
    if not isinstance(cells, list):
        return
    for i, cell in enumerate(cells):
        where = f"{path} cells[{i}]"
        require(isinstance(cell, list) and len(cell) == 4, errors, f"{where}: [ux, uy, n, mean_speed] required")
        if isinstance(cell, list) and len(cell) == 4:
            ux, uy, n, speed = cell
            require(is_num(ux) and is_num(uy), errors, f"{where}: ux, uy must be numbers")
            require(is_int(n) and n >= 0, errors, f"{where}: n must be an int ≥ 0")
            require(is_num(speed) and speed >= 0, errors, f"{where}: mean_speed must be ≥ 0")


def check_map(doc, path, errors):
    require(isinstance(doc, dict), errors, f"{path}: object required")
    if not isinstance(doc, dict):
        return
    mode = doc.get("mode")
    require(mode in ("FLOW", "NONE"), errors, f"{path}: mode must be FLOW or NONE")
    frames = doc.get("frames")
    require(isinstance(frames, list), errors, f"{path}: frames list required")
    tracks = set()
    if isinstance(frames, list):
        prev = None
        for i, frame in enumerate(frames):
            where = f"{path} frames[{i}]"
            if not isinstance(frame, dict):
                errors.append(f"{where}: object required")
                continue
            t = frame.get("t")
            require(is_num(t), errors, f"{where}: t required")
            if is_num(t) and prev is not None and t < prev:
                errors.append(f"{where}: frames must be sorted by t")
            if is_num(t):
                prev = t
            points = frame.get("p")
            require(isinstance(points, list), errors, f"{where}: p list required")
            if isinstance(points, list):
                for j, point in enumerate(points):
                    check_point(point, f"{where} p[{j}]", errors)
                    if isinstance(point, list) and point and is_int(point[0]):
                        tracks.add(point[0])
    alerts = doc.get("alerts")
    require(isinstance(alerts, list), errors, f"{path}: alerts list required")
    if isinstance(alerts, list):
        for i, alert in enumerate(alerts):
            check_alert(alert, f"{path} alerts[{i}]", errors, need_reason=False)
    if mode == "FLOW":
        check_flow(doc.get("flow"), f"{path} flow", errors)
    return tracks


def check_index(doc, path, errors):
    require(isinstance(doc, dict) and isinstance(doc.get("matches"), list), errors, f"{path}: matches list required")
    if not isinstance(doc, dict) or not isinstance(doc.get("matches"), list):
        return
    for i, match in enumerate(doc["matches"]):
        where = f"{path} matches[{i}]"
        if not isinstance(match, dict):
            errors.append(f"{where}: object required")
            continue
        require(isinstance(match.get("match_id"), str) and match["match_id"], errors, f"{where}: match_id required")
        require(match.get("map_mode") in ("FLOW", "NONE"), errors, f"{where}: map_mode must be FLOW or NONE")
        lanes = match.get("lanes")
        require(isinstance(lanes, dict), errors, f"{where}: lanes required")
        if isinstance(lanes, dict):
            require(lanes.get("A") == LANE_A, errors, f"{where}: lanes.A name and colour must match the contract")
            require(lanes.get("B") == LANE_B, errors, f"{where}: lanes.B name and colour must match the contract")
        parts = match.get("parts")
        require(isinstance(parts, list) and 1 <= len(parts) <= 3, errors, f"{where}: 1 to 3 parts required")
        total = 0.0
        if isinstance(parts, list):
            for j, part in enumerate(parts):
                prow = f"{where} parts[{j}]"
                if not isinstance(part, dict):
                    errors.append(f"{prow}: object required")
                    continue
                require(
                    isinstance(part.get("original_video"), str) and part["original_video"].startswith("s3://"),
                    errors,
                    f"{prow}: original_video must be an s3 URI",
                )
                segs = part.get("segments")
                require(isinstance(segs, list) and segs, errors, f"{prow}: segments required")
                if isinstance(segs, list):
                    for k, seg in enumerate(segs):
                        swhere = f"{prow} segments[{k}]"
                        if not isinstance(seg, dict):
                            errors.append(f"{swhere}: object required")
                            continue
                        require(is_int(seg.get("idx")) and seg["idx"] >= 0, errors, f"{swhere}: idx required")
                        require(is_num(seg.get("t0")) and is_num(seg.get("t1")) and seg["t1"] > seg["t0"], errors, f"{swhere}: need t0 < t1")
                        require(
                            isinstance(seg.get("source"), str) and seg["source"].startswith("s3://"),
                            errors,
                            f"{swhere}: source must be an s3 URI",
                        )
                        if is_num(seg.get("t0")) and is_num(seg.get("t1")):
                            total += seg["t1"] - seg["t0"]
        require(total <= 600, errors, f"{where}: parts exceed 600 seconds")


def check_demo(directory, segments, attacks, anomalies, errors):
    require(len(segments) == 60, errors, f"{directory}: expected 60 segments, found {len(segments)}")
    require(len(attacks) == 12, errors, f"{directory}: expected 12 episodes, found {len(attacks)}")
    for i, seg in enumerate(segments):
        if not isinstance(seg, dict):
            continue
        require(seg.get("source") == PENDING, errors, f"{directory}: segments[{i}].source must be {PENDING}")
        require(seg.get("original_video") == PENDING, errors, f"{directory}: segments[{i}].original_video must be {PENDING}")
        require(seg.get("match_id") == "i24_cam-1", errors, f"{directory}: segments[{i}].match_id must be i24_cam-1")
        if is_num(seg.get("t0")) and is_num(seg.get("t1")):
            require(seg["t0"] == i * 8 and seg["t1"] == seg["t0"] + 8, errors, f"{directory}: segments[{i}] must be 8 s apart")
    flows = {seg.get("flow") for seg in segments if isinstance(seg, dict)}
    require(len(flows & set("FMDSU")) >= 4, errors, f"{directory}: segments need mixed flow states")
    if isinstance(anomalies, list) and len(anomalies) >= 2:
        ordered = sorted(
            [r for r in anomalies if isinstance(r, dict) and is_int(r.get("rank"))],
            key=lambda r: r["rank"],
        )
        top = ordered[:2]
        require(len(top) == 2 and [r["rank"] for r in top] == [1, 2], errors, f"{directory}: rank 1 and 2 missing")
        for row in top:
            require(is_num(row.get("s_feat")) and row["s_feat"] >= 2.5 and row.get("flagged") is True, errors, f"{directory}: rank {row.get('rank')} must be a flagged outlier")
        if len(ordered) > 2:
            rest = [r for r in ordered if r["rank"] > 2]
            require(
                all(not (is_num(r.get("s_feat")) and r["s_feat"] >= ordered[1]["s_feat"]) for r in rest),
                errors,
                f"{directory}: a lower rank outscores rank 2",
            )


def check_demo_map(directory, mp, alerts_doc, sim, tracks, errors):
    require(isinstance(mp, dict) and mp.get("mode") == "FLOW", errors, f"{directory}: map mode must be FLOW")
    require(14 <= len(tracks) <= 16, errors, f"{directory}: expected about 15 vehicles, found {len(tracks)}")
    size = (directory / "map.json").stat().st_size if (directory / "map.json").exists() else 0
    require(size < MAP_LIMIT, errors, f"{directory}: map.json is {size} bytes, limit {MAP_LIMIT}")
    alerts = mp.get("alerts") if isinstance(mp, dict) else None
    require(isinstance(alerts, list) and len(alerts) == 2, errors, f"{directory}: map.alerts must contain 2 alerts")
    if isinstance(alerts, list):
        for alert in alerts:
            if not isinstance(alert, dict):
                continue
            require(_score_above(mp, alert), errors, f"{directory}: track {alert.get('track_id')} needs score_x100 above 100 during its alert")
    require(isinstance(alerts_doc, list) and isinstance(alerts, list) and len(alerts_doc) == len(alerts), errors, f"{directory}: track_alerts.json must list the map alerts")
    if isinstance(alerts_doc, list) and isinstance(alerts, list) and len(alerts_doc) == len(alerts):
        for i, (extra, base) in enumerate(zip(alerts_doc, alerts)):
            if isinstance(extra, dict) and isinstance(base, dict):
                for key in ("track_id", "t0", "t1", "type", "peak_d2", "peak_score", "u", "v"):
                    require(extra.get(key) == base.get(key), errors, f"{directory}: track_alerts[{i}].{key} must match map.alerts")
                reason = extra.get("reason")
                require(isinstance(reason, str) and "\n" not in reason and reason.strip(), errors, f"{directory}: track_alerts[{i}].reason must be one line")
    require(isinstance(sim, dict) and sim.get("simulated") is True, errors, f"{directory}: map_sim.json simulated must be true")
    if isinstance(sim, dict) and isinstance(alerts, list):
        sim_alerts = sim.get("alerts")
        require(isinstance(sim_alerts, list) and len(sim_alerts) == len(alerts) + 1, errors, f"{directory}: map_sim needs one extra alert")
        if isinstance(sim_alerts, list) and len(sim_alerts) == len(alerts) + 1:
            extra = sim_alerts[-1]
            require(isinstance(extra, dict) and extra.get("type") == "wrong_way", errors, f"{directory}: extra sim alert must be wrong_way")


def _score_above(mp, alert):
    if not isinstance(mp, dict) or not isinstance(alert, dict):
        return False
    tid = alert.get("track_id")
    t0, t1 = alert.get("t0"), alert.get("t1")
    if not is_int(tid) or not is_num(t0) or not is_num(t1):
        return False
    for frame in mp.get("frames") or []:
        if not isinstance(frame, dict) or not is_num(frame.get("t")):
            continue
        if not (t0 <= frame["t"] <= t1):
            continue
        for point in frame.get("p") or []:
            if isinstance(point, list) and len(point) == 9 and point[0] == tid and is_int(point[8]) and point[8] > 100:
                return True
    return False


def validate_bundle(directory, errors, demo):
    segments_doc = load_json(directory / "segments.json", errors)
    attacks_doc = load_json(directory / "attacks.json", errors)
    anomalies_doc = load_json(directory / "anomalies.json", errors)
    map_doc = load_json(directory / "map.json", errors)
    for doc, name in (
        (segments_doc, "segments.json"),
        (attacks_doc, "attacks.json"),
        (anomalies_doc, "anomalies.json"),
        (map_doc, "map.json"),
    ):
        if doc is not None:
            walk_keys(doc, f"{directory.name}/{name}", errors)
    segments = check_segments(segments_doc, f"{directory.name}/segments.json", errors) if segments_doc is not None else []
    attacks = check_attacks(attacks_doc, f"{directory.name}/attacks.json", errors) if attacks_doc is not None else []
    anomalies = check_anomalies(anomalies_doc, f"{directory.name}/anomalies.json", errors, attacks) if anomalies_doc is not None else []
    tracks = check_map(map_doc, f"{directory.name}/map.json", errors) if map_doc is not None else set()

    alerts_path = directory / "track_alerts.json"
    sim_path = directory / "map_sim.json"
    alerts_doc = None
    sim_doc = None
    if alerts_path.exists():
        alerts_doc = load_json(alerts_path, errors)
        if alerts_doc is not None:
            walk_keys(alerts_doc, f"{directory.name}/track_alerts.json", errors)
            require(isinstance(alerts_doc, list), errors, f"{directory.name}/track_alerts.json: array required")
            if isinstance(alerts_doc, list):
                for i, row in enumerate(alerts_doc):
                    check_alert(row, f"{directory.name}/track_alerts.json[{i}]", errors, need_reason=True)
    if sim_path.exists():
        sim_doc = load_json(sim_path, errors)
        if sim_doc is not None:
            walk_keys(sim_doc, f"{directory.name}/map_sim.json", errors)
            require(isinstance(sim_doc, dict) and sim_doc.get("simulated") is True, errors, f"{directory.name}/map_sim.json: simulated true required")
            check_map(sim_doc, f"{directory.name}/map_sim.json", errors)
    if demo:
        check_demo(directory, segments, attacks, anomalies, errors)
        check_demo_map(directory, map_doc, alerts_doc, sim_doc, tracks or set(), errors)
        for name in ("track_alerts.json", "map_sim.json"):
            require((directory / name).exists(), errors, f"{directory.name}: missing {name}")


def main():
    errors = []
    demo = DATA / "demo"
    if not demo.is_dir():
        errors.append("data/demo missing")
    else:
        validate_bundle(demo, errors, demo=True)
    if DATA.is_dir():
        for child in sorted(DATA.iterdir()):
            if child.is_dir() and child.name != "demo" and (child / "segments.json").exists():
                validate_bundle(child, errors, demo=False)
    index = DATA / "index.json"
    skipped = not index.exists()
    if index.exists():
        doc = load_json(index, errors)
        if doc is not None:
            walk_keys(doc, "index.json", errors)
            check_index(doc, "index.json", errors)
    if errors:
        # Drop a blank message if a guard appended one.
        errors = [e for e in errors if e]
        print("FAIL")
        for err in errors:
            print(f"- {err}")
        return 1
    if skipped:
        print("ok demo; skip data/index.json (missing)")
    else:
        print("ok demo; ok data/index.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
