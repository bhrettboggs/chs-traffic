"""Fast static user-equilibrium assignment: Conjugate Frank-Wolfe (CFW).

Same model as ``assignment.user_equilibrium`` (BPR link costs, Wardrop UE) but
vectorized with numpy and ``scipy.sparse.csgraph.dijkstra``. The search calls
this thousands of times; ``assignment.py`` stays as the readable reference and
a test checks the two agree.

CFW (Mitradjieva & Lindberg 2013) replaces the plain Frank-Wolfe direction with
one that is conjugate to the previous direction under the (diagonal) Hessian of
the Beckmann objective. It converges to tight gaps much faster than plain FW.
"""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

from . import config

# Cap on the conjugacy weight. Near 1 the direction stops moving and CFW stalls
# (seen at gap ~4e-4 on the toy grid with a 1 - 1e-6 cap).
CFW_MAX_ALPHA = 0.99


@dataclass
class FastResult:
    edges: list[tuple]                 # edge order used by the arrays below
    flow: np.ndarray                   # vph per edge
    time: np.ndarray                   # seconds per edge at equilibrium
    total_system_time_h: float
    relative_gap: float
    iterations: int
    unreachable_demand: float

    @property
    def flows(self) -> dict[tuple, float]:
        return dict(zip(self.edges, self.flow.tolist()))

    @property
    def times(self) -> dict[tuple, float]:
        return dict(zip(self.edges, self.time.tolist()))


class Network:
    """Array form of a DiGraph, built once and reused across solves."""

    def __init__(self, D: nx.DiGraph):
        self.nodes = list(D.nodes())
        self.index = {n: i for i, n in enumerate(self.nodes)}
        self.edges = list(D.edges())
        self.u = np.array([self.index[a] for a, _ in self.edges], dtype=np.int64)
        self.v = np.array([self.index[b] for _, b in self.edges], dtype=np.int64)
        self.t0 = np.array([D.edges[e]["fftt_s"] for e in self.edges], dtype=float)
        self.cap = np.array([D.edges[e]["capacity_vph"] for e in self.edges], dtype=float)
        self.n = len(self.nodes)
        # (u, v) -> edge index, as a dense lookup keyed u * n + v
        self._eid = {int(a) * self.n + int(b): k for k, (a, b) in enumerate(zip(self.u, self.v))}
        self.eid_dense = np.full(self.n * self.n, -1, dtype=np.int64)
        self.eid_dense[self.u * self.n + self.v] = np.arange(len(self.edges))
        # CSR layout built once; each shortest-path call only refills the data array
        order = np.lexsort((self.v, self.u))
        self._csr_order = order
        self._W = csr_matrix((np.ones(len(order)), (self.u[order], self.v[order])), shape=(self.n, self.n))
        self._W.sort_indices()

    # The two edge lookups are n*n / per-edge tables (~10 MB on the peninsula). Leave them out when a
    # Network is pickled to a worker process and rebuild them there (WinError 1450 with 15 workers).
    def __getstate__(self):
        return {k: v for k, v in self.__dict__.items() if k not in ("eid_dense", "_eid")}

    def __setstate__(self, state):
        self.__dict__.update(state)
        self._eid = {int(a) * self.n + int(b): k for k, (a, b) in enumerate(zip(self.u, self.v))}
        self.eid_dense = np.full(self.n * self.n, -1, dtype=np.int64)
        self.eid_dense[self.u * self.n + self.v] = np.arange(len(self.edges))

    def weights(self, w: np.ndarray) -> csr_matrix:
        self._W.data = np.maximum(w[self._csr_order], 1e-9)
        return self._W

    def edge_id(self, a: int, b: int) -> int:
        return self._eid[a * self.n + b]


def _bpr(t0, x, cap, a, b):
    return t0 * (1.0 + a * (x / cap) ** b)


def _bpr_deriv(t0, x, cap, a, b):
    return t0 * a * b * (x / cap) ** (b - 1.0) / cap


def _line_search(t0, x, d, cap, a, b, tol=1e-10):
    """Minimize the Beckmann objective on x + lam*d, lam in [0, 1]:
    safeguarded Newton on g(lam) = d . t(x + lam d), which is increasing."""
    g1 = float(d @ _bpr(t0, x + d, cap, a, b))
    if g1 <= 0:
        return 1.0
    lo, hi, lam = 0.0, 1.0, 0.5
    for _ in range(30):
        xl = x + lam * d
        g = float(d @ _bpr(t0, xl, cap, a, b))
        if abs(g) < tol * (1.0 + abs(g1)):
            break
        if g > 0:
            hi = lam
        else:
            lo = lam
        gp = float((d * d) @ _bpr_deriv(t0, xl, cap, a, b))
        nxt = lam - g / gp if gp > 0 else 0.5 * (lo + hi)
        if not (lo < nxt < hi):
            nxt = 0.5 * (lo + hi)
        if hi - lo < 1e-12:
            break
        lam = nxt
    return lam


