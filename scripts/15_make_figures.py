"""All figures for the write-up (README.md, docs/RESULTS.md), in one script.

    py -3.11 scripts\\15_make_figures.py            (Windows)
    python scripts/15_make_figures.py               (Linux/macOS)

Writes docs/figures/*.png. Reads only frozen results and reference data; it never reruns a model:

* outputs/final/raw/city.csv, decompose.csv          static results (Task 3), per scenario
* outputs/final/task2_screenlines/*.csv             screenlines before/after Task 2 (04_calibrate.py output)
* outputs/final/sumo/seeds40_summary.csv, seeds40_where.csv   SUMO, 40 paired seeds (Task 4b)
* data/processed/chs_digraph.gpickle + segment_widths.csv     the network, for the two maps
  (built by scripts/02_build_graph.py and scripts/05_join_widths.py, as in scripts/run_final.cmd)

Every number drawn is computed here from those files, so a figure can't drift from the tables.
"""
from __future__ import annotations

import pickle
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from chstraffic import config, feasibility, widths  # noqa: E402
from chstraffic.variants import CITY_STREETS, city_variants  # noqa: E402

FINAL = ROOT / "outputs" / "final"
OUT = ROOT / "docs" / "figures"

# Colors: a fixed categorical order (blue, orange, aqua), recessive grays for context, text in ink colors.
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, GRID, CONTEXT, BAND = "#0b0b0b", "#52514e", "#e4e3df", "#c9c8c3", "#f0efec"
FREEWAY = {"motorway", "motorway_link", "trunk", "trunk_link"}
VARIANTS = ["Coming Street", "Rutledge Avenue", "Ashley Avenue", "all three"]
SHORT = {"Coming Street": "Coming", "Rutledge Avenue": "Rutledge", "Ashley Avenue": "Ashley",
         "all three": "all three", "today (other sim seed)": "placebo\n(today vs today,\nother sim seed)"}

plt.rcParams.update({
    "font.size": 10, "axes.edgecolor": CONTEXT, "axes.labelcolor": INK2, "xtick.color": INK2,
    "ytick.color": INK2, "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlecolor": INK,
    "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False,
    "figure.facecolor": "white", "savefig.facecolor": "white",
})


def save(fig, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / name, dpi=170, bbox_inches="tight")
    plt.close(fig)
    print(f"  {name}")


def note(fig, text: str, ax=None) -> None:
    if ax is not None:   # maps: anchor under the map itself (equal-aspect axes leave figure margins)
        ax.text(0.0, 0.0, text, transform=ax.transAxes, ha="left", va="top", fontsize=8, color=INK2, wrap=True)
    else:
        fig.text(0.01, -0.01, text, ha="left", va="top", fontsize=8, color=INK2, wrap=True)


# ------------------------------------------------------------------ static results from raw rows
def changes(raw: pd.DataFrame, config_name: str, peak: str, scale: float, bonus: float = 1.1,
            base: str = "today") -> pd.Series:
    """Per-scenario change new/today - 1 in TSTT; peak 'am+pm' adds the two peaks of a scenario."""
    sel = raw[(raw.scale == scale) & (raw.bonus == bonus)]
    peaks = ["am", "pm"] if peak == "am+pm" else [peak]
    sel = sel[sel.peak.isin(peaks)]
    v = sel[sel.config == config_name].groupby("scenario").tstt_h.sum()
    t = sel[sel.config == base].groupby("scenario").tstt_h.sum()
    return (v / t - 1).dropna()


def summary(d: pd.Series) -> tuple[float, float, float]:
    return float(d.mean()), float(np.percentile(d, 10)), float(np.percentile(d, 90))


# ------------------------------------------------------------------ network and maps
def load_network():
    proc = ROOT / "data" / "processed"
    if not (proc / "chs_digraph.gpickle").exists():
        sys.exit("data/processed/chs_digraph.gpickle missing: run scripts/02_build_graph.py and "
                 "scripts/05_join_widths.py first (scripts/run_final.cmd does both)")
    D = pickle.loads((proc / "chs_digraph.gpickle").read_bytes())
    table = feasibility.segment_table(D, feasibility.load_overrides(ROOT / "data" / "reference" / "overrides.csv"),
                                      widths.load(proc / "segment_widths.csv"))
    return D, table


