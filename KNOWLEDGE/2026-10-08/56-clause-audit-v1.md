# 56 — T5-B clause audit v1: persisted tool + first deterministic zero-loss pass

## What was built
- `tools/audit/clause_audit.py` — deterministic (no LLM) tool: splits oracle text into
  clauses (reminder-parenthetical stripping, bullet/loyalty-prefix handling, keyword-line
  preservation), maps each clause to engine vocab/tree-shape probes against the compiled
  golden tree, and classifies every unmapped clause into the owner taxonomy
  (COVERED / BOILERPLATE-NOTSIGNIFICANT / NOT-ENCODED / MISSING-ENCODING /
  MISSING-EXPRESSIVENESS). NOT-ENCODED rows carry targeted compiler grep evidence
  (`file::symbol` or `no-template`). Output: `tools/audit/clause_audit_v1.json`.
- `tools/audit/test_clause_audit.py` — 8 ground-truth gates (see below); full
  `pytest tools/audit -q` = **87 passed**.

## Headline numbers (command: `python tools/audit/clause_audit.py`)
- 305 golden trees / 589 clauses / **584 mapped = 99.15% zero-loss**, 5 residuals.
- Residual classes: NOT-ENCODED 3, MISSING-EXPRESSIVENESS 2, MISSING-ENCODING 0,
  BOILERPLATE 0 (M21 has no pure rules-prose clauses).

## The 5 genuine residuals (tokenizer/encoding evidence for T4)
1. NOT-ENCODED `Conspicuous Snoop` — top-card conditional grant of activated abilities;
   `Verb.GRANT_ABILITY` exists in engine, tree lacks it (compiler sites cited).
2. NOT-ENCODED `Makeshift Battalion` — KW:BATTALION atom is present but the battalion
   trigger's `PUT_COUNTER` leg never compiled (phantom keyword — see §10 blindness law).
3. NOT-ENCODED `Transmogrify` — 2nd-leg "reveals … until … creature card" repeat-until
   reveal loop absent from tree though `Verb.REVEAL` exists (cf. Kitesail Freebooter).
4. MISSING-EXPRESSIVENESS `Peer into the Abyss` — "Round up each time": no rounding-policy
   atom anywhere in vocabulary.
5. MISSING-EXPRESSIVENESS `Sanctum of All` — "that ability triggers an additional time":
   no additional-trigger-count atom.

## Validated ground truths (all executed in `tools/audit/test_clause_audit.py`)
- 5/5 add-any-mana clauses map (Meteorite, Prismite, Sanctum of Fruitful Harvest,
  Traitorous Greed, Treasure); Gadrak's Treasure parenthetical is correctly stripped.
- Two-leg-removal-shape detector over oracle pool finds EXACTLY 4 cards: Angelic
  Ascension, Liliana Death Mage, Secure the Scene, Transmogrify (Transmogrify honestly
  reports its 2nd-leg gap — same card flagged by the old ad-hoc audit).
- Keyword reminder lines map to Keyword atoms (Elder Gargaroth
  `Vigilance, reach, trample` -> `KW:VIGILANCE,REACH,TRAMPLE`), never residuals.
- Every residual carries class + non-empty evidence; per-card sums are consistent.

## Method notes (pitfalls found in the ad-hoc predecessor, now fixed)
- Regex inflection was the dominant false-residual source: `create` vs `creates`,
  `remove` vs `removes`, `block` vs `blocked`, `ability` vs `abilities`, plural zone
  words (`owners' hands`), P/T with `X` (`+X/+0`), and `Add six {R}` (no literal word
  "mana"). Fixed via inflection-aware rules; residuals went 22 -> 5 (all genuine).
- Tree probes are exact compact-JSON substrings (`V:`/`KW:`/`Z:`/`T:`/`S:` prefixes) —
  no parse-shape assumptions; numeric census ignores `Cost*` nodes to avoid mana-cost
  false positives.
- Supersedes: the 50-residual list in `/tmp/opencode/clause/residuals.txt` (ad-hoc,
  mostly false positives) for coverage claims; its genuine items survive above.
