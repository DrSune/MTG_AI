# Plan: map new cards onto existing components, and prove they play right (2026-10-29)

Owner, 2026-10-29: "We should get some more cards encoded, and make sure they work as intended at
play-time ... Use expert methods and techniques for both the mapping to components, and verifying
they play out as intended in practice, so we dont introduce bugs for our play engine to abuse."

The code is on `main` (`tools/cards/`; the record loader `MTG_bot/core/compiler/card_records.py`).
It was built on branch `cards/mapping`, which reached `main` with the `cards/integration` merge
(a26578f, 2026-11-05).

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
| G0 static | Strict decode and round trip. Printed fields equal ingest: cost, types, P/T, loyalty, colours. Every number in the text appears in the tree. MTGJSON keywords are present. Verbs are executor-supported. A composition never seen before is flagged. The lints (`tools/cards/lints.py`, since 2026-11-14) check the tree against the text: who acts, each activated ability's cost, no number the text never prints, nothing on a permanent's cast carrier. | Malformed trees, a changed printed cost or size, a dropped clause, a wrong number, a flipped controller, a lost cost |
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

## New set playbook (2026-11-14, from M21, M20 and FDN: KNOWLEDGE/2026-11-14/207)
The order runs from free to dear. Each step's numbers are what the three sets cost.
1. **Intake, no agents.** `tools/audit/new_set.py verify` (the source) and `first-touch` (the sealed
   split), as for M20 and KHM (KNOWLEDGE 159).
2. **Reprints, no agents.** `cardtool.py status SET` lists the printings that another set's
   verified record covers (same oracle id and printed text). For each,
   `cardtool.py verify SET "Card" --reprint-of HOME --reviewer <id>`.
   - It stamps the card only when its tree here has the home stamp's bytes. It re-runs G0 and the
     probe here, and the home packs and G3 in the home set, where their supporting cards are.
   - In the 16 other ingested sets this is 404 printings of 182 cards: 9.4% of their 4,308 cards,
     and 66 of M19's 299. Every one has the home stamp's tree bytes. A dry run stamps 402; the
     other 2 need a pack for a G3 mutant newer than their home packs.
   - Without it, M20 and FDN re-reviewed 62 cards already verified elsewhere (85 reviews).
3. **Compiled cards, by blind review.**
   - Batches of 30-38 packets, with planted faults (2 per batch, or 10-15%); verifiers from
     another model family than the fixers.
   - The lowest risk first: 416 cards of the 16 sets have every sentence word for word in a
     verified card.
   - Cost: 0.7-1.1 agent-minutes per packet. Real cards judged WRONG: 25% during the M21 campaign,
     5% (26 of 490) since; 14 of those 26 were engine faults.
   - The verifier runs `cardtool.py survivors` before reporting (MAPPER_GUIDE). Before it, 30 of
     the 72 cards judged OK in waves 1-1e needed a second trip for G3.
4. **Partly compiled cards, by mappers.**
   - Cheapest first (the `status` worklist): 24 cards per mapper, 5 mappers at once, about 40
     minutes a batch (1.75 agent-minutes per card).
   - Give the second wave the first wave's lessons and its known engine faults: the M20 wave given
     them needed 36-41 minutes a batch, the first wave 39-51.
   - G0's lints run at `try`. 82 of M20's 237 attempts (35%) ended needs-atom, each naming the
     missing piece.
5. **A census before any IR work.**
   - Group the needs-atom notes by missing piece, and count each piece's reach in every ingested
     set. Wave 3's census turned M20's 55 castable-unverified cards into three packages.
   - Build the widest piece first, one adversarial gate round per IR change: 7 rounds, about 40
     agent-minutes each, 14 MAJOR findings at the gate.
   - Design against what the gates found most: a second encoding the validator accepts, or a
     role allowed where it means nothing (7 of the 14).
6. **Engine faults at their cause.**
   - A test that fails before the fix.
   - The blast radius by script: trees changed, verified cards in and out, and 300-600 seeded
     replays before and after.
   - Re-verify the cards a merge touches: 34 stamps were re-made after tree changes, and 22 of
     the 189 faults were played by cards already verified.
   - Merge main into every lane before its gate round. One day of lanes took 11 catch-up merges
     for 15 merges into main. `gates.py` and the BACKLOG conflicted in text, and two correct
     fixes turned one pack red in meaning.
7. **Soak (G5), then deal** the `verified` supply only.

**Where the time goes.**
- A card that needs no new component costs about 3 agent-minutes: mapping 1.75 when it needs
  mapping, blind review about 1, G3 follow-up packs 0.1 on average.
- A card that waits on an IR or engine change costs about 49. The backlog waves spent 2,141
  agent-minutes for 44 newly verified cards: fixes 71%, gate rounds 13%, G3 rule work 7%,
  verification 6%, the census 2%.
- So the census and the gate rounds decide a set's pace.

**The pace.** `cardtool.py status SET [SET ...]` prints, per set, the cards by state, the reprints
it can carry over, and the verified cards by the date of their last stamp.

## Era boundary (merge)
Done: the branch merged into `main` with `cards/integration` (a26578f, 2026-11-05). Training now
runs from a pinned run worktree, so engine and card work lands on `main` between runs
(TRAINING_REVIEW_PROTOCOL §1).
