# Known engine faults, the 2026-11-18 triage (KNOWLEDGE/2026-11-18/215)

Each folder holds the repro packs of one open fault. Every pack plays verified cards of one deal
pool (M21, M20 or FDN), states the outcome the printed text and its rulings demand, and FAILS on
main 8d85e0a7. A pack moves to `tools/scenarios/` in the commit whose fix makes it pass.

    .venv/bin/python tools/run_scenarios.py --dir tools/scenarios/known_bugs/2026-11-18/<folder>

| Folder | 215 id | Direction | Pool | Wave |
|---|---|---|---|---|
| `cast_time_target_restriction_rechecked_at_resolution` | F13 | WEAKER | M21 (Enthralling Hold, Tolarian Kraken) | W2 |
| `lifelink_damage_to_its_own_controller_is_no_life_gain` | F27 | WEAKER | FDN (Midnight Reaper, Unflinching Courage, Ajani's Pridemate) | W2 |

Wave W1 fixed F14, F45d and F44; their packs moved to `tools/scenarios/` (Griffin Protector,
Colossus Hammer, Watcher of the Spheres, Brought Back with Oakenform, Dub on Riddleform) and
`tools/scenarios/mapped/M20/` (Masterful Replication, verification wave 7's F44 pack).

Where a pack uses the runner's `move` op, it stands in for removal the pool has (a destroy, a
sacrifice): the move is journalled as another effect's, so Brought Back's "put there from the
battlefield this turn" sees it. The returns are the real cards'.
