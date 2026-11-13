"""SUMO check of the static model's finalists (finish plan Task 4).

    py -3.11 scripts\\14_sumo_check.py all --workers 15
    py -3.11 scripts\\14_sumo_check.py nets | baseline | variants | report  [--workers N] [--seeds 5]

The static model has no signals, queues or turns. This re-runs today's network and the city variants
(Coming St, Rutledge Ave, Ashley Ave two-way, all three together; chstraffic.variants, the same layouts
as outputs/final/) in SUMO's mesoscopic simulation with signals, from the same OSM snapshot and the
project's own OD matrix (base scenario, AM and PM peak), and compares the relative change in total
travel time with the static model's.

Parts (each resumable; finished runs are rows in outputs/sumo/runs.csv):
  nets      one SUMO network per variant (outputs/sumo/nets/), built by chstraffic.sumo from
            data/raw/chs_peninsula_overpass.osm, plus the AM and PM OD matrices
  baseline  today's network for every peak and seed at demand x1.0. If any run gridlocks (teleports
            above config.SUMO_STABLE_TELEPORT_SHARE of vehicles, vehicles not inserted, or not arrived),
            the next lower config.SUMO_DEMAND_STEPS level is tried. The first level where every run is
            stable is used for the variants; if none is, the check stops as inconclusive.
  variants  every variant at that level with the same trips per seed (paired comparison), plus today's
            network re-simulated with another sim seed (SUMO's own noise floor)
  report    outputs/final/sumo/: SUMO_CHECK.md, sumo_check.csv, sumo_runs.csv, sumo_screenlines.csv
  all       the four parts in order

Rules (HANDOFF / Task 4): SUMO's signal timings are netconvert defaults, not Charleston's, so only relative
changes between variants are reported, never absolute delay. If SUMO disagrees with the static model,
SUMO wins. Verdict rule (config.SUMO_*), fixed before any run: a SUMO effect is detectable if it has the
same sign in >= 80% of seeds and |mean| > max(0.1%, 2 x SUMO noise floor); agree = SUMO detectable with
the static model's sign, or neither model detects an effect; disagree = SUMO detectable with the other
sign, or SUMO detects an effect the static model calls not detectable; inconclusive = the static model
detects an effect that SUMO cannot resolve.
"""

from __future__ import annotations

import argparse
import pickle
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from chstraffic import calibrate, config, demand, feasibility, files, robust, sumo, widths  # noqa: E402
from chstraffic.variants import city_variants  # noqa: E402

OSM = ROOT / "data" / "raw" / "chs_peninsula_overpass.osm"
WORK = ROOT / "outputs" / "sumo"
FINAL = ROOT / "outputs" / "final" / "sumo"
PEAKS = ("am", "pm")
BASE = "today"
VARIANTS = ["Coming Street", "Rutledge Avenue", "Ashley Avenue", "all three"]
NOISE = "today (other sim seed)"
NOISE_SIM_OFFSET = 1000
KEY = ["variant", "peak", "scale", "seed", "sim_seed"]


def slug(name: str) -> str:
    return name.lower().replace(" ", "_").replace("(", "").replace(")", "")


# ---------------------------------------------------------------------------
# Model setup
# ---------------------------------------------------------------------------

def load_model():
    D = files.load_graph()
    table = feasibility.segment_table(D, feasibility.load_overrides(ROOT / "data" / "reference" / "overrides.csv"),
                                      widths.load(ROOT / "data" / "processed" / "segment_widths.csv"))
    base_cfg = feasibility.baseline_config(table)
    variants, _ = city_variants(table, base_cfg)
    cfgs = {BASE: base_cfg, **{k: variants[k][0] for k in VARIANTS}}
    return D, table, cfgs


