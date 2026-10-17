import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from attacks import group_attacks


def seg(flow, events, t0=0, t1=5, part="p"):
    return {
        "seg_id": f"{part}_{t0}",
        "part_id": part,
        "flow": flow,
        "scene": "H",
        "events": events,
        "t0": t0,
        "t1": t1,
    }


def test_flow_flip_splits_episodes():
    episodes = group_attacks([
        seg("F", ["none"], t0=0, t1=5),
        seg("F", ["none"], t0=5, t1=10),
        seg("D", ["none"], t0=10, t1=15),
    ])
    assert [(e["flow"], e["n_seg"], e["ended_by"]) for e in episodes] == [
        ("F", 2, "flow_change"),
        ("D", 1, "end"),
    ]


def test_one_unclear_gap_stays_inside():
    episodes = group_attacks([
        seg("M", ["none"], t0=0, t1=5),
        seg("U", ["none"], t0=5, t1=10),
        seg("M", ["lane_change"], t0=10, t1=15),
    ])
    assert len(episodes) == 1
    assert episodes[0]["n_seg"] == 3
    assert episodes[0]["flow"] == "M"
    assert episodes[0]["ended_by"] == "end"


def test_collision_ends_episode_and_keeps_the_segment():
    episodes = group_attacks([
        seg("M", ["none"], t0=0, t1=5),
        seg("M", ["collision"], t0=5, t1=10),
        seg("S", ["none"], t0=10, t1=15),
    ])
    assert episodes[0]["ended_by"] == "risk_event"
    assert episodes[0]["n_seg"] == 2
    assert episodes[0]["t1"] == 10
    assert episodes[1]["flow"] == "S"
