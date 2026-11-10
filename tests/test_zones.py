"""Tests for LODES zones, connectors and internal demand.

Offline: a made-up LODES extract on the synthetic grid (synthetic.py), never Charleston.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from chstraffic import config, demand, lodes, synthetic  # noqa: E402
from chstraffic.graph import build_digraph  # noqa: E402

TRACT = "45019999900"


@pytest.fixture()
def toy_lodes(tmp_path, monkeypatch):
    """24 blocks over the toy grid, written in LODES file layout."""
    D = build_digraph(synthetic.grid_osm())
    monkeypatch.setattr(config, "PENINSULA_TRACTS", [TRACT])
    monkeypatch.setattr(config, "BBOX", (-79.96, 32.77, -79.93, 32.80))
    rng = np.random.default_rng(0)
    ids = [f"{TRACT}{i:04d}" for i in range(24)]
    lat = 32.7805 + rng.uniform(0, 0.008, 24)
    lon = -79.9495 + rng.uniform(0, 0.008, 24)
    jobs, workers = rng.integers(0, 300, 24), rng.integers(0, 80, 24)
    pd.DataFrame(dict(tabblk2020=ids, trct=TRACT, blklatdd=lat, blklondd=lon)).to_csv(tmp_path / "sc_xwalk.csv.gz", index=False)
    pd.DataFrame(dict(w_geocode=ids, C000=jobs)).to_csv(tmp_path / "sc_wac_S000_JT00_2024.csv.gz", index=False)
    pd.DataFrame(dict(h_geocode=ids, C000=workers)).to_csv(tmp_path / "sc_rac_S000_JT00_2024.csv.gz", index=False)
    outside = "450190000001000"
    rows = [(ids[w], ids[h], 3) for w in range(0, 24, 2) for h in range(1, 24, 5) if jobs[w] >= 15 and workers[h] >= 40]
    rows += [(ids[w], outside, 5) for w in range(24) if jobs[w] >= 50]
    pd.DataFrame(rows, columns=["w_geocode", "h_geocode", "S000"]).to_csv(tmp_path / "sc_od_main_JT00_2024.csv.gz", index=False)
    pd.DataFrame([(ids[0], "370010000001000", 2)], columns=["w_geocode", "h_geocode", "S000"]).to_csv(
        tmp_path / "sc_od_aux_JT00_2024.csv.gz", index=False)
    return D, tmp_path, jobs, workers


def test_cluster_is_deterministic_and_complete():
    rng = np.random.default_rng(1)
    xy, w = rng.uniform(0, 1000, (200, 2)), rng.uniform(1, 50, 200)
    a, b = lodes.cluster(xy, w, 12, seed=5), lodes.cluster(xy, w, 12, seed=5)
    assert np.array_equal(a, b)
    assert len(set(a)) == 12


def test_build_conserves_activity_and_connector_shares(toy_lodes):
    D, path, jobs, workers = toy_lodes
    zones, con, internal, rep = lodes.build(D, path, year=2024, k=6)
    active = (jobs + workers) > 0
    assert zones.jobs.sum() == jobs[active].sum() and zones.workers.sum() == workers[active].sum()
    assert np.allclose(con.groupby("zone").share.sum(), 1.0, atol=1e-3)
    sizes = con.groupby("zone").size()
    assert sizes.min() >= 2 and sizes.max() <= config.MAX_CONNECTORS_PER_ZONE
    assert set(con.node) <= set(lodes.eligible_nodes(D))          # never a freeway stub
    # internal + external never exceeds what the zone holds
    assert (zones.jobs_internal + zones.jobs_external <= zones.jobs + 1e-9).all()
    assert (zones.workers_internal <= zones.workers + 1e-9).all()
    assert internal.commuters.sum() == zones.jobs_internal.sum() == zones.workers_internal.sum()


def _lodes_zones(D, path, tmp_path, monkeypatch):
    zones, con, internal, _ = lodes.build(D, path, year=2024, k=6)
    ref = tmp_path / "ref"
    ref.mkdir()
    zones.to_csv(ref / "zones_lodes.csv", index=False)
    con.to_csv(ref / "zone_connectors.csv", index=False)
    internal.to_csv(ref / "internal_od.csv", index=False)
    (ref / "zones.csv").write_text(
        "zone_id,kind,name,lat,lon,snap_road,aadt,aadt_station,attraction,notes\n"
        "freeway,gateway_in,fw,32.79,-79.955,Freeway,30000,1,,\n"
        "freeway_out,gateway_out,fw,32.79,-79.956,Freeway,,,,\n"
        "south,gateway_in,s,32.78,-79.95,Avenue 0,10000,2,,\n")
    monkeypatch.setattr(config, "ZONE_SOURCE", "lodes")
    return demand.load_zones(D, ref / "zones.csv")


def test_lodes_od_keeps_gateway_totals_and_internal_total(toy_lodes, tmp_path, monkeypatch):
    D, path, _, _ = toy_lodes
    z = _lodes_zones(D, path, tmp_path, monkeypatch)
    od = demand.build_od(D, z, through_share={"south": {"freeway_out": 0.5}})
    gw_nodes = {n for n, _ in z.gateways.values()}
    exit_nodes = {n for n, _ in z.outbound.values()}
    fw_exit = z.sinks["freeway_out"]
    assert od[(z.gateways["south"][0], fw_exit)] == pytest.approx(0.5 * z.gateways["south"][1])
    # a through trip counts once at each end: inbound = AADT x K x split, outbound = AADT x K x (1 - split)
    assert sum(q for (o, _), q in od.items() if o == "fw_in") == pytest.approx(z.gateways["freeway"][1])
    assert sum(q for (_, d), q in od.items() if d == fw_exit) == pytest.approx(z.outbound["freeway"][1])
    south, south_exit = z.gateways["south"][0], z.outbound["south"][0]
    conn = {n for c in z.connectors.values() for n, _ in c}
    assert south not in conn and south_exit not in conn        # else the sums below would mix in internal trips
    assert sum(q for (o, _), q in od.items() if o == south) == pytest.approx(z.gateways["south"][1])
    assert sum(q for (_, d), q in od.items() if d == south_exit) == pytest.approx(z.outbound["south"][1])
    # what is left is internal: LODES commuters x factor, less pairs that share a node
    internal = sum(q for (o, d), q in od.items() if o not in gw_nodes and d not in exit_nodes)
    want = sum(z.internal.values()) * config.INTERNAL_VEH_PER_COMMUTER
    assert 0.8 * want <= internal <= want + 1e-6
    assert sum(demand.internal_vph(z, {"z001": 3.0}, 2.0).values()) == pytest.approx(2 * want)
    assert all(o != d for (o, d) in z.internal)                    # intrazonal dropped


def test_through_traffic_cannot_exceed_exit_volume():
    z = demand.Zones(gateways={"a": ("a_in", 1000.0), "b": ("b_in", 100.0)}, sinks={"b_out": "b_x"},
                     dests={}, snap_report=[], outbound={"b": ("b_x", 200.0)})
    flows = demand.through_flows(z, {}, {"a": {"b_out": 0.5}})        # wants 500 into an exit that carries 200
    assert flows[("a", "b_out")] == pytest.approx(config.THROUGH_MAX_SHARE_OF_EXIT * 200.0)
    z.outbound = None                                                 # inbound-only model: no cap
    assert demand.through_flows(z, {}, {"a": {"b_out": 0.5}})[("a", "b_out")] == pytest.approx(500.0)


def test_lodes_scenarios_vary_internal_volume(toy_lodes, tmp_path, monkeypatch):
    D, path, _, _ = toy_lodes
    z = _lodes_zones(D, path, tmp_path, monkeypatch)
    gw_nodes = {n for n, _ in z.gateways.values()}
    exit_nodes = {n for n, _ in z.outbound.values()}
    ods = demand.scenarios(D, z, n=6, seed=2)
    internal = np.array([sum(q for (o, d), q in od.items() if o not in gw_nodes and d not in exit_nodes) for od in ods])
    base = sum(z.internal.values()) * config.INTERNAL_VEH_PER_COMMUTER
    lo, hi = config.SCENARIO_INTERNAL_RANGE
    assert internal.std() > 0 and np.all(internal <= hi * base + 1e-9) and np.all(internal >= 0.8 * lo * base)


def test_through_shares_of_one_gateway_cannot_exceed_its_volume(monkeypatch):
    z = demand.Zones(gateways={"a": ("a_in", 1000.0)}, sinks={"b_out": "b_x", "c_out": "c_x"},
                     dests={}, snap_report=[])
    monkeypatch.setattr(config, "THROUGH_SCALE", 2.0)
    flows = demand.through_flows(z, {}, {"a": {"b_out": 0.4, "c_out": 0.4}})   # 2 x 0.8 = 160% of a
    assert sum(flows.values()) == pytest.approx(1000.0)


def test_health_weight_and_nonwork_weights_shift_zone_weights(toy_lodes, tmp_path, monkeypatch):
    D, path, _, _ = toy_lodes
    base = _lodes_zones(D, path, tmp_path, monkeypatch)
    ref = tmp_path / "ref"
    zl = pd.read_csv(ref / "zones_lodes.csv")
    zl["jobs_health"] = np.where(zl.zone == "z001", zl.jobs, 0.0)             # z001 is all hospital
    zl.to_csv(ref / "zones_lodes.csv", index=False)
    monkeypatch.setattr(config, "HEALTH_JOB_WEIGHT", 0.5)
    monkeypatch.setattr(config, "NONWORK_RESIDENT_WEIGHT", 2.0)
    z = demand.load_zones(D, ref / "zones.csv")
    row = zl.set_index("zone")
    def total(zz, zone):
        return sum(w for k, (_, w) in zz.items() if k.startswith(zone + "#"))
    for zone in ("z001", "z002"):
        hw = 0.5 if zone == "z001" else 1.0
        assert total(z.dests, zone) == pytest.approx(row.jobs_external[zone] * hw + 2.0 * row.workers[zone])
        assert total(z.origins, zone) == pytest.approx(row.workers_external[zone] + 2.0 * row.workers[zone])
        assert total(base.dests, zone) == pytest.approx(row.jobs_external[zone])


def test_cut_edges_finds_both_carriageways():
    import networkx as nx
    from chstraffic import calibrate
    G = nx.DiGraph()
    for n, (x, y) in {"a": (0.0, 0.0), "b": (1.0, 0.0), "c": (1.0, 0.1), "d": (0.0, 0.1), "e": (2.0, 0.0)}.items():
        G.add_node(n, x=x, y=y)
    G.add_edge("a", "b", name="Parkway")       # eastbound carriageway
    G.add_edge("c", "d", name="Parkway")       # westbound carriageway
    G.add_edge("b", "e", name="Parkway")       # does not cross x = 0.5
    G.add_edge("a", "c", name="Side Street")   # crosses, wrong name
    assert sorted(calibrate.cut_edges(G, "^Parkway$", "lon=0.5")) == [("a", "b"), ("c", "d")]


def test_screenline_sums_parallel_streets_and_applies_tolerance():
    from chstraffic import calibrate
    assert calibrate.max_desirable_deviation(20_000) == pytest.approx(0.45)
    assert calibrate.max_desirable_deviation(30_000) == pytest.approx(0.40)        # halfway 20k..40k
    assert calibrate.max_desirable_deviation(1_000_000) == pytest.approx(0.20)     # flat beyond the last point
    df = pd.DataFrame(dict(station=[1, 2, 3], aadt=[10_000, 10_000, 20_000], count_peak=[900, 900, 1800],
                           geh=[1.0, 1.0, 1.0]))
    # street 1 is 400 too high, street 2 is 400 too low: the screenline total is exact
    df.attrs["per_scenario"] = {1: (np.array([1300.0, 1300.0]), np.array([1000.0, 1000.0])),
                                2: (np.array([500.0, 500.0]), np.array([900.0, 900.0])),
                                3: (np.array([900.0, 900.0]), np.array([1800.0, 1800.0]))}
    lines = pd.DataFrame(dict(screenline=["X", "Y"], name=["pair", "single"], stations=["1 2", "3"]))
    sl = calibrate.screenline_table(df, lines).set_index("screenline")
    assert sl.model["X"] == 1800 and sl.deviation["X"] == 0 and bool(sl.passes["X"])
    assert sl.deviation["Y"] == -0.5 and not bool(sl.passes["Y"]) and bool(sl.passes_section["Y"])
