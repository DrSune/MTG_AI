# 2026-09-28 /09 — Grammar round 8-B: fidelity flip pass (results)

Phase 8-B of `/08-grammar-round8-decision.md`. Consumes 8-A primitives (C17 QAtMost,
TokenSpec.color R8-2, ADD_MANA "ANY" R8-3, DEAL_DAMAGE dealer/recipient R8-5) and flips
pre-existing LOSSY encodings. Zero coverage change; goldens moved by design with a
dedicated re-baseline audit. No commit (owner gate).

## Headline numbers (see NUMBERS.md rows, `tools/measure_grammar.py`)

- PC-1 **274/305 exact**, PC-2 **599/639 exact**, PC-3 **0**, queue **40/40 unchanged** (hard gates).
- PC-4: 0 diffs before flips → 38 expected diffs pre-refresh → re-baseline → **0 verified**.
- PC-5 0.222 ms/card, PC-9 stable, PC-10 100%/0% — stable. PC-6 orphans 3 unchanged.
- **PC-8 0.2885→0.3148 (88→96)** — deviation ③, F1-attributable (target designations visible).
- Suite `MTG_bot/core` **1521 passed** (13 test pins updated, 4 new pins added); pyright 0 on
  all 11 touched files; ruff check delta 0; ruff format applied to the 2 touched files that
  demanded it; `tools/gen_buckets.py` — 8 bucket JSONs byte-identical, pins hold.

## Flip ledger (builder site → flipped shape → golden cards)

### F1 — targeted "up to N" = TARGET + QAtMost(N) (C17) — 10 code sites, 14 template rows

| Site | File (post-edit line) | Before → After | Cards |
|---|---|---|---|
| `_build_barrin_etb` | b2a:700 | T QConst1 → QAtMost1 | Barrin |
| `_build_basris_acolyte` | b2a:1223 | T QConst2 → QAtMost2 | Basri's Acolyte |
| `_build_roaming_ghostlight` | b2a:1337 | T QConst1 → QAtMost1 | Roaming Ghostlight |
| `_build_feline_sovereign` | b2b:1854 | T QConst1 → QAtMost1 | Feline Sovereign (④ sweep-add) |
| `_up_to_two_target_creatures` | b5b:210 | CHOOSE Q2 → **TARGET** QAtMost2 | Basri's Aegis (put-counter), Frost Breath (tap) |
| `_up_to_two_target_creature_cards_your_graveyard` | b5b:264 | CHOOSE Q2 → **TARGET** QAtMost2 | Read the Tides (option 2) |
| `_up_to_one_target_creature` | b5c:212 | CHOOSE Q1 → **TARGET** QAtMost1 | Basri Ket (+1), Basri, Devoted Paladin / Garruk, Unleashed pt+trample (×2 steps each; pt_trample = ④ sweep-add) |
| `_up_to_two_target_creatures` (salvo) | b5c:357 | CHOOSE Q2 → **TARGET** QAtMost2 | Volcanic Salvo |
| `_build_loyalty_return_creature` inline | b5c:742 | CHOOSE Q1 → **TARGET** QAtMost1 | Liliana, Death Mage |
| `_build_bullet_return_two_creatures_hand` inline | b5c:2108 | CHOOSE Q2 → **TARGET** QAtMost2 | Sanguine Indulgence |

KEEP-CHOOSE verified (resolution-time "up to", per /05 C17): b2a Kinetic Augur discard,
b5c `untap up to four lands`, b5c `_build_then_it_fights_up_to_one` (C17 verbatim case),
b5c up-to-seven-permanents-from-hand, b5b cultivate searches, b5c:1010 library-top exile
(no up-to wording). b3/b4/b1/b5a: zero targeted up-to rows (exhaustive sweep).

### F2 — printed color word → TokenSpec.color — 18 builder sites, 22 card goldens

b2a helpers Soldier W/Saproling G/Knight W/Griffin W (Treasure stays None = colorless);
b2b Bird W/Knight W/Saproling G/Cat G + `_cast_subtype_token_builder` dynamic
`m.group(3)` W|G (Lucky Charm Dog/Cat rows; pattern frozen, color group unnamed → positional);
b3 Angel W; b5a Goblin Wizard R; b5b Demon B, Zombie B, Necromentia Zombie B, Fungal Saproling G,
its-controller Angel/Soldier W (covers Angelic Ascension + Secure the Scene + Basri Ket Emblem
payload); b5c loyalty Beast G + bullet Beast G (Garruk, Unleashed / Elder Gargaroth choose folds).
**Skipped with reason:** b5a Weird ("blue and red" — `TokenSpec.color` is a single-color `str`;
bichrome needs a color-set field → R9 candidate, documented in code); Falconer Adept's
"that's tapped and attacking" stays dropped (enters-tapped/attacking rows are 8-C scope).

