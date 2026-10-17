#!/usr/bin/env python3
"""Check the JSON files this match actually produced."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(obj, keys, label):
    missing = [key for key in keys if key not in obj]
    if missing:
        raise SystemExit(f"{label} missing {missing}")


def main() -> None:
    match = sys.argv[1] if len(sys.argv) > 1 else "m1"
    base = ROOT / "data" / match
    segments = json.loads((base / "segments.json").read_text())
    attacks = json.loads((base / "attacks.json").read_text())
    anomalies = json.loads((base / "anomalies.json").read_text())
    require(segments, ["match_id", "parse_rate", "segments"], "segments")
    require(attacks, ["match_id", "attacks"], "attacks")
    require(anomalies, ["match_id", "feature_names", "per_team"], "anomalies")
    for seg in segments["segments"]:
        require(seg, ["seg_id", "t0", "t1", "possession", "zone", "events", "parse_ok"], seg["seg_id"])
    for attack in attacks["attacks"]:
        require(attack, ["attack_id", "team", "t0", "t1", "ended_by", "seg_ids"], attack["attack_id"])
    for team, rows in anomalies["per_team"].items():
        for row in rows:
            require(row, ["attack_id", "rank", "reasons", "moment", "flagged"], f"{team} {row.get('attack_id')}")
    print(
        f"ok match={match} parse_rate={segments['parse_rate']} "
        f"attacks={len(attacks['attacks'])} "
        f"flagged={sum(1 for rows in anomalies['per_team'].values() for row in rows if row['flagged'])}"
    )


if __name__ == "__main__":
    main()
