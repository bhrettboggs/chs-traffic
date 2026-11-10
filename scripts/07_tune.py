"""Step D: tune a few demand knobs on the CALIBRATE half of the count stations.

    python scripts/07_tune.py [--grid demand|nonwork] [--tol 1e-4]

Grid search over three demand knobs at a time (about 19 calibrate stations cannot pin
more): through-traffic scale, health-job weight and internal-trip volume, or the two
non-work weights and internal-trip volume. Each combination is one
assignment of the base demand (no scenario noise). The score is the mean GEH over the
calibrate stations whose mapping confidence is not "low". The test half is printed
for the best combinations but never used to choose. Nothing is written to config:
copy the chosen values there by hand, with the date. Writes outputs/tune_grid_<grid>.csv.
"""

import argparse
import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from chstraffic import config, demand  # noqa: E402
from chstraffic.calibrate import baseline_graph, fit_table, load_counts, summary  # noqa: E402
from chstraffic.fast_assignment import Network, user_equilibrium  # noqa: E402

GRIDS = {
    "demand": {
        "THROUGH_SCALE": [0.75, 1.0, 1.25],
        "HEALTH_JOB_WEIGHT": [0.4, 0.7, 1.0],
        "INTERNAL_VEH_PER_COMMUTER": [0.25, 1.0, 2.0],
    },
    "nonwork": {
        "NONWORK_RETAIL_FOOD_WEIGHT": [0.0, 1.0, 3.0],
        "NONWORK_RESIDENT_WEIGHT": [0.0, 1.0, 3.0],
        "INTERNAL_VEH_PER_COMMUTER": [0.25, 1.0],
    },
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid", choices=list(GRIDS), default="demand")
    ap.add_argument("--tol", type=float, default=1e-4, help="UE gap; 1e-3 is too noisy to rank combinations")
    args = ap.parse_args()
    GRID = GRIDS[args.grid]
    B = baseline_graph(ROOT)
    net = Network(B)
    st, counts = load_counts(ROOT)
    rows = []
    for values in itertools.product(*GRID.values()):
        for name, v in zip(GRID, values):
            setattr(config, name, v)
        zones = demand.load_zones(B, ROOT / "data" / "reference" / "zones.csv")
        od = demand.build_od(B, zones)
        res = user_equilibrium(net, od, tol=args.tol)
        df = fit_table(B, net, res.flow[None, :], st, counts)
        ok = df[(df.split == "calibrate") & (df.conf != "low")]
        row = dict(zip(GRID, values), score=float(ok.geh.mean()), demand_vph=round(sum(od.values())))
        for part in ("calibrate", "test"):
            m = summary(df, part, drop_low=True)
            row.update({f"{part}_geh5": m["geh5"], f"{part}_geh10": m["geh10"], f"{part}_median_geh": m["median_geh"],
                        f"{part}_total": m["total_ratio"]})
        rows.append(row)
    out = pd.DataFrame(rows).sort_values("score").reset_index(drop=True)
    (ROOT / "outputs").mkdir(exist_ok=True)
    out.to_csv(ROOT / "outputs" / f"tune_grid_{args.grid}.csv", index=False)
    pd.set_option("display.width", 220)
    print(out.round(2).to_string())
    print(f"\nscore = mean GEH on {int((st.split == 'calibrate').sum())} calibrate stations minus the low-confidence ones; "
          f"spread of score over the grid: {out.score.min():.2f} to {out.score.max():.2f}")


if __name__ == "__main__":
    main()
