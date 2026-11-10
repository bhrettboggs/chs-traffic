"""P4 back-test: Spring St and Cannon St before and after the 2017 two-way conversion.

    python scripts/08_backtest_spring_cannon.py [--scenarios 20] [--bonus 1.10] [--demand-scale 1.0]

OSM is the "after" network. "Before" turns every two-way segment of Spring St
into one-way westbound and of Cannon St into one-way eastbound, the directions
the remaining one-way pieces at the Crosstown still have. Same pavement: a
2-lane segment is 1 + 1 lanes after and 2 lanes one way before (with the
one-way capacity bonus, --bonus).

The question is not "what did the conversion do" (the model is not calibrated)
but "does the model call a change the city made and kept a disaster". If it
does, distrust the model. Reports the change in total system travel time and
vehicle-km over demand scenarios, and the modeled volume on both streets next
to SCDOT's counts from before and after (data/reference/spring_cannon_history.csv).
Writes outputs/backtest_spring_cannon.csv.
"""

import argparse
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from chstraffic import config, demand, feasibility, widths  # noqa: E402
from chstraffic.calibrate import locate  # noqa: E402
from chstraffic.fast_assignment import Network, user_equilibrium  # noqa: E402

BEFORE = {"Spring Street": "west", "Cannon Street": "east"}
STATIONS = {"Spring Street": ("^Spring Street$", "^Meeting Street$", "Septima", 5600, 419),
            "Cannon Street": ("^Cannon Street$", "Septima", "^Coming Street$", 5700, 417)}


def solve(G, ods):
    net = Network(G)
    length = np.array([G.edges[e]["length_m"] for e in net.edges])
    res = [user_equilibrium(net, od) for od in ods]
    return dict(net=net, flow=np.array([r.flow for r in res]),
                tstt=np.array([r.total_system_time_h for r in res]),
                vkm=np.array([float(r.flow @ length) / 1000 for r in res]),
                gap=max(r.relative_gap for r in res), unreachable=max(r.unreachable_demand for r in res))


def street_flow(G, sol, key):
    road, frm, to, _, _ = STATIONS[key]
    seg, _ = locate(G, road, frm, to)
    a, b = tuple(seg)
    eidx = {e: k for k, e in enumerate(sol["net"].edges)}
    return sol["flow"][:, [eidx[e] for e in ((a, b), (b, a)) if e in eidx]].sum(axis=1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", type=int, default=config.N_SCENARIOS)
    ap.add_argument("--bonus", type=float, default=config.ONEWAY_CAPACITY_BONUS)
    ap.add_argument("--demand-scale", type=float, default=1.0,
                    help="multiply all demand (stress test: the base network is almost uncongested)")
    args = ap.parse_args()
    config.ONEWAY_CAPACITY_BONUS = args.bonus

    D = pickle.loads((ROOT / "data" / "processed" / "chs_digraph.gpickle").read_bytes())
    table = feasibility.segment_table(D, feasibility.load_overrides(ROOT / "data" / "reference" / "overrides.csv"),
                                      widths.load(ROOT / "data" / "processed" / "segment_widths.csv"))
    after_cfg = feasibility.baseline_config(table)
    before_cfg, changed = dict(after_cfg), []
    for sid, s in table.items():
        if s.name in BEFORE and s.state == "two":
            heads_east = D.nodes[s.b]["x"] > D.nodes[s.a]["x"]            # direction of a -> b
            want_east = BEFORE[s.name] == "east"
            before_cfg[sid] = "ab" if heads_east == want_east else "ba"
            changed.append((s.name, round(s.template["length_m"]), s.total_lanes))
    ch = pd.DataFrame(changed, columns=["street", "length_m", "lanes"])
    print("segments made one-way for 'before':")
    print(ch.groupby("street").agg(segments=("length_m", "size"), metres=("length_m", "sum"),
                                   min_lanes=("lanes", "min"), max_lanes=("lanes", "max")).to_string())

    A = feasibility.apply_config(D, table, after_cfg)
    Bf = feasibility.apply_config(D, table, before_cfg)
    zones = demand.load_zones(A, ROOT / "data" / "reference" / "zones.csv")
    ods = [{k: q * args.demand_scale for k, q in od.items()} for od in demand.scenarios(A, zones, n=args.scenarios)]
    pairs = sorted({k for od in ods for k in od}, key=str)
    scr = feasibility.screen(A, Bf, pairs)
    print(f"\ntier-1 screen of 'before' against today: ok={scr.ok}, mean free-flow detour {scr.detour_ratio:.4f}x")

    sa, sb = solve(A, ods), solve(Bf, ods)
    d_tstt = sa["tstt"] / sb["tstt"] - 1          # effect of the conversion: after vs before
    d_vkm = sa["vkm"] / sb["vkm"] - 1
    pct = lambda x: np.percentile(x, [10, 50, 90])  # noqa: E731
    print(f"\n{args.scenarios} scenarios, one-way capacity bonus {args.bonus:.2f}, demand x{args.demand_scale:g}, "
          f"max UE gap {max(sa['gap'], sb['gap']):.1e}, unreachable {max(sa['unreachable'], sb['unreachable']):.0f} vph")
    print(f"TSTT before: median {np.median(sb['tstt']):,.1f} veh-h; after: {np.median(sa['tstt']):,.1f} veh-h")
    p = pct(d_tstt)
    print(f"effect of going two-way on TSTT:  median {p[1]:+.2%}  (p10 {p[0]:+.2%}, p90 {p[2]:+.2%}); "
          f"worse in {np.mean(d_tstt > 0):.0%} of scenarios; solver noise is about 0.1%")
    p = pct(d_vkm)
    print(f"effect of going two-way on veh-km: median {p[1]:+.2%}  (p10 {p[0]:+.2%}, p90 {p[2]:+.2%})")
    rows = []
    for key, (_, _, _, aadt, station) in STATIONS.items():
        fb, fa = street_flow(Bf, sb, key), street_flow(A, sa, key)
        rows.append(dict(street=key, station=station, count_2025_peak=round(aadt * config.K_FACTOR),
                         model_before=round(float(np.median(fb))), model_after=round(float(np.median(fa))),
                         model_change=f"{np.median(fa) / max(np.median(fb), 1) - 1:+.0%}"))
    out = pd.DataFrame(rows)
    print("\nmodeled two-way volume at the count station (vph, median over scenarios):")
    print(out.to_string(index=False))
    hist = pd.read_csv(ROOT / "data" / "reference" / "spring_cannon_history.csv", comment="#")
    piv = hist.pivot(index="street", columns="year", values="aadt")
    piv["2016_to_2018"] = (piv[2018] / piv[2016] - 1).map("{:+.0%}".format)
    piv["2016_to_2019"] = (piv[2019] / piv[2016] - 1).map("{:+.0%}".format)
    print("\nobserved SCDOT AADT (conversion: late 2017):")
    print(piv.to_string())
    (ROOT / "outputs").mkdir(exist_ok=True)
    pd.DataFrame(dict(scenario=range(args.scenarios), tstt_before_h=sb["tstt"], tstt_after_h=sa["tstt"],
                      vkm_before=sb["vkm"], vkm_after=sa["vkm"])).to_csv(
        ROOT / "outputs" / f"backtest_spring_cannon_bonus{args.bonus:.2f}_demand{args.demand_scale:g}.csv", index=False)
    print("\nUNCALIBRATED model: a plausibility check, not an estimate of what the conversion did.")


if __name__ == "__main__":
    main()