### F3 — "mana of any one color" → color "ANY" — 4 builder sites, 5 card goldens

b2a Sanctum of Fruitful Harvest; b5a Prismite; b3 add-one-any (**Meteorite** — ④: anchor doc
missed that Meteorite's 2nd ability lands here); b5c sac-this-token-any (**Treasure** token card
+ **Traitorous Greed** treasure-sacrifice step). Colorless `{C}`+ rows keep "C" (b3:654 —
Llanowar precedent verified).

### F4 — damage-surface dealer/recipient — 2 flips, 2 skip-notes

- **Nine Lives** (b5b:2033): replacement event filter (the damaged-object slot)
  `FAnd(())` → `FAtom(CONTROLLER_IS, YOU)` — printed "to you" restored (mission shape,
  ControllerRef vocabulary). Golden diff = FAnd→FAtom re-shape (FAtom serializes all slots;
  nulls included) — single key `abilities`.
- **Fiery Emancipation** (b5b:1128): replacement DEAL_DAMAGE atom gains
  `dealer=FAtom(CONTROLLER_IS, YOU)` = printed "a source you control" dealer side; event
  recipient half stays lossy (no player predicate) and "to that permanent or player" already
  rides the event-referent target.
- **Skip (documented in `_noncombat_source_event` docstring):** b2b Incinerator/Pyreling
  noncombat triggers — dealer side already faithful via event `source=`; 8-A roles exist only
  on DEAL_DAMAGE atoms and both rows' atoms act on their own source ⇒ role flip cosmetic;
  recipient "to an opponent" still lacks a predicate.

## Golden re-baseline audit (dedicated, per /08)

Pre-snapshot `/tmp/golden_pre_r8b_2026-09-28` (flat 305). Changed files: **38 == PC-4 pre-refresh
diff list == post-audit count**; every changed file's diff-keys ⊆ {`abilities`} + `emblem`
(Basri Ket — emblem-payload abilities, within the abilities/emblem/keywords payload rule).
Leaf-path walk attributed all 38 to F1/F2/F3/F4 above; **zero unexplained files**, no revert.

## Deviations (documented, accepted)

1. **Mode flips beyond literal QConst→QAtMost**: 7 template rows were R7/C15-era CHOOSE+QConst
   (the interim targeted-up-to encoding); C17 says CHOOSE-for-targeted is a rejected shape, so
   the fidelity flip includes CHOOSE→TARGET. This is what moved PC-8.
2. **F4(a) shape**: the mission allowed "recipient=…or the 8-A shape"; Nine Lives has no
   DEAL_DAMAGE atom, so the recipient attaches at the event's damaged-object filter (the only
   faithful slot; dealer/recipient ATOM roles are atom-only by design).
3. **PC-8 88→96**: consequence of 1 — cards whose only target designation was hidden by CHOOSE.
   Not a hard gate (gates = PC-1/PC-2 exact, PC-3 0); flagged for the owner's PC-8 re-baseline
   expectations in future rounds.
4. **Sweep additions beyond the 08-doc anchors**: Feline Sovereign (F1), pt_trample row +
   shared-helper card rows (Basri Ket / Devoted Paladin / Garruk Unleashed), Meteorite +
   Traitorous Greed (F3). Exhaustive sweep over all 6 template modules was the mandate.
5. `reports/grammar_2026-09-28.json` + NUMBERS.md rows refreshed by the tool (3 runs today);
   NUMBERS auto-append header noise unchanged.

## Files touched

`templates_b2a/b2b/b3/b5a/b5b/b5c.py` (flips + lossy→faithful docstrings + module-header
convention notes), `test_templates_b2a/b3/b5a/b5b/b5c.py` (13 pin updates: QAtMost, TARGET,
"ANY", color="W", + new dealer/filter/color pins for F4/F2), 38 goldens re-baselined.
UNCOVERED registers, patterns, gen_buckets pins: untouched by design.
