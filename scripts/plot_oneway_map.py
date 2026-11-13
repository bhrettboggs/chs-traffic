"""Map of the peninsula network colored by one-way / two-way.

    python scripts/plot_oneway_map.py   ->  outputs/network_oneway.png

Draws today's network as the model sees it: OSM directions with data/reference/overrides.csv
applied (segments whose direction comes from an override are drawn in green).
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from chstraffic import feasibility, files  # noqa: E402

FREEWAY = {"motorway", "motorway_link", "trunk", "trunk_link"}


def main() -> None:
    D = files.load_graph()
    table = feasibility.segment_table(D, feasibility.load_overrides(ROOT / "data" / "reference" / "overrides.csv"))
    fig, ax = plt.subplots(figsize=(9, 11))
    styles = {"freeway": ("#b0b0b0", 2.2), "two-way": ("#2b6cb0", 1.1), "one-way": ("#d9480f", 1.4),
              "direction corrected": ("#2f9e44", 2.4)}
    for sid, seg in table.items():
        u, v = (seg.a, seg.b) if seg.state in ("two", "ab") else (seg.b, seg.a)
        d = D.edges[u, v] if D.has_edge(u, v) else D.edges[v, u]
        kind = ("freeway" if seg.highway in FREEWAY else
                "direction corrected" if seg.direction_source == "override" else
                "one-way" if seg.state != "two" else "two-way")
        color, lw = styles[kind]
        geom = d.get("geometry")
        if geom is not None:
            xs, ys = list(geom.xy[0]), list(geom.xy[1])
            if D.has_edge(v, u) and not D.has_edge(u, v):   # geometry is stored the other way round
                xs, ys = xs[::-1], ys[::-1]
        else:
            xs = [D.nodes[u]["x"], D.nodes[v]["x"]]
            ys = [D.nodes[u]["y"], D.nodes[v]["y"]]
        ax.plot(xs, ys, color=color, lw=lw, solid_capstyle="round", zorder=1 if kind == "freeway" else 2)
        if seg.state != "two" and kind != "freeway" and len(xs) >= 2:
            i = len(xs) // 2
            x0, y0, x1, y1 = xs[i - 1], ys[i - 1], xs[i], ys[i]
            if (x0, y0) != (x1, y1):
                ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                            arrowprops=dict(arrowstyle="-|>", color=color, lw=0.8, mutation_scale=7), zorder=3)
    ax.set_aspect(1 / 0.841)  # cos(32.8 deg)
    ax.set_axis_off()
    ax.set_title("Charleston peninsula: drivable network by direction (OSM + overrides)", fontsize=12)
    ax.legend(handles=[Line2D([], [], color=c, lw=w + 1, label=k) for k, (c, w) in styles.items()],
              loc="upper left", frameon=False)
    out = ROOT / "outputs" / "network_oneway.png"
    out.parent.mkdir(exist_ok=True)
    fig.savefig(out, dpi=200, bbox_inches="tight")
    print(f"saved {out}")


if __name__ == "__main__":
    sys.exit(main())