def part_nets(force: bool = False) -> None:
    if not OSM.exists():
        sys.exit(f"missing {OSM}: run `14_sumo_check.py export-osm` once (needs the osmnx cache in cache/)")
    D, table, cfgs = load_model()
    (WORK / "nets").mkdir(parents=True, exist_ok=True)
    osm = sumo.load_osm(OSM)
    paths, missing = sumo.segment_paths(D, table, osm)
    print(f"OSM snapshot {osm.timestamp}: {len(table)} segments, {len(missing)} without an OSM node chain")
    sumo.add_sumo_tools_to_path()
    rows = []
    for name, cfg in cfgs.items():
        s = slug(name)
        net_path, map_path = WORK / "nets" / f"{s}.net.xml", WORK / "nets" / f"{s}.map.pkl"
        if net_path.exists() and map_path.exists() and not force:
            net = pickle.loads(map_path.read_bytes())[0]
        else:
            G = feasibility.apply_config(D, table, cfg)
            wm = sumo.write_variant_osm(WORK / "nets" / f"{s}.osm", D, G, table, paths, osm)
            sumo.netconvert(WORK / "nets" / f"{s}.osm", net_path, WORK / "nets" / f"{s}.netconvert.log")
            net = sumo.read_net(net_path, wm, D)
            map_path.write_bytes(pickle.dumps((net, wm)))
        rows.append(dict(variant=name, sumo_edges=len(net.edges), unmapped=len(net.unmapped_edges),
                         junctions=net.n_junctions, signals=net.n_tls,
                         project_edges=len(set(net.edges.values()))))
    print(pd.DataFrame(rows).to_string(index=False))
    B = feasibility.apply_config(D, table, cfgs[BASE])
    for peak in PEAKS:
        p = WORK / f"od_{peak}.pkl"
        if not p.exists() or force:
            zones = demand.load_zones(B, ROOT / "data" / "reference" / "zones.csv", peak=peak)
            od = demand.build_od(B, zones)                       # base scenario, no noise, demand x1.0
            p.write_bytes(pickle.dumps(od))
            print(f"OD {peak}: {len(od):,} pairs, {sum(od.values()):,.0f} vph")


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

def run_unit(u: dict, keep_raw: bool) -> dict:
    """One SUMO run (executed in a worker process)."""
    t0 = time.time()
    net_variant = BASE if u["variant"] == NOISE else u["variant"]
    s = slug(net_variant)
    net = pickle.loads((WORK / "nets" / f"{s}.map.pkl").read_bytes())[0]
    od = pickle.loads((WORK / f"od_{u['peak']}.pkl").read_bytes())
    tag = f"{slug(u['variant'])}_{u['peak']}_x{u['scale']}_s{u['seed']}_{u['sim_seed']}"
    run_dir = WORK / "runs" / tag
    run_dir.mkdir(parents=True, exist_ok=True)
    trips = run_dir / "trips.xml"
    info = sumo.write_trips(trips, od, net, seed=u["seed"], scale=u["scale"])
    res = sumo.run(WORK / "nets" / f"{s}.net.xml", trips, run_dir, sim_seed=u["sim_seed"], meso=True)
    D_edges = pickle.loads((WORK / "edge_list.pkl").read_bytes())
    flows = sumo.project_flows(res.pop("edge_entered"), net, D_edges)
    (WORK / "flows").mkdir(exist_ok=True)
    np.save(WORK / "flows" / f"{tag}.npy", flows)
    if not keep_raw:
        shutil.rmtree(run_dir, ignore_errors=True)
    row = {**u, **info, **res, "seconds": round(time.time() - t0, 1), "tag": tag}
    row["stable"] = is_stable(row)
    return row


def is_stable(r) -> bool:
    """No gridlock: few teleports, every vehicle inserted, none left in the network at the end.
    (Vehicles teleported past their destination never record an arrival, so `unfinished_peak`
    repeats teleports already counted and is not part of the test.)"""
    return bool(r["teleports"] <= config.SUMO_STABLE_TELEPORT_SHARE * r["loaded"]
                and r["inserted"] == r["loaded"] and r["running"] == 0)


def load_runs() -> pd.DataFrame:
    p = WORK / "runs.csv"
    if not p.exists():
        return pd.DataFrame(columns=KEY)
    df = pd.read_csv(p)
    df["stable"] = [is_stable(r) for r in df.to_dict("records")]
    return df


