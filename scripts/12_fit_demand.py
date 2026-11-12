"""Task 2: fit the demand level (three non-work parameters) on screenline totals of the CALIBRATE half.

    python scripts/12_fit_demand.py grid [--time-budget 140]       # resumable; run until it says "grid done"
    python scripts/12_fit_demand.py heldout                        # once, after the grid: neutral vs chosen

The plan, the held-out stations and the adoption rule were written down first: docs/task2_fit_plan.md.
Grid mode reads only calibrate-half stations. Each point = base demand (no scenario noise), UE gap 1e-4,
AM and PM peaks. Loss = mean over 6 screenlines x 2 peaks of ln(model / count)^2 on the half's totals.
Writes outputs/task2/fit_grid.csv (one row per point, appended as it goes) and outputs/task2/fit_heldout.csv.
Nothing is written to config: copy the chosen values there by hand if the adoption rule passes.
"""

import argparse
import itertools
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from chstraffic import config, demand  # noqa: E402
from chstraffic.calibrate import baseline_graph, congestion, fit_table, load_counts  # noqa: E402
from chstraffic.fast_assignment import Network, user_equilibrium  # noqa: E402

GRID = {"NONWORK_RETAIL_FOOD_WEIGHT": [0.0, 0.5, 1.0, 2.0],
        "NONWORK_RESIDENT_WEIGHT": [0.0, 0.5, 1.0],
        "NONWORK_INTERNAL_VPH": [0.0, 1000.0, 2000.0, 3000.0, 4500.0, 6000.0]}
OUT = ROOT / "outputs" / "task2"


def points():
    for r, p, n in itertools.product(*GRID.values()):
        if r == 0 and p == 0 and n > 0:
            continue
        yield (r, p, n)


def evaluate(B, net, st, counts, lines, half, values):
    """Loss and per-line ratios for one parameter point, using only the stations of `half`."""
    for name, v in zip(GRID, values):
        setattr(config, name, v)
    sub = st[st.split == half]
    row, logs = {}, []
    for peak in ("am", "pm"):
        zones = demand.load_zones(B, ROOT / "data" / "reference" / "zones.csv", peak=peak)
        od = demand.build_od(B, zones)
        res = user_equilibrium(net, od, tol=1e-4)
        df = fit_table(B, net, res.flow[None, :], sub, counts, peak=peak).set_index("station")
        for ln in lines.itertuples():
            ids = [i for i in map(int, str(ln.stations).split()) if i in df.index]
            ratio = float(df.model_median[ids].sum() / df.count_peak[ids].sum())
            row[f"{peak}_{ln.screenline}"] = round(ratio, 3)
            logs.append(np.log(ratio) ** 2)
        row[f"{peak}_demand_vph"] = round(sum(od.values()))
        row[f"{peak}_congestion"] = round(float(congestion(net, [res])[0]), 4)
        row[f"{peak}_gap"] = res.relative_gap
    return float(np.mean(logs)), row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["grid", "heldout"])
    ap.add_argument("--time-budget", type=float, default=140.0, help="seconds per call (grid mode)")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    B = baseline_graph(ROOT)
    net = Network(B)
    st, counts = load_counts(ROOT)
    lines = pd.read_csv(ROOT / "data" / "reference" / "screenlines.csv", comment="#")
    grid_file = OUT / "fit_grid.csv"
    names = ["R_retail_food", "P_resident", "N_internal_vph"]
    if args.mode == "grid":
        done = pd.read_csv(grid_file) if grid_file.exists() else pd.DataFrame(columns=names)
        seen = {tuple(x) for x in done[names].to_numpy(dtype=float)}
        todo = [v for v in points() if v not in seen]
        t0 = time.time()
        for values in todo:
            if time.time() - t0 > args.time_budget:
                break
            loss, row = evaluate(B, net, st, counts, lines, "calibrate", values)
            rec = pd.DataFrame([dict(zip(names, values), loss_calibrate=round(loss, 5), **row)])
            rec.to_csv(grid_file, mode="a", header=not grid_file.exists(), index=False)
            print(dict(zip(names, values)), f"loss {loss:.4f}", flush=True)
        done = pd.read_csv(grid_file)
        left = len(list(points())) - len(done)
        print(f"{len(done)} of {len(list(points()))} points done" + ("; grid done" if left == 0 else f"; {left} left"))
        if left == 0:
            pd.set_option("display.width", 250)
            print(done.sort_values("loss_calibrate").head(10).to_string(index=False))
    else:
        grid = pd.read_csv(grid_file)
        if len(grid) < len(list(points())):
            sys.exit("grid not finished")
        best = grid.sort_values("loss_calibrate").iloc[0]
        chosen = tuple(float(best[n]) for n in names)
        rows = []
        for label, values in (("neutral", (0.0, 0.0, 0.0)), ("chosen", chosen)):
            cal = float(grid.loc[(grid[names].to_numpy(dtype=float) == values).all(axis=1), "loss_calibrate"].iloc[0])
            loss, row = evaluate(B, net, st, counts, lines, "test", values)
            rows.append(dict(point=label, **dict(zip(names, values)), loss_calibrate=cal, loss_heldout=round(loss, 5), **row))
        out = pd.DataFrame(rows)
        out.to_csv(OUT / "fit_heldout.csv", index=False)
        pd.set_option("display.width", 250)
        print(out.to_string(index=False))
        n, c = out.iloc[0], out.iloc[1]
        adopt = c.loss_calibrate < n.loss_calibrate and c.loss_heldout < n.loss_heldout
        print("ADOPT (both losses lower than neutral)" if adopt else "DO NOT ADOPT (adoption rule fails)")


if __name__ == "__main__":
    main()
