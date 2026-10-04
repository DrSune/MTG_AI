# 2026-10-04/02 — BUGCATCH B2: anomaly detectors D1–D6 shipped, first genuine hits landed

**Scope**: tools-only batch per `KNOWLEDGE/2026-10-02/12-bugcatch-design.md` §D.
Built `tools/audit/detectors.py` (D1–D6 oracle-free detectors + catalog & replay
scan lanes) validated by `tools/audit/test_detectors.py` (28 fault-injection
tests, all fire-on-fault / silent-on-clean). Artifact: `tools/audit/anomalies.json`
(regenerate: `.venv/bin/python tools/audit/detectors.py --seeds 20 --pool all
--deck-pairs-seed 1409 --turns 60`). No MTG_bot/** edits, no commits, bcs.py/bcs.json untouched.

## Gates (all green, 2026-10-04)
- `pytest tools/audit -q` → **28 passed**
- `pytest MTG_bot/core -q` → **2345 passed + 3 subtests** (baseline unchanged)
- pyright **0 errors** on detectors.py + test_detectors.py; ruff **Δ0** (new files)
- `tools/traces/catalog.json` md5 **6507767c3c842857b12953c753e11f69** before = after

## Genuine finding #1 — LOSE_LIFE life loss is unjournalled (D1, 4/20 seeds)
`Verb.LOSE_LIFE` is a registered executor handler (`executor/__init__.py:204`)
and mutates player life, but the journal emitter (`executor/events.py:476-490`)
emits on a life DECREASE only when `cause_verb == "DEAL_DAMAGE"`; there is no
LIFE_LOST kind. A LOSE_LIFE resolution leaves **zero** journal rows. Smoking
gun: all-pool seed 12 has *Life Goes On* ("…you lose 3 life") on the battlefield,
player:0 fold 20+0−0 vs final life 17 (delta −3), and the string "LOSE" appears
in no journal verb all game. Hits: seeds 10 (−4/−4), 12 (−3), 13 (−2/−2), 17 (−2/−2).
Consequence: the replay-fingerprint journal cannot reconstruct life history for
any game containing LOSE_LIFE cards. Adjudicate: observability bug (state change
is rules-legal, the journal is the liar).

## Suspects — D6 (seeds 16, 17)
- multi-replacement-per-event ×2: two live `repl` registrations sharing one
  ZoneChangeEvent **pattern** repr (ANY-zone matchers). Caveat: repl.dump()
  stores patterns, not concrete event instances, and there are no fire counts —
  containment signal only, CR 614.3 ordering makes co-registration legal.
- dead-handle-bound-ref seed 16: live `grant` layer tag=Eot bound to card:72
  which ended in graveyard — Eot-tagged grant outliving its source smells like
  an IS_SOURCE detach leak. Adjudicate.

## Clean verdicts (20-seed all-pool replay)
D3 phantom counters 0, D4 token ledger 0 (incl. ledger/world split),
D5 trufflesnout class 0 (Rule A + Rule B silent on all real decks),
D6 pending-delayed 0, attached-dead-handle 0 (beyond the seed-16 layer hit).
D2 EXEMPT 20/20 (no mana verbs journalled — Treasure-{T}-gap precedent).

## Coverage facts (pinned in anomalies.json coverage_note)
- catalog.json rows = `[sha16, "kind|subject|cause|verb"]` — payload hashed
  away → D1–D5 structurally infeasible from catalog; catalog lane verified to
  produce **zero fabricated hits** (all clean/EXEMPT, tested).
- `--repro` persists no rows; full rows require in-process replay mirroring the
  recipe (`get_supply`/`deal_decks`/`_setup_game`/`_play`/`RandomPolicy`).
- Engine `Handle.__eq__` is class-scoped: reconstructed mirror handles NEVER
  match engine map keys — iterate `world.cards` and key by `str(handle)`
  (`"card:3"`); `zone_of` returns ZoneState, use `.kind`.
