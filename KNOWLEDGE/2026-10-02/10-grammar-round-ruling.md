# 10 — Grammar round ruling (orchestrator self-decision, 2026-10-02)

OWNER DIRECTIVE: decide by True North, don't route technical rulings up. TRUE NORTH: compiled
trees that EXECUTE correctly vs printed text — a card whose printed text names a destination
("to an opponent") or an owner ("its controller creates") is NOT executed correctly without
those slots; the two suspects are print-fidelity failures, not optional features.

APPROVED — additive grammar round (batch 6), bounded:
1. Damage/event DESTINATION predicate (pyreling "to an opponent") — destination slot or
   destination predicate on DamageDealtEvent matching the existing event-filter idiom.
2. CREATE_TOKEN.controller role slot (secure_the_scene "its controller creates").
NOT approved by this ruling: response-window / COUNTER_SPELL arc (separate owner-sized design),
any non-additive grammar change, any state.py touch.

STANDARDS (inherited, non-negotiable): additive byte-stable (R3 law; PC-4 = 0 for unaffected
goldens, C1-form evidence for moved ones); PC-3 stays 0; new decision vocab catalog-provable;
determinism; C15 query surface; games 0-crash bar; promotion law MOVE+strip. If honest work
surfaces a need beyond the two slots → STOP back to this doc for a new ruling.

## Closeout (batch B6 landed — ruling fully executed, 2026-10-04)
Both slots landed exactly as ruled: FAtomPred.OPPONENT_OF (player-total destination
predicate; Pyreling + Incinerator trigger filters now FAtom(OPPONENT_OF, YOU)) and the
optional CREATE_TOKEN controller role (referent-target CHOOSE selector, zero new cast
slots). The two ruled suspects are promoted — suspect folder now EMPTY. Additive law held:
exactly 4 of 305 goldens moved, each with only the `abilities` key changed (2 filter swaps,
2 additive role pairs); PC-4 0 after refresh; every PC Δ0 vs 24a. Packs 304/304, suite
2345+3, games 0-crash 100 decisive, catalog 0/10, ruff Δ0, pyright 0. STOP clause NOT
invoked — nothing beyond the two slots was needed. Evidence: 11-batch6-role-slots.md +
NUMBERS.md 2026-10-04 B6 section. Ruling standards remain in force for future rounds.
