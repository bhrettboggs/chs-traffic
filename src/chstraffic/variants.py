"""Fixed network variants used by the result scripts (03, 08, 13), defined once.

* City question (HANDOFF section 10): Coming St, Rutledge Ave and Ashley Ave two-way where the
  pavement allows it (>= 2 total lanes), alone and all three together.
* Spring/Cannon back-test: "before" the 2017 conversion = today's two-way pieces of Spring St made
  one-way westbound and of Cannon St one-way eastbound.

A two-way segment gets total_lanes // 2 lanes per direction and no one-way capacity bonus
(feasibility.apply_config), so a 2-lane one-way street becomes one lane each way.
"""

from __future__ import annotations

CITY_STREETS = ["Coming Street", "Rutledge Avenue", "Ashley Avenue"]
SPRING_CANNON_BEFORE = {"Spring Street": "west", "Cannon Street": "east"}


def city_variants(table: dict, base_cfg: dict) -> tuple[dict, list]:
    """{label: (cfg, n_segments_converted)} and the one-way segments that can't go two-way."""
    variants, blocked = {}, []
    groups = {s: [s] for s in CITY_STREETS}
    groups["all three"] = CITY_STREETS
    for label, streets in groups.items():
        cfg, n_conv = dict(base_cfg), 0
        for sid, s in table.items():
            if s.name in streets and s.state != "two":
                if "two" in s.allowed:
                    cfg[sid], n_conv = "two", n_conv + 1
                elif label != "all three":
                    blocked.append(dict(street=s.name, a=s.a, b=s.b, length_m=round(s.template["length_m"]),
                                        total_lanes=s.total_lanes, lanes_source=s.lanes_source,
                                        reason=s.frozen_reason or "1 lane"))
        variants[label] = (cfg, n_conv)
    return variants, blocked


def spring_cannon_before(D, table: dict, after_cfg: dict) -> tuple[dict, list]:
    """Config for the network before the 2017 Spring/Cannon conversion, and the changed segments."""
    before_cfg, changed = dict(after_cfg), []
    for sid, s in table.items():
        if s.name in SPRING_CANNON_BEFORE and s.state == "two":
            heads_east = D.nodes[s.b]["x"] > D.nodes[s.a]["x"]            # direction of a -> b
            want_east = SPRING_CANNON_BEFORE[s.name] == "east"
            before_cfg[sid] = "ab" if heads_east == want_east else "ba"
            changed.append((s.name, round(s.template["length_m"]), s.total_lanes))
    return before_cfg, changed
