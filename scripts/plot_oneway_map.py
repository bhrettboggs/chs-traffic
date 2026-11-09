"""Map of the peninsula network colored by one-way / two-way.

    python scripts/plot_oneway_map.py   ->  outputs/network_oneway.png
"""
import pickle
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parents[1]
FREEWAY = {"motorway", "motorway_link", "trunk", "trunk_link"}


def main() -> None:
    D = pickle.loads((ROOT / "data" / "processed" / "chs_digraph.gpickle").read_bytes())
    fig, ax = plt.subplots(figsize=(9, 11))
    styles = {"freeway": ("#b0b0b0", 2.2), "two-way": ("#2b6cb0", 1.1), "one-way": ("#d9480f", 1.4)}
    drawn = set()
    for u, v, d in D.edges(data=True):
        if d["segment_id"] in drawn:
            continue
        drawn.add(d["segment_id"])
        hw = d["highway"]
        kind = "freeway" if hw in FREEWAY else ("one-way" if d["oneway"] else "two-way")
        color, lw = styles[kind]
        geom = d.get("geometry")
        if geom is not None:
            xs, ys = geom.xy
        else:
            xs = [D.nodes[u]["x"], D.nodes[v]["x"]]
            ys = [D.nodes[u]["y"], D.nodes[v]["y"]]
        ax.plot(xs, ys, color=color, lw=lw, solid_capstyle="round", zorder=1 if kind == "freeway" else 2)
        if kind == "one-way" and len(xs) >= 2:
            i = len(xs) // 2
            x0, y0, x1, y1 = xs[i - 1], ys[i - 1], xs[i], ys[i]
            if (x0, y0) != (x1, y1):
                ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                            arrowprops=dict(arrowstyle="-|>", color=color, lw=0.8, mutation_scale=7), zorder=3)
    ax.set_aspect(1 / 0.841)  # cos(32.8 deg)
    ax.set_axis_off()
    ax.set_title("Charleston peninsula: OSM drivable network by direction", fontsize=12)
    ax.legend(handles=[Line2D([], [], color=c, lw=w + 1, label=k) for k, (c, w) in styles.items()],
              loc="upper left", frameon=False)
    out = ROOT / "outputs" / "network_oneway.png"
    out.parent.mkdir(exist_ok=True)
    fig.savefig(out, dpi=200, bbox_inches="tight")
    print(f"saved {out}")


if __name__ == "__main__":
    sys.exit(main())