def seg_xy(D, seg):
    """Coordinates of a segment, drawn in its travel direction for one-way segments."""
    u, v = (seg.a, seg.b) if seg.state in ("two", "ab") else (seg.b, seg.a)
    d = D.edges[u, v] if D.has_edge(u, v) else D.edges[v, u]
    geom = d.get("geometry")
    if geom is not None:
        xs, ys = list(geom.xy[0]), list(geom.xy[1])
        if D.has_edge(v, u) and not D.has_edge(u, v):
            xs, ys = xs[::-1], ys[::-1]
    else:
        xs, ys = [D.nodes[u]["x"], D.nodes[v]["x"]], [D.nodes[u]["y"], D.nodes[v]["y"]]
    return xs, ys


def map_axes(figsize=(7.2, 7.6)):
    fig, ax = plt.subplots(figsize=figsize)
    ax.set_aspect(1 / np.cos(np.radians(32.79)))
    ax.set_axis_off()
    return fig, ax


def arrow(ax, xs, ys, color):
    if len(xs) < 2:
        return
    i = max(1, len(xs) // 2)
    x0, y0, x1, y1 = xs[i - 1], ys[i - 1], xs[i], ys[i]
    if (x0, y0) != (x1, y1):
        ax.annotate("", xy=(x1, y1), xytext=(x0, y0), zorder=3,
                    arrowprops=dict(arrowstyle="-|>", color=color, lw=0.7, mutation_scale=6))


def fig_network(D, table) -> None:
    fig, ax = map_axes()
    n = {"freeway": 0, "two-way": 0, "one-way": 0}
    for seg in table.values():
        xs, ys = seg_xy(D, seg)
        kind = "freeway" if seg.highway in FREEWAY else ("two-way" if seg.state == "two" else "one-way")
        n[kind] += 1
        color, lw = {"freeway": (CONTEXT, 2.0), "two-way": (BLUE, 0.9), "one-way": (ORANGE, 1.3)}[kind]
        ax.plot(xs, ys, color=color, lw=lw, solid_capstyle="round", zorder=1 if kind == "freeway" else 2)
        if kind == "one-way":
            arrow(ax, xs, ys, ORANGE)
    ax.set_title("Charleston peninsula: the modeled street network today", loc="left")
    ax.legend(handles=[Line2D([], [], color=BLUE, lw=2, label=f"two-way ({n['two-way']} segments)"),
                       Line2D([], [], color=ORANGE, lw=2, label=f"one-way, arrow = direction ({n['one-way']}, freeways not counted)"),
                       Line2D([], [], color=CONTEXT, lw=3, label=f"freeway / ramps, fixed ({n['freeway']})")],
              loc="upper left", fontsize=9)
    note(fig, "OpenStreetMap (2026-11-09 snapshot, (c) OpenStreetMap contributors, ODbL) with the direction "
              "fix in data/reference/overrides.csv. One segment = one street between two intersections.", ax)
    save(fig, "fig1_network.png")


def fig_converted(D, table) -> None:
    base_cfg = feasibility.baseline_config(table)
    variants, blocked = city_variants(table, base_cfg)
    all_cfg = variants["all three"][0]
    colors = dict(zip(CITY_STREETS, [BLUE, ORANGE, AQUA]))
    fig, ax = map_axes()
    counts = {s: 0 for s in CITY_STREETS}
    label_at = {s: [] for s in CITY_STREETS}
    for sid, seg in table.items():
        xs, ys = seg_xy(D, seg)
        if seg.name in colors and all_cfg.get(sid) == "two" and seg.state != "two":
            counts[seg.name] += 1
            label_at[seg.name].append((np.mean(xs), np.mean(ys)))
            ax.plot(xs, ys, color=colors[seg.name], lw=3.0, solid_capstyle="round", zorder=3)
        else:
            ax.plot(xs, ys, color=CONTEXT, lw=0.6 if seg.highway not in FREEWAY else 1.4, zorder=1)
    for b in blocked:
        p, q = D.nodes[b["a"]], D.nodes[b["b"]]
        ax.plot([(p["x"] + q["x"]) / 2], [(p["y"] + q["y"]) / 2], marker="x", color=INK, ms=6, mew=1.4, zorder=4)
    for s, pts in label_at.items():   # direct labels, placed by hand so they don't collide
        main = [p for p in pts if 32.78 < p[1] < 32.80]   # the long middle stretch (skips the stub pieces)
        if not main:
            continue
        if s.startswith("Rutledge"):
            (x, y), dx, ha = min(main, key=lambda t: t[1]), 8, "left"
        else:
            (x, y), dx, ha = max(main, key=lambda t: t[1]), (-6 if s.startswith("Ashley") else 6), \
                ("right" if s.startswith("Ashley") else "left")
        ax.annotate(s.split()[0], (x, y), xytext=(dx, 0), textcoords="offset points", ha=ha, va="center",
                    fontsize=10, color=INK, fontweight="bold", zorder=5)
    handles = [Line2D([], [], color=colors[s], lw=3, label=f"{s}: {counts[s]} one-way segments made two-way")
               for s in CITY_STREETS]
    handles.append(Line2D([], [], color=INK, marker="x", lw=0, label=f"{len(blocked)} short divided-road pieces that stay one-way"))
    ax.legend(handles=handles, loc="upper left", fontsize=9)
    ax.set_title("The city's question: the three streets the model converts", loc="left")
    note(fig, "Every one-way piece of each street with at least 2 lanes of pavement becomes one lane each way "
              "(src/chstraffic/variants.py). That reaches past the city's study limits (Coming: Calhoun to Race; Rutledge and "
              "Ashley: Calhoun to the Crosstown): Coming south to Beaufain, Rutledge and Ashley north of the Crosstown "
              "and one block at Broad St.", ax)
    save(fig, "fig5_converted_streets.png")


# ------------------------------------------------------------------ charts
def fig_screenlines() -> None:
    d = FINAL / "task2_screenlines"
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.4), sharey=True)
    for ax, peak in zip(axes, ["am", "pm"]):
        before = pd.read_csv(d / f"guess_nonwork0_{peak}.csv")
        after = pd.read_csv(d / f"final_{peak}.csv")
        x = np.arange(len(after))
        for i, r in after.iterrows():
            ax.add_patch(plt.Rectangle((i - 0.38, -r.tolerance * 100), 0.76, 2 * r.tolerance * 100,
                                       color=BAND, zorder=0, lw=0))
        for df, dx, color, label in [(before, -0.13, ORANGE, "before Task 2 (guessed peak factors, no non-work trips)"),
                                     (after, 0.13, BLUE, "after Task 2 (measured peak factors, fitted non-work trips)")]:
            y = (df.model / df.count_peak - 1) * 100
            lo, hi = (df.p10 / df.count_peak - 1) * 100, (df.p90 / df.count_peak - 1) * 100
            ax.vlines(x + dx, lo, hi, color=color, lw=2, zorder=2)
            ax.plot(x + dx, y, "o", color=color, ms=7, mec="white", mew=1.2, zorder=3, label=label)
        ax.axhline(0, color=INK2, lw=0.8, zorder=1)
        npass_b, npass_a = int(before.passes.sum()), int(after.passes.sum())
        ax.set_title(f"{peak.upper()} peak: pass {npass_b}/6 before, {npass_a}/6 after", loc="left", fontsize=11)
        ax.set_xticks(x, after.screenline)
        ax.grid(axis="y", color=GRID, lw=0.6)
        ax.set_axisbelow(True)
    axes[0].set_ylabel("model vs count, % (median, p10 to p90 of 10 scenarios)")
    h, l = axes[0].get_legend_handles_labels()
    h.append(Patch(color=BAND, label="allowed deviation (FHWA screenline curve)"))
    fig.legend(handles=h, loc="upper center", bbox_to_anchor=(0.5, 0.0), ncol=2, fontsize=9)
    fig.text(0.01, -0.14, "A screenline sums the counted streets that cross one imaginary line. Counts = SCDOT 2025 AADT x "
              "peak-hour factor (the factor changed in Task 2, so the count side moved too). Line A is the upper "
              "peninsula; B the Line-Spring band (Rutledge/MUSC). outputs/final/task2_screenlines/.",
             ha="left", va="top", fontsize=8, color=INK2, wrap=True)
    fig.suptitle("Screenline check: modeled vs counted traffic across six lines", x=0.01, ha="left",
                 fontweight="bold", color=INK)
    fig.tight_layout()
    save(fig, "fig2_screenlines.png")


