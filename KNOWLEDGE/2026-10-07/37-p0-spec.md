# 37 — T4 P0 design spec landed (docs-only, 2026-10-07; no code/enum/golden touched)

Deliverables: `docs/T4_SPEC.md` (instance classes OPERATION(6)/POLICY(7)/EFFECT(36) — class =
payload role, menus belong to the shared PICK wrapper per §9; canonical slot table extracted
from closed `_VERB_ROLES` ability_tree.py:3305; menu taxonomy FULL-LIST|ZONE+FILTER|DERIVED|
NUMBER clamped by ONE `count_semantics`; zone-verb unification MILL(3)+EXILE(19)+DISCARD(17)
→ MOVE{from,to} = **39/305 golden churn**, DESTROY/PHASE_* stay; one-grammar static≡ask table
riding /31 `one_of:s:i of k` frozen precedent; PT timestamp = OPEN, two candidates (CR 613
layers vs derived-value PT), pinned test `test_current_pt_timestamp_behavior` owns the defect).
`docs/T4_BLINDNESS_AUDIT.md`: full atom-by-atom audit — BLIND 10 rows / PHANTOM 4 / rest CLEAN
or volume-floored. `docs/T4_GAP_LEDGER.md`: **26 rows = MIS-ENCODE 11 / COVERAGE-HOLE 13
(4 ask-channel) / ENFORCEMENT-ABSENT 1 / OPEN 1**.

Significance-criterion pass (10 pool cards, DB oracle vs golden IR): **30/31 clauses mapped
= 96.8%**, 1 UNCOVERED (Snoop top-card-abilities = new DERIVED-from-object menu type L-21).
Corrections found by verifying against code/DB (earlier-session hypotheses wrong): Duress
noncreature+nonland filter IS present (FAnd of FNot×2); Teferi −10 count=2 IS oracle-correct
("two extra turns"); Basri −2 THAT_MANY shape IS oracle-faithful. New rows L-21..L-26 incl.
EQUIP/ATTACH double-encoding and pool-has-no-saga/adventure (DB scan: 397 M21 cards).

Verdict — **P1 can proceed WITHOUT current-code fixes**, conditionally: verb-class partition,
MOVE merge, silent-PICK→PICK lift and HEXPROOF enforcement are additive/P1-safe (ask vocab
frozen per /31 law, want==1 replay bytes protected); the PT-timestamp and E1 direction merges
must NOT enter P1 — they are gated behind the T4 layer-model decision (L-5) and P2.
Commands producing the numbers: `tools/dump_unparsed_queue.py` (PC-1 303/305, PC-2 637/639),
`_VERB_ROLES` + event dataclass extraction via `.venv/bin/python` import `MTG_bot.core.ability_tree`,
golden IR from `MTG_bot/core/golden/M21/*.json`, oracle texts sqlite `mode=ro` cards table.
