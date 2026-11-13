"""Tests for scripts/16_sumo_seeds.py (Task 4b) that need no SUMO binaries. Toy junction maps, not Charleston."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("sumo_seeds", ROOT / "scripts" / "16_sumo_seeds.py")
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)


@pytest.fixture
def toy(monkeypatch, tmp_path):
    # node 3 and 4 are one junction in the "joined" networks (like Rutledge / all three)
    plain = SimpleNamespace(junction_of={1: "1", 2: "2", 3: "3", 4: "4"})
    joined = SimpleNamespace(junction_of={1: "1", 2: "2", 3: "c_3_4", 4: "c_3_4"})
    nets = {"today": plain, "Coming Street": plain, "all three": joined, "Rutledge Avenue": joined}
    od = {(1, 2): 300.0, (2, 3): 200.0, (4, 1): 100.0, (3, 4): 50.0}
    monkeypatch.setattr(m, "_cache", {"nets": nets})
    monkeypatch.setattr(m, "WORK", tmp_path)
    monkeypatch.setattr(m, "od_shared", lambda: {k: q for k, q in od.items() if k != (3, 4)})
    return nets


def test_trips_shared_and_checked(toy, tmp_path):
    man = m.make_trips(7, 1.0, keep=True)
    assert man["trips"] == man["vehicles"] > 0 and man["renamed_endpoints"] > 0
    d = m.trip_dir(7, 1.0)
    a, b = m.read_trips(d / "today.xml"), m.read_trips(d / "all_three.xml")
    assert [(i, t) for i, t, _, _ in a] == [(i, t) for i, t, _, _ in b]
    assert man["sha"]["today"] == man["sha"]["coming_street"] != man["sha"]["all_three"]


def test_check_catches_a_changed_trip(toy, tmp_path):
    m.make_trips(8, 1.0, keep=True)
    d = m.trip_dir(8, 1.0)
    p = d / "coming_street.xml"
    txt = p.read_text()
    p.write_text(txt.replace('fromJunction="1"', 'fromJunction="2"', 1))
    files = {n: d / f"{m.chk.slug(n)}.xml" for n in m.NET_NAMES}
    with pytest.raises(RuntimeError):
        m.check_same_trips(files)


def test_bootstrap_deterministic_and_covers_mean():
    d = np.random.default_rng(1).normal(0.01, 0.03, 40)
    lo, hi = m.boot_ci(d)
    assert (lo, hi) == m.boot_ci(d) and lo < d.mean() < hi
    assert hi - lo == pytest.approx(2 * 1.96 * d.std(ddof=1) / np.sqrt(40), rel=0.2)


def test_verdict_rule():
    r = lambda mean, lo, hi, static=-0.0015, grid=0: pd.Series(  # noqa: E731
        dict(mean=mean, ci_lo=lo, ci_hi=hi, static_am_mean=static, gridlock_runs=grid))
    assert m.verdict(r(-0.01, -0.02, -0.002), True).startswith("SUMO agrees")
    assert m.verdict(r(0.01, 0.002, 0.02), True).startswith("SUMO disagrees")
    assert m.verdict(r(-0.004, -0.007, -0.001), True).startswith("inconclusive")      # |mean| < 0.5%
    assert "rules out" in m.verdict(r(0.001, -0.004, 0.004), True)
    assert "rules out" not in m.verdict(r(0.001, -0.01, 0.01), True)
    assert m.verdict(r(-0.01, -0.02, -0.002), False).startswith("inconclusive (placebo")
    assert "UNRELIABLE" in m.verdict(r(-0.01, -0.02, -0.002, grid=3), True)
    assert "UNRELIABLE" not in m.verdict(r(-0.01, -0.02, -0.002, grid=2), True)