def fig_city_question() -> None:
    raw = pd.read_csv(FINAL / "raw" / "city.csv")
    levels = list(config.SENSITIVITY_DEMAND_LEVELS)
    fig, ax = plt.subplots(figsize=(8.6, 4.6))
    ax.axhspan(-config.MIN_MEAN_IMPROVEMENT * 100, config.MIN_MEAN_IMPROVEMENT * 100, color=BAND, zorder=0, lw=0)
    shades = [BLUE, ORANGE, AQUA]
    sel = raw[(raw.scale == 1.0) & (raw.bonus == 1.1)]
    tot = sel.groupby(["config", "scenario"]).tstt_h.sum()
    coming_vh = float((tot["today"] - tot["Coming Street"]).mean())
    for j, lvl in enumerate(levels):
        for i, v in enumerate(VARIANTS):
            m, lo, hi = (100 * t for t in summary(changes(raw, v, "am+pm", lvl)))
            x = i + (j - 1) * 0.22
            ax.vlines(x, lo, hi, color=shades[j], lw=2, zorder=2)
            ax.plot(x, m, "o", color=shades[j], ms=7, mec="white", mew=1.2, zorder=3,
                    label=f"demand x{lvl:g}" if i == 0 else None)
            ax.annotate(f"{m:+.2f}", (x, m), xytext=(5, 0), textcoords="offset points", ha="left",
                        va="center", fontsize=7.5, color=INK2)
    ax.axhline(0, color=INK2, lw=0.8)
    ax.set_xticks(range(len(VARIANTS)), ["Coming", "Rutledge", "Ashley", "all three"])
    ax.set_ylabel("change in total travel time, AM+PM, %")
    ax.grid(axis="y", color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    ax.set_title("Static model: converting the city's three streets to two-way", loc="left")
    h, _ = ax.get_legend_handles_labels()
    h.append(Patch(color=BAND, label="+/-0.1%: too small to call"))
    ax.legend(handles=h, loc="upper left", fontsize=9, ncol=4)
    ax.set_ylim(-0.32, 0.72)
    note(fig, "Dot = mean over 20 demand scenarios, whisker = p10 to p90. Negative = faster. Bonus 1.1 for one-way "
              "capacity. Detectable still means small: Coming's -0.13% at x1.0 is about "
              f"{coming_vh:.1f} vehicle-hours over the two peak hours combined. outputs/final/raw/city.csv.")
    save(fig, "fig3_city_question.png")


def fig_ashley_bridge() -> None:
    dec = pd.read_csv(FINAL / "raw" / "decompose.csv")
    city = pd.read_csv(FINAL / "raw" / "city.csv")
    name = "Ashley Calhoun-Crosstown"
    steps = []
    for model, label in [("old: K .09, split .60, no non-work", "AM, first model\n(guessed 60/40 split,\nK 0.09)"),
                         ("measured K and split, no non-work", "AM, measured\npeak factors"),
                         ]:
        steps.append((label, changes(dec, f"{name} | {model}", "am", 1.0, base=f"today | {model}")))
    # the final demand model is the one in city.csv (decompose.csv holds only the two earlier models)
    steps.append(("AM, + non-work\ntrips (final)", changes(city, name, "am", 1.0)))
    steps.append(("PM, final", changes(city, name, "pm", 1.0)))
    steps.append(("AM+PM, final\n(the result)", changes(city, name, "am+pm", 1.0)))
    fig, ax = plt.subplots(figsize=(9, 4.6))
    ax.axhspan(-config.MIN_MEAN_IMPROVEMENT * 100, config.MIN_MEAN_IMPROVEMENT * 100, color=BAND, zorder=0, lw=0)
    prev = None
    for i, (label, d) in enumerate(steps):
        m, lo, hi = (100 * t for t in summary(d))
        color = ORANGE if i < 3 else (BLUE if i == 4 else INK2)
        ax.bar(i, m, width=0.55, color=color, zorder=2)
        ax.vlines(i, lo, hi, color=INK, lw=1, zorder=3)
        ax.annotate(f"{m:+.3f}%", (i, hi if m >= 0 else lo), xytext=(0, 4 if m >= 0 else -12),
                    textcoords="offset points", ha="center", fontsize=9, color=INK)
        if prev is not None and i < 3:
            ax.annotate("", xy=(i - 0.3, m), xytext=(i - 0.7, prev),
                        arrowprops=dict(arrowstyle="->", color=INK2, lw=0.8))
        prev = m
    ax.axhline(0, color=INK2, lw=0.8)
    ax.axvline(2.5, color=CONTEXT, lw=0.8, ls=":")
    ax.set_ylim(-0.52, 0.32)
    ax.set_xticks(range(len(steps)), [s[0] for s in steps], fontsize=8.5)
    ax.set_ylabel("change in total travel time, %")
    ax.grid(axis="y", color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    ax.set_title("How an early 'win' disappeared: Ashley Ave two-way, Calhoun to the Crosstown", loc="left")
    note(fig, "Same street change, same code; only the demand changes from bar to bar (demand x1.0, bonus 1.1, "
              "20 scenarios, whisker p10 to p90). The AM+PM bar is not a sum: it is the change in the two peaks' "
              "combined travel time. Shaded band: +/-0.1%. outputs/final/raw/decompose.csv, city.csv.")
    save(fig, "fig4_ashley_reversal.png")


def fig_static_vs_sumo() -> None:
    s = pd.read_csv(FINAL / "sumo" / "seeds40_summary.csv").set_index("variant")
    order = ["Coming Street", "Rutledge Avenue", "all three", "today (other sim seed)"]
    fig, ax = plt.subplots(figsize=(9, 4.8))
    for i, v in enumerate(order):
        r = s.loc[v]
        ax.vlines(i - 0.12, 100 * r.ci_lo, 100 * r.ci_hi, color=BLUE, lw=2.2, zorder=2)
        flagged = r.gridlock_runs > 2 and v != "today (other sim seed)"
        ax.plot(i - 0.12, 100 * r["mean"], "o", ms=8, zorder=3, color=BLUE, mec="white", mew=1.2)
        ax.plot(i + 0.02, 100 * r.sec_mean, "o", ms=6, zorder=3, mfc="white", mec=BLUE, mew=1.4)
        ax.annotate(f"{100 * r['mean']:+.2f}%\n({100 * r.ci_lo:+.1f} to {100 * r.ci_hi:+.1f})",
                    (i - 0.12, 100 * r.ci_hi), xytext=(0, 4), textcoords="offset points", ha="center",
                    fontsize=8, color=INK)
        if flagged:
            ax.annotate(f"flag: {int(r.gridlock_runs)} of 40 runs\ngridlock-affected\n"
                        f"({100 * r.sec_mean:+.1f}% without\ngridlock seeds)",
                        (i - 0.12, 100 * r.ci_lo), xytext=(0, -8), textcoords="offset points", ha="center",
                        va="top", fontsize=7.5, color=INK2)
        if pd.notna(r.static_am_mean):
            ax.vlines(i + 0.16, 100 * r.static_am_p10, 100 * r.static_am_p90, color=ORANGE, lw=2.2, zorder=2)
            ax.plot(i + 0.16, 100 * r.static_am_mean, "D", ms=6, color=ORANGE, mec="white", mew=1, zorder=3)
            ax.annotate(f"{100 * r.static_am_mean:+.2f}%", (i + 0.16, 100 * r.static_am_mean), xytext=(6, -3),
                        textcoords="offset points", fontsize=8, color=INK2)
    ax.axhline(0, color=INK2, lw=0.8)
    ax.set_xticks(range(len(order)), [SHORT[v] for v in order])
    ax.set_ylabel("change in AM total travel time, %")
    ax.set_ylim(-5.5, 8.2)
    ax.grid(axis="y", color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    ax.set_title("Static model vs signal-level simulation (SUMO), AM peak, demand x1.0", loc="left")
    ax.legend(handles=[
        Line2D([], [], color=BLUE, marker="o", lw=2, label="SUMO: mean of 40 paired seeds, 95% interval"),
        Line2D([], [], color=BLUE, marker="o", mfc="white", lw=0, label="SUMO: mean without the 10 gridlock seeds"),
        Line2D([], [], color=ORANGE, marker="D", lw=2, label="static model: mean, p10 to p90 of 20 scenarios")],
        loc="upper left", fontsize=8.5)
    note(fig, "SUMO uses netconvert's generic signal programs, rebuilt at every signal a conversion touches; a real "
              "conversion would retime them. Read SUMO as relative changes on Charleston's geometry, not as "
              "Charleston's delay. Gridlock flag: more than 2 of 40 runs gridlock-affected, rule fixed before the "
              "runs (docs/task4b_plan.md). outputs/final/sumo/seeds40_summary.csv.")
    save(fig, "fig6_static_vs_sumo.png")


def fig_where() -> None:
    w = pd.read_csv(FINAL / "sumo" / "seeds40_where.csv")
    w = w[w.variant == "all three"]
    clean = w[~w.gridlock_today & ~w.gridlock_variant]
    parts = [("loss_street_h", "the three streets"), ("loss_approaches_h", "cross-street approaches\nto their junctions"),
             ("loss_elsewhere_h", "everywhere else")]
    fig, ax = plt.subplots(figsize=(8, 4.2))
    x = np.arange(len(parts))
    for df, dx, color, label in [(w, -0.19, BLUE, f"all {len(w)} seeds"), (clean, 0.19, AQUA, f"{len(clean)} seeds without gridlock")]:
        vals = [df[c].mean() for c, _ in parts]
        ax.bar(x + dx, vals, width=0.36, color=color, label=label, zorder=2)
        for xi, v in zip(x + dx, vals):
            ax.annotate(f"+{v:.0f}", (xi, v), xytext=(0, 3), textcoords="offset points", ha="center", fontsize=9)
    ax.set_xticks(x, [p[1] for p in parts])
    ax.set_ylabel("extra time lost in the AM peak hour, veh-h")
    ax.grid(axis="y", color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    ax.legend(loc="upper right", fontsize=9)
    ax.set_title("SUMO: where converting all three streets adds delay (mean over seeds)", loc="left")
    note(fig, f"Edge time loss (SUMO edgeData, peak hour) vs today. The 65 junctions on the three streets include "
              f"22 signals, and netconvert rebuilt the program at all 22. Today's total travel time in SUMO is about "
              f"{w.tstt_today_h.mean():,.0f} veh-h; the all-three change is +{w.tstt_change_h.mean():.0f} veh-h "
              f"(+{clean.tstt_change_h.mean():.0f} without gridlock seeds). outputs/final/sumo/seeds40_where.csv.")
    save(fig, "fig7_all_three_where.png")


def main() -> None:
    print(f"writing to {OUT.relative_to(ROOT)}")
    fig_screenlines()
    fig_city_question()
    fig_ashley_bridge()
    fig_static_vs_sumo()
    fig_where()
    D, table = load_network()
    fig_network(D, table)
    fig_converted(D, table)


if __name__ == "__main__":
    sys.exit(main())