def _group_od(net: Network, od: dict[tuple, float]):
    """origins (node indices) and a dense demand matrix Q[origin row, dest node]."""
    by_o: dict[int, dict[int, float]] = {}
    for (o, d), q in od.items():
        if q > 0 and o != d:
            row = by_o.setdefault(net.index[o], {})
            row[net.index[d]] = row.get(net.index[d], 0.0) + float(q)
    origins = np.array(sorted(by_o), dtype=np.int64)
    Q = np.zeros((len(origins), net.n))
    for r, o in enumerate(origins):
        dd = by_o[int(o)]
        Q[r, list(dd)] = list(dd.values())
    return origins, Q


def _aon(net: Network, w: np.ndarray, origins, Q):
    """All-or-nothing loading on shortest paths for weights w (seconds).

    All origins at once: visit nodes from the farthest to the nearest and hand
    each node's accumulated demand to its predecessor. A predecessor is always
    strictly nearer (weights > 0), so one pass over the distance order is enough.
    """
    if len(origins) == 0:
        return np.zeros(len(net.edges)), 0.0
    dist, pred = dijkstra(net.weights(w), directed=True, indices=origins, return_predecessors=True)
    reach = np.isfinite(dist)
    unreachable = float(Q[~reach].sum())
    R, n = Q.shape
    acc = np.zeros((R, n + 1))            # extra column n: bin for "no predecessor"
    acc[:, :n] = np.where(reach, Q, 0.0)
    flat = acc.reshape(-1)
    order = np.argsort(np.where(reach, dist, -1.0), axis=1, kind="stable")   # unreachable first
    base = (np.arange(R) * (n + 1))[:, None]
    parent = np.where(pred >= 0, pred, n)
    iv = np.ascontiguousarray((base + order).T)                                   # [col, row] flat index of node
    ip = np.ascontiguousarray((base + np.take_along_axis(parent, order, axis=1)).T)  # ... of its predecessor
    for col in range(n - 1, 0, -1):       # within a column every row is a different origin: no clashes
        flat[ip[col]] += flat[iv[col]]
    r, v = np.nonzero(pred >= 0)
    y = np.bincount(net.eid_dense[pred[r, v] * n + v], weights=acc[r, v], minlength=len(net.edges))
    return y, unreachable


def user_equilibrium(D_or_net, od: dict[tuple, float], tol: float = config.UE_GAP_SEARCH,
                     max_iter: int = config.UE_MAX_ITER, alpha: float = config.BPR_ALPHA,
                     beta: float = config.BPR_BETA) -> FastResult:
    net = D_or_net if isinstance(D_or_net, Network) else Network(D_or_net)
    origins, Q = _group_od(net, od)
    t0, cap = net.t0, net.cap

    x, unreachable = _aon(net, t0, origins, Q)
    s_prev = None
    gap, it = float("inf"), 0
    for it in range(1, max_iter + 1):
        t = _bpr(t0, x, cap, alpha, beta)
        y, _ = _aon(net, t, origins, Q)
        tstt = float(x @ t)
        gap = (tstt - float(y @ t)) / tstt if tstt > 0 else 0.0
        if gap < tol:
            break
        # conjugate direction
        if s_prev is None:
            s = y
        else:
            h = _bpr_deriv(t0, x, cap, alpha, beta)
            num = float(((s_prev - x) * h) @ (y - x))
            den = float(((s_prev - x) * h) @ (y - s_prev))
            a_k = num / den if den != 0 else 0.0
            a_k = min(max(a_k, 0.0), CFW_MAX_ALPHA)
            s = a_k * s_prev + (1.0 - a_k) * y
            if float((s - x) @ t) >= 0:   # not a descent direction: plain FW step
                s = y
        dvec = s - x
        lam = _line_search(t0, x, dvec, cap, alpha, beta)
        x = x + lam * dvec
        s_prev = s

    t = _bpr(t0, x, cap, alpha, beta)
    return FastResult(edges=net.edges, flow=x, time=t,
                      total_system_time_h=float(x @ t) / 3600.0, relative_gap=gap,
                      iterations=it, unreachable_demand=unreachable)
