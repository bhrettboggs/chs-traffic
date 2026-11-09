"""Static traffic assignment: user equilibrium via Frank-Wolfe with BPR costs.

This is the "simulate traffic" engine for the optimization loop: given a graph
and an origin-destination (OD) demand table, find the flow on every directed
edge when no driver can lower their own travel time by switching routes
(Wardrop's first principle). It is fast enough to run thousands of times inside
a search over one-way/two-way configurations. Use a microsimulator (SUMO) only
to sanity-check the final winners.
"""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx

from . import config


def bpr_time(fftt: float, flow: float, cap: float,
             alpha: float = config.BPR_ALPHA, beta: float = config.BPR_BETA) -> float:
    return fftt * (1.0 + alpha * (flow / cap) ** beta)


@dataclass
class AssignmentResult:
    flows: dict[tuple, float]          # (u, v) -> vehicles/hour
    times: dict[tuple, float]          # (u, v) -> seconds at equilibrium
    total_system_time_h: float         # sum(flow * time) in vehicle-hours
    relative_gap: float
    iterations: int
    unreachable_demand: float          # demand with no path (vph)


def _all_or_nothing(D, od, weight_by_edge):
    aux = {e: 0.0 for e in D.edges()}
    unreachable = 0.0
    by_origin: dict = {}
    for (o, d), q in od.items():
        if q > 0:
            by_origin.setdefault(o, []).append((d, q))
    for o, dests in by_origin.items():
        _, paths = nx.single_source_dijkstra(
            D, o, weight=lambda u, v, _d: weight_by_edge[(u, v)])
        for d, q in dests:
            path = paths.get(d)
            if path is None:
                unreachable += q
                continue
            for u, v in zip(path[:-1], path[1:]):
                aux[(u, v)] += q
    return aux, unreachable


def user_equilibrium(D: nx.DiGraph, od: dict[tuple, float], max_iter: int = 100,
                     tol: float = 1e-4, alpha: float = config.BPR_ALPHA,
                     beta: float = config.BPR_BETA) -> AssignmentResult:
    """Frank-Wolfe UE assignment.

    od: {(origin_node, destination_node): vehicles per hour}
    Edges need ``fftt_s`` (seconds) and ``capacity_vph``.
    """
    E = list(D.edges())
    t0 = {e: D.edges[e]["fftt_s"] for e in E}
    cap = {e: D.edges[e]["capacity_vph"] for e in E}

    x, unreachable = _all_or_nothing(D, od, t0)
    gap, it = float("inf"), 0
    for it in range(1, max_iter + 1):
        t = {e: bpr_time(t0[e], x[e], cap[e], alpha, beta) for e in E}
        y, _ = _all_or_nothing(D, od, t)
        tstt = sum(x[e] * t[e] for e in E)
        sptt = sum(y[e] * t[e] for e in E)
        gap = (tstt - sptt) / tstt if tstt > 0 else 0.0
        if gap < tol:
            break
        # bisection line search on the Beckmann objective derivative
        lo, hi = 0.0, 1.0
        for _ in range(30):
            mid = (lo + hi) / 2
            deriv = sum((y[e] - x[e]) * bpr_time(
                t0[e], x[e] + mid * (y[e] - x[e]), cap[e], alpha, beta) for e in E)
            if deriv > 0:
                hi = mid
            else:
                lo = mid
        step = (lo + hi) / 2
        x = {e: x[e] + step * (y[e] - x[e]) for e in E}

    t = {e: bpr_time(t0[e], x[e], cap[e], alpha, beta) for e in E}
    return AssignmentResult(
        flows=x, times=t,
        total_system_time_h=sum(x[e] * t[e] for e in E) / 3600.0,
        relative_gap=gap, iterations=it, unreachable_demand=unreachable,
    )
