"""Fault-injection tests for tools/audit/detectors.py.

Every detector must (a) fire on its synthetic fault and (b) stay silent on
the matching clean fixture — no detector ships unvalidated. All fixtures
fabricate ReplayData directly (journal-shaped Row lists + register dumps);
no engine game runs here, so the suite is fast and hermetic.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import detectors as D

P0, P1 = "player:0", "player:1"


def game(
    rows: list[D.Row],
    *,
    start_life: dict[str, int] | None = None,
    final_life: dict[str, int] | None = None,
    final_zone: dict[str, str] | None = None,
    identity_name: dict[str, str] | None = None,
    layers_rows: list[tuple[object, ...]] | None = None,
    repl_rows: list[tuple[object, ...]] | None = None,
    binder_dump: dict[str, list[object]] | None = None,
    printed_pt: dict[str, tuple[int | None, int | None]] | None = None,
    pt_changes: list[tuple[str, int]] | None = None,
    counter_removals: list[tuple[str, int, int]] | None = None,
    delayed_seen: dict[int, int] | None = None,
) -> D.ReplayData:
    return D.ReplayData(
        seed="fixture",
        rows=rows,
        start_life=start_life or {},
        final_life=final_life or {},
        final_zone=final_zone or {},
        identity_name=identity_name or {},
        layers_rows=layers_rows,
        repl_rows=repl_rows,
        binder_dump=binder_dump,
        printed_pt=printed_pt,
        pt_changes=pt_changes,
        counter_removals=counter_removals,
        delayed_seen=delayed_seen,
    )


def row(
    i: int,
    kind: str,
    subject: str,
    data: tuple[object, ...] | None = None,
    verb: str = "X",
) -> D.Row:
    return D.Row(i, i, kind, subject, P0, verb, data)


# --------------------------------------------------------------------------
# data payload parsing (dump() carries data as a repr string)


def test_parse_data_handle_repr_roundtrip() -> None:
    parsed = D._parse_data(
        "('battlefield', Handle(namespace='player', index=1), 'Creature — Wolf', 2, 2)"
    )
    assert parsed is not None and len(parsed) == 5
    assert str(parsed[1]) == "player:1"
    assert parsed[3] == 2


def test_parse_data_rejects_garbage() -> None:
    assert D._parse_data("open( not a tuple") is None


# --------------------------------------------------------------------------
# D1 life conservation


def _life_rows() -> list[D.Row]:
    return [
        row(0, D.KIND_LIFE_GAINED, P0, (3,)),
        row(1, D.KIND_DAMAGE, P1, (5,)),
    ]


def test_d1_clean_fold() -> None:
    g = game(
        _life_rows(),
        start_life={P0: 20, P1: 20},
        final_life={P0: 23, P1: 15},
    )
    assert D.d1_life(g).status == "clean"


def test_d1_fires_on_unjournalled_loss() -> None:
    g = game(
        _life_rows(),
        start_life={P0: 20, P1: 20},
        final_life={P0: 23, P1: 12},  # 3 life vanished without a row
    )
    v = D.d1_life(g)
    assert v.status == "HIT"
    assert any("unjournalled" in h.detail for h in v.hits)


def test_d1_exempt_without_state() -> None:
    v = D.d1_life(game(_life_rows(), start_life={P0: 20}))
    assert v.status == "EXEMPT"


def test_d1_life_lost_rows_fold_clean() -> None:
    # A journalled LOSE_LIFE (LIFE_LOST row) is a foldable loss: it must
    # reconstruct, not HIT.
    rows = [
        row(0, D.KIND_LIFE_GAINED, P0, (3,)),
        row(1, D.KIND_LIFE_LOST, P0, (3,)),
        row(2, D.KIND_LIFE_LOST, P1, (2,)),
    ]
    g = game(rows, start_life={P0: 20, P1: 20}, final_life={P0: 20, P1: 18})
    assert D.d1_life(g).status == "clean"


def test_d1_still_fires_when_life_lost_undercounts() -> None:
    # A life loss without its row still HITS even when other LIFE_LOST
    # rows exist.
    rows = [row(0, D.KIND_LIFE_LOST, P0, (1,))]
    g = game(rows, start_life={P0: 20}, final_life={P0: 15})
    v = D.d1_life(g)
    assert v.status == "HIT"
    assert any("unjournalled" in h.detail for h in v.hits)


# --------------------------------------------------------------------------
# D2 mana conservation (defensive fold; EXEMPT while no mana verbs exist)


def test_d2_exempt_without_rows() -> None:
    v = D.d2_mana(game([row(0, D.KIND_DAMAGE, P0, (2,))]))
    assert v.status == "EXEMPT"
    assert "no mana verb" in v.note


def test_d2_clean_spend() -> None:
    g = game(
        [
            row(0, D.KIND_MANA_ADDED, P0, (2,)),
            row(1, D.KIND_MANA_SPENT, P0, (2,)),
        ]
    )
    assert D.d2_mana(g).status == "clean"


def test_d2_fires_on_overdraw() -> None:
    g = game(
        [
            row(0, D.KIND_MANA_ADDED, P0, (1,)),
            row(1, D.KIND_MANA_SPENT, P0, (2,)),
        ]
    )
    v = D.d2_mana(g)
    assert v.status == "HIT" and v.hits[0].klass == "leak"


def test_d2_fires_on_pool_surviving_cleanup() -> None:
    g = game(
        [
            row(0, D.KIND_MANA_ADDED, P0, (3,)),
            row(1, D.KIND_TURN_PHASE, "", ("ending",)),
        ]
    )
    v = D.d2_mana(g)
    assert v.status == "HIT" and v.hits[0].klass == "leak"


# --------------------------------------------------------------------------
# D3 counter conservation (phantom placements)


def _enter(handle: str, i: int, clock: int) -> D.Row:
    return D.Row(
        i,
        clock,
        D.KIND_ZONE_CHANGE,
        handle,
        P0,
        "CAST",
        ("hand", D.BATTLEFIELD, P0, P0),
    )


def test_d3_clean_placement() -> None:
    g = game(
        [
            _enter("card:1", 0, 0),
            D.Row(
                1, 5, D.KIND_COUNTER_PLACED, "card:1", P0, "PUT", ("PLUS_1_PLUS_1", 1)
            ),
        ]
    )
    assert D.d3_counters(g).status == "clean"


def test_d3_fires_after_death() -> None:
    g = game(
        [
            _enter("card:1", 0, 0),
            D.Row(
                1,
                8,
                D.KIND_ZONE_CHANGE,
                "card:1",
                P0,
                "DIED",
                (D.BATTLEFIELD, "graveyard", P0, P0),
            ),
            D.Row(
                2,
                9,
                D.KIND_CREATURE_DIES,
                "card:1",
                P0,
                "DIED",
                (D.BATTLEFIELD, P0, "Creature", 2, 2),
            ),
            D.Row(
                3, 10, D.KIND_COUNTER_PLACED, "card:1", P0, "PUT", ("PLUS_1_PLUS_1", 1)
            ),
        ]
    )
    v = D.d3_counters(g)
    assert v.status == "HIT" and "phantom" in v.hits[0].detail


def test_d3_clean_after_a_death_and_a_return() -> None:
    """A creature that died and came back is on the battlefield: a counter put on it then is no
    phantom (the detector used to flag every placement after the card's last death)."""
    died = [
        D.Row(1, 8, D.KIND_ZONE_CHANGE, "card:1", P0, "DIED", (D.BATTLEFIELD, "graveyard", P0, P0)),
        D.Row(2, 9, D.KIND_CREATURE_DIES, "card:1", P0, "DIED", (D.BATTLEFIELD, P0, "Creature", 2, 2)),
    ]
    g = game([
        _enter("card:1", 0, 0),
        *died,
        D.Row(3, 10, D.KIND_ZONE_CHANGE, "card:1", P0, "MOVE", ("graveyard", D.BATTLEFIELD, P0, P0)),
        D.Row(4, 11, D.KIND_COUNTER_PLACED, "card:1", P0, "PUT", ("PLUS_1_PLUS_1", 1)),
    ])
    assert D.d3_counters(g).status == "clean"


def test_d3_fires_before_entry() -> None:
    g = game(
        [
            D.Row(
                0, 3, D.KIND_COUNTER_PLACED, "card:1", P0, "PUT", ("PLUS_1_PLUS_1", 2)
            ),
            _enter("card:1", 1, 4),
        ]
    )
    assert D.d3_counters(g).status == "HIT"


def test_d3_exempt_on_payloadless_rows() -> None:
    rows = [
        D.Row(0, 0, D.KIND_ZONE_CHANGE, "card:1", P0, "CAST", None),
        D.Row(1, 1, D.KIND_COUNTER_PLACED, "card:1", P0, "PUT", None),
    ]
    # payload-less placements produce no deltas -> quiet note, not a false HIT
    v = D.d3_counters(game(rows))
    assert v.status == "clean"


# --------------------------------------------------------------------------
# D4 token ledger


def _token_row(
    handle: str, to_state: str = D.BATTLEFIELD, i: int = 0, clock: int = 0
) -> D.Row:
    return D.Row(
        i, clock, D.KIND_ZONE_CHANGE, handle, P0, "CREATE", (None, to_state, P0, P0)
    )


def test_d4_clean_token() -> None:
    g = game(
        [_token_row("card:50")],
        final_zone={"card:50": D.BATTLEFIELD},
    )
    assert D.d4_tokens(g).status == "clean"


def test_d4_fires_on_created_off_battlefield() -> None:
    g = game([_token_row("card:50", "hand")], final_zone={"card:50": "hand"})
    v = D.d4_tokens(g)
    assert v.status == "HIT" and "created into" in v.hits[0].detail


def test_d4_fires_on_ledger_world_split() -> None:
    # journal last says token entered the battlefield; world ends elsewhere
    g = game(
        [_token_row("card:50")],
        final_zone={"card:50": "graveyard"},
    )
    v = D.d4_tokens(g)
    assert v.status == "HIT" and "ledger/world split" in v.hits[0].detail


def test_d4_exempt_without_final_state() -> None:
    v = D.d4_tokens(game([_token_row("card:50")]))
    assert v.status == "EXEMPT"


# --------------------------------------------------------------------------
# D5 independent PT recompute


def _dies(handle: str, clock: int, pt: tuple[int, int], i: int) -> D.Row:
    return D.Row(
        i,
        clock,
        D.KIND_CREATURE_DIES,
        handle,
        P0,
        "DIED",
        (D.BATTLEFIELD, P0, "Creature — Beast", pt[0], pt[1]),
    )


def _counter(handle: str, clock: int, n: int, i: int) -> D.Row:
    return D.Row(
        i, clock, D.KIND_COUNTER_PLACED, handle, P0, "PUT", ("PLUS_1_PLUS_1", n)
    )


_IDENT = {"card:1": "Trufflesnout", "card:2": "Trufflesnout"}
_PRINTED = {"card:1": (2, 2), "card:2": (2, 2)}  # Trufflesnout is a 2/2


def _d5(rows: list[D.Row], **kw: object) -> D.Verdict:
    """D5 on a game watched for P/T effects (none unless ``pt_changes`` says so)."""
    kw.setdefault("printed_pt", _PRINTED)
    kw.setdefault("pt_changes", [])
    kw.setdefault("counter_removals", [])
    return D.d5_pt_recompute(game(rows, identity_name=_IDENT, **kw))  # type: ignore[arg-type]


def _leave(handle: str, i: int, clock: int, to: str = "hand") -> D.Row:
    return D.Row(i, clock, D.KIND_ZONE_CHANGE, handle, P0, "MOVE", (D.BATTLEFIELD, to, P0, P0))


def test_d5_clean_two_plain_copies() -> None:
    assert _d5([_dies("card:1", 5, (2, 2), 0), _dies("card:2", 9, (2, 2), 1)]).status == "clean"


def test_d5_clean_counter_applied() -> None:
    rows = [_dies("card:1", 5, (2, 2), 0), _counter("card:2", 6, 1, 1), _dies("card:2", 9, (3, 3), 2)]
    assert _d5(rows).status == "clean"


def test_d5_fires_counter_blind_trufflesnout() -> None:
    # the copy carries a +1/+1 counter but still dies as the uncountered printed 2/2
    rows = [_dies("card:1", 5, (2, 2), 0), _counter("card:2", 6, 1, 1), _dies("card:2", 9, (2, 2), 2)]
    v = _d5(rows)
    assert v.status == "HIT"
    assert {h.klass for h in v.hits} == {"counter-blind"}


def test_d5_consistent_counter_folds_stay_silent() -> None:
    # two copies with different counters, each dying as printed + its own counters
    rows = [_counter("card:1", 1, 1, 0), _dies("card:1", 5, (3, 3), 1),
            _counter("card:2", 2, 2, 2), _dies("card:2", 9, (4, 4), 3)]
    assert _d5(rows).status == "clean"
    # a death the fold cannot explain (no counter, no effect) is still a hit
    v = _d5([_dies("card:1", 5, (4, 4), 0)])
    assert v.status == "HIT" and v.hits[0].klass == "unexplained-diff"


def test_d5_counters_stay_with_the_object_they_were_on() -> None:
    """KNOWLEDGE 215 F65, M21 soak seed 229: a Watcher of the Spheres with two +1/+1 counters is
    bounced and recast (a new object, CR 400.7) and dies a plain 2/2 beside another copy that died
    a plain 2/2: rightly, but the old fold summed the first life's counters (counter-blind, twice).
    FDN 123's shape too: one card dying twice, a counter in each life."""
    two_lives = [_enter("card:2", 0, 0), _counter("card:2", 1, 2, 1), _leave("card:2", 2, 2),
                 _enter("card:2", 3, 3), _dies("card:1", 4, (2, 2), 4), _dies("card:2", 5, (2, 2), 5)]
    assert _d5(two_lives).status == "clean"
    twice = [_enter("card:1", 0, 0), _counter("card:1", 1, 1, 1), _dies("card:1", 2, (3, 3), 2),
             _leave("card:1", 3, 3, "graveyard"), _enter("card:1", 4, 4), _counter("card:1", 5, 1, 5),
             _dies("card:1", 6, (3, 3), 6)]
    assert _d5(twice).status == "clean"
    # a counter placed in the CURRENT life still has to show
    blind = [*two_lives[:4], _counter("card:2", 4, 1, 6), _dies("card:2", 7, (2, 2), 7)]
    assert _d5(blind).status == "HIT"


def test_d5_a_death_under_a_pt_effect_is_not_judged() -> None:
    """KNOWLEDGE 215 F65, M21 soak seed 172: one Pack Leader dies a 4/3 under another's "Other Dogs
    you control get +1/+1" and a pump, a second dies 3/3 with one +1/+1 counter. Both are right,
    but the old fold anchored the second on the first (4/3 + 1/1 = 5/4) and cried counter-blind.
    The journal carries no P/T effect, so the watched ledger names the objects that had one; a
    death with one in that life is not judged, and one recorded in an earlier life does not count."""
    rows = [_enter("card:1", 0, 0), _dies("card:1", 5, (4, 3), 1),
            _enter("card:2", 2, 6), _counter("card:2", 7, 1, 3), _dies("card:2", 8, (3, 3), 4)]
    v = _d5(rows, pt_changes=[("card:1", 1), ("card:1", 2)])
    assert v.status == "clean" and "1 not" in v.note
    # Mold Adder 0/0 after Stab, an effect in the life it died in: not judged
    assert _d5([_enter("card:1", 0, 0), _dies("card:1", 2, (0, 0), 1)], pt_changes=[("card:1", 1)]).status == "clean"
    # an effect from an earlier life does not excuse this one's wrong P/T
    earlier = [_enter("card:1", 0, 0), _leave("card:1", 1, 2), _enter("card:1", 2, 3), _dies("card:1", 4, (0, 0), 3)]
    assert _d5(earlier, pt_changes=[("card:1", 1)]).status == "HIT"


def test_d5_a_life_with_a_counter_removed_is_not_judged() -> None:
    """M20 Barkhide Troll enters with a +1/+1 counter and removes it for hexproof ("{1}, Remove a
    +1/+1 counter from this creature"): it dies a 2/2, rightly. The journal has no removal row, so
    the fold would count the counter; the watch places the removal between two looks (after clock
    lo, by hi), and a life it may fall in is not judged."""
    troll = [_enter("card:1", 0, 0), _counter("card:1", 1, 1, 1), _dies("card:1", 6, (2, 2), 2)]
    assert _d5(troll).status == "HIT"  # unwatched removal: the fold says 3/3
    assert _d5(troll, counter_removals=[("card:1", 3, 8)]).status == "clean"  # removed in (3, 8]
    assert _d5(troll, counter_removals=[("card:1", 6, 8)]).status == "HIT"  # only after it died


def test_d5_needs_the_printed_pt_and_the_watch() -> None:
    rows = [_dies("card:1", 5, (2, 2), 0)]
    assert _d5(rows, pt_changes=None).status == "EXEMPT"
    assert _d5(rows, printed_pt=None).status == "EXEMPT"
    assert _d5(rows, printed_pt={"card:1": (None, None)}).note.startswith("0 deaths judged")


# --------------------------------------------------------------------------
# D6 lifecycle audit


_LIVE_LAYER: tuple[object, ...] = (
    1,
    "static",
    "card:9",
    P0,
    "tag",
    "live",
    (),
    "payload",
    (),
)
_DORMANT = ("repl", 1, "card:9", P0, "tag", "dormant", "EVT-A", "noop")


def test_d6_clean_quiet_registers() -> None:
    g = game(
        [_enter("card:9", 0, 0)],
        final_zone={"card:9": D.BATTLEFIELD},
        layers_rows=[_LIVE_LAYER],
        repl_rows=[_DORMANT],
        binder_dump={"attached": [("card:9", "tag")], "delayed": []},
    )
    assert D.d6_lifecycle(g).status == "clean"


def test_d6_exempt_without_registers() -> None:
    v = D.d6_lifecycle(game([]))
    assert v.status == "EXEMPT"


def test_d6_fires_on_pending_delayed_trigger() -> None:
    # unwatched (no first-seen clocks), every pending delayed trigger is flagged, as before
    g = game(
        [], binder_dump={"attached": [], "delayed": [(4, "Eot", "card:9", P1, "Evt")]}
    )
    v = D.d6_lifecycle(g)
    assert v.status == "HIT" and v.hits[0].klass == "registered-never-drained"


def _upkeep(clock: int, active: str) -> D.Row:
    return D.Row(clock, clock, D.KIND_TURN_PHASE, "None", active, "TURN", ("UPKEEP", active))


def test_d6_a_delayed_trigger_of_the_game_s_last_turn_is_in_its_window() -> None:
    """KNOWLEDGE 215 F65, M21 soak seeds 9, 193, 235, 281: Subira's or Basri's "until end of turn"
    delayed trigger, made in the turn the game ended in, is pending at the end because the cleanup
    that sweeps it never came (CR 514.2; the game ended at a loss, CR 104.2a). The old (i) flagged
    every pending one. One that saw a later turn begin did outlive its window, and still fires;
    an until-your-next-turn one lives until its controller's next turn."""
    eot = (4, "Eot", "card:77", P1, "DamageDealtEvent")
    last_turn = game([_upkeep(5, P1)], binder_dump={"attached": [], "delayed": [eot]}, delayed_seen={4: 10})
    assert D.d6_lifecycle(last_turn).status == "clean"
    outlived = game([_upkeep(5, P1), _upkeep(12, P0)], binder_dump={"attached": [], "delayed": [eot]},
                    delayed_seen={4: 10})
    v = D.d6_lifecycle(outlived)
    assert v.status == "HIT" and v.hits[0].klass == "registered-never-drained"
    unt = (5, "UntilNextTurn", "card:7", P0, "Evt")
    theirs = game([_upkeep(12, P1)], binder_dump={"attached": [], "delayed": [unt]}, delayed_seen={5: 10})
    assert D.d6_lifecycle(theirs).status == "clean"
    mine = game([_upkeep(12, P1), _upkeep(15, P0)], binder_dump={"attached": [], "delayed": [unt]},
                delayed_seen={5: 10})
    assert D.d6_lifecycle(mine).status == "HIT"


def test_d6_fires_on_dead_handle_binding() -> None:
    g = game(
        [],
        final_zone={"card:9": "graveyard"},
        layers_rows=[_LIVE_LAYER],
        binder_dump={"attached": [("card:9", "tag")], "delayed": []},
    )
    v = D.d6_lifecycle(g)
    assert v.status == "HIT"
    assert sum(h.klass == "dead-handle-bound-ref" for h in v.hits) == 2


def test_d6_fires_on_double_replacement() -> None:
    # one source holding two live records of one replacement: a registration that never detached
    g = game(
        [],
        repl_rows=[
            ("repl", 1, "card:9", P0, "t1", "live", "EVT-A", "replace"),
            ("repl", 2, "card:9", P0, "t1", "live", "EVT-A", "replace"),
        ],
    )
    v = D.d6_lifecycle(g)
    assert v.status == "HIT"
    assert v.hits[0].klass == "multi-replacement-per-event"


def test_d6_two_copies_of_one_replacement_are_two_effects() -> None:
    """KNOWLEDGE 215 F65, M21 soak seeds 114, 297: two Fiery Emancipations each register "it deals
    triple that damage instead"; both apply, one after the other (CR 616.1), so two live records
    of two sources for one event are no fault. The old (iii) counted records per event."""
    g = game(
        [],
        repl_rows=[
            ("repl", 1, "card:9", P0, "t1", "live", "EVT-A", "replace"),
            ("repl", 2, "card:3", P0, "t2", "live", "EVT-A", "replace"),
        ],
    )
    assert D.d6_lifecycle(g).status == "clean"


def test_d6_dormant_duplicate_is_silent() -> None:
    g = game(
        [],
        repl_rows=[
            ("repl", 1, "card:9", P0, "t1", "live", "EVT-A", "replace"),
            ("repl", 2, "card:3", P0, "t2", "dormant", "EVT-A", "noop"),
        ],
    )
    assert D.d6_lifecycle(g).status == "clean"


def test_d6_expired_repl_ghosts_are_silent() -> None:
    # A card that left the battlefield re-registers on re-entry, and attach_source
    # self-detaches the old record — the dump keeps BOTH as expired audit
    # rows. They never co-exist with a live record, so they cannot both
    # apply to one event (CR 614.3 requires simultaneous application).
    g = game(
        [],
        repl_rows=[
            ("repl", 1, "card:9", P0, "t1", "expired", "EVT-A", "noop"),
            ("repl", 2, "card:9", P0, "t1", "expired", "EVT-A", "noop"),
        ],
    )
    assert D.d6_lifecycle(g).status == "clean"


def test_d6_live_plus_expired_ghost_is_silent() -> None:
    # The re-entry shape: one live record plus its own expired ghost.
    g = game(
        [],
        repl_rows=[
            ("repl", 3, "card:9", P0, "t1", "expired", "EVT-A", "noop"),
            ("repl", 4, "card:9", P0, "t1", "live", "EVT-A", "replace"),
        ],
    )
    assert D.d6_lifecycle(g).status == "clean"


_GRANT_EOT_LAYER: tuple[object, ...] = (
    9,
    "grant",
    "card:72",
    P0,
    "Eot",
    "live",
    ("card:68",),
    "payload",
    (),
)


def test_d6_grant_eot_dead_source_is_silent() -> None:
    # Crash Through resolved to the graveyard; its duration-tagged EOT
    # +3/+3 grant stays live on the (alive) creature — CR 611.2a: an effect
    # exists independently of its source once created.
    g = game(
        [],
        final_zone={"card:72": "graveyard", "card:68": D.BATTLEFIELD},
        layers_rows=[_GRANT_EOT_LAYER],
    )
    assert D.d6_lifecycle(g).status == "clean"


def test_d6_a_resolved_permission_lives_off_the_battlefield() -> None:
    # Chandra, Heart of Fire's [+1] (ontology round R13): "until end of turn, you may play cards
    # exiled this way" stays live while she is gone (CR 611.2a), over cards in exile (CR 601.3).
    permit = (9, "permit", "card:72", P0, "Eot", "live", ("card:68",), "payload", (), None, 40, True)
    g = game([], final_zone={"card:72": "graveyard", "card:68": "exile"}, layers_rows=[permit])
    assert D.d6_lifecycle(g).status == "clean"
    # a static's permission (not made by a resolution) still dies with its source (CR 611.3a)
    static = (10, "permit", "card:72", P0, "Permanent", "live", (), "payload", (), None, 0, False)
    assert D.d6_lifecycle(game([], final_zone={"card:72": "graveyard"}, layers_rows=[static])).status == "HIT"


def test_d6_grant_dead_target_still_fires() -> None:
    # The narrowing is SOURCE-side only: a live grant bound to a dead
    # TARGET remains a hit.
    g = game(
        [],
        final_zone={"card:72": "graveyard", "card:68": "exile"},
        layers_rows=[_GRANT_EOT_LAYER],
    )
    v = D.d6_lifecycle(g)
    assert v.status == "HIT"
    assert v.hits[0].klass == "dead-handle-bound-ref"


# --------------------------------------------------------------------------
# catalog lane: payload-free rows must never fabricate hits


def test_catalog_scan_produces_no_hits() -> None:
    games = D.load_catalog()
    assert games, "catalog.json must be readable"
    for seed, g in games.items():
        for detector in D.DETECTORS:
            v = detector(g)
            assert v.status in ("clean", "EXEMPT"), (seed, v.detector, v.status)
            assert not v.hits, (seed, v.detector, v.hits)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
