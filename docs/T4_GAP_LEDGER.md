# T4 — Zero-loss GAP LEDGER (2026-10-07, P0)

Classes: **MIS-ENCODE** (real component, wrong encoding) · **COVERAGE-HOLE** (semantically
significant text/decision with NO component or ask channel) · **ENFORCEMENT-ABSENT** (encoding
fine, executor doesn't honour it) · **OPEN** (tracked design decision pending).
Every row: source, evidence, future-set exposure guess. §11 significance criterion: text is
significant iff it can alter legal options or state outcomes.

## 1. Seeded rows (knowledge-tree verified; each independently re-checked in code/goldens today)

| id | gap | class | source / evidence | future-set exposure |
|---|---|---|---|---|
| L-1 | `{3/W}` number-prefixed hybrid costs not wired to `CostManaHybrid` (grammar models 2-colour hybrids only) | COVERAGE-HOLE | /34; compiler KNOWN-GAP marker | every hybrid/Phyrexian-cost set |
| L-2 | "Choose one or more —" → `QUnbounded` loses min=1 (phantom zero-pick) | MIS-ENCODE | /34; Sublime golden verified | modal double-faces, kick-era modals |
| L-3 | "attacks or blocks" → TWO duplicate TriggeredAbility records (event needs {kind-union}) | MIS-ENCODE | /34; Gargaroth golden verified today (2 identical abilities) | many; or-combat triggers common |
| L-4 | HEXPROOF: 6 goldens carry keyword, ZERO executor enforcement | **DONE** (/42: hexproof_of oracle + TARGET-mode chokepoint; +stack fix — stack rows from compiled record, quality no longer collapses to bare) | /32 E8, /33; audit table; /42 fresh-eyes MAJOR | every hexproof/shroud-ish set |
| L-5 | PT fold order-dependent ([+1/+1,SET_PT]=3/3 vs reverse=4/4; CR 613 ⇒ both 4/4) | OPEN | /36 pinned `test_current_pt_timestamp_behavior`; SPEC §8 two candidates, undecided | every layer-interaction puzzle |
| L-6 | 14 compiler KNOWN-GAP markers: hybrid costs ×2, bare-unbuildable keywords, Sublime approx, Gargaroth split, anaphoric play-permission, token-effect/land-cost bucketing ×2, P/T fallback, /36 restatement, narrow-shape note | COVERAGE-HOLE | `grep -rn KNOWN-GAP MTG_bot/core/compiler/*.py` = 14 lines | mixed |
| L-7 | `PlayLandEvent` absent → landfall un-encodable | COVERAGE-HOLE | /32 | landfall sets (M19 Rise of the West-era heavy) |
| L-8 | direction axis 2-way encoded: 7 event `.controller` fields vs `CONTROLLER_IS` filters | MIS-ENCODE | /32 E1; extracted slots today | unify BEFORE more event atoms arrive |
| L-9 | `LifeGainedEvent` has NO amount slot | COVERAGE-HOLE | /32; slots verified today | life-gain payoffs (Aetherflux-style) |
| L-10 | `StepEvent` dead atom (0 consumers) | MIS-ENCODE(phantom) | /32 | delete at T4 |
| L-11 | `_choice_bounds` = 4th legality/count surface after /36 unified helper | MIS-ENCODE | /36 deferral | consolidation debt |
| L-12 | `QAtMost(0)` edge semantics unregistered | MIS-ENCODE(risk) | /36 deferral | rare; test-pinned at T4 |
| L-13 | 9 static template UNCOVERED rows (b2a ETB-choose-one, b2b attacks-or-blocks, b4 copy-new-targets, b5a×3, b5b×2, b5c×1) | COVERAGE-HOLE | templates_b*.py tables | modal/trigger/copy families |
| L-14 | 2 live unparsed cards: Conspicuous Snoop (recursive top-card ability grant), Sanctum of All (Shrine additional-trigger gate); PC-1 303/305, PC-2 637/639 | COVERAGE-HOLE | `tools/dump_unparsed_queue.py` run 2026-10-07 | transform/double-faced era |
| L-15 | silent selector-CHOOSE: 170 goldens' decisions never reach ask channel | COVERAGE-HOLE(ask) | /30 census 170/0 | MERGE→PICK is THE lift |
| L-16 | scry within-group order pinned Handle-asc (player order unobservable) | COVERAGE-HOLE(ask) | /30; verbs.py:1008-1018 | every scry-set |
| L-17 | attack = N binar asks, no visible attacker-set declaration | COVERAGE-HOLE(ask) | /30 13g/2a | every combat-heavy eval |
| L-18 | mana ask fuses colour; amount never askable | COVERAGE-HOLE(ask) | /30 | every X-spell / pool-payment set |
| L-19 | zero spelled 4 ways; order vocab = str(i); cw (stack.py:677) vs counter (stack.py:824) twin impls | MIS-ENCODE | /30 | pre-existing debt |
| L-20 | MILL/SCRY/FIGHT exist as BOTH Verb and Keyword (double encoding) | MIS-ENCODE | /33 §3.1 | canonical-form merge |

## 2. NEW rows from the 10-card significance-criterion pass (§4)

| id | gap | class | card / evidence | future-set exposure |
|---|---|---|---|---|
| L-21 | "as long as the top card … is a Goblin card, this creature has **all activated abilities of that card**" — DERIVED-from-object ability menu absent from menu taxonomy (FULL-LIST/ZONE+FILTER/DERIVED-state/NUMBER) | COVERAGE-HOLE | Snoop UNCOVERED clause (L-14 card) | ability-copy/face-down/Impulse sets (AFR/DKH era) |
| L-22 | "up to two" encoded `QConst(2)` (min-0 lost) — same family as L-2 | MIS-ENCODE | Cultivate golden: `SEARCH cards sel(CHOOSE q=QConst(2))` | every "up to" card |
| L-23 | "Play with the top card of your library revealed" modeled as one-shot private `REVEAL{count=1, controller=YOU, permanent}` — should be public + standing-top-card | MIS-ENCODE | Snoop golden | topdeck/reveal-play mechanics |
| L-24 | EQUIP keyword node AND separate ATTACH activated ability encode the same rules fact | MIS-ENCODE(phantom double) | Malefic Scythe golden (EQUIP params=[] + Equip{1} ability) | every Equipment set |
| L-25 | atomics have NO saga-chapter / adventure / delve / proliferate / kick / daybound / venture / experience shapes; DB verified pool contains 0 sagas/adventures (M21-only, 397 cards) | COVERAGE-HOLE | /33 §5 + cards-table scan today | every post-M21 set — §8 mandatory re-eval |
| L-26 | structural context: creature goldens lack SpellAbility cast node (castability ceiling, engine-side B-1) | COVERAGE-HOLE | wave-3b census (163/165) | full-game play |
| L-27 | decision-channel is CONTROLLER-seat only: surfaces whose rules-decider is an OPPONENT or EACH PLAYER (Goremand "each opponent sacrifices", Run Afoul "of their choice", Liliana's Steward/Waker "+1 each player discards") and forced each-target nodes (Keral Keep Disciples "1 damage to each opponent" — no decision at all) have no honest ask lane; pinned CHOOSE via PICK_ASK_FORCE_SILENT | COVERAGE-HOLE(phantom-if-lifted) | /41 §disposition; oracle texts M21 | every opponent-interaction set; needs provider-seat routing **CLOSED 2026-10-29 (V10, branch engine/verify-fixes-2)**: edict and discard asks go to the deciding seat (`ExecCtx.take_decision_of`; BACKLOG B-53) |
| L-28 | "choose a card NAME" (Runed Halo protection) has no NAME-value menu atom; _v_grant never reads the selector (protection rides a compile-time constant) — entity-pick encoding was phantom | COVERAGE-HOLE | Runed Halo golden + verbs.py:_v_grant | name-restriction cards (Nameless Inversion, Bearer of Loyalty era) |
| L-29 | top-of-library POSITION semantics compiled as entity SELECTOR (Furious Rise exile-top-then-play, Radha cast-top-land): _v_move_zone pop_order=TOP never resolves the selector; _v_cast designates via the look-at binding — an ONE_OF there offers a library-wide menu the rules never grant | MIS-ENCODE(silent-phantom) | verbs.py:_v_move_zone TOP branch; /41 | topdeck/predict mechanics; needs position-anchor slot |

## 3. Totals
**26 rows: MIS-ENCODE 11 · COVERAGE-HOLE 13 (4 ask-channel, audit L-15..18) ·
ENFORCEMENT-ABSENT 0 (L-4 closed /42) · OPEN 1.** Top-5 by generalization priority: **L-15** (170 surfaces onto
the asking channel — biggest tokenizer lift), **L-21+L-13+L-14 cluster** (menu taxonomy gap that
breaks compile entirely), **L-16/L-17/L-18** (eval-relevant blindness on 12+13+10-volume atoms),
**L-2/L-22** (min-quantity class of mis-encodes), ~~**L-4**~~ (enforcement bug — CLOSED /42).

## 4. Significance-criterion pass — 10 pool cards, clause-by-clause (DB oracle text vs golden IR)

| card | printed significant clauses → component(s) | mapped | flags |
|---|---|---|---|
| Opt | scry 1→SCRY; draw 1→DRAW | 2/2 | — (L-16 general) |
| Duress | reveal hand→REVEAL; choose noncreature nonland→CHOOSE+FAnd(FNot,FNot) **verified present**; discard that card→DISCARD ref=result | 3/3 | — |
| Fabled Passage | cost{T,Sac-IS_SOURCE}; SEARCH ONE_OF basic→BF tapped (asks); SHUFFLE; IF lands≥4→UNTAP ref=result | 4/4 | — |
| Cultivate | SEARCH 2 basic; REVEAL; MOVE ONE_OF→BF tapped (asks); MOVE REST→hand; SHUFFLE | 5/5 | L-22; k-of-2 pick silent (L-15) |
| Sublime Epiphany | modal 1..5→Choose{opts 5, printed duplicate counter KEPT ✓} | 6/6 | L-2 |
| Conspicuous Snoop | standing-reveal→REVEAL?; may-cast-Goblin-top→Optional{CAST sel top-Goblin}; top-card-abilities→ **UNCOVERED** | 2/3 (67%) | L-21, L-23 |
| Teferi, Master of Time | loyalty-any-turn static→GRANT_ACTIVATION(POLICY ✓); +1→DRAW+DISCARD; −3→PHASE_OUT(filter FNot CONTROLLER_IS YOU); −10→EXTRA_TURN count=2 **byte-correct vs oracle** | 4/4 | L-8 filter-lane usage |
| Basri Ket | +1 PUT_COUNTER QAtMost(1)+GRANT ref=result (**orthogonal-axes exemplar**); −2 attack-trigger QProp THAT_MANY (oracle-faithful); −6 emblem | 3/3 | — |
| Elder Gargaroth | keywords REACH/TRAMPLE/VIGILANCE; "attacks or blocks" trigger; modal 3 | 3/3 | L-3 (duplicate abilities) |
| Malefic Scythe | EtBState initial counter; derived PT MODIFY_PT QBin(1×COUNTER_COUNT source); dies-trigger→PUT_COUNTER; Equip{1}→ATTACH | 4/4 | L-24; L-5 (layer case) |

**Clause totals: 31 significant clauses → 30 mapped = 96.8 %; 1 UNCOVERED (Snoop L-21).**
No clause that alters legal options was silently dropped in 9 of 10 cards; the DB has no
saga/adventure card to test, so L-25 records that structural absence as future exposure.