def execute(units: list[dict], workers: int, keep_raw: bool, budget_s: float) -> None:
    done = load_runs()
    have = {tuple(r) for r in done[KEY].astype(str).itertuples(index=False)}
    todo = [u for u in units if tuple(str(u[k]) for k in KEY) not in have]
    if not todo:
        return
    for u in todo:
        files.require(WORK / "nets" / f"{slug(BASE if u['variant'] == NOISE else u['variant'])}.map.pkl",
                      files.NETS_HINT)
    D_edges_p = WORK / "edge_list.pkl"
    if not D_edges_p.exists():
        D, table, cfgs = load_model()
        D_edges_p.write_bytes(pickle.dumps(list(feasibility.apply_config(D, table, cfgs[BASE]).edges)))
    print(f"{len(todo)} runs to do ({len(units) - len(todo)} already done), {workers or 1} worker(s)")
    t_start = time.time()
    out = WORK / "runs.csv"

    def save(row):
        cols = list(pd.read_csv(out, nrows=0).columns) if out.exists() else list(row)
        pd.DataFrame([row]).reindex(columns=cols).to_csv(out, mode="a", header=not out.exists(), index=False)
        print(f"  {row['variant']:<24} {row['peak']} x{row['scale']} seed {row['seed']} sim {row['sim_seed']}: "
              f"{row['vehicles']:,} veh, teleports {row['teleports']}, stable {row['stable']}, {row['seconds']:.0f} s",
              flush=True)

    if workers and workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futs = []
            for u in todo:
                futs.append(ex.submit(run_unit, u, keep_raw))
            for f in as_completed(futs):
                save(f.result())
                if time.time() - t_start > budget_s:
                    print("time budget reached: cancelling queued runs (rerun to resume)")
                    for g in futs:
                        g.cancel()
                    break
    else:
        for u in todo:
            if time.time() - t_start > budget_s:
                print("time budget reached (rerun to resume)")
                break
            save(run_unit(u, keep_raw))


def seeds(n: int) -> list[int]:
    return [config.SUMO_SEED_BASE + i for i in range(n)]


def level_status(n_seeds: int) -> dict:
    """Per peak: (decided demand level or None, next level to try or None). A level fails as soon as one
    baseline run at it is unstable; it passes when all n_seeds runs are stable. Levels are tried per peak,
    highest first (the AM and PM can end up at different levels)."""
    df = load_runs()
    out = {}
    for p in PEAKS:
        chosen, nxt = None, None
        for s in config.SUMO_DEMAND_STEPS:
            sub = df[(df.variant == BASE) & (df.peak == p) & (df.scale.astype(float) == s)
                     & (df.sim_seed.astype(int) == df.seed.astype(int))]
            if len(sub) and not sub.stable.all():
                continue                                  # failed: try the next lower level
            if len(sub) >= n_seeds:
                chosen = s
            else:
                nxt = s
            break
        out[p] = (chosen, nxt)
    return out


def chosen_scales(n_seeds: int) -> dict | None:
    st = level_status(n_seeds)
    return {p: c for p, (c, _) in st.items()} if all(c is not None for c, _ in st.values()) else None


def part_baseline(args) -> dict | None:
    while True:
        st = level_status(args.seeds)
        todo = {p: nxt for p, (c, nxt) in st.items() if c is None and nxt is not None}
        if not todo:
            break
        units = [dict(variant=BASE, peak=p, scale=s, seed=sd, sim_seed=sd) for p, s in todo.items()
                 for sd in seeds(args.seeds)]
        n_before = len(load_runs())
        execute(units, args.workers, args.keep_raw, args.time_budget)
        if len(load_runs()) == n_before:
            print("baseline not finished (time budget); rerun to resume")
            return None
    st = level_status(args.seeds)
    for p, (c, _) in st.items():
        print(f"baseline {p}: " + (f"stable at demand x{c}" if c is not None else "no stable level: SUMO check inconclusive"))
    return chosen_scales(args.seeds)


def part_variants(args) -> None:
    sc = chosen_scales(args.seeds)
    if sc is None:
        sys.exit("no stable baseline for both peaks: run the baseline part first")
    units = [dict(variant=v, peak=p, scale=sc[p], seed=sd, sim_seed=sd) for p in PEAKS for sd in seeds(args.seeds)
             for v in VARIANTS]
    units += [dict(variant=NOISE, peak=p, scale=sc[p], seed=sd, sim_seed=sd + NOISE_SIM_OFFSET)
              for p in PEAKS for sd in seeds(args.seeds)]
    execute(units, args.workers, args.keep_raw, args.time_budget)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def static_base_od(scales: dict) -> dict:
    """Static model on the same base-scenario OD and demand level SUMO uses (one demand, no scenario noise)."""
    D, table, cfgs = load_model()
    ods = {p: {k: q * scales[p] for k, q in pickle.loads((WORK / f"od_{p}.pkl").read_bytes()).items()} for p in PEAKS}
    out, flows = {}, {}
    for name, cfg in cfgs.items():
        G = feasibility.apply_config(D, table, cfg)
        ev = {p: robust.evaluate(G, [ods[p]], gap=config.UE_GAP_SEARCH) for p in PEAKS}
        out[name] = {p: float(ev[p].tstt_h[0]) for p in PEAKS}
        if name == BASE:
            from chstraffic.fast_assignment import user_equilibrium
            flows = {p: user_equilibrium(G, ods[p], tol=config.UE_GAP_SEARCH).flow for p in PEAKS}
    return out, flows


