"""Tests for the configuration engine, demand, fast solver and robust search.

All offline, all on the synthetic grid (synthetic.py), never on Charleston.
"""

import random
import sys
from pathlib import Path

import networkx as nx
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from chstraffic import assignment, demand, fast_assignment, feasibility, robust, synthetic  # noqa: E402
from chstraffic.graph import build_digraph  # noqa: E402


@pytest.fixture(scope="module")
def grid():
    D = build_digraph(synthetic.grid_osm())
    return D, feasibility.segment_table(D)


def _toy_zones(D):
    gw, dests = synthetic.toy_zones()
    return demand.Zones(
        gateways={k: (n, q) for k, (n, q) in gw.items()},
        sinks={"freeway_out": "fw_out"},
        dests={k: (n, w) for k, (n, w) in dests.items()},
        snap_report=[])


def test_pavement_conserved_under_random_configs(grid):
    D, table = grid
    rng = random.Random(0)
    for _ in range(25):
        cfg = feasibility.random_config(table, rng)
        D2 = feasibility.apply_config(D, table, cfg)
        t2 = feasibility.segment_table(D2)
        for sid, s in table.items():
            assert t2[sid].total_lanes == s.total_lanes
            assert t2[sid].state == cfg[sid]


def test_frozen_and_one_lane_rules(grid):
    D, table = grid
    fw = [s for s in table.values() if s.highway == "motorway"]
    assert fw and all(s.allowed == (s.state,) for s in fw)
    one = [s for s in table.values() if s.total_lanes == 1 and not s.frozen_reason]
    assert one and all("two" not in s.allowed for s in one)
    two = [s for s in table.values() if s.total_lanes >= 2 and not s.frozen_reason]
    assert two and all(set(s.allowed) == {"two", "ab", "ba"} for s in two)
    with pytest.raises(ValueError):
        feasibility.apply_config(D, table, {one[0].sid: "two"})


def test_overrides_change_lanes_and_freeze(grid, tmp_path):
    D, table = grid
    one = next(s for s in table.values() if s.total_lanes == 1 and s.name)
    p = tmp_path / "overrides.csv"
    p.write_text("# comment line\nname,osmid,total_lanes,frozen,source,note\n"
                 f"{one.name},,2,,test,\nAvenue 0,,,yes,test,\n")
    t2 = feasibility.segment_table(D, feasibility.load_overrides(p))
    assert t2[one.sid].total_lanes == 2 and "two" in t2[one.sid].allowed
    assert t2[one.sid].lanes_source == "override"
    av0 = [s for s in t2.values() if s.name == "Avenue 0"]
    assert av0 and all(s.frozen_reason == "override" for s in av0)


def test_screen_catches_stranded_grid(grid):
    D, table = grid
    base = feasibility.apply_config(D, table, feasibility.baseline_config(table))
    pairs = [("fw_in", 4005), (0, 4005)]
    assert feasibility.screen(base, base, pairs).ok
    # point every segment touching node 4005 into it: it becomes a sink
    cfg = feasibility.baseline_config(table)
    for sid, s in table.items():
        if 4005 in sid and not s.frozen_reason:
            cfg[sid] = "ab" if s.b == 4005 else "ba"
    bad = feasibility.apply_config(D, table, cfg)
    res = feasibility.screen(base, bad, pairs)
    assert not res.ok and "strongly connected" in res.reason


def test_robbins():
    cycle = nx.cycle_graph(5, create_using=nx.DiGraph)
    assert feasibility.robbins_orientable(cycle)
    path = nx.path_graph(5, create_using=nx.DiGraph)   # every edge is a bridge
    assert not feasibility.robbins_orientable(path)


def test_gravity_conserves_origin_totals():
    origins = {"a": 1000.0, "b": 400.0}
    dests = {"x": 3.0, "y": 1.0, "z": 2.0}
    cost = {(o, d): c for (o, d), c in zip([(o, d) for o in origins for d in dests], [3, 8, 5, 6, 2, 9])}
    od = demand.gravity_od(origins, dests, cost, beta=0.1)
    for o, q in origins.items():
        assert sum(v for (oo, _), v in od.items() if oo == o) == pytest.approx(q)


def test_scenarios_vary_but_stay_near_base(grid):
    D, _ = grid
    zones = _toy_zones(D)
    ods = demand.scenarios(D, zones, n=8, seed=1)
    totals = np.array([sum(od.values()) for od in ods])
    base = sum(q for _, q in zones.gateways.values())
    assert totals.std() > 0
    assert np.all(np.abs(totals / base - 1) <= 0.2 + 1e-9)
    shares = [od.get(("fw_in", 4005), 0) / sum(od.values()) for od in ods]
    assert np.std(shares) > 0          # destination split changes too


def test_fast_matches_reference_assignment(grid):
    D, table = grid
    base = feasibility.apply_config(D, table, feasibility.baseline_config(table))
    od = demand.build_od(base, _toy_zones(base), through_share={})
    ref = assignment.user_equilibrium(base, od, max_iter=2000, tol=1e-5)
    fast = fast_assignment.user_equilibrium(base, od, tol=1e-5)
    assert fast.relative_gap < 1e-5
    assert fast.total_system_time_h == pytest.approx(ref.total_system_time_h, rel=2e-3)
    assert fast.unreachable_demand == ref.unreachable_demand == 0


def test_greedy_never_worse_than_baseline(grid):
    D, table = grid
    zones = _toy_zones(D)
    ods = demand.scenarios(D, zones, n=5, seed=3)
    cors = feasibility.corridors(D, table)
    cfg, ev, base_ev, log = robust.greedy_corridor_search(D, table, cors, ods, max_moves=1, verbose=False)
    assert ev.tstt_h.mean() <= base_ev.tstt_h.mean() + 1e-9
    for _, _, _, s in log.accepted:
        assert s.accept()


def test_coarse_corridors_are_a_subset_and_two_way_share_moves(grid):
    D, table = grid
    full = feasibility.corridors(D, table)
    coarse = feasibility.corridors(D, table, split_highways={"motorway", "trunk", "primary"},
                                   classes={"primary", "secondary"}, min_length_m=300.0)
    assert 0 < len(coarse) < len(full)
    assert [c.cid for c in coarse] == list(range(len(coarse)))
    for c in coarse:
        assert feasibility.corridor_length_m(table, c) >= 300.0
        assert all(table[sid].highway in {"primary", "secondary"} for sid in c.segments)
    base = feasibility.baseline_config(table)
    share = feasibility.two_way_share(table, base)
    one_way = next(c for c in coarse if any(table[sid].state != "two" for sid in c.segments))
    part, blocked = one_way.config_for(table, "two")
    assert not blocked and feasibility.two_way_share(table, {**base, **part}) > share
