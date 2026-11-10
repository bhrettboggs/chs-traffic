"""Step D: compare modeled link flows with SCDOT interior counts (GEH statistic).

    python scripts/04_calibrate.py [--scenarios 10] [--zone-source lodes|hand]

Count side:  AADT x K_FACTOR = peak-hour volume, BOTH directions.
Model side:  sum of UE flow on both directions of the matched segment, AM peak.

GEH = sqrt(2 (M - C)^2 / (M + C)); common practice wants GEH < 5 at ~85% of
stations. Stations are split into "calibrate" and "test" halves
(data/reference/count_stations.csv): tune config on calibrate only, then report
test. Writes outputs/calibration.csv.
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from chstraffic import config, demand  # noqa: E402
from chstraffic.calibrate import baseline_graph, fit_table, load_counts, summary  # noqa: E402
from chstraffic.fast_assignment import Network, user_equilibrium  # noqa: E402

config_default_source = config.ZONE_SOURCE


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", type=int, default=10)
    ap.add_argument("--zones", type=Path, default=ROOT / "data" / "reference" / "zones.csv",
                    help="zones file; the LODES tables are read from the same folder")
    ap.add_argument("--out", default=None, help="output file name in outputs/ (default calibration.csv)")
    ap.add_argument("--zone-source", choices=["lodes", "hand"], default=config.ZONE_SOURCE)
    args = ap.parse_args()
    config.ZONE_SOURCE = args.zone_source

    B = baseline_graph(ROOT)
    zones = demand.load_zones(B, args.zones)
    ods = demand.scenarios(B, zones, n=args.scenarios)
    net = Network(B)
    res = [user_equilibrium(net, od) for od in ods]
    flows = np.array([r.flow for r in res])                              # scenarios x edges
    max_gap = max(r.relative_gap for r in res)
    st, counts = load_counts(ROOT)
    df = fit_table(B, net, flows, st, counts)
    out = ROOT / "outputs"
    out.mkdir(exist_ok=True)
    df.to_csv(out / (args.out or ("calibration.csv" if args.zone_source == config_default_source
                                  else f"calibration_{args.zone_source}.csv")), index=False)
    pd.set_option("display.width", 200)
    print(df.drop(columns=["note"]).to_string(index=False))
    ok = df.dropna(subset=["geh"])
    for part in ("calibrate", "test"):
        for drop in (False, True):
            m = summary(df, part, drop)
            print(f"{part:>9}{' (no low-conf)' if drop else '':<14}: {m['n']:>2} stations, GEH<5 {m['geh5']:.0%}, "
                  f"GEH<10 {m['geh10']:.0%}, median GEH {m['median_geh']:.1f}, model/count total {m['total_ratio']:.2f}, "
                  f"median |log2 ratio| {m['log2']:.2f}")
    print(f"unmatched: {df.geh.isna().sum()}")
    n_od = len({k for od in ods for k in od})
    print(f"zone source: {args.zone_source}; {n_od} O-D pairs; median demand "
          f"{np.median([sum(od.values()) for od in ods]):,.0f} vph; max UE gap {max_gap:.1e}")
    print("Uncalibrated. Internal-trip volume, through shares, K and the inbound split are unsourced guesses "
          "(config); see HANDOFF 6 and 9 before tuning anything.")


if __name__ == "__main__":
    main()