class _EdgeList:
    def __init__(self, edges):
        self.edges = edges


def part_report(args) -> None:
    sc = chosen_scales(args.seeds)
    df = load_runs()
    FINAL.mkdir(parents=True, exist_ok=True)
    keep = ["variant", "peak", "scale", "seed", "sim_seed", "vehicles", "loaded", "inserted", "unfinished_peak",
            "teleports", "teleports_jam", "teleports_yield", "teleports_wronglane", "stable", "seconds"]
    df.sort_values(KEY)[keep].to_csv(FINAL / "sumo_runs.csv", index=False)
    if sc is None:
        print("no stable baseline: only sumo_runs.csv written")
        return
    df = df[[float(r.scale) == sc[r.peak] for r in df.itertuples()]].copy()
    tstt = df.pivot_table(index=["variant", "seed"], columns="peak", values="tstt_h", aggfunc="first")
    tstt["am+pm"] = tstt["am"] + tstt["pm"]
    base = tstt.loc[BASE]
    noise_rel = (tstt.loc[NOISE] / base - 1).abs()
    floor = {k: float(noise_rel[k].median()) for k in ["am", "pm", "am+pm"]}
    thr = {k: max(config.MIN_MEAN_IMPROVEMENT, 2 * f) for k, f in floor.items()}

    fq = pd.read_csv(ROOT / "outputs" / "final" / "city_question.csv")
    fq = fq[(fq.demand == 1.0) & (fq.bonus == config.ONEWAY_CAPACITY_BONUS)]
    st_base, st_flows = static_base_od(sc)

    rows = []
    for v in VARIANTS + [NOISE]:
        rel = tstt.loc[v] / base - 1
        for peak in ["am", "pm", "am+pm"]:
            r = rel[peak].dropna()
            same = max((r < 0).mean(), (r > 0).mean())
            sumo_det = bool(same >= config.SUMO_MIN_SIGN_SHARE and abs(r.mean()) > thr[peak])
            row = dict(variant=v, peak=peak, seeds=len(r), sumo_mean=r.mean(), sumo_min=r.min(), sumo_max=r.max(),
                       sumo_better_share=(r < 0).mean(), sumo_detectable=sumo_det)
            if v != NOISE:
                stv = st_base[v]
                sb = (stv["am"] + stv["pm"]) / (st_base[BASE]["am"] + st_base[BASE]["pm"]) - 1 if peak == "am+pm" \
                    else stv[peak] / st_base[BASE][peak] - 1
                f = fq[(fq.config == v) & (fq.peak == peak)]
                if len(f):
                    f = f.iloc[0]
                    st_det = f.verdict.startswith("detectable")
                    row.update(static_mean=f["mean"], static_p10=f.p10, static_p90=f.p90,
                               static_better_share=f.improved_share, static_verdict=f.verdict)
                    if peak == "am+pm":
                        if sumo_det and (np.sign(r.mean()) == np.sign(f["mean"])) and st_det:
                            verdict = "agree"
                        elif sumo_det and st_det:
                            verdict = "disagree (opposite sign)"
                        elif sumo_det:
                            verdict = "disagree (SUMO finds an effect, static does not)"
                        elif st_det:
                            verdict = "inconclusive (SUMO cannot resolve it)"
                        else:
                            verdict = "agree (neither detects an effect)"
                        row["verdict"] = verdict
                row["static_base_od"] = sb
            rows.append(row)
    res = pd.DataFrame(rows)
    res.to_csv(FINAL / "sumo_check.csv", index=False)

    # screenlines: SUMO baseline (per seed) vs static (base OD) vs SCDOT counts
    D, table, cfgs = load_model()
    B = feasibility.apply_config(D, table, cfgs[BASE])
    edges = list(B.edges)
    st_stations, counts = calibrate.load_counts(ROOT)
    lines = pd.read_csv(ROOT / "data" / "reference" / "screenlines.csv", comment="#")
    sl_rows = []
    for peak in PEAKS:
        sub = df[(df.variant == BASE) & (df.peak == peak)]
        F = np.array([np.load(WORK / "flows" / f"{t}.npy") for t in sub.tag])
        F, left = sumo.fill_uncovered(F, edges, B)
        print(f"{peak}: {int(np.isnan(np.load(WORK / 'flows' / f'{sub.tag.iloc[0]}.npy')).sum())} project edges "
              f"without a SUMO edge, {left} still empty after filling from same-street neighbours")
        F = np.nan_to_num(F, nan=0.0)
        sumo_tab = calibrate.screenline_table(calibrate.fit_table(B, _EdgeList(edges), F, st_stations, counts, peak=peak), lines)
        sf = st_flows[peak][None, :]
        stat_tab = calibrate.screenline_table(calibrate.fit_table(B, _EdgeList(edges), sf, st_stations, counts, peak=peak), lines)
        for a, b in zip(sumo_tab.itertuples(), stat_tab.itertuples()):
            sl_rows.append(dict(peak=peak, screenline=a.screenline, name=a.name, streets=a.streets, count_peak=a.count_peak,
                                tolerance=a.tolerance, sumo_median=a.model, sumo_min=a.p10, sumo_max=a.p90,
                                sumo_dev=a.deviation, sumo_passes=a.passes, static_base_od=b.model,
                                static_dev=b.deviation, static_passes=b.passes,
                                sumo_over_static=round(a.model / b.model, 2) if b.model else np.nan))
    sl = pd.DataFrame(sl_rows)
    sl.to_csv(FINAL / "sumo_screenlines.csv", index=False)
    # p10/p90 in screenline_table are percentiles over seeds; with 5 seeds they are close to min/max
    write_markdown(res, sl, df, sc, floor, thr)
    print((FINAL / "SUMO_CHECK.md").read_text())


