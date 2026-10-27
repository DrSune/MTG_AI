# 168 — Grammar round S-3b: frames, a trigger or cost composed with any clause (2026-10-27)

Owner: "Go ahead then", on the S-3b plan in /167: parse the frames once and compose them with
general effect clauses. CPU only, on branch `sets/onboarding` (60691cf, sealed reads 58af9ae).
The 02:41Z task merges it after its own gates.

## Why frames first
- 1,252 of the 2,831 unparsed dev sentences in the 15 new sets carry a trigger or cost frame. In
  217 of them, the clause after the frame already parses on its own.
- A differential over M21, ZNR, M20 and KHM decided whether composing is safe, before any code was
  written. For 75 sentences that a specific template parses and a frame also splits, composing
  rebuilt 73 byte for byte.
- The two misses:
  - **B-47:** B3 writes Speaker of the Heavens' token type line as "Angel"; every other carrier
    writes "Creature — Angel".
  - **Pronouns:** standalone, "it" is an object named earlier. In Emeria Captain's trigger it is
    the source. So clauses with a pronoun stay out.

## What was built (`core/compiler/frames.py`, `compile_card` Step 2d, bucket B13)
- **Frames:**
  - this permanent enters; this creature dies; your upkeep; your end step; combat on your turn;
    this creature attacks;
  - a mana/tap cost; a loyalty cost [+N]/[−N].
- **Reuse.** Each event or cost comes from the existing helpers: B2a `_etb_event`, `_dies_event`,
  `_upkeep_event`, `_end_step_event` and `_combat_event`; B2b `_attack_event`; B3 `_COST`,
  `_parse_cost` and `_build_activated`; B5c `_loyalty_wrapper`. The clause comes from the registry.
- **Conditions.** Fallback only, after Steps 2a and 2c. The clause must be a pure effect with no
  pronoun ("its owner" stays). Several clause readings with different outcomes are recorded as an
  ambiguity, as in Step 2.
- **`test_frames.py`:**
  - the differential (73 agree; the only difference is B-47, which no compile reaches);
  - fallback-only on either face (M21: no card changes);
  - the pronoun guard and the composed shapes.

## Effect
| 15 new sets, pooled | First touch | After S-3a | After S-3b |
|---|---|---|---|
| Dev PC-1 | 0.0910 | 0.0974 | **0.1194** |
| Dev PC-2 | 0.3420 | 0.3496 | **0.3699** |
| Dev PC-2, unseen shapes | 0.1044 | 0.1078 | **0.1345** |
| Test PC-1 (sealed) | 0.0905 | 0.0926 | **0.1198** |
| Test PC-2 (sealed) | 0.3458 | 0.3503 | **0.3764** |
| Test PC-2, unseen shapes | 0.1094 | 0.1103 | **0.1436** |

- **The sealed test moved as much as dev, or more.** Frames are structure, not tuning.
- **Dev counts:** +89 sentences parsed, against S-3a's +32. Fully compiled dev cards rose
  199 → 243, with 0 new ambiguities.
- **By frame:** enters 34, mana/tap cost 24, loyalty 18, dies 6, upkeep 4, attacks 2, end step 1.
- **Older sets:**
  - M20 test PC-1 0.1714 → 0.1905, PC-2 0.3433 → 0.3734, unseen 0.0994 → 0.1429;
  - KHM test PC-2 0.3197 → 0.3260.
- **Gates.**
  - `pytest MTG_bot`: 2 failed (the D3/D11 gates) / 3501 passed (+7) / 40 deselected / 23 xfailed.
  - `run_scenarios` 429/429; M21 goldens unchanged.
  - Engine fuzz: 40/40 games and 0 crashes each on M19, ORI, FDN and WAR.

## Next (S-3c)
- **More frames.** The reach left on the table: combat damage to a player, cast triggers
  ("whenever you cast a noncreature spell"), sacrifice costs, mutate and draw-count triggers.
- **Clause grammar.** Most unparsed sentences still fail in the clause itself. Effect clauses over
  B11's noun phrases come next:
  - damage to any noun phrase;
  - "<NP> gets ±N/±N [until end of turn]";
  - "put N <counter> counters on <NP>";
  - "<player> draws / gains / loses N".
- **One more volume read.** K1 on the new compile would show whether clean volume converts into
  transfer. Run B grows with every round, so rerun K1b's run B after S-3c.
