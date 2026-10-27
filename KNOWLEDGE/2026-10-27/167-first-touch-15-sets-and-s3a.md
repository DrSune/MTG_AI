# 167 — First touch on 15 more sets, and grammar round S-3a (2026-10-27)

K1b (/166) found the compiler is the volume tap: only 27.5% of the cards the new sets deal are fully
compiled. B-46 says to put those sets through sealed first touch before any grammar round. That
was done here, CPU only, on branch `sets/onboarding`, which the 02:41Z task merges after its own
gates. Then one small, general round.

## Verify and first touch (`tools/audit/new_set.py`; commit a5065a1)
- **Sources.** All 15 set files match this world's Scryfall: printings, Scryfall ids, and every
  oracle text. The sets are 10E, M10–M15, ORI, M19, DOM, WAR, ELD, THB, IKO and FDN. Reports are
  `reports/set_source_<SET>.json`. Owner sign-off stays pending.
- **Protocol fix (`new_set.py`).**
  - S-1 and S-2 have read M20's and KHM's text, so a new set's first touch now counts their shapes
    as seen (`ROUND_SETS`). Otherwise "unseen shape" would flatter the compiler.
  - A set already touched keeps the `developed_on` list of its earliest report
    (`frozen_developed`). So M20's and KHM's later sealed reads still split as at their first touch.
  - Tested in `tools/audit/test_new_set.py`.
- **First touch.** Dev groups, pooled over the 15 sets, on the S-2 compiler: 2,044 entries, 4,377
  sentences.

  | | Value |
  |---|---|
  | Sentences whose shape no development set has | **67.4%** |
  | PC-1 | **0.091** |
  | PC-2, all shapes | 0.342 |
  | PC-2, seen shapes | 0.73–0.92 per set |
  | PC-2, unseen shapes | **0.104** |
  | Compile crashes | 0 (the S-1 crash fixes hold on sets they were not built for) |
  | Shape-gap exclusions | 10 |
  | Carry-over PC-1 | 0.80–1.00 |

- **The tail.** 2,890 unparsed dev sentences fall into **2,327 distinct shapes** (reminder text
  stripped). The 45 most common cover only 10.2%. Per-shape templates cannot reach these sets (B-41).
- **Sealed baselines.** The 15 sets got no sealed read at first touch, so there was nothing to
  measure a round against.
  - They were taken at a5065a1 from a detached worktree, after S-3a was written. S-3a never read
    the test groups. Each read is logged in `reports/sealed_reads_<SET>.tsv` with its commit and
    that reason.
  - Test pooled: PC-1 0.0905, PC-2 0.3458, unseen 0.1094. That is level with dev, so the split
    is fair.

## Round S-3a: a spell's own name as the subject (Step 2c + bucket B12; 836f3ec)
- **The gap.** M21's burn template is literally `^Shock deals (\d+) damage to any target\.$`
  (`templates_b5b.py:3004`). So Lava Axe, Incinerate and every other burn spell matched nothing.
  254 unparsed dev sentences name their own card; 53 of them are "<name> deals N damage to <X>."
- **The fix.**
  - `compile_card` Step 2c: when no template matches, retry once with the card's own name written
    "~". The name must stand alone. Only bucket B12 may match, so a sentence that compiles today
    is never re-read.
  - B12's builders are the existing carriers: Shock, Volcanic Geyser, Turn to Slag, the B3
    activated effect, and the B6 each-creature atom.
  - `test_templates_b12.py` pins byte-identical IR against each carrier. It also pins that over
    every card of M21, ZNR, M20 and KHM, only cards with an unparsed self-named sentence change.
    M21: none.
- **Effect, measured with sealed reads at the round end (2662930).**

  | | Dev | Test (sealed) |
  |---|---|---|
  | PC-1 | 0.0910 → 0.0974 | 0.0905 → 0.0926 |
  | PC-2 | 0.3420 → 0.3496 | 0.3458 → 0.3503 |
  | Fully compiled dev cards | 186 → 199 | — |

  - Test moved like dev, by about 60% of dev's PC-2 gain, so the fix generalizes.
  - M20 test: PC-1 0.1619 → 0.1714. KHM unchanged.
  - Modest, as sized beforehand.
- **Gates.**
  - `pytest MTG_bot`: 2 failed (the D3/D11 gates) / 3494 passed (+11) / 40 deselected / 23 xfailed.
  - `run_scenarios` 429/429, goldens unchanged.
  - Engine fuzz: 40/40 games and 0 crashes each on 10E, M19 and M11
    (`reports/<set>_engine_smoke_2026-10-27.*`).

## What the tail is made of (planning for S-3b; rough first-match regexes over dev shapes)
- **Frames:** spell or static text 58%, triggered 26%, activated 13%, keyword lines 3%.
- **Verb families:** damage 10.5%, P/T change 9.9%, counters 7.1%, tokens 5.5%, library
  (search/look/mill) 5.3%, draw 5.0%, restrictions 4.6%, exile 4.6%, life 4.6%, bounce 4.0%,
  keyword grants 3.7%, modal 3.2%, other 21%.
- **So the next round is grammar, not shapes.**
  - Parse the frames once: "When(ever) <event>, <clause>", "<cost>: <clause>", "<clause> until end
    of turn".
  - Compose them with general effect clauses over B11's noun phrases: damage to any NP; "<NP> gets
    ±N/±N"; "put N <counter> counters on <NP>"; "<player> draws / gains / loses N"; tokens.
  - Each builder must reuse the existing carrier, and each must pass a differential over the four
    development sets, as B11 and B12 do.
  - That is the parser half of the tied rank-1 goal, and per /166 it is also the learner's
    volume.
