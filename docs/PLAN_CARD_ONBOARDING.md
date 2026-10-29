# Plan: map new cards onto existing components, and prove they play right (2026-10-29)

Owner, 2026-10-29: "We should get some more cards encoded, and make sure they work as intended at
play-time ... Use expert methods and techniques for both the mapping to components, and verifying
they play out as intended in practice, so we dont introduce bugs for our play engine to abuse."

Code lives on branch `cards/mapping` (worktree `/home/sune/Desktop/MTG_AI-sets`) until an era
boundary: the record loader touches `MTG_bot/`, which the RL pin fingerprints.

## Where we stand (measured, S-3b reports, 2026-10-27)
- 17 sets beyond M21/ZNR are ingested: 5,120 entries, 3,421 castable, but only **1,145 castable
  and fully compiled**. 5,734 of 10,181 rules sentences do not parse.
- The atoms exist; the phrasebook does not generalise. Of 507 templates, 266 are exact sentences.
  "Draw two cards." parses; "Draw three cards." does not. Nor do "Destroy all creatures." and
  "Whenever this creature deals combat damage to a player, draw a card.".
- Not one of the 1,145 compiled cards outside M21/ZNR has been checked at play time. Templates
  written for M21 can misread a sentence in another set (B-47 is one such case).
- **Why this matters for RL.** A high-exploration RL run is a fuzzer: it finds any card that is
  stronger than printed and builds its play around it (specification gaming). So every dealt
  card passes the gates below, whether the compiler or an agent produced its tree.

## Decisions
1. **The unit is one card. A mapped card is data, not code.**
   - Records live at `MTG_bot/data/cards/<SET>/<oracle_id>.json`, holding the card's `keywords` and
     `abilities` as canonical `to_dict` JSON.
   - Adding a card made of known components needs no code change (King Goal, tied rank 1).
2. **Existing components only.**
   - Mappers write the tree with the IR's own constructors (Python, evaluated in a namespace that
     holds only IR names).
   - The IR's validation (`_VERB_ROLES`, `AtomArgs`, `__post_init__`) runs, and so do the
     compiler's canonicalising passes (`_flip_search_picks_in`, `_promote_liftable_picks`).
   - Same meaning, same bytes (identity law).
   - A card that needs a new atom is marked `needs-atom` with the missing piece named. It is never
     approximated.
3. **Verification is keyed to IR bytes.**
   - A card's `verified` block stores the sha256 of its canonical tree.
   - If a re-map or a compiler change alters that tree, the card leaves the verified pool until it
     is re-verified.
   - The new supply mode `verified` deals only cards whose current tree has a passing entry.
4. **The mapper is never the verifier** (two-person rule). The verifier judges the card's behaviour
   in the engine, not only its tree.
5. **Sealed protocol.**
   - The first-touch numbers stand as recorded; the 17 sets are now labelled sets.
   - Compiler generalisation is measured on sets not yet labelled. There are many.
   - Mapping agents never edit compiler code.

## Mapping method (`tools/cards/cardtool.py`)
- **Compiler in the loop.** The tools are:
  - `show` prints the oracle text, each sentence's parse (template id or UNPARSED) and the
    compiled tree as Python.
  - `similar` retrieves parsed sentences from all 19 sets that are worded like the target,
    each with its tree, as exemplars to adapt. This is retrieval-augmented mapping by analogy.
  - `try` evaluates a draft, validates it and plays it (gate G1 below).
  - `write` stores the record.
- **Gold calibration.**
  - Each batch mixes in about 10% honeypots: cards the compiler already parses, with one sentence
    masked as unparsed.
  - Agreement is exact bytes with the compiler.
  - A batch whose honeypot agreement is under 0.9 is redone. Mismatches go into the mapper guide.
- **Clause traceability.** The record lists every oracle clause with the tree path that implements
  it. An unlisted clause fails gate G0.
- **Order.**
  1. Core sets first, for simple mechanics: FDN, M19, M20, M10–M15, 10E, ORI.
  2. Then the expansions, whose set mechanics are mostly `needs-atom` (saga, adventure, mutate,
     foretell, amass).

