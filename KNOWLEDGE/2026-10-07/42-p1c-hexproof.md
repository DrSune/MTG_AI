# 42 — T4 P1c: HEXPROOF enforcement lands (gap L-4 CLOSED) + fresh-eyes stack fix (2026-10-07)

Closes ledger **L-4** (`docs/T4_GAP_LEDGER.md`): six goldens carried the
HEXPROOF keyword with ZERO executor enforcement.

## Design (one oracle, one chokepoint)

- **Row oracle** — `LayerRegistry.hexproof_of(handle)`
  (`MTG_bot/core/executor/layers.py` ~1110): the live HEXPROOF rows,
  one entry per row — `None` for bare "Hexproof" (vetoes EVERY
  opponent source), a `Filter` for "Hexproof from {quality}" (Spined
  Megalodon / Sporeweb Weaver compiled COLOR_HAS param). Gate is the
  loss-aware `_keywords` materialized map (not a raw record scan, so a
  live LOSE_ABILITY stops the block — `test_lost_hexproof_stops_blocking`).
- **Single chokepoint** — `legality._hexproof_vetoes_target`
  (~440-480) applied in `enumerate_candidates` ONLY when
  `sel.mode is SelectorMode.TARGET`: every target surface (legal_targets,
  spell target slots, 601.2c cast validator, trigger ask menus,
  optional_offer) presents the same legal menu (§10 blindness audit);
  ALL-mode sweepers untouched (`test_non_targeting_sweeper_still_destroys_hexproof`).
- **Direction** (CR 702.11b): only OPPONENT-controlled sources are
  vetoed; controller targets their own object freely; read through
  `controller_of` (16e GAIN_CONTROL aware). Player seats are never
  vetoed (702.11 protects the OBJECT — `test_hexproof_creature_controller_is_a_legal_player_target`).
- **Zone** (CR 113.10/112.6): keyword live only on battlefield/stack;
  identity-seeded names are zone-less, so the CONSUMER guards the zone
  (`test_hexproof_is_dead_outside_the_battlefield`).
- **TREASURE stays decorative** (decision, not oversight):
  `Keyword.TREASURE` (ability_tree.py:740) is Gadrak's Treasure-token
  type-line word — it creates no continuous effect and has zero
  executor consumers; P1c deliberately registers no layers row or veto
  for it.

## Fresh-eyes MAJOR — the stack lane (this card's fix)

Reviewer finding: a hexproof card **on the STACK** passes the
identity-seeded zone-less `_keywords` NAME gate, but has NO live layer
rows — the binder's continuous lifecycle (`attach_card →
layers.attach_source`) fires only on battlefield entry (both cast lanes
gate on `dest == ZONE_BATTLEFIELD`, stack.py 938/1073). The empty
live-scan fell back to the BARE row, collapsing "Hexproof from blue"
into bare hexproof while the card is a spell: an opponent's RED
counterspell was wrongly refused against a printed blue-only-hexproof
creature spell. Both quality cards ARE in the M21 pool (DB
`text LIKE '%hexproof from%'`: Sporeweb Weaver — blue; Garruk's
Harbinger — black; 4 rows = 2 cards × prints).

**Fix** (`LayerRegistry._printed_stack_rows`, reviewer option (a)):
when the live scan yields no rows and `world.zone_of(handle).kind ==
ZONE_STACK`, source the rows from the compiled record registered for
the handle's identity (`binder.records[oracle_id]` — the SAME
KeywordAbility nodes `attach_source` would register; stack.py:937
precedent). Bare printed → stays `(None,)` (CR 702.11b DOES cover
creature spells on the stack: `test_stack_bare_hexproof_vetoes_every_opponent_source`
must not regress); quality printed → quality rows. A card with no
registered record cannot pass `spell_castable` in the real pipeline, so
the residual bare fallback is a defensive read for uncompiled handles
(pinned: `test_stack_without_registered_record_reads_bare`).

**CR cites**: 702.11b (hexproof = "can't be the target of spells or
abilities your opponents control"; covers creature spells on the
stack), 113.10 (keyword abilities of permanents/spells function in the
zones they mention — battlefield/stack), 601.2h (the spell parks on
the stack, where the response window reads hexproof).

**Test-first evidence**: the 5 pins in
`MTG_bot/core/test_executor_hexproof.py::TestHexproofOnStack` (new
`hexproof_spell` stack rig — registers the record in the binder oracle
registry, parks the card, settles; the old rig only battlefield-attached,
which WAS the test blind spot). With `_printed_stack_rows` monkeypatched
off, EXACTLY `test_stack_hexproof_from_blue_still_lets_red_source_target`
fails (the reviewer's bug reproduced); with the fix, 18/18 in the file.

## Gates (final state, 2026-10-07)

- `pytest MTG_bot/core -q` → **2491 passed + 2 subtests** (was 2486+2st; +5 stack pins… file now 18 tests)
- `tools/run_scenarios.py` → **373/373 packs passed**
- `pytest tools/audit tools/training -q` → **153 passed**
- No commit made (uncommitted working state, per brief).
