"""Peak-hour factors (K and directional split) from SCDOT continuous-count stations.

Input: hourly two-direction counts for Tue-Thu weekdays (data/raw/scdot_ccs_hourly_2025.csv) and the
station table (data/reference/ccs_stations.csv). Output: one row per (gateway, peak) with
    k             = weekday volume in the peak hour / section AADT (both directions)
    inbound_split = share of that hour's volume travelling toward the peninsula
taken as the median over valid days, with the 10th-90th percentile across days.

One clock hour per peak for the whole model (config.PEAK_WINDOWS): the hour in which the summed
weekday volume of all stations is highest. Gateways peak at different hours (I-26 at 7-8 am,
the bridge at 8 am); a static model loads one hour, so it takes the network's hour.
Gateways with no nearby station take the AADT-weighted mean of the stations, and so do the
interior count stations (row gateway = "_interior"). Both are labeled in the source column.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import config


def load_hourly(path: Path | str) -> pd.DataFrame:
    """Hourly rows with complete, plausible days only (24 hours, no missing value, no zero direction 6-19 h)."""
    d = pd.read_csv(path, comment="#", na_values="-", dtype={"station": str})
    d["station"] = d.station.str.zfill(4)
    keep = []
    for (_, _), h in d.groupby(["station", "date"]):
        day = h[(h.hour >= 6) & (h.hour <= 19)]
        if len(h) == 24 and not h[["dir1", "dir2"]].isna().any().any() and not (day[["dir1", "dir2"]] == 0).any().any():
            keep.append(h)
    return pd.concat(keep, ignore_index=True)


def group_hourly(d: pd.DataFrame, stations: pd.DataFrame) -> pd.DataFrame:
    """Per station group, date and hour: total volume and inbound volume (stations of a group summed;
    a date counts only if every station of the group has it)."""
    st = stations.set_index("station")
    d = d[d.station.isin(st.index)].copy()
    inbound_col = np.where(d.dir1_name.values == st.inbound_dir.reindex(d.station).values, "dir1", "dir2")
    d["inbound"] = np.where(inbound_col == "dir1", d.dir1, d.dir2)
    d["group"] = st.group.reindex(d.station).values
    n_st = st.groupby("group").size()
    g = d.groupby(["group", "date", "hour"]).agg(all=("all", "sum"), inbound=("inbound", "sum"), n=("station", "nunique"))
    g = g.reset_index()
    return g[g.n == g.group.map(n_st)].drop(columns="n")


def peak_hour(g: pd.DataFrame, window: tuple[int, int]) -> int:
    """The clock hour in `window` (inclusive) with the highest summed median weekday volume over all groups."""
    prof = g.groupby(["group", "hour"])["all"].median().groupby("hour").sum()
    return int(prof.loc[window[0]:window[1]].idxmax())


def factors(hourly_path: Path | str, stations_path: Path | str, gateways: list[str]) -> pd.DataFrame:
    stations = pd.read_csv(stations_path, comment="#", dtype={"station": str})
    stations["station"] = stations.station.str.zfill(4)
    g = group_hourly(load_hourly(hourly_path), stations)
    aadt = stations.dropna(subset=["aadt"]).set_index("group").aadt
    rep = stations.drop_duplicates("group").set_index("group").represents
    rows = []
    for peak, window in config.PEAK_WINDOWS.items():
        hour = peak_hour(g, window)
        h = g[g.hour == hour]
        per = {}
        for grp, x in h.groupby("group"):
            k = x["all"] / aadt[grp]
            s = x["inbound"] / x["all"]
            per[grp] = dict(k=k.median(), k_p10=k.quantile(0.1), k_p90=k.quantile(0.9), inbound_split=s.median(),
                            split_p10=s.quantile(0.1), split_p90=s.quantile(0.9), n_days=len(x))
            rows.append(dict(gateway=rep[grp], peak=peak, hour=hour, **per[grp],
                             source=f"SCDOT continuous count station(s) of group '{grp}', Tue-Thu Sep-Oct 2025"))
        w = aadt.reindex(list(per))
        mean = {c: float(sum(per[grp][c] * w[grp] for grp in per) / w.sum())
                for c in ("k", "k_p10", "k_p90", "inbound_split", "split_p10", "split_p90")}
        covered = set(rep[list(per)])
        for gw in [x for x in gateways if x not in covered] + ["_interior"]:
            rows.append(dict(gateway=gw, peak=peak, hour=hour, **mean, n_days=0,
                             source="no station: AADT-weighted mean of the stations (ASSUMPTION)"))
    out = pd.DataFrame(rows)
    for c in ("k", "k_p10", "k_p90"):
        out[c] = out[c].round(4)
    for c in ("inbound_split", "split_p10", "split_p90"):
        out[c] = out[c].round(3)
    return out


def load_factors(path: Path | str) -> dict:
    """{(gateway, peak): (k, inbound_split)} from data/reference/peak_factors.csv."""
    f = pd.read_csv(path, comment="#")
    return {(r.gateway, r.peak): (float(r.k), float(r.inbound_split)) for r in f.itertuples()}