def pct(x):
    return "" if pd.isna(x) else f"{x * 100:+.3f}%"


def write_markdown(res, sl, df, sc, floor, thr):
    L = ["# SUMO check of the static model (Task 4)", "",
         f"SUMO {sumo_version()} mesoscopic, signals from OSM with netconvert's default timings (not Charleston's), "
         f"routes by the rerouting device. Base-scenario OD, demand AM x{sc['am']}, PM x{sc['pm']} (highest level "
         f"without gridlock per peak), {df.seed.nunique()} seeds "
         f"(each seed = its own Poisson trip draw, the same trips for every variant). "
         f"Measured: total travel time of trips due in the peak hour after a {config.SUMO_WARMUP_S // 60}-min warm-up, "
         f"AM and PM added per seed. Relative changes only.", "",
         "SUMO noise floor (today re-simulated with another sim seed, median |change|): "
         + ", ".join(f"{k} {floor[k] * 100:.3f}%" for k in floor) + ". Detectable threshold: "
         + ", ".join(f"{k} {thr[k] * 100:.3f}%" for k in thr) + ".", "",
         "## Static vs SUMO, AM+PM", "",
         "| Two-way | Static (20 scenarios, x1.0) mean (p10 to p90), better | Static, same OD and level as SUMO | SUMO mean (min to max over seeds), better | Verdict |",
         "|---|---|---|---|---|"]
    for r in res[(res.peak == "am+pm") & (res.variant != NOISE)].itertuples():
        L.append(f"| {r.variant} | {pct(r.static_mean)} ({pct(r.static_p10)} to {pct(r.static_p90)}), "
                 f"{r.static_better_share:.0%} | {pct(r.static_base_od)} | {pct(r.sumo_mean)} ({pct(r.sumo_min)} to "
                 f"{pct(r.sumo_max)}), {r.sumo_better_share:.0%} | {r.verdict} |")
    sd = float((df[df.variant == NOISE].pivot_table(index="seed", columns="peak", values="tstt_h").sum(axis=1)
                / df[df.variant == BASE].pivot_table(index="seed", columns="peak", values="tstt_h").sum(axis=1) - 1).std())
    left = df[(df.running > 0)]
    L += ["", "## How to read this", "",
          f"* The same network re-simulated with another sim seed changes AM+PM total travel time by {sd * 100:.1f}% "
          f"(standard deviation over seeds). Telling a 0.15% effect from zero at 2 sigma would take about "
          f"{(2 * sd / 0.0015) ** 2:,.0f} seeds. With {df.seed.nunique()} seeds SUMO can confirm or contradict only "
          f"effects of several percent; the static effects are 0.03 to 0.2%.",
          "* Runs that ended with vehicles still in the network (stability is tested on the baseline only): "
          + ("; ".join(f"{r.variant} {r.peak} seed {r.seed}: {r.running}" for r in left.itertuples()) or "none") + ".",
          f"* The PM runs at demand x{sc['pm']}; the screenline counts below are the x1.0 counts, so part of the PM "
          f"shortfall is the demand cut itself. The static column uses the same OD and level as SUMO.",
          "* Absolute travel times are not reported: signal timings are netconvert defaults."]
    L += ["", "## By peak", "", "| Two-way | Peak | Static mean | SUMO mean (min to max) | SUMO better |", "|---|---|---|---|---|"]
    for r in res[res.peak != "am+pm"].itertuples():
        L.append(f"| {r.variant} | {r.peak} | {pct(getattr(r, 'static_mean', np.nan))} | {pct(r.sumo_mean)} "
                 f"({pct(r.sumo_min)} to {pct(r.sumo_max)}) | {r.sumo_better_share:.0%} |")
    L += ["", "## Teleports (gridlock) per run", "", "| Variant | Peak | Teleports per seed | Stable |", "|---|---|---|---|"]
    for (v, p), g in df.sort_values("seed").groupby(["variant", "peak"]):
        L.append(f"| {v} | {p} | {', '.join(str(int(t)) for t in g.teleports)} | {int(g.stable.sum())}/{len(g)} |")
    L += ["", "## Screenlines, baseline volumes (vph, both directions, middle segment)", "",
          "| Peak | Line | Count | Tol. | SUMO median (min to max) | dev | Static base OD | dev | SUMO/static |",
          "|---|---|---|---|---|---|---|---|---|"]
    for r in sl.itertuples():
        L.append(f"| {r.peak} | {r.screenline} | {r.count_peak:,} | ±{r.tolerance:.0%} | {r.sumo_median:,} "
                 f"({r.sumo_min:,} to {r.sumo_max:,}) | {r.sumo_dev:+.0%}{'' if r.sumo_passes else ' ✗'} | "
                 f"{r.static_base_od:,} | {r.static_dev:+.0%}{'' if r.static_passes else ' ✗'} | {r.sumo_over_static} |")
    (FINAL / "SUMO_CHECK.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def sumo_version() -> str:
    import subprocess
    out = subprocess.run([sumo.binary("sumo"), "--version"], capture_output=True, text=True).stdout
    return out.splitlines()[0].replace("Eclipse SUMO sumo ", "") if out else "?"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("part", choices=["export-osm", "nets", "baseline", "variants", "report", "all"])
    ap.add_argument("--workers", type=int, default=0)
    ap.add_argument("--seeds", type=int, default=config.SUMO_SEEDS)
    ap.add_argument("--time-budget", type=float, default=float("inf"), help="seconds; stop starting new runs after this")
    ap.add_argument("--keep-raw", action="store_true", help="keep tripinfo/edgedata per run (large)")
    ap.add_argument("--force-nets", action="store_true")
    args = ap.parse_args()
    if args.part == "export-osm":
        cached = sorted((ROOT / "cache").glob("*.json"), key=lambda p: p.stat().st_size)
        if not cached:
            raise SystemExit("export-osm needs the osmnx cache (cache/, not in git) from scripts/01_fetch_osm.py.\n"
                             f"  The 2026-11-09 export is already in git: {OSM.relative_to(ROOT)}")
        src = cached[-1]
        sumo.export_overpass_json(src, OSM)
        print(f"wrote {OSM} from {src.name}")
        return
    if args.part in ("nets", "all"):
        part_nets(args.force_nets)
    if args.part in ("baseline", "all"):
        if part_baseline(args) is None and args.part == "all":
            part_report(args)
            return
    if args.part in ("variants", "all"):
        part_variants(args)
    if args.part in ("report", "all"):
        part_report(args)


if __name__ == "__main__":
    main()
