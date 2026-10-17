#!/usr/bin/env python3
"""Traffic episodes: runs of the same FLOW state. PIVOT_TRAFFIC §3.2."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RISK = {
    "collision", "near_miss", "hard_braking", "sudden_stop", "wrong_way",
    "reversing", "pedestrian_in_road", "emergency_vehicle",
}


def _risk(events: list[str]) -> str | None:
    hits = [e for e in events if e in RISK]
    return hits[0] if hits else None


def _finalize(open_ep: dict, ended_by: str) -> dict:
    segs = open_ep["segs"]
    events: list[str] = []
    for seg in segs:
        events.extend(seg.get("events") or [])
    return {
        "attack_id": open_ep["attack_id"],
        "match_id": open_ep["match_id"],
        "team": "A",
        "flow": open_ep["flow"],
        "t0": segs[0]["t0"],
        "t1": segs[-1]["t1"],
        "seg_ids": [s["seg_id"] for s in segs],
        "n_seg": len(segs),
        "duration_s": round(segs[-1]["t1"] - segs[0]["t0"], 3),
        "zones": [s.get("scene") or "U" for s in segs],
        "events": events,
        "max_zone": segs[-1].get("scene") or "U",
        "ended_by": ended_by,
    }


def group_attacks(segments: list[dict], match_id: str = "i24") -> list[dict]:
    ordered = sorted(segments, key=lambda s: (s.get("part_id") or "", s.get("t0") or 0))
    episodes: list[dict] = []
    open_ep = None
    unclear = 0
    seq = 0

    def close(ended_by: str) -> None:
        nonlocal open_ep, unclear
        if open_ep:
            episodes.append(_finalize(open_ep, ended_by))
        open_ep = None
        unclear = 0

    def start(seg: dict) -> dict:
        nonlocal seq
        seq += 1
        return {
            "attack_id": f"{match_id}_e{seq:03d}",
            "match_id": match_id,
            "flow": seg["flow"],
            "segs": [seg],
        }

    for seg in ordered:
        flow = seg.get("flow") or "U"
        risk = _risk(seg.get("events") or [])
        if open_ep and seg.get("part_id") and open_ep["segs"][-1].get("part_id") not in (None, seg.get("part_id")):
            close("end")
        if open_ep is None:
            if flow in {"F", "M", "D", "S"}:
                open_ep = start(seg)
                unclear = 0
                if risk:
                    close("risk_event")
            continue
        if flow == open_ep["flow"]:
            open_ep["segs"].append(seg)
            unclear = 0
            if risk:
                close("risk_event")
            continue
        if flow == "U" and unclear < 1:
            open_ep["segs"].append(seg)
            unclear += 1
            if risk:
                close("risk_event")
            continue
        close("flow_change")
        if flow in {"F", "M", "D", "S"}:
            open_ep = start(seg)
            if risk:
                close("risk_event")
    close("end")
    return episodes


def summarize(episodes: list[dict]) -> str:
    if not episodes:
        return "episodes 0"
    durs = [e["duration_s"] for e in episodes]
    return (
        f"episodes {len(episodes)} mean {statistics.mean(durs):.2f}s "
        f"median {statistics.median(durs):.2f}s "
        f"flow {dict(Counter(e['flow'] for e in episodes))} "
        f"ended_by {dict(Counter(e['ended_by'] for e in episodes))}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--match", required=True)
    args = parser.parse_args()
    src = ROOT / "data" / args.match / "segments.json"
    doc = json.loads(src.read_text())
    episodes = group_attacks(doc["segments"], args.match)
    dest = ROOT / "data" / args.match / "attacks.json"
    dest.write_text(json.dumps({"match_id": args.match, "attacks": episodes}, indent=2) + "\n")
    print(summarize(episodes))
    print(f"wrote {dest}")


if __name__ == "__main__":
    main()
