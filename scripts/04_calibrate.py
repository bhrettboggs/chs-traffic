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
import math
import pickle
import re
import sys
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from chstraffic import config, demand, feasibility, widths  # noqa: E402
from chstraffic.fast_assignment import Network, user_equilibrium  # noqa: E402

config_default_source = config.ZONE_SOURCE


def geh(m, c):
    return math.sqrt(2 * (m - c) ** 2 / (m + c)) if m + c > 0 else 0.0


def locate(D, road, frm, to):
    """Middle segment of `road` between its crossings with `frm` and `to`."""
    rx, fx, tx = (re.compile(p, re.I) for p in (road, frm, to))
    name = lambda d: str(d.get("name"))  # noqa: E731
    R = nx.Graph()
    R.add_edges_from((u, v) for u, v, d in D.edges(data=True) if rx.search(name(d)))
    def crossing(px):
        return {n for u, v, d in D.edges(data=True) if px.search(name(d)) and not rx.search(name(d))
                for n in (u, v) if n in R}
    A, B = crossing(fx), crossing(tx)
    if not A or not B:
        return None, f"no crossing with {frm if not A else to}"
    best = None
    for a in A:
        lengths = nx.single_source_shortest_path_length(R, a)
        for b in B:
            if b in lengths and (best is None or lengths[b] < best[0]) and a != b:
                best = (lengths[b], a, b)
    if best is None:
        return None, "crossings not connected along road"
    path = nx.shortest_path(R, best[1], best[2])
    i = (len(path) - 1) // 2
    return frozenset((path[i], path[i + 1])), f"{len(path) - 1} segments"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", type=int, default=10)
    ap.add_argument("--zones", type=Path, default=ROOT / "data" / "reference" / "zones.csv",
                    help="zones file; the LODES tables are read from the same folder")
    ap.add_argument("--out", default=None, help="output file name in outputs/ (default calibration.csv)")
    ap.add_argument("--zone-source", choices=["lodes", "hand"], default=config.ZONE_SOURCE)
    args = ap.parse_args()
    config.ZONE_SOURCE = args.zone_source

    D = pickle.loads((ROOT / "data" / "processed" / "chs_digraph.gpickle").read_bytes())
    table = feasibility.segment_table(D, feasibility.load_overrides(ROOT / "data" / "reference" / "overrides.csv"),
                                        widths.load(ROOT / "data" / "processed" / "segment_widths.csv"))
    B = feasibility.apply_config(D, table, feasibility.baseline_config(table))
    zones = demand.load_zones(B, args.zones)
    ods = demand.scenarios(B, zones, n=args.scenarios)
    net = Network(B)
    res = [user_equilibrium(net, od) for od in ods]
    flows = np.array([r.flow for r in res])                              # scenarios x edges
    max_gap = max(r.relative_gap for r in res)
    eidx = {e: k for k, e in enumerate(net.edges)}

    counts = pd.read_csv(ROOT / "data" / "raw" / "scdot_aadt_2025_peninsula.csv")
    st = pd.read_csv(ROOT / "data" / "reference" / "count_stations.csv", comment="#")
    rows = []
    for r in st.merge(counts[["station", "aadt_2025"]], on="station").itertuples():
        seg, how = locate(B, r.road, r.from_street, r.to_street)
        if seg is None:
            rows.append(dict(station=r.station, road=r.road, split=r.split, note=how))
            continue
        a, b = tuple(seg)
        ks = [eidx[e] for e in ((a, b), (b, a)) if e in eidx]
        m = flows[:, ks].sum(axis=1)
        c = r.aadt_2025 * config.K_FACTOR
        rows.append(dict(station=r.station, road=r.road.strip("^$"), split=r.split, conf=r.mapping_confidence,
                         aadt=r.aadt_2025, count_peak=round(c), model_median=round(float(np.median(m))),
                         model_p10=round(float(np.percentile(m, 10))), model_p90=round(float(np.percentile(m, 90))),
                         ratio=round(float(np.median(m)) / c, 2), geh=round(geh(float(np.median(m)), c), 1),
                         directions=len(ks), note=how))
    df = pd.DataFrame(rows)
    out = ROOT / "outputs"
    out.mkdir(exist_ok=True)
    df.to_csv(out / (args.out or ("calibration.csv" if args.zone_source == config_default_source
                                  else f"calibration_{args.zone_source}.csv")), index=False)
    pd.set_option("display.width", 200)
    print(df.drop(columns=["note"]).to_string(index=False))
    ok = df.dropna(subset=["geh"])
    for part in ("calibrate", "test"):
        p = ok[ok.split == part]
        print(f"{part:>9}: {len(p)} stations, GEH<5 at {np.mean(p.geh < 5):.0%}, GEH<10 at {np.mean(p.geh < 10):.0%}, "
              f"median GEH {p.geh.median():.1f}, sum model / sum count = {p.model_median.sum() / p.count_peak.sum():.2f}, "
              f"median |log2 ratio| {np.median(np.abs(np.log2(np.maximum(p.ratio, 0.01)))):.2f}")
    print(f"unmatched: {df.geh.isna().sum()}")
    n_od = len({k for od in ods for k in od})
    print(f"zone source: {args.zone_source}; {n_od} O-D pairs; median demand "
          f"{np.median([sum(od.values()) for od in ods]):,.0f} vph; max UE gap {max_gap:.1e}")
    print("Uncalibrated. Internal-trip volume, through shares, K and the inbound split are unsourced guesses "
          "(config); see HANDOFF 6 and 9 before tuning anything.")


if __name__ == "__main__":
    main()
