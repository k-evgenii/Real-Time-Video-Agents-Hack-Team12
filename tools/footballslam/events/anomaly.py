#!/usr/bin/env python3
"""Per-team robust-z kNN anomalies. Plan §6.3–§6.6."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path

from features import FEATURE_NAMES, feature_vector

ROOT = Path(__file__).resolve().parents[1]
LABELS = {
    "duration_s": "duration",
    "n_seg": "segments",
    "mean_vehicles": "mean vehicles",
    "max_vehicles": "max vehicles",
    "mean_peds": "mean pedestrians",
    "n_risk_events": "risk events",
    "n_manoeuvres": "manoeuvres",
    "share_dense_or_stopped": "share dense or stopped",
    "flow_code": "flow code",
    "ended_by_code": "ended-by code",
}
ZONE_NAME = {0: "free", 1: "moderate", 2: "dense", 3: "stopped"}


def _fmt_value(name: str, value: float) -> str:
    if name == "duration_s":
        return f"{value:.0f} s"
    if name in {"n_seg", "n_shots", "n_turnover_ev", "ended_by_code"}:
        return str(int(round(value)))
    if name == "flow_code":
        return ZONE_NAME.get(int(round(value)), str(value))
    return f"{value:.2f}"


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def _dist(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _knn_mean(rows: list[list[float]], k: int) -> list[float]:
    n = len(rows)
    if n <= 1:
        return [0.0] * n
    k = min(k, n - 1)
    out = []
    for i, row in enumerate(rows):
        dists = [_dist(row, other) for j, other in enumerate(rows) if j != i]
        dists.sort()
        out.append(sum(dists[:k]) / k)
    return out


def score_team(attacks: list[dict], vectors: list[list[float]], embs: list[list[float] | None]) -> list[dict]:
    n = len(attacks)
    k = max(3, int(round(math.sqrt(n))))
    if n < 2:
        return [{
            "attack_id": attack["attack_id"],
            "rank": 1,
            "s_feat": None,
            "s_emb": None,
            "flagged": False,
            "agree": False,
            "z": [0.0] * 10,
            "reasons": [f"not enough attacks for this team ({n} < 2)"],
            "_i": i,
        } for i, attack in enumerate(attacks)]
    med = [_median([row[j] for row in vectors]) for j in range(10)]
    mad = []
    for j in range(10):
        mad.append(1.4826 * _median([abs(row[j] - med[j]) for row in vectors]) + 1e-6)
    z = []
    for row in vectors:
        z.append([max(-5.0, min(5.0, (row[j] - med[j]) / mad[j])) for j in range(10)])
    d = _knn_mean(z, k)
    med_d = _median(d) + 1e-6
    s_feat = [value / med_d for value in d]
    use_emb = all(e is not None and len(e) == 256 for e in embs)
    s_emb = None
    if use_emb:
        norms = [math.sqrt(sum(v * v for v in e)) + 1e-9 for e in embs]
        unit = [[v / norms[i] for v in e] for i, e in enumerate(embs)]
        dcos = []
        for i, left in enumerate(unit):
            dists = []
            for j, right in enumerate(unit):
                if i == j:
                    continue
                dot = sum(a * b for a, b in zip(left, right))
                dists.append(1 - dot)
            dists.sort()
            kk = min(k, n - 1)
            dcos.append(sum(dists[:kk]) / kk)
        med_c = _median(dcos) + 1e-6
        s_emb = [value / med_c for value in dcos]
    combined = s_feat if s_emb is None else [(a + b) / 2 for a, b in zip(s_feat, s_emb)]
    order = sorted(range(n), key=lambda i: -combined[i])
    rank_of = {idx: rank for rank, idx in enumerate(order, start=1)}
    rows = []
    for i, attack in enumerate(attacks):
        top = sorted(range(10), key=lambda j: -abs(z[i][j]))[:3]
        reasons = []
        for j in top:
            name = FEATURE_NAMES[j]
            direction = "above" if z[i][j] >= 0 else "below"
            reasons.append(
                f"{LABELS[name]} {abs(z[i][j]):.1f}σ {direction} camera median "
                f"({_fmt_value(name, vectors[i][j])} vs {_fmt_value(name, med[j])})"
            )
        feat = s_feat[i]
        emb = None if s_emb is None else s_emb[i]
        rows.append({
            "attack_id": attack["attack_id"],
            "t0": attack["t0"],
            "t1": attack["t1"],
            "team": attack["team"],
            "rank": rank_of[i],
            "s_feat": round(feat, 3),
            "s_emb": None if emb is None else round(emb, 3),
            "flagged": bool(feat >= 2.5 or (emb is not None and emb >= 2.5)),
            "agree": bool(emb is not None and feat >= 2.0 and emb >= 2.0),
            "z": [round(v, 3) for v in z[i]],
            "reasons": reasons,
            "_i": i,
        })
    rows.sort(key=lambda r: r["rank"])
    return rows


def _moment(attack: dict, segments_by_id: dict[str, dict], freq: Counter) -> dict:
    best = None
    best_key = None
    for sid in attack["seg_ids"]:
        seg = segments_by_id.get(sid)
        if not seg:
            continue
        multiset = tuple(sorted(seg.get("events") or ["none"]))
        rarity = 1 - freq[multiset] / max(sum(freq.values()), 1)
        note = (seg.get("note") or "").strip()
        key = (rarity, 1 if note else 0, seg["t0"])
        if best_key is None or key > best_key:
            best_key = key
            why = ", ".join(multiset)
            if note:
                why = f"{why}; {note}"
            best = {"seg_id": sid, "t": seg["t0"], "why": why}
    return best or {"seg_id": attack["seg_ids"][0], "t": attack["t0"], "why": "only segment"}


def build(match_id: str, attacks: list[dict], segments: list[dict], emb_by_seg: dict | None = None) -> dict:
    by_id = {s["seg_id"]: s for s in segments}
    freq = Counter(tuple(sorted(s.get("events") or ["none"])) for s in segments)
    per_team: dict[str, list] = {"A": [], "B": []}
    for team in ("A", "B"):
        rows = [a for a in attacks if a["team"] == team]
        if not rows:
            continue
        vectors = [feature_vector(a, by_id) for a in rows]
        embs = []
        for attack in rows:
            parts = []
            if emb_by_seg:
                for sid in attack["seg_ids"]:
                    vec = emb_by_seg.get(by_id.get(sid, {}).get("source"))
                    if vec is not None:
                        parts.append(vec)
            if parts:
                width = len(parts[0])
                embs.append([sum(part[j] for part in parts) / len(parts) for j in range(width)])
            else:
                embs.append(None)
        scored = score_team(rows, vectors, embs)
        for row in scored[:5]:
            attack = rows[row.pop("_i")]
            row["t0"] = attack["t0"]
            row["t1"] = attack["t1"]
            row["team"] = attack["team"]
            row["moment"] = _moment(attack, by_id, freq)
            per_team[team].append(row)
    return {"match_id": match_id, "k": 5, "feature_names": FEATURE_NAMES, "per_team": per_team}


def write_report(doc: dict, dest: Path) -> None:
    lines = ["# Anomaly report", "", "How to read this: episodes are compared only with other episodes from the same camera. A score near 1 is typical. A score at or above 2.5 is flagged. Lane A is the episode layer. Lane B is left for trajectory alerts.", ""]
    for team, rows in doc["per_team"].items():
        lines.append(f"## Lane {team}")
        lines.append("")
        lines.append("| attack | t0–t1 | s_feat | s_emb | reasons |")
        lines.append("| --- | --- | --- | --- | --- |")
        if not rows:
            lines.append("| — | — | — | — | no attacks |")
        for row in rows:
            reasons = "; ".join(row["reasons"])
            lines.append(
                f"| {row['attack_id']} | {row['t0']}–{row['t1']} | {row['s_feat']} | {row['s_emb']} | {reasons} |"
            )
        lines.append("")
    dest.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--match", required=True)
    args = parser.parse_args()
    base = ROOT / "data" / args.match
    attacks = json.loads((base / "attacks.json").read_text())["attacks"]
    segments = json.loads((base / "segments.json").read_text())["segments"]
    emb_by_seg = None
    rows_path = ROOT / "data" / "raw" / f"rows_{args.match}.json"
    if rows_path.exists():
        emb_by_seg = {}
        for row in json.loads(rows_path.read_text()):
            vec = row.get("vectors_visual")
            if vec and len(vec) == 256:
                emb_by_seg[row["source"]] = [float(v) for v in vec]
    used = emb_by_seg is not None
    doc = build(args.match, attacks, segments, emb_by_seg=emb_by_seg)
    (base / "anomalies.json").write_text(json.dumps(doc, indent=2) + "\n")
    write_report(doc, base / "anomaly_report.md")
    print(f"wrote anomalies embeddings={'loaded' if used else 'missing'} attacks={len(attacks)}")
    for team, rows in doc["per_team"].items():
        print(f"team {team} top {len(rows)} flagged {sum(1 for r in rows if r['flagged'])}")
        for row in rows:
            print(" ", row["attack_id"], row["s_feat"], row["reasons"][0] if row["reasons"] else "")


if __name__ == "__main__":
    main()
