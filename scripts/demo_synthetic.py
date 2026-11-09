"""End-to-end dry run of all tiers on the toy grid (NOT Charleston).

    python scripts/demo_synthetic.py
"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from chstraffic import demand, feasibility, robust, synthetic  # noqa: E402
from chstraffic.graph import build_digraph, summarize  # noqa: E402


def main() -> None:
    t = time.time()
    D = build_digraph(synthetic.grid_osm())
    table = feasibility.segment_table(D)
    cors = feasibility.corridors(D, table)
    print("toy grid:", summarize(D))
    print(f"{len(table)} segments, {len(cors)} corridors, "
          f"Robbins-orientable: {feasibility.robbins_orientable(D, feasibility.core_nodes(D))}")
    gw, de = synthetic.toy_zones()
    zones = demand.Zones(gateways=gw, sinks={"freeway_out": "fw_out"}, dests=de, snap_report=[])
    ods = demand.scenarios(D, zones, n=10, seed=7)
    cfg, ev, base, log = robust.greedy_corridor_search(D, table, cors, ods, max_moves=3)
    ch = ev.tstt_h / base.tstt_h - 1
    print(f"tried {log.tried} moves ({log.screened_out} screened out), accepted {len(log.accepted)}")
    print(f"final vs baseline: mean {ch.mean():+.2%}, range {ch.min():+.2%} to {ch.max():+.2%}")
    print(f"{time.time() - t:.1f} s. Toy grid only; these numbers mean nothing for Charleston.")


if __name__ == "__main__":
    main()
