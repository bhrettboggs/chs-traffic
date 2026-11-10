"""P3 + P5: greedy search over the coarse corridor set, in resumable chunks.

    python scripts/09_search.py [--time-budget 150] [--max-rounds 5] [--scenarios 20] [--shortlist 12] [--reset]

One round = try every corridor in every other state (two-way, one-way either
direction) on top of the moves accepted so far:
  1. tier-1 graph screen;
  2. screening: config.SEARCH_SCREEN_SCENARIOS scenarios at gap SEARCH_SCREEN_GAP;
  3. confirmation of the best SEARCH_CONFIRM_TOP on all scenarios at UE_GAP_SEARCH;
  4. accept the best confirmed move that passes robust.Score.accept().
Progress is saved to outputs/search_state.json after every candidate, so the
script can be stopped (or run with a --time-budget in seconds) and started again.
Every evaluated move is written to outputs/search_moves.csv with its change in
travel time, vehicle-km and two-way share (the inputs for a Pareto chart).

UNCALIBRATED model (4 of 6 screenlines pass): results are relative comparisons.
"""

import argparse
import json
import pickle
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from chstraffic import config, demand, feasibility, robust, widths  # noqa: E402

STATE = ROOT / "outputs" / "search_state.json"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--time-budget", type=float, default=1e9, help="seconds; stop cleanly after this long")
    ap.add_argument("--max-rounds", type=int, default=5)
    ap.add_argument("--scenarios", type=int, default=config.N_SCENARIOS)
    ap.add_argument("--shortlist", type=int, default=0,
                    help="from round 2 on, re-screen only the N best moves of round 1 (a shortcut; 0 = all)")
    ap.add_argument("--reset", action="store_true")
    args = ap.parse_args()
    t0 = time.time()
    left = lambda: args.time_budget - (time.time() - t0)  # noqa: E731

    D = pickle.loads((ROOT / "data" / "processed" / "chs_digraph.gpickle").read_bytes())
    table = feasibility.segment_table(D, feasibility.load_overrides(ROOT / "data" / "reference" / "overrides.csv"),
                                      widths.load(ROOT / "data" / "processed" / "segment_widths.csv"))
    cors = feasibility.search_corridors(D, table)
    by_cid = {c.cid: c for c in cors}
    base_cfg = feasibility.baseline_config(table)
    B0 = feasibility.apply_config(D, table, base_cfg)
    zones = demand.load_zones(B0, ROOT / "data" / "reference" / "zones.csv")
    ods = demand.scenarios(B0, zones, n=args.scenarios)
    ods_screen = ods[:config.SEARCH_SCREEN_SCENARIOS]
    od_pairs = sorted({k for od in ods for k in od}, key=str)

    (ROOT / "outputs").mkdir(exist_ok=True)
    st = dict(accepted=[], round=1, screen={}, confirm={}, done=False, n_scenarios=args.scenarios)
    if STATE.exists() and not args.reset:
        st = json.loads(STATE.read_text())
        if st["n_scenarios"] != args.scenarios:
            sys.exit("state file was made with a different --scenarios; use --reset")
    save = lambda: STATE.write_text(json.dumps(st, indent=1))  # noqa: E731

    def cfg_after(moves):
        cfg = dict(base_cfg)
        for cid, mode in moves:
            cfg.update(by_cid[cid].config_for(table, mode)[0])
        return cfg

    print(f"{len(cors)} corridors, {args.scenarios} scenarios; round {st['round']}, accepted so far: "
          f"{[(by_cid[c].name, m) for c, m in st['accepted']]}")
    while not st["done"] and st["round"] <= args.max_rounds and left() > 0:
        cur_cfg = cfg_after(st["accepted"])
        D_cur = feasibility.apply_config(D, table, cur_cfg)
        core = feasibility.core_nodes(D_cur)
        cur_screen = robust.evaluate(D_cur, ods_screen, gap=config.SEARCH_SCREEN_GAP)
        share_cur = feasibility.two_way_share(table, cur_cfg)
        # ---- stage 1: screen every candidate
        short = None
        if args.shortlist and st["round"] > 1:
            r1 = {k: v for k, v in st["screen"].items() if k.startswith("1|") and v["status"] == "ok"}
            short = {k.split("|", 1)[1] for k in sorted(r1, key=lambda k: r1[k]["d_tstt"])[:args.shortlist]}
        for c in cors:
            for mode in ("two", "fwd", "rev"):
                key = f"{st['round']}|{c.cid}|{mode}"
                if key in st["screen"] or (short is not None and f"{c.cid}|{mode}" not in short):
                    continue
                if left() <= 0:
                    save()
                    print(f"time budget used; {len(st['screen'])} screening results saved. Run again to continue.")
                    return
                part, blocked = c.config_for(table, mode)
                if blocked or all(cur_cfg[s] == v for s, v in part.items()):
                    st["screen"][key] = dict(status="blocked" if blocked else "same")
                    continue
                cand = {**cur_cfg, **part}
                D_new = feasibility.apply_config(D, table, cand)
                sc = feasibility.screen(D_cur, D_new, od_pairs, core=core)
                if not sc.ok:
                    st["screen"][key] = dict(status="screened_out", reason=sc.reason)
                    save()
                    continue
                ev = robust.evaluate(D_new, ods_screen, gap=config.SEARCH_SCREEN_GAP)
                s = robust.score_config(cur_screen, ev)
                st["screen"][key] = dict(status="ok", name=c.name, length_m=round(feasibility.corridor_length_m(table, c)),
                                         d_tstt=s.mean_change, win=s.win_rate,
                                         d_vkm=float(np.mean(ev.vkm / cur_screen.vkm - 1)),
                                         d_two_way_share=feasibility.two_way_share(table, cand) - share_cur)
                save()
        # ---- stage 2: confirm the best few
        rnd = {k: v for k, v in st["screen"].items() if k.startswith(f"{st['round']}|") and v["status"] == "ok"}
        top = sorted((k for k, v in rnd.items() if v["d_tstt"] < -config.SEARCH_SCREEN_MIN_IMPROVEMENT),
                     key=lambda k: rnd[k]["d_tstt"])[:config.SEARCH_CONFIRM_TOP]
        cur_full = None
        for key in top:
            if key in st["confirm"]:
                continue
            if left() <= 0:
                save()
                print("time budget used during confirmation. Run again to continue.")
                return
            if cur_full is None:                       # cached: it costs as much as one candidate
                ck = f"full|{st['round']}"
                if ck not in st.setdefault("cache", {}):
                    e = robust.evaluate(D_cur, ods)
                    st["cache"][ck] = dict(tstt=e.tstt_h.tolist(), unreachable=e.unreachable.tolist(),
                                           gap=e.max_gap, vkm=e.vkm.tolist())
                    save()
                c_ = st["cache"][ck]
                cur_full = robust.Evaluation(np.array(c_["tstt"]), np.array(c_["unreachable"]), c_["gap"], np.array(c_["vkm"]))
                if left() <= 0:
                    print("time budget used during confirmation. Run again to continue.")
                    return
            _, cid, mode = key.split("|")
            cand = {**cur_cfg, **by_cid[int(cid)].config_for(table, mode)[0]}
            ev = robust.evaluate(feasibility.apply_config(D, table, cand), ods)
            s = robust.score_config(cur_full, ev)
            st["confirm"][key] = dict(name=by_cid[int(cid)].name, mode=mode, mean=s.mean_change, p10=s.p10, median=s.median,
                                      p90=s.p90, win=s.win_rate, accept=bool(s.accept()),
                                      d_vkm=float(np.median(ev.vkm / cur_full.vkm - 1)))
            save()
        ok = [k for k in top if st["confirm"][k]["accept"]]
        if not ok:
            st["done"] = True
            print(f"round {st['round']}: no move passes (mean better than {config.MIN_MEAN_IMPROVEMENT:.1%} "
                  f"and wins in {config.MIN_WIN_RATE:.0%} of scenarios). Search finished.")
        else:
            best = min(ok, key=lambda k: st["confirm"][k]["mean"])
            _, cid, mode = best.split("|")
            st["accepted"].append([int(cid), mode])
            print(f"round {st['round']}: ACCEPT {by_cid[int(cid)].name} [{cid}] -> {mode}: {st['confirm'][best]}")
            st["round"] += 1
        save()

    rows = []
    for key, v in st["screen"].items():
        r, cid, mode = key.split("|")
        c = by_cid[int(cid)]
        rows.append(dict(round=int(r), corridor=int(cid), name=c.name, mode=mode,
                         **{k: x for k, x in v.items() if k != "name"}, **{f"confirm_{k}": x for k, x in
                         st["confirm"].get(key, {}).items() if k not in ("name", "mode")}))
    df = pd.DataFrame(rows)
    df.to_csv(ROOT / "outputs" / "search_moves.csv", index=False)
    ok = df[df.status == "ok"].sort_values("d_tstt")
    pd.set_option("display.width", 220)
    print(f"\nstatus counts: {df.status.value_counts().to_dict()}")
    cols = ["round", "name", "mode", "length_m", "d_tstt", "win", "d_vkm", "d_two_way_share"]
    fmt = {c: (lambda x: f"{x:+.2%}") for c in ("d_tstt", "d_vkm", "d_two_way_share")}
    print("best screening results:\n", ok[cols].head(12).to_string(index=False, formatters=fmt))
    print("worst screening results:\n", ok[cols].tail(5).to_string(index=False, formatters=fmt))
    if st["confirm"]:
        print("confirmed on all scenarios:")
        for k, v in st["confirm"].items():
            print(f"  round {k.split('|')[0]} {v['name']:<18} {v['mode']:<4} mean {v['mean']:+.2%} "
                  f"(p10 {v['p10']:+.2%}, p90 {v['p90']:+.2%}) win {v['win']:.0%} veh-km {v['d_vkm']:+.2%} accept={v['accept']}")
    print("accepted:", [(by_cid[c].name, m) for c, m in st["accepted"]], "| finished:", st["done"])


if __name__ == "__main__":
    main()
