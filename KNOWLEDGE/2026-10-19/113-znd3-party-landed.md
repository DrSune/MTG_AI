# 113 — ZND-3 PARTY LANDED: register 387→353 (−34, prediction exact), PC-1 0.2411→0.2979 (84/282, EXACT-16 flips), ONE grammar atom (QPartyCount); the round that proved the post-implementation gate earns its keep — T6 withdrawn for misexecuting, coder's ruff claim corrected, and a shared-index capture caught red-handed

**Headline numbers** (post-fix tree; commands: `pytest MTG_bot/core tools -q`,
`tools/run_scenarios.py`, `tools/measure_grammar.py --set ZNR|--set M21`, executed 2026-10-19 ~05:2x):

| metric | pre-ZND-3 (ff041a1-era, committed 387-row register) | post-ZND-3 | law |
|---|---|---|---|
| ZNR register | 387 | **353** (−34) | spec /107 predicted −34 (−35 iff T6); T6 landed at −35 then was **WITHDRAWN by the diff gate (FM2)** — honest final −34, prediction hit |
| PC-1 card_coverage | 0.2411 (68/282) | **0.2979 (84/282)** | flips = EXACTLY the /107 16-card set; zero outside-set flips |
| PC-2 sentence_coverage | 0.4669 (339/726) | **0.5138 (373/726)** | +34 sentences |
| suite | 2855+ | **2927 passed + 36 subtests** | green (tree included sibling WAS_KICKED + HAS_KICKER WIP — executor-side caveat: re-run after their lane commits) |
| packs | 405 | **410/410** | incl. my 3-pack falsification triangle `znr_deadly_alliance_party_{discount,absent,fullprice_control}` (same pool: illegal without party, legal at party-2, full-price control) + sibling's live packs |
| M21 | — | **PC-4 0 diffs (305), deterministic fields byte-identical ex PC-5/generated/git_head** | [G-FM4] amendment applied |

**What landed** (spec /107, gate-confirmed): `QPartyCount(selector)` — the round's ONE grammar
item — a live-type-oracle distinct-class census (`PARTY_CLASSES` = {Cleric, Rogue, Warrior,
Wizard}, world-canonical from ZNR.json reminder text per /92 law; two Clerics + one Wizard = 2,
bifclass "Cleric Wizard" = 2 from ONE body — both pinned on boards); bucket **B8** with 22
templates / 34 rows (T1 cost-reduction 11 via CostDeltaReduceGeneric×QBin, T2 scaled effects 8,
T3 full-party 5 as FAnd-of-4 CONTROLLER_COUNT_GE×SUBTYPE_EQ — zero new predicates, T4
X-announcement 7 via the `_shrine_count` substitution idiom with arithmetic resolving LIVE over
the census ([4,2] Spellcraft; 3+2=5 look-top), T5 class-grants 3 (Tajuru Paragon et al. — the
§11 golden: the grant MOVES other cards' party census, granted identity line byte-untouched)).

**Post-implementation diff gate (adversarial, fresh-eyes) — FM disposition:**
- **FM1 FATAL (process) — SHARED-INDEX CAPTURE**: my staged ZND-3 set was committed at 04:10
  under the SIBLING's message `1b7b9bf feat(engine)` (a bare `git commit` commits the shared
  index — my staged 10 files rode in; its gate line "2665+36st" is NOT attributable to this
  round). No history rewrite (amend on shared main = worse). Attribution split: grammar atom +
  first-cut templates + packs + reports are in `1b7b9bf`; this commit carries the gate fixes,
  the T6 withdrawal, the landing note. Law → PITFALLS (shared-index-capture).
- **FM2 fatal-as-shipped → T6 WITHDRAWN (ZND-3f)**: Acquisitions Expert's "reveals … from their
  hand" COMPILED and was build-tested only, but `Verb.REVEAL` executes through `_look`
  (verbs.py:1102–1114, ZONE_LIBRARY) — a from-hand reveal running as a library peek is a
  materially different effect. Compiled-but-misexecuting rows do not count; the row is back in
  the register (Acquisitions Expert: 2 rows unparsed) — "−35" would have been an inflated
  headline. The preexisting whole-hand-reveal convention (b2a:2625, doc /10 no-op law) shares
  the zone gap — ZND-3f names the HAND-zone role fix for the REVEAL lane (engine item).
- **FM3 patchable → pinned**: bifclass test (no ZNR board has one — the LAW is pinned
  regardless of the corpus).
- **FM4 patchable → pinned**: selector-axis test now asserts VALUES (string_value "Creature",
  who YOU, zone BATTLEFIELD), not just predicate types.
- **FM5 patchable → pinned**: X-arithmetic resolve pins over a live party-2 board.
- **FM6 patchable → ledger (ZND-3g)**: full-party free-cast ask gates CMC_LE≤4 over HAND —
  lands ride the candidate menu at CMC 0 (phantom candidates, §10). No SPELL-kind FAtomPred
  exists at all — a tokenizer gap, new predicate before the next set round, NOT a one-line filter.
- **FM7 → renamed** `_target_creature_on_battlefield` (controller ANY is CR-correct; the old
  name lied).
- **FM8 → coder claim CORRECTED**: the round's "ruff Δ+1 TRY004" finding was FALSE — gate
  counted 259 `raise ValueError` guards at HEAD == post, **Δ0**. (Reported claims are evidence;
  verified claims are evidence-of-evidence.)

**Engine pending (ZND-3d/e, unchanged)**: payer-seat counter-unless (Concerted Defense,
1 row) + static-layer census re-resolution (Archpriest power / Mace static, 2 rows) — all
three still UNPARSED (verified in the 353 register).

**Numbers note**: NUMBERS.md ZNR section replaced in place by the harness (353/373/84; the
−34 delta matches /107 exactly). The 35-row attribution lives at /tmp/opencode/znd3_attribution.json.
