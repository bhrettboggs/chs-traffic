"""Step D: compare modeled link flows with SCDOT interior counts (GEH statistic and screenlines).

    python scripts/04_calibrate.py [--scenarios 10] [--peak am|pm|both] [--zone-source lodes|hand] [--out PREFIX]

Count side:  AADT x K = peak-hour volume, BOTH directions (K for the interior stations of that peak,
             calibrate.count_k).
Model side:  sum of UE flow on both directions of the matched segment, in that peak hour.

GEH = sqrt(2 (M - C)^2 / (M + C)); common practice wants GEH < 5 at ~85% of
stations. Stations are split into "calibrate" and "test" halves
(data/reference/count_stations.csv): tune config on calibrate only, then report
test. Also prints the congestion level: total travel time / free-flow travel time of the same flows.
Writes outputs/<prefix>calibration_<peak>.csv and outputs/<prefix>screenlines_<peak>.csv
(no prefix, AM only, no --peak given: the old names calibration.csv and screenlines.csv).
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from chstraffic import config, demand  # noqa: E402
from chstraffic.calibrate import (baseline_graph, congestion, count_k, fit_table, load_counts,  # noqa: E402
                                  screenline_table, summary)
from chstraffic.fast_assignment import Network, user_equilibrium  # noqa: E402


def run_peak(B, net, zones_file, peak, n, st, counts):
    zones = demand.load_zones(B, zones_file, peak=peak)
    ods = demand.scenarios(B, zones, n=n)
    res = [user_equilibrium(net, od) for od in ods]
    flows = np.array([r.flow for r in res])                              # scenarios x edges
    df = fit_table(B, net, flows, st, counts, peak=peak)
    return df, res, ods


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", type=int, default=10)
    ap.add_argument("--peak", choices=["am", "pm", "both"], default=None, help="default config.PEAK")
    ap.add_argument("--zones", type=Path, default=ROOT / "data" / "reference" / "zones.csv",
                    help="zones file; the LODES tables are read from the same folder")
    ap.add_argument("--out", default=None, help="prefix for the output files in outputs/ (may include a folder)")
    ap.add_argument("--zone-source", choices=["lodes", "hand"], default=config.ZONE_SOURCE)
    args = ap.parse_args()
    legacy_names = args.peak is None and args.out is None and args.zone_source == config.ZONE_SOURCE
    peaks = ["am", "pm"] if args.peak == "both" else [args.peak or config.PEAK]
    config.ZONE_SOURCE = args.zone_source

    B = baseline_graph(ROOT)
    net = Network(B)
    st, counts = load_counts(ROOT)
    lines = pd.read_csv(ROOT / "data" / "reference" / "screenlines.csv", comment="#")
    out = ROOT / "outputs"
    pd.set_option("display.width", 200)
    for peak in peaks:
        df, res, ods = run_peak(B, net, args.zones, peak, args.scenarios, st, counts)
        sl = screenline_table(df, lines)
        prefix = (args.out or "") + ("" if args.zone_source == "lodes" else f"{args.zone_source}_")
        cal_name, sl_name = (("calibration.csv", "screenlines.csv") if legacy_names and peak == "am"
                             else (f"{prefix}calibration_{peak}.csv", f"{prefix}screenlines_{peak}.csv"))
        (out / cal_name).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out / cal_name, index=False)
        sl.to_csv(out / sl_name, index=False)
        print(f"\n===== {peak.upper()} peak (count K = {count_k(peak):.4f}) =====")
        print(df.drop(columns=["note"]).to_string(index=False))
        for part in ("calibrate", "test"):
            for drop in (False, True):
                m = summary(df, part, drop)
                print(f"{part:>9}{' (no low-conf)' if drop else '':<14}: {m['n']:>2} stations, GEH<5 {m['geh5']:.0%}, "
                      f"GEH<10 {m['geh10']:.0%}, median GEH {m['median_geh']:.1f}, model/count total "
                      f"{m['total_ratio']:.2f}, median |log2 ratio| {m['log2']:.2f}")
        print(f"unmatched: {df.geh.isna().sum()}")
        print("\nScreenlines (parallel streets summed; tolerance = FHWA maximum desirable deviation):")
        print(sl.drop(columns=["name"]).to_string(index=False))
        print(f"pass: {int(sl.passes.sum())} of {len(sl)} (middle segment), "
              f"{int(sl.passes_section.sum())} of {len(sl)} (section mean)")
        cg = congestion(net, res)
        tstt = np.array([r.total_system_time_h for r in res])
        n_od = len({k for od in ods for k in od})
        print(f"congestion (TSTT / free-flow TT): median {np.median(cg):.3f} (p10 {np.percentile(cg, 10):.3f}, "
              f"p90 {np.percentile(cg, 90):.3f}); TSTT median {np.median(tstt):,.0f} veh-h "
              f"(p10 {np.percentile(tstt, 10):,.0f}, p90 {np.percentile(tstt, 90):,.0f})")
        print(f"zone source: {args.zone_source}; {n_od} O-D pairs; median demand "
              f"{np.median([sum(od.values()) for od in ods]):,.0f} vph; max UE gap {max(r.relative_gap for r in res):.1e}")
    print("Peak factors: config.PEAK_FACTOR_SOURCE =", repr(config.PEAK_FACTOR_SOURCE),
          "| non-work:", config.NONWORK_RETAIL_FOOD_WEIGHT, config.NONWORK_RESIDENT_WEIGHT, config.NONWORK_INTERNAL_VPH)


if __name__ == "__main__":
    main()
