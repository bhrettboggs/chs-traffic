"""Check OSM one-way directions against the Charleston County street centerlines.

    python scripts/10_oneway_check.py

Reads  data/processed/chs_digraph.gpickle, data/raw/chs_county_streets_oneway.geojson,
       data/reference/overrides.csv, data/reference/oneway_review.csv
Writes outputs/oneway_check.csv          one row per compared segment: OSM flag and direction, county
                                         value and direction, agree / disagree / no match, whether the
                                         segment is on one of the search corridors, the review verdict,
                                         and today's state in the model after overrides.csv
       outputs/oneway_focus_streets.csv  the same rows for Meeting St, East Bay St, Lockwood Dr and
                                         Hagood Ave, in order along each street
Prints the counts the network QA reports.
"""

import csv
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from chstraffic import feasibility, files, oneway_check, widths  # noqa: E402

FOCUS = ["Meeting Street", "East Bay Street", "Lockwood Drive", "Hagood Avenue"]


def nid(x):
    try:
        return int(x)
    except ValueError:
        return x


def main() -> None:
    D = files.load_graph()
    table = feasibility.segment_table(D, feasibility.load_overrides(ROOT / "data" / "reference" / "overrides.csv"),
                                      widths.load(ROOT / "data" / "processed" / "segment_widths.csv"))
    rows = oneway_check.compare(D, ROOT / "data" / "raw" / "chs_county_streets_oneway.geojson",
                                model_states=feasibility.baseline_config(table))
    raw = Counter(r["result"] for r in rows)
    n_div = oneway_check.mark_divided(D, rows)

    cors = feasibility.search_corridors(D, table)
    on_cor = {sid: f"{c.name} #{c.cid}" for c in cors for sid in c.segments}
    review = {}
    path = ROOT / "data" / "reference" / "oneway_review.csv"
    if path.exists():
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(line for line in f if not line.startswith("#")):
                review[frozenset((nid(r["a"]), nid(r["b"])))] = r
    for r in rows:
        sid = frozenset((r["a"], r["b"]))
        r["search_corridor"] = on_cor.get(sid, "")
        rv = review.get(sid, {})
        r["verdict"] = rv.get("verdict", "")
        r["confidence_pct"] = rv.get("confidence_pct", "")
        r["evidence"] = rv.get("evidence", "")
        r["lat"] = round((D.nodes[r["a"]]["y"] + D.nodes[r["b"]]["y"]) / 2, 6)
        r["lon"] = round((D.nodes[r["a"]]["x"] + D.nodes[r["b"]]["x"]) / 2, 6)

    out = ROOT / "outputs"
    out.mkdir(exist_ok=True)
    cols = ["a", "b", "name", "highway", "osmid", "length_m", "lat", "lon", "osm_state", "osm_dir",
            "county_value", "county_state", "county_dir", "county_objectids", "match_dist_m", "points_matched",
            "result", "note", "search_corridor", "verdict", "confidence_pct", "evidence", "model_state", "model_dir"]
    for name, sel in (("oneway_check.csv", rows),
                      ("oneway_focus_streets.csv",
                       sorted((r for r in rows if r["name"] in FOCUS), key=lambda r: (FOCUS.index(r["name"]), r["lat"])))):
        with open(out / name, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(sel)

    res = Counter(r["result"] for r in rows)
    dis = [r for r in rows if r["result"] == "disagree"]
    dis_cor = [r for r in dis if r["search_corridor"]]
    verdicts = Counter(r["verdict"] or "not reviewed" for r in dis_cor)
    fixed = [r for r in dis if r.get("model_state") != r["osm_state"]]
    print(f"segments with a street name: {len(rows)}")
    print(f"raw join: {dict(raw)}")
    print(f"re-labelled as divided-road drawing differences: {n_div}")
    print(f"after that: {dict(res)}   (compared = agree + disagree = {res['agree'] + res['disagree']})")
    print(f"disagreements on the {len(cors)} search corridors: {len(dis_cor)} -> {dict(verdicts)}")
    print(f"disagreements off the corridors (listed, not reviewed): {len(dis) - len(dis_cor)}")
    print(f"segments whose direction the model now takes from overrides.csv: {len(fixed)} "
          f"({sum(r['length_m'] for r in fixed):.0f} m): "
          + ", ".join(sorted({r['name'] for r in fixed})))
    for nm in FOCUS:
        c = Counter(r["result"] for r in rows if r["name"] == nm)
        print(f"  {nm:<16} {dict(c)}")
    print(f"wrote {out / 'oneway_check.csv'} and {out / 'oneway_focus_streets.csv'}")


if __name__ == "__main__":
    main()
