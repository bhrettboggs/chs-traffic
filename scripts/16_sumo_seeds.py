"""SUMO with enough seeds (finish plan Task 4b). Pre-registered design: docs/task4b_plan.md.

    py -3.11 scripts\\16_sumo_seeds.py level  [--workers N]     demand level check (AM)
    py -3.11 scripts\\16_sumo_seeds.py main   --workers 15      trips + runs + report (resumable)
    py -3.11 scripts\\16_sumo_seeds.py trips | runs | report     the three parts of `main`

Task 4 (14_sumo_check.py, 5 seeds) could not resolve 0.1-0.2% effects: SUMO's seed-to-seed noise was
about 3.5% of total travel time. Here: AM peak only, 40 trip seeds, each seed's trips drawn once and
shared by every variant (today, Coming St two-way, all three two-way, optionally Rutledge two-way),
the same SUMO sim seed for every variant of a seed, plus a placebo (today re-simulated with another
sim seed on the same trips) that measures the noise of an identical network.

Statistic: per seed, d = TSTT(variant) / TSTT(today) - 1. Mean, 95% bootstrap interval over seeds,
share of seeds better. Detected only if the interval excludes 0, |mean| > 0.5%, and the placebo's
interval includes 0 (otherwise the pairing isn't working and everything is inconclusive).

Shared trips. Netconvert joins two OD nodes into one junction in the Rutledge and all-three networks
(cluster_26868139_440907927) but not in the others. So each seed's trips are drawn once from the OD
without pairs that would start and end at the same junction in any variant (0.04 vph dropped), and
written per network with that network's junction names: same draws, same departure times, same order.
`trips` checks this trip by trip and records each file's SHA-256; every run re-creates its file,
checks the hash, and writes it to the runs file with its sim seed.

Everything resumable: finished runs are rows in outputs/sumo/4b/runs.csv (level check: level_runs.csv).
Per-run trip and edge summaries go to outputs/sumo/4b/details/ (gitignored); outputs/final/sumo/
gets seeds40.csv and RESULTS_4b.md. SUMO's signal timings are netconvert defaults: results are about
the street geometry with generic signals, not Charleston's real delay.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import pickle
import re
import shutil
import tempfile
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from chstraffic import config, demand, feasibility, files, robust, sumo  # noqa: E402

_spec = importlib.util.spec_from_file_location("sumo_check", ROOT / "scripts" / "14_sumo_check.py")
chk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(chk)

WORK = ROOT / "outputs" / "sumo" / "4b"
# raw SUMO output per run (tripinfo ~15 MB) goes to the system temp folder, not the repo, and is deleted after each run
RAW = Path(os.environ.get("CHS_SUMO_TMP", tempfile.gettempdir())) / "chs_traffic_4b_runs"
NETS = ROOT / "outputs" / "sumo" / "nets"
FINAL = ROOT / "outputs" / "final" / "sumo"
PLAN = ROOT / "docs" / "task4b_plan.md"
PEAK = "am"
BASE = "today"
MAIN = ["Coming Street", "all three"]
OPTIONAL = ["Rutledge Avenue"]
PLACEBO = "today (other sim seed)"
PLACEBO_OFFSET = 1000
TASK4_SEEDS = [4100, 4101, 4102, 4103, 4104]
FRESH_SEEDS = [4105, 4106, 4107]
SEED_BASE = 4200
N_SEEDS = 40
DETECT_MIN = 0.005            # |mean| above 0.5% (plan)
BOOT_N, BOOT_SEED = 10_000, 4242
MAX_GRIDLOCK_RUNS = 2         # more than this many of 40 gridlock-affected runs -> unreliable (plan)
KEY = ["kind", "variant", "scale", "seed", "sim_seed"]
NET_NAMES = [BASE, *MAIN, *OPTIONAL]


def slug(name: str) -> str:
    return chk.slug(BASE if name == PLACEBO else name)


# ---------------------------------------------------------------------------
# Shared trips
# ---------------------------------------------------------------------------

_cache: dict = {}


def nets() -> dict:
    if "nets" not in _cache:
        _cache["nets"] = {n: pickle.loads(files.require(NETS / f"{chk.slug(n)}.map.pkl", files.NETS_HINT)
                                          .read_bytes())[0] for n in NET_NAMES}
    return _cache["nets"]


def od_shared() -> dict:
    """Base AM OD without pairs whose ends share a junction in any network (they can't be the same trip
    everywhere)."""
    if "od" not in _cache:
        od = pickle.loads(files.require(ROOT / "outputs" / "sumo" / f"od_{PEAK}.pkl", files.NETS_HINT).read_bytes())
        ns = nets().values()
        _cache["od"] = {k: q for k, q in od.items()
                        if all(k[0] in n.junction_of and k[1] in n.junction_of
                               and n.junction_of[k[0]] != n.junction_of[k[1]] for n in ns)}
    return _cache["od"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


_TRIP = re.compile(r'<trip id="(\d+)" type="car" depart="([0-9.]+)" fromJunction="([^"]+)" toJunction="([^"]+)"')


def read_trips(path: Path) -> list[tuple]:
    return [(int(i), d, a, b) for i, d, a, b in _TRIP.findall(path.read_text(encoding="utf-8"))]


def write_net_trips(path: Path, name: str, seed: int, scale: float) -> dict:
    return sumo.write_trips(path, od_shared(), nets()[name], seed=seed, scale=scale)


def check_same_trips(trip_files: dict) -> dict:
    """Same trip ids, departure times and OSM endpoints in every network's file. Junction names may differ
    only where a network joined OSM nodes into another junction."""
    ns = nets()
    ref = read_trips(trip_files[BASE])
    inv_base = {j: n for n, j in ns[BASE].junction_of.items()}          # today's junctions are single nodes
    renamed = 0
    for name, p in trip_files.items():
        tr = read_trips(p)
        if len(tr) != len(ref):
            raise RuntimeError(f"{name}: {len(tr)} trips vs {len(ref)} for today")
        jmap = ns[name].junction_of
        for (i0, d0, a0, b0), (i1, d1, a1, b1) in zip(ref, tr):
            if i0 != i1 or d0 != d1:
                raise RuntimeError(f"{name}: trip {i1} differs in id or departure from today's")
            for j0, j1 in ((a0, a1), (b0, b1)):
                if j0 != j1:
                    if jmap.get(inv_base.get(j0)) != j1:
                        raise RuntimeError(f"{name}: trip {i1} junction {j1} is not today's {j0}")
                    renamed += 1
    return dict(trips=len(ref), renamed_endpoints=renamed)


def trip_dir(seed: int, scale: float) -> Path:
    return WORK / "trips" / f"x{scale}_s{seed}"


def make_trips(seed: int, scale: float, keep: bool = False) -> dict:
    """Write and check one seed's trip files; record their hashes in a manifest (rebuilt files are re-checked
    against it in every run)."""
    d = trip_dir(seed, scale)
    man = d / "manifest.json"
    if man.exists():
        return json.loads(man.read_text())
    d.mkdir(parents=True, exist_ok=True)
    trip_files, info = {}, None
    for name in NET_NAMES:
        trip_files[name] = d / f"{chk.slug(name)}.xml"
        i = write_net_trips(trip_files[name], name, seed, scale)
        if info is not None and i != info:
            raise RuntimeError(f"seed {seed}: {name} drew {i}, today {info}")
        info = i
    chkd = check_same_trips(trip_files)
    m = dict(seed=seed, scale=scale, **info, **chkd,
             sha={chk.slug(n): sha256(p) for n, p in trip_files.items()}, checked_utc=_now())
    if not keep:
        for p in trip_files.values():
            p.unlink()
    man.write_text(json.dumps(m, indent=1))
    return m


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

def run_unit(u: dict, keep_raw: bool) -> dict:
    """One SUMO run in a worker: rebuild the seed's trip file for this network, check its hash against the
    manifest, run, keep the summaries."""
    t0, started = time.time(), _now()
    s = slug(u["variant"])
    tag = f"{u['kind']}_{chk.slug(u['variant'])}_x{u['scale']}_s{u['seed']}_{u['sim_seed']}"
    run_dir = RAW / tag
    run_dir.mkdir(parents=True, exist_ok=True)
    trips = run_dir / "trips.xml"
    if u["kind"] == "repro":       # Task 4's generator, unfiltered OD, today's network
        od = pickle.loads((ROOT / "outputs" / "sumo" / f"od_{PEAK}.pkl").read_bytes())
        info = sumo.write_trips(trips, od, nets()[BASE], seed=u["seed"], scale=u["scale"])
        file_sha, trips_sha = sha256(trips), ""
    else:
        man = json.loads((trip_dir(u["seed"], u["scale"]) / "manifest.json").read_text())
        info = write_net_trips(trips, BASE if u["variant"] == PLACEBO else u["variant"], u["seed"], u["scale"])
        file_sha, trips_sha = sha256(trips), man["sha"][chk.slug(BASE)]
        if file_sha != man["sha"][s]:
            raise RuntimeError(f"{tag}: trip file hash {file_sha[:12]} != manifest {man['sha'][s][:12]}")
    res = sumo.run(NETS / f"{s}.net.xml", trips, run_dir, sim_seed=u["sim_seed"], meso=True)
    res.pop("edge_entered")
    det = sumo.run_details(run_dir)
    (WORK / "details").mkdir(parents=True, exist_ok=True)
    np.savez_compressed(WORK / "details" / f"{tag}.npz",
                        **{k: (v.astype(np.float32) if v.dtype == np.float64 else v) for k, v in det.items()})
    if not keep_raw:
        shutil.rmtree(run_dir, ignore_errors=True)
    row = {**u, "trips_sha": trips_sha, "file_sha": file_sha, **info, **res, "started_utc": started,
           "seconds": round(time.time() - t0, 1), "tag": tag, "platform": sys.platform}
    row["stable"] = chk.is_stable(row)
    return row


def load(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=KEY)
    df = pd.read_csv(path)
    df["stable"] = [chk.is_stable(r) for r in df.to_dict("records")]
    return df


def execute(units: list[dict], out: Path, workers: int, keep_raw: bool, budget_s: float) -> None:
    done = load(out)
    have = {tuple(r) for r in done[KEY].astype(str).itertuples(index=False)}
    todo = [u for u in units if tuple(str(u[k]) for k in KEY) not in have]
    if not todo:
        return
    print(f"{len(todo)} runs to do ({len(units) - len(todo)} already done), {workers or 1} worker(s)", flush=True)
    t_start = time.time()

    def save(row):
        cols = list(pd.read_csv(out, nrows=0).columns) if out.exists() else list(row)
        pd.DataFrame([row]).reindex(columns=cols).to_csv(out, mode="a", header=not out.exists(), index=False)
        n = len(load(out))
        print(f"  [{n}] {row['variant']:<24} x{row['scale']} seed {row['seed']} sim {row['sim_seed']}: "
              f"{row['vehicles']:,} veh, teleports {row['teleports']}, left {row['running'] + row['waiting']}, "
              f"stable {row['stable']}, {row['seconds']:.0f} s", flush=True)

    if workers and workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(run_unit, u, keep_raw) for u in todo]
            for f in as_completed(futs):
                save(f.result())
                if time.time() - t_start > budget_s:
                    print("time budget reached: cancelling queued runs (rerun to resume)", flush=True)
                    for g in futs:
                        g.cancel()
                    break
    else:
        for u in todo:
            if time.time() - t_start > budget_s:
                print("time budget reached (rerun to resume)")
                break
            save(run_unit(u, keep_raw))


# ---------------------------------------------------------------------------
# Level check
# ---------------------------------------------------------------------------

def task4_record(scale: float) -> pd.DataFrame:
    r = pd.read_csv(FINAL / "sumo_runs.csv")
    return r[(r.variant == BASE) & (r.peak == PEAK) & (r.scale == scale) & (r.sim_seed == r.seed)
             & r.seed.isin(TASK4_SEEDS)]


def part_level(args) -> float | None:
    out = WORK / "level_runs.csv"
    decision = WORK / "level.json"
    for scale in config.SUMO_DEMAND_STEPS:
        rec = task4_record(scale)
        units = [dict(kind="level", variant=BASE, scale=scale, seed=s, sim_seed=s) for s in FRESH_SEEDS]
        if len(rec) == len(TASK4_SEEDS):
            if not rec.stable.all():
                print(f"x{scale}: a Task 4 baseline seed was unstable -> next level")
                continue
            units.append(dict(kind="repro", variant=BASE, scale=scale, seed=TASK4_SEEDS[0], sim_seed=TASK4_SEEDS[0]))
        else:
            units += [dict(kind="level", variant=BASE, scale=scale, seed=s, sim_seed=s) for s in TASK4_SEEDS]
        for u in units:
            if u["kind"] == "level":
                make_trips(u["seed"], scale)
        execute(units, out, args.workers, args.keep_raw, args.time_budget)
        df = load(out)
        lv = df[(df.kind == "level") & (df.scale == scale)]
        need = len([u for u in units if u["kind"] == "level"])
        if not lv.stable.all():
            print(f"x{scale}: unstable fresh run(s): " + ", ".join(
                f"seed {r.seed} (left {r.running + r.waiting}, teleports {r.teleports})" for r in lv[~lv.stable].itertuples()))
            continue
        if len(lv) < need:
            print("level check not finished; rerun to resume")
            return None
        rp = df[(df.kind == "repro") & (df.scale == scale)]
        repro = None
        if len(rp) and len(rec):
            a, b = rp.iloc[0], rec[rec.seed == TASK4_SEEDS[0]].iloc[0]
            repro = dict(vehicles=[int(a.vehicles), int(b.vehicles)], teleports=[int(a.teleports), int(b.teleports)],
                         inserted=[int(a.inserted), int(b.inserted)])
        decision.write_text(json.dumps(dict(scale=scale, decided_utc=_now(), reproducibility_4100=repro,
                                            task4_seeds=rec[["seed", "teleports", "stable"]].to_dict("records")
                                            if len(rec) else "run fresh"), indent=1, default=str))
        print(f"demand level AM x{scale}: stable in all checked seeds ({decision})")
        return scale
    print("no stable level: inconclusive")
    return None


def chosen_scale() -> float:
    p = WORK / "level.json"
    if not p.exists():
        sys.exit("run the level check first (16_sumo_seeds.py level)")
    return float(json.loads(p.read_text())["scale"])


# ---------------------------------------------------------------------------
# Main runs
# ---------------------------------------------------------------------------

def main_seeds(n: int) -> list[int]:
    return [SEED_BASE + i for i in range(n)]


def part_trips(args) -> None:
    scale = chosen_scale()
    t0 = time.time()
    for s in main_seeds(args.seeds):
        m = make_trips(s, scale)
        print(f"seed {s}: {m['vehicles']:,} trips, identical in all {len(m['sha'])} networks "
              f"({m['renamed_endpoints']} endpoint names differ by a joined junction)", flush=True)
    print(f"trips checked in {time.time() - t0:.0f} s")


def main_units(n: int, scale: float, rutledge: bool) -> list[dict]:
    units = []
    for s in main_seeds(n):
        units += [dict(kind="main", variant=v, scale=scale, seed=s, sim_seed=s) for v in [BASE, *MAIN]]
        units.append(dict(kind="main", variant=PLACEBO, scale=scale, seed=s, sim_seed=s + PLACEBO_OFFSET))
    if rutledge:     # queued after everything else (plan: only if time allows)
        units += [dict(kind="main", variant=v, scale=scale, seed=s, sim_seed=s) for s in main_seeds(n) for v in OPTIONAL]
    return units


def part_runs(args) -> None:
    scale = chosen_scale()
    execute(main_units(args.seeds, scale, not args.no_rutledge), WORK / "runs.csv", args.workers, args.keep_raw,
            args.time_budget)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def boot_ci(d: np.ndarray) -> tuple[float, float]:
    rng = np.random.default_rng(BOOT_SEED)
    m = d[rng.integers(0, len(d), size=(BOOT_N, len(d)))].mean(axis=1)
    lo, hi = np.percentile(m, [2.5, 97.5])
    return float(lo), float(hi)


def summarize(d: np.ndarray) -> dict:
    lo, hi = boot_ci(d)
    return dict(seeds=len(d), mean=float(d.mean()), ci_lo=lo, ci_hi=hi, median=float(np.median(d)),
                min=float(d.min()), max=float(d.max()), better_share=float((d < 0).mean()),
                sd=float(d.std(ddof=1)))


def static_numbers(scale: float) -> pd.DataFrame:
    fq = pd.read_csv(ROOT / "outputs" / "final" / "city_question.csv")
    fq = fq[(fq.demand == 1.0) & (fq.bonus == config.ONEWAY_CAPACITY_BONUS)]
    D, table, cfgs = chk.load_model()
    od = {k: q * scale for k, q in od_shared().items()}
    names = [BASE, *MAIN, *OPTIONAL]
    tstt = {n: float(robust.evaluate(feasibility.apply_config(D, table, cfgs[n]), [od], gap=config.UE_GAP_SEARCH).tstt_h[0])
            for n in names}
    rows = []
    for n in names[1:]:
        g = lambda p: fq[(fq.config == n) & (fq.peak == p)].iloc[0]  # noqa: E731
        am, both = g("am"), g("am+pm")
        rows.append(dict(variant=n, static_am_mean=am["mean"], static_am_p10=am.p10, static_am_p90=am.p90,
                         static_am_verdict=am.verdict, static_ampm_mean=both["mean"],
                         static_sumo_od=tstt[n] / tstt[BASE] - 1))
    return pd.DataFrame(rows)


def verdict(r: pd.Series, placebo_ok: bool) -> str:
    if not placebo_ok:
        return "inconclusive (placebo interval excludes 0: pairing not working)"
    det = (r.ci_lo > 0 or r.ci_hi < 0) and abs(r["mean"]) > DETECT_MIN
    if det:
        v = ("SUMO agrees with the static model (same sign)" if np.sign(r["mean"]) == np.sign(r.static_am_mean)
             else "SUMO disagrees with the static model (opposite sign); SUMO wins")
    else:
        v = "inconclusive (no effect detected)"
        if -DETECT_MIN < r.ci_lo and r.ci_hi < DETECT_MIN:
            v += "; SUMO rules out an effect of 0.5% or more"
    if r.gridlock_runs > MAX_GRIDLOCK_RUNS:
        v += f"; UNRELIABLE ({r.gridlock_runs} gridlock-affected runs > {MAX_GRIDLOCK_RUNS})"
    return v


def pct(x, nd=2):
    return "" if pd.isna(x) else f"{x * 100:+.{nd}f}%"


def part_report(args) -> None:
    files.require(WORK / "runs.csv", "the per-run rows of Task 4b are not in git; the frozen results are in "
                  "outputs/final/sumo/ (seeds40*.csv, RESULTS_4b.md). Rebuild them with `16_sumo_seeds.py level` and "
                  "`16_sumo_seeds.py main` (200 runs, about 4.2 h with 15 workers on an 8-core laptop)")
    scale = chosen_scale()
    df = load(WORK / "runs.csv")
    df = df[df.kind == "main"].copy()
    df["gridlock"] = ~df.stable
    FINAL.mkdir(parents=True, exist_ok=True)

    # pairing checks
    pairing = []
    for s, g in df.groupby("seed"):
        nonp = g[g.variant != PLACEBO]
        pairing.append(dict(seed=s, variants=len(g), one_trip_draw=g.trips_sha.nunique() == 1,
                            same_sim_seed=bool((nonp.sim_seed == s).all()),
                            placebo_other_seed=bool((g[g.variant == PLACEBO].sim_seed == s + PLACEBO_OFFSET).all()),
                            same_vehicles=g.vehicles.nunique() == 1))
    pairing = pd.DataFrame(pairing)

    base = df[df.variant == BASE].set_index("seed")
    complete_seeds = sorted(base.index)
    variants = [BASE, *MAIN, PLACEBO, *OPTIONAL]
    df["d_vs_today"] = [r.tstt_h / base.tstt_h.get(r.seed, np.nan) - 1 for r in df.itertuples()]
    keep = ["variant", "seed", "sim_seed", "scale", "trips_sha", "file_sha", "vehicles", "expected", "loaded", "inserted",
            "running", "waiting", "teleports", "teleports_jam", "teleports_yield", "teleports_wronglane", "unfinished_peak",
            "vehicles_peak", "tstt_h", "tstt_all_h", "d_vs_today", "stable", "gridlock", "started_utc", "seconds", "platform"]
    order = {v: i for i, v in enumerate(variants)}
    out = df.sort_values(["seed", "variant"], key=lambda c: c.map(order) if c.name == "variant" else c)[keep]
    out.to_csv(FINAL / "seeds40.csv", index=False)

    # seeds where any variant or the placebo is gridlock-affected (secondary analysis)
    bad_seeds = set(df[df.gridlock & df.variant.isin([BASE, *MAIN, PLACEBO])].seed)
    rows = []
    for v in variants[1:]:
        sub = df[(df.variant == v) & df.seed.isin(complete_seeds)].set_index("seed")
        if len(sub) < len(complete_seeds):
            rows.append(dict(variant=v, seeds=len(sub), note=f"incomplete ({len(sub)} of {len(complete_seeds)} seeds): not reported"))
            continue
        d = sub.d_vs_today.to_numpy()
        r = dict(variant=v, **summarize(d),
                 gridlock_runs=int(sub.gridlock.sum()), runs_any_teleport=int((sub.teleports > 0).sum()),
                 runs_vehicles_left=int(((sub.running + sub.waiting) > 0).sum()), teleports_total=int(sub.teleports.sum()))
        d2 = sub.loc[[s for s in sub.index if s not in bad_seeds], "d_vs_today"].to_numpy()
        if len(d2) >= 2:
            s2 = summarize(d2)
            r.update(sec_seeds=len(d2), sec_mean=s2["mean"], sec_ci_lo=s2["ci_lo"], sec_ci_hi=s2["ci_hi"],
                     sec_better=s2["better_share"])
        rows.append(r)
    res = pd.DataFrame(rows)
    pl = res[res.variant == PLACEBO].iloc[0]
    placebo_ok = bool(pl.ci_lo <= 0 <= pl.ci_hi)
    st = static_numbers(scale)
    res = res.merge(st, on="variant", how="left")
    res["verdict"] = [verdict(r, placebo_ok) if r.variant != PLACEBO and pd.isna(r.get("note", np.nan)) else ""
                      for _, r in res.iterrows()]
    tb = base
    today_row = dict(variant=BASE, seeds=len(tb), gridlock_runs=int((~tb.stable).sum()),
                     runs_any_teleport=int((tb.teleports > 0).sum()),
                     runs_vehicles_left=int(((tb.running + tb.waiting) > 0).sum()), teleports_total=int(tb.teleports.sum()))
    res = pd.concat([pd.DataFrame([today_row]), res], ignore_index=True)
    res.to_csv(FINAL / "seeds40_summary.csv", index=False)
    where = part_where(res, df, scale) if args.where or any(res.verdict.fillna("").str.startswith("SUMO")) else None
    write_md(res, pairing, df, scale, placebo_ok, bad_seeds, where)
    print((FINAL / "RESULTS_4b.md").read_text(encoding="utf-8"))


JUNCTION_NOTES: dict = {}


def part_where(res, df, scale) -> pd.DataFrame:
    """For each variant vs today, per seed (sums over peak-hour trips, veh-h): change by trip origin
    (each gateway, internal), by component (insertion wait at the origin vs time in the network), and edge
    time loss on the converted streets / other edges ending at a signal / other edges without one.
    Trips are matched by id; trips with no tripinfo record in one of the two runs (never inserted by the
    end) are counted, not compared."""
    import xml.etree.ElementTree as ET
    D, table, cfgs = chk.load_model()
    B = feasibility.apply_config(D, table, cfgs[BASE])
    zones = demand.load_zones(B, ROOT / "data" / "reference" / "zones.csv", peak=PEAK)
    jgw = {nets()[BASE].junction_of[n]: g for g, (n, _) in zones.gateways.items() if n in nets()[BASE].junction_of}
    w0, w1 = config.SUMO_WARMUP_S, config.SUMO_WARMUP_S + config.SUMO_PEAK_S

    def netinfo(name):
        root = ET.parse(NETS / f"{chk.slug(name)}.net.xml").getroot()
        tl = {j.get("id") for j in root.iter("junction") if j.get("type", "").startswith("traffic_light")}
        to = {e.get("id"): e.get("to") for e in root.iter("edge") if e.get("function") != "internal"}
        prog = {t.get("id"): [(p.get("duration"), p.get("state")) for p in t.iter("phase")] for t in root.iter("tlLogic")}
        return {e for e, j in to.items() if j in tl}, to, prog

    info = {n: netinfo(n) for n in [BASE, *MAIN, *OPTIONAL]}
    sig = {n: info[n][0] for n in info}
    JUNCTION_NOTES.clear()
    grid = {(r.variant, r.seed): bool(r.gridlock) for r in df.itertuples()}
    rows = []
    for v in [x for x in [*MAIN, *OPTIONAL] if res.verdict.fillna("").str.startswith("SUMO")[res.variant == x].any()
              or _cache.get("where_all")]:
        changed = {sid for sid in table if cfgs[v].get(sid) != cfgs[BASE].get(sid)}
        conv_uv = {(table[x].a, table[x].b) for x in changed} | {(table[x].b, table[x].a) for x in changed}
        conv = {n: {e for e, uv in nets()[n].edges.items() if uv in conv_uv} for n in (BASE, v)}
        nodes = {table[x].a for x in changed} | {table[x].b for x in changed}
        juncs = {n: {nets()[n].junction_of[x] for x in nodes if x in nets()[n].junction_of} for n in (BASE, v)}
        appr = {n: {e for e, j in info[n][1].items() if j in juncs[n]} - conv[n] for n in (BASE, v)}
        on_tl = [j for j in juncs[v] if j in info[v][2]]
        JUNCTION_NOTES[v] = dict(junctions=len(juncs[v]), signalized=len(on_tl),
                                 programs_changed=sum(info[BASE][2].get(j) != info[v][2][j] for j in on_tl))
        for s in sorted(df[df.variant == v].seed):
            tb, tv = (df[(df.variant == x) & (df.seed == s)].iloc[0].tag for x in (BASE, v))
            A, Z = (np.load(WORK / "details" / f"{t}.npz") for t in (tb, tv))
            origin = read_trips_meta(s, scale)
            ids, ia, iz = np.intersect1d(A["trip_id"], Z["trip_id"], return_indices=True)
            r = dict(variant=v, seed=s, gridlock_today=grid[(BASE, s)], gridlock_variant=grid[(v, s)],
                     trips_missing_today=int(len(origin) - len(A["trip_id"])),
                     trips_missing_variant=int(len(origin) - len(Z["trip_id"])))
            peak = (A["trip_planned"][ia] >= w0) & (A["trip_planned"][ia] < w1)
            org = np.array([jgw.get(j, "internal") for j in origin[ids]])
            for comp, key in (("wait", "trip_departDelay"), ("net", "trip_duration")):
                diff = Z[key][iz].astype(float) - A[key][ia].astype(float)
                for g in [*zones.gateways, "internal"]:
                    r[f"{comp}_{g}_h"] = float(diff[peak & (org == g)].sum() / 3600)
            for part, inc in (("converted", lambda n: conv[n]), ("signal", lambda n: sig[n] - conv[n]), ("other", None)):
                vals = []
                for n, Zz in ((BASE, A), (v, Z)):
                    ids_e, tl = Zz["edge_id"], np.nan_to_num(Zz["edge_timeLoss"].astype(float))
                    m = np.isin(ids_e, list(inc(n))) if inc else ~np.isin(ids_e, list(sig[n] | conv[n]))
                    vals.append(tl[m].sum())
                r[f"timeloss_{part}_h"] = float((vals[1] - vals[0]) / 3600)
            for part, sets in (("street", conv), ("approaches", appr), ("elsewhere", None)):
                vals = []
                for n, Zz in ((BASE, A), (v, Z)):
                    ids_e, tl = Zz["edge_id"], np.nan_to_num(Zz["edge_timeLoss"].astype(float))
                    m = np.isin(ids_e, list(sets[n])) if sets else ~np.isin(ids_e, list(conv[n] | appr[n]))
                    vals.append(tl[m].sum())
                r[f"loss_{part}_h"] = float((vals[1] - vals[0]) / 3600)
            tt = lambda x: float(df[(df.variant == x) & (df.seed == s)].tstt_h.iloc[0])  # noqa: E731
            r["tstt_change_h"], r["tstt_today_h"] = tt(v) - tt(BASE), tt(BASE)
            rows.append(r)
    w = pd.DataFrame(rows)
    w.to_csv(FINAL / "seeds40_where.csv", index=False)
    return w


def read_trips_meta(seed: int, scale: float) -> np.ndarray:
    """Origin junction (today's names) per trip id, rebuilt from the seed's draw and checked against the
    manifest hash (the draw must match the one the runs used, e.g. after a numpy change)."""
    d = WORK / "trips" / f"x{scale}_s{seed}"
    p = d / "today_origins.npy"
    if not p.exists():
        tmp = d / "today_check.xml"
        write_net_trips(tmp, BASE, seed, scale)
        want = json.loads((d / "manifest.json").read_text())["sha"][chk.slug(BASE)]
        raw = tmp.read_bytes()       # a file written on Windows has CRLF line ends: same trips, other bytes
        if want not in (hashlib.sha256(raw).hexdigest(), hashlib.sha256(raw.replace(b"\n", b"\r\n")).hexdigest()):
            raise RuntimeError(f"seed {seed}: rebuilt trips do not match the manifest (numpy/platform difference?)")
        tr = read_trips(tmp)
        tmp.unlink()
        arr = np.empty(len(tr), dtype=object)
        for i, _, a, _ in tr:
            arr[i] = a
        np.save(p, arr, allow_pickle=True)
    return np.load(p, allow_pickle=True)


def write_md(res, pairing, df, scale, placebo_ok, bad_seeds, where):
    plan_sha = sha256(PLAN)
    plan_m = datetime.fromtimestamp(PLAN.stat().st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lvl = json.loads((WORK / "level.json").read_text())
    lv_runs = load(WORK / "level_runs.csv")
    first_run = min([*lv_runs.started_utc.dropna(), *df.started_utc.dropna()])
    n_seeds = df[df.variant == BASE].seed.nunique()
    L = ["# SUMO with enough seeds (Task 4b)", "",
         f"Pre-registered plan: `docs/task4b_plan.md` (sha256 `{plan_sha[:16]}…`, last modified {plan_m}; first "
         f"Task 4b simulation started {first_run}). SUMO {chk.sumo_version()} meso, netconvert default signal "
         f"timings, rerouting device, AM peak only, base-scenario OD at **demand x{scale}**, **{n_seeds} trip seeds** "
         f"({min(df.seed)}-{max(df.seed)}). Relative changes only: SUMO's signals are generic defaults, so this is "
         "Charleston's street geometry with generic signals, not real Charleston delay.", "",
         "## Demand level (AM)", ""]
    rp = lvl.get("reproducibility_4100")
    t4 = lvl["task4_seeds"]
    t4s = t4 if isinstance(t4, str) else ", ".join(f"{r['seed']}: {r['teleports']} teleports" for r in t4)
    L.append(f"Chosen: x{lvl['scale']} (decided {lvl['decided_utc']}, before any main run). Task 4 baseline seeds "
             f"4100-4104 (recorded): {t4s}. "
             "Fresh seeds: " + ", ".join(f"{r.seed} x{r.scale}: {r.teleports} teleports, {int(r.running + r.waiting)} left, "
                                         f"{'stable' if r.stable else 'UNSTABLE'}" for r in lv_runs[lv_runs.kind == "level"].itertuples()) + ".")
    if rp:
        L.append(f"Reproducibility, seed 4100 at x{lvl['scale']} re-run with Task 4's generator: vehicles {rp['vehicles'][0]:,} "
                 f"(Task 4 {rp['vehicles'][1]:,}), teleports {rp['teleports'][0]} (Task 4 {rp['teleports'][1]}).")
    L += ["", "## Pairing", "",
          f"{len(pairing)} seeds; one trip draw shared by every variant in {int(pairing.one_trip_draw.sum())}; same sim seed "
          f"for every non-placebo variant in {int(pairing.same_sim_seed.sum())}; placebo on sim seed + {PLACEBO_OFFSET} in "
          f"{int(pairing.placebo_other_seed.sum())}; identical vehicle count in {int(pairing.same_vehicles.sum())}. Each "
          "run rebuilt its trip file and matched the SHA-256 checked trip by trip before the runs (`trips_sha`, "
          "`file_sha` in `seeds40.csv`).", "",
          "## Results: change in AM total travel time vs today, per seed", "",
          f"Detected = 95% bootstrap interval excludes 0 AND |mean| > {DETECT_MIN:.1%} AND the placebo's interval includes 0. "
          f"Placebo interval includes 0: **{'yes' if placebo_ok else 'NO: pairing not working, everything inconclusive'}**.", "",
          "| Variant | Seeds | Mean | 95% interval | Median | Min to max | Better | Gridlock runs | Any teleport / vehicles left / teleports total | Static AM x1.0 mean (p10 to p90) | Static AM+PM | Static on SUMO's OD | Verdict |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in res.itertuples():
        if r.variant == BASE:
            L.append(f"| today | {r.seeds} | (reference) | | | | | {r.gridlock_runs} | {r.runs_any_teleport} / "
                     f"{r.runs_vehicles_left} / {r.teleports_total} | | | | |")
            continue
        if isinstance(getattr(r, "note", None), str):
            L.append(f"| {r.variant} | {r.seeds} | {r.note} |||||||||||")
            continue
        stat = "" if r.variant == PLACEBO else f"{pct(r.static_am_mean, 3)} ({pct(r.static_am_p10, 3)} to {pct(r.static_am_p90, 3)})"
        L.append(f"| {r.variant} | {r.seeds} | **{pct(r.mean)}** | {pct(r.ci_lo)} to {pct(r.ci_hi)} | {pct(r.median)} | "
                 f"{pct(r.min)} to {pct(r.max)} | {r.better_share:.0%} | {r.gridlock_runs} | {r.runs_any_teleport} / "
                 f"{r.runs_vehicles_left} / {r.teleports_total} | {stat} | "
                 f"{'' if r.variant == PLACEBO else pct(r.static_ampm_mean, 3)} | "
                 f"{'' if r.variant == PLACEBO else pct(r.static_sumo_od, 3)} | {r.verdict or 'noise of an identical network'} |")
    L += ["", f"Gridlock-affected run = not stable (vehicles not inserted or left at the end, or teleports above "
          f"{config.SUMO_STABLE_TELEPORT_SHARE:.1%} of loaded); more than {MAX_GRIDLOCK_RUNS} of the seeds makes a variant "
          "unreliable. 'Any teleport' is shown for reference only (plan).", "",
          f"**Secondary (plan):** dropping the {len(bad_seeds)} seed(s) where today, Coming, all three or the placebo is "
          f"gridlock-affected ({', '.join(map(str, sorted(bad_seeds))) or 'none'}):", "",
          "| Variant | Seeds | Mean | 95% interval | Better |", "|---|---|---|---|---|"]
    for r in res.itertuples():
        if r.variant != BASE and not pd.isna(getattr(r, "sec_mean", np.nan)):
            L.append(f"| {r.variant} | {int(r.sec_seeds)} | {pct(r.sec_mean)} | {pct(r.sec_ci_lo)} to {pct(r.sec_ci_hi)} | {r.sec_better:.0%} |")
    if where is not None and len(where):
        gws = [c[5:-2] for c in where.columns if c.startswith("wait_") and c.endswith("_h")]
        L += ["", "## Where the change comes from (variants meeting the detection criteria)", "",
              "Change vs today, veh-h, mean over seeds (sums over the peak-hour trips matched by id). 'Clean' = "
              "seeds where neither today's run nor the variant's is gridlock-affected. Wait = waiting to be "
              "inserted at the origin (queues backing up to the entry point); network = time from insertion to "
              "arrival. Edge time loss (edgeData, peak hour) on the converted streets, on other edges that end "
              "at a signal, and on the rest.", "",
              "| Variant | Seeds | TSTT change (today's TSTT) | " + " | ".join(f"{g}: wait / network" for g in gws)
              + " | Edge time loss: converted / other signalized / rest |",
              "|---|---|---|" + "---|" * len(gws) + "---|"]
        for v, g in where.groupby("variant", sort=False):
            for lab, sub in (("all", g), ("clean", g[~g.gridlock_today & ~g.gridlock_variant])):
                m = sub.mean(numeric_only=True)
                L.append(f"| {v} | {lab} {len(sub)} | {m.tstt_change_h:+.0f} ({m.tstt_today_h:,.0f}) | "
                         + " | ".join(f"{m[f'wait_{x}_h']:+.0f} / {m[f'net_{x}_h']:+.0f}" for x in gws)
                         + f" | {m.timeloss_converted_h:+.0f} / {m.timeloss_signal_h:+.0f} / {m.timeloss_other_h:+.0f} |")
        L += ["", "Same edge time loss split by place: the converted street's own edges / every other edge that "
              "ends at one of its junctions (cross-street approaches) / everything else. Signal programs: netconvert "
              "rebuilds its default program at every signalized junction whose movements change.", "",
              "| Variant | Seeds | Street / approaches / elsewhere (veh-h) | Junctions on the street | Signalized | Programs changed |",
              "|---|---|---|---|---|---|"]
        for v, g in where.groupby("variant", sort=False):
            jn = JUNCTION_NOTES.get(v, {})
            for lab, sub in (("all", g), ("clean", g[~g.gridlock_today & ~g.gridlock_variant])):
                m = sub.mean(numeric_only=True)
                L.append(f"| {v} | {lab} {len(sub)} | {m.loss_street_h:+.0f} / {m.loss_approaches_h:+.0f} / "
                         f"{m.loss_elsewhere_h:+.0f} | {jn.get('junctions', '')} | {jn.get('signalized', '')} | "
                         f"{jn.get('programs_changed', '')} |")
        miss = where[["variant", "seed", "trips_missing_today", "trips_missing_variant"]]
        miss = miss[(miss.trips_missing_today > 0) | (miss.trips_missing_variant > 0)]
        if len(miss):
            L += ["", "Trips with no tripinfo record (never inserted by the end of the run, so absent from TSTT, "
                  "which makes that run look slightly better): " + "; ".join(
                      f"{r.variant} seed {r.seed}: today {r.trips_missing_today}, variant {r.trips_missing_variant}"
                      for r in miss.itertuples()) + "."]
    L += ["", "## Notes", "",
          f"* today itself has {int(res[res.variant == BASE].gridlock_runs.iloc[0])} gridlock-affected runs of 40 and the "
          f"placebo {int(res[res.variant == PLACEBO].gridlock_runs.iloc[0])}: x1.0 is marginal for every network, so "
          "the secondary analysis (gridlock seeds dropped) is the check that the means are not riding on them.",
          "* The placebo's spread (SD of d over seeds) is "
          f"{res[res.variant == PLACEBO].sd.iloc[0]:.1%} against {res[res.variant.isin(MAIN)].sd.mean():.1%} for the "
          "variants: sharing the sim seed roughly halves the noise, which is what pairing is for. The placebo answers "
          "'is an identical network centred on 0', not 'how noisy is a paired comparison'.",
          "* TSTT (Task 4 definition) leaves out trips never inserted by the end of the run; that only happens in "
          "gridlock-affected runs and makes those runs look better, not worse.",
          "* Generic signals: netconvert rebuilds a default program at every signal a conversion touches (see the "
          "table above). A real conversion would come with retimed signals and turn lanes; SUMO's answer is about "
          "the geometry with generic signals, not Charleston's real delay.", ""]
    (FINAL / "RESULTS_4b.md").write_text("\n".join(L) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("part", choices=["level", "trips", "runs", "report", "main"])
    ap.add_argument("--workers", type=int, default=0)
    ap.add_argument("--seeds", type=int, default=N_SEEDS, help="40 (plan); 20 only under the plan's fallback")
    ap.add_argument("--no-rutledge", action="store_true", help="skip the optional Rutledge variant")
    ap.add_argument("--time-budget", type=float, default=float("inf"))
    ap.add_argument("--keep-raw", action="store_true")
    ap.add_argument("--where", action="store_true", help="where-table for every variant, detected or not")
    args = ap.parse_args()
    if args.where:
        _cache["where_all"] = True
    if args.part == "level":
        part_level(args)
        return
    if args.part in ("trips", "main"):
        part_trips(args)
    if args.part in ("runs", "main"):
        part_runs(args)
    if args.part in ("report", "main"):
        part_report(args)


if __name__ == "__main__":
    main()
