"""The city's question: what if Coming St, Rutledge Ave and Ashley Ave go two-way?

    python scripts/03_city_scenario.py [--scenarios 20]

Converts the one-way segments of each street to two-way where the pavement
allows it (>= 2 total lanes), alone and all three together, and reports the
change in total system travel time across demand scenarios: median and
10th-90th percentile, never a single number. Lists segments that CAN'T go
two-way because their lane count is 1 (often a missing OSM lanes tag; fix in
data/reference/overrides.csv after checking imagery).

UNCALIBRATED until HANDOFF step D. Do not quote these numbers yet.
"""

import argparse
import pickle
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from chstraffic import config, demand, feasibility, widths, robust  # noqa: E402
from chstraffic.variants import city_variants  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", type=int, default=config.N_SCENARIOS)
    ap.add_argument("--graph", type=Path, default=ROOT / "data" / "processed" / "chs_digraph.gpickle")
    ap.add_argument("--demand-scale", type=float, default=config.DEMAND_SCALE,
                    help="multiply all demand (config.SENSITIVITY_DEMAND_LEVELS); not a calibrated state")
    args = ap.parse_args()
    config.DEMAND_SCALE = args.demand_scale

    D = pickle.loads(args.graph.read_bytes())
    table = feasibility.segment_table(D, feasibility.load_overrides(ROOT / "data" / "reference" / "overrides.csv"),
                                        widths.load(ROOT / "data" / "processed" / "segment_widths.csv"))
    base_cfg = feasibility.baseline_config(table)
    B = feasibility.apply_config(D, table, base_cfg)
    zones = demand.load_zones(B, ROOT / "data" / "reference" / "zones.csv")

    print("Zone snaps (check these):")
    for r in zones.snap_report:
        print(f"  {r['zone']:<15} {r['kind']:<12} node {r['node']:<12} {r['snap_m']:>4} m  road={r['road']}")

    ods = demand.scenarios(B, zones, n=args.scenarios)
    pairs = sorted({k for od in ods for k in od}, key=str)
    print(f"\n{len(ods)} demand scenarios, {len(pairs)} O-D pairs, "
          f"{sum(ods[0].values()):,.0f} vph in scenario 0")
    base_ev = robust.evaluate(B, ods)
    print(f"baseline TSTT median {pd.Series(base_ev.tstt_h).median():,.1f} veh-h "
          f"(max gap {base_ev.max_gap:.1e}, unreachable {base_ev.unreachable.max():.0f} vph)")

    rows = []
    variants, blocked_rows = city_variants(table, base_cfg)
    for label, (cfg, n_conv) in variants.items():
        N = feasibility.apply_config(D, table, cfg)
        scr = feasibility.screen(B, N, pairs)
        if not scr.ok:
            rows.append(dict(variant=label, converted=n_conv, screen=scr.reason))
            continue
        sc = robust.score_config(base_ev, robust.evaluate(N, ods))
        rows.append(dict(variant=label, converted=n_conv, screen=f"ok ({scr.detour_ratio:.3f}x)",
                         median=f"{sc.median:+.2%}", p10=f"{sc.p10:+.2%}", p90=f"{sc.p90:+.2%}",
                         worse_in=f"{1 - sc.win_rate:.0%}"))

    res = pd.DataFrame(rows)
    blk = pd.DataFrame(blocked_rows)
    print("\nChange in total system travel time vs today (negative = faster):")
    print(res.to_string(index=False))
    if len(blk):
        print("\nOne-way segments that CAN'T go two-way on today's pavement data:")
        print(blk.groupby(["street", "reason", "lanes_source"])["length_m"].agg(["count", "sum"]).to_string())
    out = ROOT / "outputs"
    out.mkdir(exist_ok=True)
    res.to_csv(out / "city_scenario.csv", index=False)
    blk.to_csv(out / "city_scenario_blocked.csv", index=False)
    print(f"\nwrote {out / 'city_scenario.csv'} and city_scenario_blocked.csv")
    print("UNCALIBRATED: link-level calibration failed and 4 of 6 screenlines pass. Relative comparison only.")


if __name__ == "__main__":
    main()
