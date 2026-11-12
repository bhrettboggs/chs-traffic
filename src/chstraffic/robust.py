"""Tier 2: judge configurations across many demand scenarios, not one guess.

A move is accepted only if it lowers MEAN total system travel time (TSTT) by
more than config.MIN_MEAN_IMPROVEMENT and wins in at least config.MIN_WIN_RATE
of the scenarios (HANDOFF 3b).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import networkx as nx
import numpy as np

from . import config
from .fast_assignment import Network, user_equilibrium
from .feasibility import apply_config, baseline_config, core_nodes, screen, _ff_times


@dataclass
class Evaluation:
    tstt_h: np.ndarray            # one per scenario
    unreachable: np.ndarray
    max_gap: float
    vkm: np.ndarray = None        # vehicle-km per scenario
    iterations: np.ndarray = None
    watched: np.ndarray = None    # [scenario, k] flow on the edges passed as `watch`


def _solve_chunk(net: Network, ods: list[dict], gap: float, length_km: np.ndarray, watch_idx: np.ndarray):
    out = []
    for od in ods:
        r = user_equilibrium(net, od, tol=gap)
        out.append((r.total_system_time_h, r.unreachable_demand, r.relative_gap, float(r.flow @ length_km),
                    r.iterations, r.flow[watch_idx].copy()))
    return out


_POOL = None


def _pool(workers: int):
    """One process pool per run, reused across evaluations (spawn start-up is slow on Windows)."""
    global _POOL
    if _POOL is None or _POOL._max_workers != workers:
        from concurrent.futures import ProcessPoolExecutor
        if _POOL is not None:
            _POOL.shutdown()
        _POOL = ProcessPoolExecutor(max_workers=workers)
    return _POOL


def evaluate(D_cfg: nx.DiGraph, ods: list[dict], gap: float = config.UE_GAP_SEARCH, workers: int = 0,
             watch: list[tuple] | None = None, net: Network | None = None) -> Evaluation:
    """Solve UE for every demand scenario. workers > 1 splits the scenarios over processes;
    the result is identical to workers = 0 (each scenario is solved the same way)."""
    net = net or Network(D_cfg)
    length_km = np.array([D_cfg.edges[e]["length_m"] for e in net.edges]) / 1000.0
    eidx = {e: k for k, e in enumerate(net.edges)}
    watch_idx = np.array([eidx.get(e, -1) for e in (watch or [])], dtype=np.int64)
    if workers and workers > 1 and len(ods) > 1:
        k = min(workers, len(ods))
        chunks = [ods[i::k] for i in range(k)]
        parts = list(_pool(workers).map(_solve_chunk, [net] * k, chunks, [gap] * k, [length_km] * k, [watch_idx] * k))
        res = [None] * len(ods)
        for i, part in enumerate(parts):
            for j, r in enumerate(part):
                res[i + j * k] = r
    else:
        res = _solve_chunk(net, ods, gap, length_km, watch_idx)
    w = np.array([r[5] for r in res]).reshape(len(res), len(watch_idx))
    if len(watch_idx):
        w[:, watch_idx < 0] = 0.0                      # an edge that doesn't exist in this config carries nothing
    return Evaluation(np.array([r[0] for r in res]), np.array([r[1] for r in res]), max(r[2] for r in res),
                      np.array([r[3] for r in res]), np.array([r[4] for r in res]), w)


def combine(evals: list[Evaluation]) -> Evaluation:
    """AM + PM: scenario i of each peak uses the same random draws (same seed), so add them per scenario."""
    return Evaluation(sum(e.tstt_h for e in evals), sum(e.unreachable for e in evals),
                      max(e.max_gap for e in evals), sum(e.vkm for e in evals))


@dataclass
class Score:
    win_rate: float
    mean_change: float            # fraction, negative = better
    worst_change: float           # largest (worst) fractional change over scenarios
    p10: float
    median: float
    p90: float

    def accept(self) -> bool:
        return self.mean_change < -config.MIN_MEAN_IMPROVEMENT and self.win_rate >= config.MIN_WIN_RATE


def score_config(base: Evaluation, new: Evaluation) -> Score:
    ch = new.tstt_h / base.tstt_h - 1.0
    # a scenario where the new layout strands demand is a loss, whatever TSTT says
    ch = np.where(new.unreachable > base.unreachable + 1e-6, np.inf, ch)
    finite = ch[np.isfinite(ch)]
    pct = np.percentile(finite, [10, 50, 90]) if finite.size else [np.inf] * 3
    return Score(win_rate=float(np.mean(ch < 0)),
                 mean_change=float(np.mean(ch)) if np.all(np.isfinite(ch)) else float("inf"),
                 worst_change=float(np.max(ch)), p10=float(pct[0]), median=float(pct[1]), p90=float(pct[2]))


@dataclass
class SearchLog:
    accepted: list = field(default_factory=list)     # (corridor name, mode, Score)
    tried: int = 0
    screened_out: int = 0
    seconds: float = 0.0


def greedy_corridor_search(D: nx.DiGraph, table: dict, cors: list, ods: list[dict],
                           max_moves: int = 20, verbose: bool = True):
    """Best-improvement greedy search over corridor states {two, fwd, rev}.

    Returns (best cfg, its Evaluation, baseline Evaluation, SearchLog). Each
    round tries every corridor in every alternative mode, keeps the one with the
    best mean change that passes Score.accept(), and stops when none does.
    """
    t_start = time.time()
    log = SearchLog()
    cfg = baseline_config(table)
    D_cur = apply_config(D, table, cfg)
    core = core_nodes(D_cur)
    od_pairs = sorted({k for od in ods for k in od}, key=str)
    base_t = _ff_times(D_cur, sorted({o for o, _ in od_pairs}, key=str), sorted({d for _, d in od_pairs}, key=str))
    base_eval = cur_eval = evaluate(D_cur, ods)

    for _ in range(max_moves):
        best = None
        for c in cors:
            for mode in ("two", "fwd", "rev"):
                part, blocked = c.config_for(table, mode)
                if blocked or all(cfg[s] == st for s, st in part.items()):
                    continue
                cand = {**cfg, **part}
                D_new = apply_config(D, table, cand)
                log.tried += 1
                sc = screen(D_cur, D_new, od_pairs, core=core, base_times=base_t)
                if not sc.ok:
                    log.screened_out += 1
                    continue
                ev = evaluate(D_new, ods)
                s = score_config(cur_eval, ev)
                if s.accept() and (best is None or s.mean_change < best[2].mean_change):
                    best = (c, mode, s, cand, ev)
        if best is None:
            break
        c, mode, s, cfg, cur_eval = best
        D_cur = apply_config(D, table, cfg)
        log.accepted.append((c.name, c.cid, mode, s))
        if verbose:
            print(f"  accept {c.name} [{c.cid}] -> {mode}: mean {s.mean_change:+.2%}, "
                  f"win {s.win_rate:.0%}, worst {s.worst_change:+.2%}")
    log.seconds = time.time() - t_start
    return cfg, cur_eval, base_eval, log
