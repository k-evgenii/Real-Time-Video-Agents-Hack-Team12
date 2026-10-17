#!/usr/bin/env python3
"""Parse Cosmos football captions into segments.json."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VOCAB = {
    "pass", "long_ball", "dribble", "cross", "shot", "goal", "save", "tackle",
    "interception", "clearance", "foul", "throw_in", "corner", "free_kick",
    "goal_kick", "offside", "injury", "celebration", "stoppage", "none",
}
KEYS = (
    "POSSESSION", "DIRECTION", "ZONE", "EVENTS", "BALL_VISIBLE",
    "PLAYERS_VISIBLE", "TEMPO", "NOTE",
)


def _grab(text: str, key: str) -> str:
    match = re.search(rf"(?im)^\s*\**{key}\**\s*[:\-]\s*(.+?)\s*$", text)
    return match.group(1).strip().strip("*") if match else ""


def _colours(prompt: str) -> dict[str, str]:
    mapping = {}
    a = re.search(r"TEAM_A wears ([A-Za-z]+)", prompt)
    b = re.search(r"TEAM_B wears ([A-Za-z]+)", prompt)
    if a:
        mapping[a.group(1).lower()] = "A"
    if b:
        mapping[b.group(1).lower()] = "B"
    return mapping


TRAFFIC_VOCAB = {
    "lane_change", "hard_braking", "sudden_stop", "stopped_vehicle", "reversing",
    "wrong_way", "u_turn", "overtaking", "tailgating", "pedestrian_crossing",
    "pedestrian_in_road", "jaywalking", "cyclist", "emergency_vehicle", "collision",
    "near_miss", "debris", "parking", "turning", "none",
}


def parse_traffic(text: str) -> dict:
    flow = {"FREE": "F", "MODERATE": "M", "DENSE": "D", "STOPPED": "S", "UNCLEAR": "U"}.get(_grab(text, "FLOW").upper(), "U")
    scene = {
        "HIGHWAY": "H", "URBAN_STREET": "S", "RESIDENTIAL": "R",
        "INTERSECTION": "I", "DASHCAM": "C", "UNCLEAR": "U",
    }.get(_grab(text, "SCENE").upper().replace(" ", "_"), "U")
    direction = {
        "LEFT": "L", "RIGHT": "R", "TOWARD": "T", "AWAY": "A", "MIXED": "X", "UNCLEAR": "U",
    }.get(_grab(text, "DIRECTION").upper(), "U")
    light = {"DAY": "D", "NIGHT": "N", "RAIN": "R", "UNCLEAR": "U"}.get(_grab(text, "LIGHT").upper(), "U")
    events = []
    for part in re.split(r"[,;/]", _grab(text, "EVENTS")):
        token = part.strip().lower().replace(" ", "_").replace("-", "_")
        if token in TRAFFIC_VOCAB:
            events.append(token)
    if not events:
        events = ["none"]
    vehicles = re.search(r"\d+", _grab(text, "VEHICLES"))
    peds = re.search(r"\d+", _grab(text, "PEDESTRIANS"))
    return {
        "flow": flow,
        "scene": scene,
        "direction": direction,
        "events": events,
        "n_vehicles": int(vehicles.group()) if vehicles else 0,
        "n_peds": int(peds.group()) if peds else 0,
        "light": light,
        "note": _grab(text, "NOTE"),
        "parse_ok": bool(_grab(text, "FLOW")) and bool(_grab(text, "SCENE")),
    }


def parse_description(text: str, colours: dict[str, str] | None = None) -> dict:
    colours = colours or {}
    raw_poss = _grab(text, "POSSESSION").upper().replace(" ", "_")
    if raw_poss in {"TEAM_A", "A"}:
        poss = "A"
    elif raw_poss in {"TEAM_B", "B"}:
        poss = "B"
    elif raw_poss in {"UNCLEAR", "U", ""}:
        low = _grab(text, "POSSESSION").lower()
        poss = colours.get(low, "U")
    else:
        poss = colours.get(raw_poss.lower(), "U")
    direction = {"LEFT": "L", "RIGHT": "R", "UNCLEAR": "U"}.get(_grab(text, "DIRECTION").upper(), "U")
    zone = {"DEFENSIVE": "D", "MIDDLE": "M", "ATTACKING": "A", "UNCLEAR": "U"}.get(_grab(text, "ZONE").upper(), "U")
    tempo = {"SLOW": "S", "NORMAL": "N", "FAST": "F"}.get(_grab(text, "TEMPO").upper(), "N")
    events = []
    for part in re.split(r"[,;/]", _grab(text, "EVENTS")):
        token = part.strip().lower().replace(" ", "_").replace("-", "_")
        if token in VOCAB:
            events.append(token)
    if not events:
        events = ["none"]
    ball_raw = _grab(text, "BALL_VISIBLE").upper()
    ball = ball_raw.startswith("Y")
    players = _grab(text, "PLAYERS_VISIBLE")
    found = re.search(r"\d+", players)
    n_players = int(found.group()) if found else 0
    note = _grab(text, "NOTE")
    present = sum(1 for key in KEYS if _grab(text, key))
    parse_ok = poss in {"A", "B", "U"} and zone in {"D", "M", "A", "U"} and present >= 2 and bool(_grab(text, "POSSESSION")) and bool(_grab(text, "ZONE"))
    return {
        "possession": poss if parse_ok or poss != "U" else "U",
        "direction": direction,
        "zone": zone if _grab(text, "ZONE") else "U",
        "events": events,
        "ball": ball,
        "n_players": n_players,
        "tempo": tempo,
        "note": note,
        "parse_ok": bool(_grab(text, "POSSESSION")) and bool(_grab(text, "ZONE")),
    }


def from_direct(match_id: str) -> dict:
    path = ROOT / "data" / match_id / "direct_reason.json"
    uploads = json.loads((ROOT / "data" / match_id / "uploads.json").read_text())
    offset = float(uploads[0].get("t_offset_s") or 0)
    prompt = (ROOT / "events" / "prompt.txt").read_text()
    colours = _colours(prompt)
    rows = json.loads(path.read_text())
    sources = {
        "seg2.mp4": "s3://team-12-vss-chunks-segments/segments/20261017_112414_45a57211_segment_002_of_003.mp4",
        "seg3.mp4": "s3://team-12-vss-chunks-segments/segments/20261017_112414_45a57211_segment_003_of_003.mp4",
    }
    segments = []
    for idx, row in enumerate(rows):
        parsed = parse_description(row["text"], colours)
        segments.append({
            "seg_id": f"m1_h1_p01_{idx:04d}",
            "part_id": "m1_h1_p01",
            "idx": idx,
            "t0": round(offset + float(row["t0"]), 3),
            "t1": round(offset + float(row["t1"]), 3),
            "source": sources.get(row["file"], row["file"]),
            **parsed,
        })
    ok = sum(1 for s in segments if s["parse_ok"])
    return {
        "match_id": match_id,
        "segment_len_s": 5.0,
        "parse_rate": round(ok / len(segments), 3) if segments else 0,
        "segments": segments,
    }


def _config_value(key: str) -> str:
    import os
    if os.environ.get(key):
        return os.environ[key]
    configs = sorted(Path("/config").glob("*.config"))
    if len(configs) != 1:
        return ""
    for line in configs[0].read_text().splitlines():
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip()
    return ""


def _label_lines(lab: dict) -> str:
    events = lab.get("events") or ["none"]
    if isinstance(events, str):
        event_text = events
    else:
        event_text = ", ".join(events) or "none"
    return "\n".join([
        f"SCENE: {lab.get('scene') or 'UNCLEAR'}",
        f"FLOW: {lab.get('flow') or 'UNCLEAR'}",
        f"VEHICLES: {lab.get('vehicles') if lab.get('vehicles') is not None else 0}",
        f"PEDESTRIANS: {lab.get('pedestrians') if lab.get('pedestrians') is not None else 0}",
        f"DIRECTION: {lab.get('direction') or 'UNCLEAR'}",
        f"EVENTS: {event_text}",
        f"LIGHT: {lab.get('light') or 'UNCLEAR'}",
        f"NOTE: {lab.get('note') or ''}",
    ])


def _wandb_batch(items: list[dict]) -> list[dict]:
    import os
    import urllib.request
    key = _config_value("WANDB_API_KEY")
    if not key:
        raise SystemExit("WANDB_API_KEY is missing from the team config")
    base = os.environ.get("WANDB_BASE_URL", "https://api.inference.wandb.ai/v1").rstrip("/")
    model = os.environ.get("WANDB_MODEL", "meta-llama/Llama-3.1-8B-Instruct")
    system = (
        "Convert each traffic description into the grammar. Use UNCLEAR when a field is not stated. "
        "Never invent events. Reply with one JSON array only, same length and order as the input. "
        "Each object has keys i, scene, flow, vehicles, pedestrians, direction, events, light, note. "
        "scene is HIGHWAY, URBAN_STREET, RESIDENTIAL, INTERSECTION, DASHCAM, or UNCLEAR. "
        "flow is FREE, MODERATE, DENSE, STOPPED, or UNCLEAR. "
        "direction is LEFT, RIGHT, TOWARD, AWAY, MIXED, or UNCLEAR. "
        "light is DAY, NIGHT, RAIN, or UNCLEAR. "
        "events is an array from lane_change, hard_braking, sudden_stop, stopped_vehicle, reversing, "
        "wrong_way, u_turn, overtaking, tailgating, pedestrian_crossing, pedestrian_in_road, jaywalking, "
        "cyclist, emergency_vehicle, collision, near_miss, debris, parking, turning, none."
    )
    user = json.dumps([
        {"i": item["i"], "description": (item["text"] or "")[:1200]}
        for item in items
    ])
    body = json.dumps({
        "model": model,
        "temperature": 0,
        "max_tokens": 2200,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }).encode()
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        data = json.loads(resp.read().decode())
    content = data["choices"][0]["message"].get("content") or ""
    start, end = content.find("["), content.rfind("]")
    labels = json.loads(content[start:end + 1])
    by_i = {}
    for lab in labels:
        if isinstance(lab, dict) and "i" in lab:
            by_i[int(lab["i"])] = lab
    if len(by_i) >= len(items):
        return [by_i[item["i"]] for item in items]
    if len(labels) >= len(items):
        return labels[:len(items)]
    raise RuntimeError(f"label count {len(labels)} for {len(items)} descriptions")


def repair_scene(match_id: str) -> dict:
    cache_path = ROOT / "data" / "raw" / "label_cache.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    rows = json.loads((ROOT / "data" / "raw" / f"rows_{match_id}.json").read_text())
    pending = []
    for idx, row in enumerate(rows):
        text = row.get("reasoning_content") or ""
        source = row["source"]
        if "\nFLOW:" in text or text.startswith("FLOW:") or "FLOW:" in text and "SCENE:" in text:
            cache[source] = {"native": True, "text": text}
            continue
        if source in cache and cache[source].get("lines"):
            continue
        pending.append({"i": idx, "source": source, "text": text})
    for start in range(0, len(pending), 10):
        batch = pending[start:start + 10]
        labels = _wandb_batch(batch)
        for item, lab in zip(batch, labels):
            cache[item["source"]] = {"native": False, "lines": _label_lines(lab)}
        cache_path.write_text(json.dumps(cache) + "\n")
        print(f"labelled {start + len(batch)}/{len(pending)}", flush=True)
    segments = []
    for row in sorted(rows, key=lambda r: (r["original_video"], int(r["segment_number"] or 0))):
        source = row["source"]
        saved = cache[source]
        parsed = parse_traffic(saved["text"] if saved.get("native") else saved["lines"])
        part = Path(row["original_video"]).stem
        segments.append({
            "seg_id": f"{match_id}_{part}_{int(row['segment_number']):04d}",
            "part_id": part,
            "idx": int(row["segment_number"]),
            "t0": float(row["segment_start_sec"] or 0),
            "t1": float(row["segment_end_sec"] or 0),
            "source": source,
            "original_video": row["original_video"],
            "camera_id": row["camera_id"],
            **parsed,
        })
    ok = sum(1 for seg in segments if seg["parse_ok"])
    return {
        "match_id": match_id,
        "segment_len_s": 5.0,
        "parse_rate": round(ok / len(segments), 3) if segments else 0,
        "segments": segments,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--match", required=True)
    parser.add_argument("--source", choices=("local", "api", "vastdb"), default="local")
    parser.add_argument("--repair", action="store_true")
    args = parser.parse_args()
    if args.repair:
        doc = repair_scene(args.match)
    else:
        if args.source != "local":
            raise SystemExit("Use --repair for traffic scenes, or --source local for the saved football clip.")
        doc = from_direct(args.match)
    dest = ROOT / "data" / args.match / "segments.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(doc, indent=2) + "\n")
    print(f"parse_rate {doc['parse_rate']} segments {len(doc['segments'])}")
    for row in doc["segments"][:8]:
        flow = row.get("flow", row.get("possession"))
        scene = row.get("scene", row.get("zone"))
        print(row["seg_id"], row["t0"], row["t1"], flow, scene, row["events"], row["parse_ok"])


if __name__ == "__main__":
    main()