## Gates: a card is dealt only when all pass
| Gate | What | Fault it catches |
|---|---|---|
| G0 static | Strict decode and round trip. Printed fields equal ingest: cost, types, P/T, loyalty, colours. Every number in the text appears in the tree. MTGJSON keywords are present. Verbs are executor-supported. A composition never seen before is flagged. | Malformed trees, a changed printed cost or size, a dropped clause, a wrong number |
| G1 behaviour probe | The engine plays the card on a standard board in every variant: each legal target, each mode, X ∈ {0, 1, 3}, each activated ability, each trigger with its stimulus (dies, attacks, upkeep, a spell cast, a creature entering). The trace holds journal events, the state diff and the asks offered. No exception is allowed, and the anomaly detectors (`tools/audit/detectors.py` D1–D6) must stay clean. | Executor bugs in a new context (B-43 bounce to seat 0), crashes, triggers that never fire |
| G2 blind review | A verifier that did not map the card reads the oracle text, the tree and the traces, and rules on each clause: OK, WRONG or NOT EXERCISED. | Wrong meaning |
| G3 adequacy (mutation analysis) | The card's tree is mutated with fault-model operators: amount ±1, until end of turn ↔ permanent, you ↔ opponent, target ↔ all, a dropped step, optional ↔ mandatory, a dropped cost, a widened filter, graveyard ↔ exile, hand ↔ battlefield, a widened trigger scope, a dropped keyword. A mutant whose trace equals the original's marks a part no evidence exercised. | A review that never saw the clause that matters |
| G4 spec packs | Where G3 finds a survivor, the verifier writes a scenario pack from the oracle text with the expected outcome (`tools/run_scenarios.py`). It stays as a regression test. | Whatever the probe cannot reach |
| G5 set soak and abuse screen | N random games per set, dealing verified cards only: 0 engine errors and clean detectors. Outliers go to review: value per mana against cards of the same mana value, activations repeatable at no cost, trigger-fire counts. | Cards stronger than printed: missing costs, missing drawbacks, loops |

**Calibrating G2.**
- Each verifier batch hides planted faults: G3 mutants presented as real records.
- A batch that catches fewer than 0.9 of them is discarded and redone.
- G2 is only as good as its measured detection rate, so the rate is reported with every batch.

**Behavioural goldens.**
- The approved traces are stored with the record.
- Any later engine change that alters a verified card's trace shows as a diff. This is approval
  testing; it extends the IR goldens to behaviour.

**Which gate fixes what.**
- G0, G1 and G3 are automatic.
- G2 costs agent tokens. Its risk-based order:
  1. Every agent-mapped card.
  2. Every compiled card whose sentences used a template from S-1..S-3b, B12 or B13 frames.
  3. A 10% sample of the cards whose every sentence matched an M21-era exact-sentence template.
     If the sample finds a fault, review the whole stratum.

## Metrics (reported per set, every round)
- Verified playable cards and their share of the set; `needs-atom` cards, grouped by missing
  piece.
- Honeypot agreement (mappers) and planted-fault detection (verifiers), with Wilson intervals.
- Mutation score: killed out of viable mutants, by operator.
- Soak engine errors per 1,000 games, detector hits, and outliers reviewed.
- **Paired with play** (METRICS §17): the verified count alone rewards verifying easy cards, so it
  is reported with the K1/K2 numbers on the set and with the duplicate-duel result.

## Who does what
- **This week (owner, 2026-10-29: "using some of this weeks Claude code usage for getting new sets
  done").** Claude builds the tooling, calibrates the gates, and maps and verifies the core sets
  with subagents.
- **After that.** Local agents run the same pipeline on new sets. Claude spot-checks with the
  honeypot and planted-fault rates.
- **Keep the model family diverse.** Where possible, mapper and verifier come from different
  families (REVIEW_2026-10-24 A-7: one model as mapper, worker and gate gives correlated errors).

## Era boundary (merge)
- The branch merges only after the current RL window has ended, with the local agent's re-smoke and
  explicit re-pin (PIN law, /146).
- Before the merge, M21 must be byte-invariant: no records exist for M21, so its supply, goldens and
  the 428 packs must be unchanged.
