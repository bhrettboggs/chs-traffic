"""Task 3: the final results, frozen to outputs/final/.

    python scripts/13_final_results.py PART [--workers N] [--time-budget SECONDS] [--scenarios 20]

PART is one of
  noise     run-to-run variation of baseline TSTT (edge order shuffled, and gap 1e-4 vs 1e-5)
  backtest  Spring/Cannon before vs after the 2017 conversion, incl. modeled volume at the count stations
  city      Coming, Rutledge, Ashley and all three two-way, plus the P5-2 Ashley move (corridor 0),
            at one-way capacity bonus 1.0, 1.1 and 1.2
  pareto    the non-dominated single moves of each open search (run 09_search.py first), on all scenarios
  decompose why city results moved since HANDOFF section 6: the same comparisons, AM, x1.0, on the demand
            before Task 2 (guessed K and split, no non-work trips) and with measured factors only
  report    build the tables in outputs/final/ from the raw results (no solving)
  all       noise, backtest, city, then report

Every solve: AM and PM peak, demand x1.0, x1.3, x1.6 (config.SENSITIVITY_DEMAND_LEVELS), gap
config.UE_GAP_SEARCH. Results are cached per (part, config, peak, demand level, bonus) in
outputs/final/raw/<part>.csv, so a run can be stopped and started again; delete a raw file to redo it.
The exact commands that rebuild outputs/final/ from a clean checkout are in outputs/final/README.md.

UNCALIBRATED at link level (screenlines AM 4/6, PM 5/6): every result is a relative comparison.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from chstraffic import config, demand, feasibility, files, robust, widths  # noqa: E402
from chstraffic.calibrate import count_k, locate  # noqa: E402
from chstraffic.fast_assignment import Network  # noqa: E402
from chstraffic.variants import city_variants, spring_cannon_before  # noqa: E402

OUT = ROOT / "outputs" / "final"
RAW = OUT / "raw"
PEAKS = ("am", "pm")
LEVELS = tuple(config.SENSITIVITY_DEMAND_LEVELS)
BONUSES = (1.0, 1.1, 1.2)
NOISE_SEEDS = (1, 2)              # edge-order shuffles
NOISE_TIGHT_GAP = 1e-5
ASHLEY_P5_CORRIDOR = 0            # Ashley Ave, Calhoun to the Crosstown, 994 m (HANDOFF P5-2)
STATIONS = {"spring": ("^Spring Street$", "^Meeting Street$", "Septima", "Spring Street"),
            "cannon": ("^Cannon Street$", "Septima", "^Coming Street$", "Cannon Street")}
KEY = ["config", "peak", "scale", "bonus"]
# Demand before Task 2 (HANDOFF section 6 P5 results) and halfway, for the decompose part only.
DEMAND_VARIANTS = {
    "old: K .09, split .60, no non-work": dict(PEAK_FACTOR_SOURCE="guess", NONWORK_RESIDENT_WEIGHT=0.0,
                                               NONWORK_INTERNAL_VPH=0.0),
    "measured K and split, no non-work": dict(PEAK_FACTOR_SOURCE="ccs", NONWORK_RESIDENT_WEIGHT=0.0,
                                              NONWORK_INTERNAL_VPH=0.0),
}


# ---------------------------------------------------------------- setup
class Ctx:
    def __init__(self, n: int, workers: int):
        self.n, self.workers = n, workers
        self.D = files.load_graph()
        self.table = feasibility.segment_table(
            self.D, feasibility.load_overrides(ROOT / "data" / "reference" / "overrides.csv"),
            widths.load(ROOT / "data" / "processed" / "segment_widths.csv"))
        self.base_cfg = feasibility.baseline_config(self.table)
        self.cors = feasibility.search_corridors(self.D, self.table)
        self._ods = {}

    def graph(self, cfg: dict, bonus: float = config.ONEWAY_CAPACITY_BONUS) -> nx.DiGraph:
        old, config.ONEWAY_CAPACITY_BONUS = config.ONEWAY_CAPACITY_BONUS, bonus
        try:
            return feasibility.apply_config(self.D, self.table, cfg)
        finally:
            config.ONEWAY_CAPACITY_BONUS = old

    def ods(self, peak: str, scale: float, variant: str = "final") -> list[dict]:
        """Demand is built on today's network (zone snaps and free-flow times don't depend on the bonus).
        variant != "final" temporarily sets the config values in DEMAND_VARIANTS (diagnostics only)."""
        if (peak, scale, variant) not in self._ods:
            settings = {"DEMAND_SCALE": scale, **DEMAND_VARIANTS.get(variant, {})}
            old = {k: getattr(config, k) for k in settings}
            try:
                for k, v in settings.items():
                    setattr(config, k, v)
                B = self.graph(self.base_cfg)
                zones = demand.load_zones(B, ROOT / "data" / "reference" / "zones.csv", peak=peak)
                self._ods[(peak, scale, variant)] = demand.scenarios(B, zones, n=self.n)
            finally:
                for k, v in old.items():
                    setattr(config, k, v)
        return self._ods[(peak, scale, variant)]


class Cache:
    def __init__(self, part: str):
        RAW.mkdir(parents=True, exist_ok=True)
        self.path = RAW / f"{part}.csv"
        self.df = pd.read_csv(self.path) if self.path.exists() else pd.DataFrame()

    def done(self, key: dict) -> bool:
        if self.df.empty:
            return False
        m = np.ones(len(self.df), bool)
        for k, v in key.items():
            col = self.df[k]
            m &= np.isclose(col, v) if isinstance(v, float) else (col.astype(str) == str(v))
        return bool(m.any())

    def add(self, key: dict, ev: robust.Evaluation, watch_names: list[str] = (), extra: dict | None = None):
        rows = pd.DataFrame(dict(**key, scenario=np.arange(len(ev.tstt_h)), tstt_h=ev.tstt_h, vkm=ev.vkm,
                                 unreachable=ev.unreachable, iterations=ev.iterations, max_gap=ev.max_gap,
                                 **{w: ev.watched[:, i] for i, w in enumerate(watch_names)}, **(extra or {})))
        rows.to_csv(self.path, mode="a", header=not self.path.exists(), index=False)
        self.df = pd.concat([self.df, rows], ignore_index=True)


class Budget:
    def __init__(self, seconds: float):
        self.t0, self.seconds, self.last = time.time(), seconds, 0.0

    def ok(self) -> bool:
        left = self.seconds - (time.time() - self.t0)
        return left > 1.2 * self.last

    def unit(self, t_start: float):
        self.last = time.time() - t_start


def run_units(ctx: Ctx, part: str, units: list[dict], build, budget: Budget, watch=None):
    """units: dicts with KEY (+ optional extras); build(unit) -> (graph, gap, net or None)."""
    cache = Cache(part)
    if not cache.df.empty and (cache.df.groupby(KEY).size() != ctx.n).any():
        sys.exit(f"{cache.path} holds runs with another number of scenarios; delete it or use --out-dir")
    todo = [u for u in units if not cache.done({k: u[k] for k in KEY})]
    print(f"[{part}] {len(units) - len(todo)} of {len(units)} units cached, {len(todo)} to run")
    for u in todo:
        if not budget.ok():
            print(f"[{part}] time budget used; run the same command again to continue")
            return False
        t = time.time()
        G, gap, net = build(u)
        w = watch(G) if watch else None
        ev = robust.evaluate(G, ctx.ods(u["peak"], u["scale"], u.get("demand", "final")), gap=gap, workers=ctx.workers,
                             watch=w[1] if w else None, net=net)
        cache.add({k: u[k] for k in KEY}, ev, w[0] if w else (), {k: v for k, v in u.items() if k not in KEY})
        budget.unit(t)
        print(f"  {u['config']:<28} {u['peak']} x{u['scale']:g} bonus {u['bonus']:.2f}: median TSTT "
              f"{np.median(ev.tstt_h):,.1f} veh-h, max gap {ev.max_gap:.1e}, {time.time() - t:.0f} s")
    return True


# ---------------------------------------------------------------- parts
def shuffled(G: nx.DiGraph, seed: int) -> nx.DiGraph:
    rng = np.random.default_rng(seed)
    nodes, edges = list(G.nodes(data=True)), list(G.edges(data=True))
    H = nx.DiGraph()
    H.add_nodes_from([nodes[i] for i in rng.permutation(len(nodes))])
    H.add_edges_from([edges[i] for i in rng.permutation(len(edges))])
    return H


def part_noise(ctx, budget):
    units = [dict(config=v, peak=p, scale=s, bonus=config.ONEWAY_CAPACITY_BONUS)
             for s in LEVELS for p in PEAKS for v in ["canonical", *[f"shuffle{k}" for k in NOISE_SEEDS], "tight"]]
    B = ctx.graph(ctx.base_cfg)

    def build(u):
        if u["config"].startswith("shuffle"):
            return shuffled(B, int(u["config"][7:])), config.UE_GAP_SEARCH, None
        return B, (NOISE_TIGHT_GAP if u["config"] == "tight" else config.UE_GAP_SEARCH), None
    return run_units(ctx, "noise", units, build, budget)


def station_edges(G):
    names, edges = [], []
    for key, (road, frm, to, _) in STATIONS.items():
        seg, _ = locate(G, road, frm, to)
        a, b = tuple(seg)
        names += [f"{key}_ab", f"{key}_ba"]
        edges += [(a, b), (b, a)]
    return names, edges


def part_backtest(ctx, budget):
    before_cfg, changed = spring_cannon_before(ctx.D, ctx.table, ctx.base_cfg)
    cfgs = {"after (today)": ctx.base_cfg, "before (2016)": before_cfg}
    units = [dict(config=c, peak=p, scale=s, bonus=config.ONEWAY_CAPACITY_BONUS)
             for s in LEVELS for p in PEAKS for c in cfgs]
    A = ctx.graph(ctx.base_cfg)
    _, watch = station_edges(A)                      # same node pairs in both configs
    return run_units(ctx, "backtest", units, lambda u: (ctx.graph(cfgs[u["config"]], u["bonus"]), config.UE_GAP_SEARCH, None),
                     budget, watch=lambda G: station_edges(A))


def city_configs(ctx) -> dict:
    variants, _ = city_variants(ctx.table, ctx.base_cfg)
    cfgs = {"today": ctx.base_cfg, **{k: v[0] for k, v in variants.items()}}
    c0 = {c.cid: c for c in ctx.cors}[ASHLEY_P5_CORRIDOR]
    cfgs["Ashley Calhoun-Crosstown"] = {**ctx.base_cfg, **c0.config_for(ctx.table, "two")[0]}
    return cfgs


def part_city(ctx, budget):
    cfgs = city_configs(ctx)
    units = [dict(config=c, peak=p, scale=s, bonus=b) for b in BONUSES for s in LEVELS for p in PEAKS for c in cfgs]
    return run_units(ctx, "city", units, lambda u: (ctx.graph(cfgs[u["config"]], u["bonus"]), config.UE_GAP_SEARCH, None), budget)


def part_decompose(ctx, budget):
    cfgs = city_configs(ctx)
    units = [dict(config=f"{c} | {d}", peak="am", scale=1.0, bonus=config.ONEWAY_CAPACITY_BONUS, demand=d, layout=c)
             for d in DEMAND_VARIANTS for c in cfgs]
    return run_units(ctx, "decompose", units,
                     lambda u: (ctx.graph(cfgs[u["layout"]], u["bonus"]), config.UE_GAP_SEARCH, None), budget)


def search_states() -> dict:
    st = {}
    for s in LEVELS:
        f = OUT / f"search_state_both_x{s:g}.json"
        if f.exists():
            st[s] = json.loads(f.read_text())
    return st


def pareto_front(df: pd.DataFrame) -> pd.DataFrame:
    """Non-dominated rows: lower d_tstt, lower d_vkm, higher d_two_way_share."""
    keep = []
    v = df[["d_tstt", "d_vkm", "d_two_way_share"]].to_numpy() * np.array([1, 1, -1])
    for i in range(len(v)):
        dom = np.all(v <= v[i], axis=1) & np.any(v < v[i], axis=1)
        keep.append(not dom.any())
    return df[np.array(keep)]


def pareto_moves(ctx) -> dict:
    """Union over demand levels of the round-1 Pareto moves (screening numbers), as configs."""
    by_cid = {c.cid: c for c in ctx.cors}
    moves = {}
    for s, st in search_states().items():
        rows = [dict(cid=int(k.split("|")[1]), mode=k.split("|")[2], **v) for k, v in st["screen"].items()
                if k.startswith("1|") and v["status"] == "ok"]
        for r in pareto_front(pd.DataFrame(rows)).itertuples():
            moves[f"{by_cid[r.cid].name} [{r.cid}] {r.mode}"] = (r.cid, r.mode)
        if st["accepted"]:
            cfg = dict(ctx.base_cfg)
            for cid, mode in st["accepted"]:
                cfg.update(by_cid[cid].config_for(ctx.table, mode)[0])
            moves[f"search result x{s:g}: " + " + ".join(f"{by_cid[c].name} [{c}] {m}" for c, m in st["accepted"])] = cfg
    cfgs = {"today": ctx.base_cfg}
    for label, m in moves.items():
        cfgs[label] = m if isinstance(m, dict) else {**ctx.base_cfg, **by_cid[m[0]].config_for(ctx.table, m[1])[0]}
    return cfgs


def part_pareto(ctx, budget):
    if len(search_states()) < len(LEVELS):
        sys.exit("run the three open searches first (outputs/final/README.md)")
    cfgs = pareto_moves(ctx)
    units = [dict(config=c, peak=p, scale=s, bonus=config.ONEWAY_CAPACITY_BONUS) for s in LEVELS for p in PEAKS for c in cfgs]
    return run_units(ctx, "pareto", units, lambda u: (ctx.graph(cfgs[u["config"]], u["bonus"]), config.UE_GAP_SEARCH, None), budget)


# ---------------------------------------------------------------- report
def compare(df: pd.DataFrame, base: str, thr: float) -> pd.DataFrame:
    """Per config, bonus, demand level and peak (AM, PM, AM+PM): change vs `base` over paired scenarios."""
    rows = []
    for (cfgname, bonus, scale), g in df.groupby(["config", "bonus", "scale"], sort=False):
        if cfgname == base:
            continue
        b = df[(df.config == base) & np.isclose(df.bonus, bonus) & np.isclose(df.scale, scale)]
        for peak in ("am", "pm", "am+pm"):
            pk = list(PEAKS) if peak == "am+pm" else [peak]
            new = g[g.peak.isin(pk)].groupby("scenario")[["tstt_h", "vkm", "unreachable"]].sum()
            old = b[b.peak.isin(pk)].groupby("scenario")[["tstt_h", "vkm", "unreachable"]].sum()
            if len(new) == 0 or len(new) != len(old):
                continue
            ch = (new.tstt_h / old.tstt_h - 1).to_numpy()
            vk = (new.vkm / old.vkm - 1).to_numpy()
            stranded = bool((new.unreachable > old.unreachable + 1e-6).any())
            mean, share = float(ch.mean()), float((ch < 0).mean())
            if stranded:
                verdict = "strands demand"
            elif mean < -thr and share >= config.MIN_WIN_RATE:
                verdict = "detectable: better"
            elif mean > thr and share <= 1 - config.MIN_WIN_RATE:
                verdict = "detectable: worse"
            else:
                verdict = "not detectable"
            rows.append(dict(config=cfgname, bonus=bonus, demand=scale, peak=peak, n=len(ch), mean=mean,
                             p10=np.percentile(ch, 10), median=np.median(ch), p90=np.percentile(ch, 90),
                             improved_share=share, vkm_mean=float(vk.mean()), verdict=verdict))
    return pd.DataFrame(rows)


def noise_report() -> tuple[pd.DataFrame, float]:
    df = pd.read_csv(RAW / "noise.csv")
    rows = []
    for (scale, peak), g in df.groupby(["scale", "peak"]):
        c = g[g.config == "canonical"].set_index("scenario").tstt_h
        for v in sorted(set(g.config) - {"canonical"}):
            d = (g[g.config == v].set_index("scenario").tstt_h / c - 1).abs()
            rows.append(dict(demand=scale, peak=peak, compare=f"{v} vs canonical", n=len(d), median_abs=d.median(),
                             p95_abs=np.percentile(d, 95), max_abs=d.max(),
                             iterations=int(g[g.config == v].iterations.median())))
    for scale, g in df.groupby("scale"):                      # AM + PM
        s = g.groupby(["config", "scenario"]).tstt_h.sum().unstack(0)
        for v in [c for c in s.columns if c != "canonical"]:
            d = (s[v] / s["canonical"] - 1).abs()
            rows.append(dict(demand=scale, peak="am+pm", compare=f"{v} vs canonical", n=len(d), median_abs=d.median(),
                             p95_abs=np.percentile(d, 95), max_abs=d.max(), iterations=np.nan))
    nr = pd.DataFrame(rows)
    # noise in a comparison of two configs = difference between two solves of the same problem
    shuf = nr[nr["compare"].str.startswith("shuffle")]
    return nr, float(shuf.max_abs.max()), float(nr[nr["compare"].str.startswith("tight")].max_abs.max())


def md(df: pd.DataFrame, floatfmt: str = ".4f") -> str:
    """Markdown table without extra dependencies. Columns named like a share or change print as percent."""
    pct = {"mean", "p10", "median", "p90", "improved_share", "vkm_mean", "median_abs", "p95_abs", "max_abs",
           "d_tstt", "d_vkm", "d_two_way_share", "win", "confirm_mean", "confirm_p10", "confirm_p90", "confirm_win"}
    def cell(c, v):
        if isinstance(v, (float, np.floating)):
            if np.isnan(v):
                return ""
            if c in ("demand", "bonus", "scale"):
                return f"{v:g}"
            if c == "iterations":
                return f"{v:.0f}"
            if c in pct or c.endswith("_change") or c.startswith("observed_"):
                return f"{v:+.3%}" if c not in ("improved_share", "win", "confirm_win") else f"{v:.0%}"
            return f"{v:{floatfmt.lstrip('+')}}"
        return str(v)
    cols = list(df.columns)
    out = ["| " + " | ".join(map(str, cols)) + " |", "|" + "---|" * len(cols)]
    out += ["| " + " | ".join(cell(c, v) for c, v in zip(cols, r)) + " |" for r in df.itertuples(index=False)]
    return "\n".join(out)


def fmt_pct(x):
    return f"{x:+.2%}"


def complete(part: str, units: int) -> pd.DataFrame | None:
    """The raw results of a part if every unit has run, else None (the report then says so)."""
    f = RAW / f"{part}.csv"
    if not f.exists():
        return None
    df = pd.read_csv(f)
    n = df.groupby(KEY).ngroups
    if n < units:
        print(f"[report] {part}: {n} of {units} units have run; skipped until the part is complete")
        return None
    return df


def report(ctx):
    OUT.mkdir(parents=True, exist_ok=True)
    lines = ["# Final results (Task 3)", "",
             f"Built by `scripts/13_final_results.py report` from `outputs/final/raw/`. {ctx.n} demand scenarios, "
             f"UE gap {config.UE_GAP_SEARCH:g}, AM and PM peak, demand x" + ", x".join(f"{s:g}" for s in LEVELS) + ".",
             "Change = new / today - 1 in total system travel time (TSTT), per scenario; negative = faster. "
             "AM+PM adds the two peaks of the same scenario.", ""]
    thr = config.MIN_MEAN_IMPROVEMENT
    if complete("noise", len(LEVELS) * len(PEAKS) * (2 + len(NOISE_SEEDS))) is not None:
        nr, measured, tight = noise_report()
        nr.to_csv(OUT / "noise_floor.csv", index=False)
        lines += ["## 1. Noise floor", "",
                  f"Largest per-scenario difference between two solves of the same network at gap {config.UE_GAP_SEARCH:g} "
                  f"(edge order shuffled): **{measured:.4%}**; largest difference between gap {config.UE_GAP_SEARCH:g} and "
                  f"{NOISE_TIGHT_GAP:g}: **{tight:.4%}**. Detection threshold used below: **{thr:.2%}** "
                  "(config.MIN_MEAN_IMPROVEMENT), and a result also needs the same sign in at least "
                  f"{config.MIN_WIN_RATE:.0%} of scenarios.", "",
                  md(nr, ".5f"), ""]
    bt = complete("backtest", len(LEVELS) * len(PEAKS) * 2)
    if bt is not None:
        c = compare(bt, "before (2016)", thr)
        c["config"] = "two-way (today) vs one-way (2016)"
        c.to_csv(OUT / "backtest_tstt.csv", index=False)
        vol = []
        for (scale, cfgname), g in bt.groupby(["scale", "config"]):
            for st in STATIONS:
                both = g[f"{st}_ab"] + g[f"{st}_ba"]
                per = g.assign(v=both).groupby(["scenario", "peak"]).v.sum().unstack()
                vol.append(dict(demand=scale, config=cfgname, street=st, am=per.am.median(), pm=per.pm.median(),
                                am_plus_pm=(per.am + per.pm).median()))
        vol = pd.DataFrame(vol)
        piv = vol.pivot_table(index=["demand", "street"], columns="config", values=["am", "pm", "am_plus_pm"])
        ch = pd.DataFrame({f"{p}_change": piv[(p, "after (today)")] / piv[(p, "before (2016)")] - 1
                           for p in ("am", "pm", "am_plus_pm")}).reset_index()
        hist = pd.read_csv(ROOT / "data" / "reference" / "spring_cannon_history.csv", comment="#")
        h = hist.pivot(index="street", columns="year", values="aadt")
        obs = {k: {y: h.loc[v[3], y] / h.loc[v[3], 2016] - 1 for y in (2018, 2019, 2025)} for k, v in STATIONS.items()}
        for y in (2018, 2019, 2025):
            ch[f"observed_2016_to_{y}"] = ch.street.map(lambda s: obs[s][y])
        ch["sign_matches_all_years"] = [all(np.sign(r.am_plus_pm_change) == np.sign(r[f"observed_2016_to_{y}"])
                                            for y in (2018, 2019, 2025)) for _, r in ch.iterrows()]
        vol.to_csv(OUT / "backtest_station_volumes.csv", index=False)
        ch.to_csv(OUT / "backtest_volume_change.csv", index=False)
        lines += ["## 2. Back-test: Spring/Cannon two-way (today) vs one-way (2016)", "",
                  md(c.drop(columns="config"), "+.4f"), "",
                  f"Modeled two-way volume at the count stations (both directions, median over scenarios, vph; "
                  f"interior count K {count_k('am'):.3f} AM / {count_k('pm'):.3f} PM):", "",
                  md(vol, ".0f"), "",
                  "Modeled change vs observed SCDOT AADT change (conversion late 2017):", "",
                  md(ch, "+.3f"), ""]
    city = complete("city", len(BONUSES) * len(LEVELS) * len(PEAKS) * len(city_configs(ctx)))
    if city is not None:
        c = compare(city, "today", thr)
        c.to_csv(OUT / "city_question.csv", index=False)
        variants, blocked = city_variants(ctx.table, ctx.base_cfg)
        conv = pd.DataFrame([dict(variant=k, segments_converted=v[1]) for k, v in variants.items()])
        conv.to_csv(OUT / "city_converted_segments.csv", index=False)
        pd.DataFrame(blocked).to_csv(OUT / "city_blocked_segments.csv", index=False)
        lines += ["## 3. City question (two-way conversions) and the P5-2 Ashley move", "",
                  md(conv), "",
                  f"{len(blocked)} one-way segment(s) on these streets cannot go two-way (1 lane or frozen): "
                  "`city_blocked_segments.csv`.", ""]
        for peak in ("am+pm", "am", "pm"):
            t = c[c.peak == peak].drop(columns=["peak", "n"])
            lines += [f"**{peak.upper()}**", "", md(t, "+.4f"), ""]
    sts = search_states()
    if sts:
        by_cid = {c.cid: c for c in ctx.cors}
        summ, allmoves = [], []
        for s, st in sts.items():
            summ.append(dict(demand=s, rounds=st["round"], finished=st["done"],
                             accepted=" + ".join(f"{by_cid[c].name} [{c}] {m}" for c, m in st["accepted"]) or "none"))
            for k, v in st["screen"].items():
                r, cid, mode = k.split("|")
                allmoves.append(dict(demand=s, round=int(r), corridor=int(cid), name=by_cid[int(cid)].name, mode=mode,
                                     **{a: b for a, b in v.items() if a != "name"},
                                     **{f"confirm_{a}": b for a, b in st["confirm"].get(k, {}).items() if a not in ("name", "mode")}))
        am = pd.DataFrame(allmoves)
        am.to_csv(OUT / "search_moves.csv", index=False)
        pf = pd.concat([pareto_front(g[(g["round"] == 1) & (g.status == "ok")]).assign(demand=s)
                        for s, g in am.groupby("demand")])
        pf[["demand", "name", "corridor", "mode", "length_m", "d_tstt", "d_vkm", "d_two_way_share", "win"]].to_csv(
            OUT / "pareto_screening.csv", index=False)
        ok = am[am.status == "ok"]
        lines += ["## 4. Open search (09_search.py, AM+PM, 46 corridors)", "", md(pd.DataFrame(summ)), "",
                  "Screening (3 scenarios, gap 1e-3), round 1, all moves: " + "; ".join(
                      f"x{s:g}: {len(g)} evaluated, {(g.d_tstt < -thr).sum()} better than -{thr:.1%}, "
                      f"{(g.d_tstt.abs() <= thr).sum()} within +/-{thr:.1%}, {(g.d_tstt > thr).sum()} worse"
                      for s, g in ok[ok["round"] == 1].groupby("demand")), "",
                  "Confirmed on all scenarios (AM+PM; only moves better than "
                  f"-{config.SEARCH_SCREEN_MIN_IMPROVEMENT:.2%} in screening go to confirmation):", "",
                  (md(am.dropna(subset=["confirm_mean"])[["demand", "round", "name", "corridor", "mode", "confirm_mean", "confirm_p10",
                                                           "confirm_p90", "confirm_win", "confirm_accept"]], "+.4f")
                   if "confirm_mean" in am.columns and am.confirm_mean.notna().any() else "none at any demand level so far"), "",
                  "Pareto front of round-1 single moves (screening numbers; lower TSTT, lower veh-km, higher two-way share):", "",
                  md(pf[["demand", "name", "corridor", "mode", "d_tstt", "d_vkm", "d_two_way_share"]], "+.4f"), ""]
    par = complete("pareto", len(LEVELS) * len(PEAKS) * len(pareto_moves(ctx))) if len(search_states()) == len(LEVELS) else None
    dec = complete("decompose", len(DEMAND_VARIANTS) * len(city_configs(ctx)))
    if dec is not None and city is not None:
        rows = []
        stages = [(d, dec[dec.demand == d].assign(config=lambda x: x.layout), "am") for d in DEMAND_VARIANTS]
        fin = city[np.isclose(city.bonus, config.ONEWAY_CAPACITY_BONUS) & np.isclose(city.scale, 1.0)]
        stages += [("final (Task 2): measured K and split + fitted non-work", fin, pk) for pk in ("am", "pm", "am+pm")]
        for label, df, pk in stages:
            c = compare(df, "today", thr)
            c = c[c.peak == pk].assign(demand_model=label)
            rows.append(c)
        dc = pd.concat(rows)[["config", "demand_model", "peak", "mean", "p10", "median", "p90", "improved_share", "verdict"]]
        dc = dc.sort_values("config", kind="stable")
        dc.to_csv(OUT / "decompose_city.csv", index=False)
        lines += ["## 5. Why the city results moved since HANDOFF section 6 (bonus 1.1, demand x1.0)", "",
                  "Same layouts, same code, demand switched back one Task 2 change at a time. The first row of each block "
                  "reproduces the earlier P5 numbers.", "", md(dc, "+.4f"), ""]
    if par is not None:
        c = compare(par, "today", thr)
        c.to_csv(OUT / "pareto_confirmed.csv", index=False)
        lines += ["## 6. Pareto moves confirmed on all scenarios (AM+PM)", "",
                  md(c[c.peak == "am+pm"].drop(columns=["peak", "n", "bonus"]), "+.4f"), ""]
    (OUT / "RESULTS.md").write_text("\n".join(lines))
    print(f"wrote {OUT / 'RESULTS.md'} and the CSVs next to it")


def main() -> None:
    global OUT, RAW
    ap = argparse.ArgumentParser()
    ap.add_argument("part", choices=["noise", "backtest", "city", "pareto", "decompose", "report", "all"])
    ap.add_argument("--workers", type=int, default=0, help="processes for the scenarios (0 = this process only)")
    ap.add_argument("--time-budget", type=float, default=1e9, help="seconds; stop cleanly between units")
    ap.add_argument("--scenarios", type=int, default=config.N_SCENARIOS)
    ap.add_argument("--out-dir", type=Path, default=ROOT / "outputs" / "final", help="for smoke tests; the frozen results live in outputs/final")
    args = ap.parse_args()
    OUT, RAW = args.out_dir, args.out_dir / "raw"
    ctx = Ctx(args.scenarios, args.workers)
    budget = Budget(args.time_budget)
    parts = {"noise": part_noise, "backtest": part_backtest, "city": part_city, "pareto": part_pareto,
             "decompose": part_decompose}
    run = ["noise", "backtest", "city", "decompose"] if args.part == "all" else [args.part] if args.part in parts else []
    finished = all([parts[p](ctx, budget) for p in run]) if run else True
    if args.part in ("report", "all") and finished:
        report(ctx)


if __name__ == "__main__":
    main()
