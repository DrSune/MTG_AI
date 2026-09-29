# 01 — Grammar round 9-B batch results (2026-09-29)

Spec: `KNOWLEDGE/2026-09-28/11-grammar-round9-decision.md` §9-B (13 rows).
All work at HEAD `6cac871`; no grammar/compiler edits (templates + tests only).
`git diff` = 7 template modules + 7 test modules + 11 goldens + `tools/gen_buckets.py`
(pins only) + report + NUMBERS row.

## Ledger (row → tid → outcome kind → C16 note)

| # | Row | tid | Kind | C16 (free-choice the IR keeps open) |
|---|-----|-----|------|--------------------------------------|
| 1 | Steward gate timing tail | — | **WITHDRAWN** | no attach path (see §Withdrawal) |
| 2 | Speaker of the Heavens activation gate | `B5a-speaker-gate` | gate (ActivationGateOutcome) | none — gate is forced; LOSSY: "and only as a sorcery" clause DROPPED (C11-class verbatim lossy note; attach rewrites only the condition slot) |
| 3 | Drowsing Tyrannodon attack-despite-defender | `B5a-aslong-attack-despite-defender` | static | none — LOSE_ABILITY(DEFENDER) under DurationWhileCondition(CONTROLLER_COUNT_GE(Creature∧POWER_GE p)) is fully forced |
| 4 | Pursued Whale token (C23) | `B2a-whale-opponent-pirate-tokens` | triggered | none — each clause forced; quoted text hand-built IR in `TokenSpec.abilities` (first production fill of the field; cant-block mirrors b4:396, mandate mirrors `B4-mandate-attack-you`, creator via EachPlayer(ALL_OPPONENTS)+Necromentia implicit-owner precedent) |
| 5 | Kraken s2 do-continuation | `B2b-do-tap-or-untap` | effect (Optional+Choose) | open — which creature to tap/untap (Choose(1) TARGET selector); merge verified: TriggeredAbility(CardDrawnEvent, Optional(Seq(PAY, Optional(Choose)))) via `_merge_do_continuation` |
| 6 | Orrery draw-per-color | `B3-draw-per-distinct-color` | activated | none — DRAW amount=QDistinctColorCount(ALL YOUR permanents) forced |
| 7 | Orrery spend-any-color | `B4-spend-any-color` | static | none — MANA_POLICY scope="ALL_YOURS" (C21), may-wrap kept (C15) |
| 8 | Teferi any-time activation | `B4-teferi-grant-activation` | static | none — GRANT_ACTIVATION(holder=FAnd(Planeswalker, NAME_CONTAINS Teferi), window=INSTANT verbatim) |
| 9 | Enthralling untapped-target ban | `B4-enthralling-target-choice` | static | none — PREVENT_EFFECT(condition=IS_ANY_TARGET spell-scope, event=TargetingEvent(Creature∧IS_UNTAPPED)) |
| 10 | Vodalian spend-this-mana | `B5b-spend-this-mana-is-or-sorcery` | static | none — MANA_POLICY scope="THIS_MANA", filter=FOr(Instant,Sorcery); restriction, no may (C15 silent) |
| 11 | Snoop play-revealed | `B5b-play-top-revealed` | static | none — REVEAL(YOU,1,DurationPermanent) R9-8 role; library-top implicit per LOOK_AT convention |
| 12 | Frost Breath s2 | `B5c-those-no-untap-next` | effect | none — PREVENT_EFFECT(condition=IS_ANY_TARGET, event=TapStateEvent(tapped=False), step=UNTAP, duration=DurationUntilNextStep(UNTAP, owner_scoped=True)); EffectOutcome so the INSTANT assembly folds Seq(TAP,PREVENT) |
| 13 | Subira s2 delayed draw | `B5c-cost-discard-hand-delayed-draw` | activated | open — which creature attacks; DelayedTrigger(DurationEot, DamageDealtEvent(QUnbounded, combat=True, source=Creature∧YOU∧POWER_LE n)) → DRAW. LOSSY (b2b-pinned R8 candidate): "to a player" dropped (no player-identity FAtomPred) |

## Withdrawal (row 1, Liliana's Steward)

"Activate only as a sorcery." stays QUEUED. `ActivationGateOutcome` carries only
`condition`; the compiler's gate-attach rewrites the s0 condition slot and cannot also
set `window`; overriding s0's pattern would double-match `B5c-cost-sacrifice-discard`
(PC-3 hard gate). The `window=SORCERY` field (R9-1) plus gate-attach ordering is needed.
**Named R10 item: gate-outcome timing attachment.** UNCOVERED reason rewritten verbatim
in `templates_b5a.py`.

## Predictions vs actuals (doc /11 §DEFER)

- PC-1: predicted 298, **actual 297/305** — the −1 is Steward (card not full). Band 296–299 ✓.
- PC-2: predicted 631, **actual 630/639** — 12 sentences landed (13 − Steward). Band 629–631 ✓.
- PC-3: **0** (every new pattern verified disjoint; E2E full-pool run clean).
- PC-4: post-refresh **0 diffs / 305**; pre-refresh diff set was EXACTLY the 11 landed
  cards (Vodalian, Enthralling, Frost, Whale, Kraken, Orrery, Subira, Speaker, Teferi,
  Drowsing, Snoop) — /07 rule held (git-changed == pre-refresh diff ids).
- Queue: predicted 8, **actual 9** = the 8 named defers (Transmogrify×2, Chrome,
  Mangara, Snoop-grant, Waker-can't-loses, Sanctum, Herald) + Steward (this withdrawal).
  0 new shapes (`/tmp/opencode/r9b_queue_pre.txt` → post diff = removals only).
- PC-6 orphans: unchanged pre-existing PHASE_IN-only fail; MANA_POLICY / GRANT_ACTIVATION
  consumed (orphan list never grew). PC-5 0.24 ms; PC-8 0.3213 (pre-existing fail, +1 card).

## Template-count table (post-batch, each module suite green)

| module | templates | bucket shapes covered | UNCOVERED |
|--------|-----------|----------------------|-----------|
| b2a | 57→60 | 59→60 / occurrences 63→64 | 3→2 |
| b2b | 58→59 | 60 | 2 |
| b3  | 29→30 | 48 | 1→0 |
| b4  | 43→46 | 46 | 4→1 |
| b5a | 56→58 | 62 | 6→5 (Steward stays) |
| b5b | 75→77 | 87 | 6→4 |
| b5c | 84→86 | 89 | 4→2 |

gen_buckets pins moved B2a 59→60, B3 47→48, B4 43→46 (dated comments); all 8 bucket
JSONs regenerate byte-identical (cmp). Compiler suite 758 passed; ruff delta vs HEAD = 0
new (37 pre-existing); pyright 0 errors on all touched modules; full-repo pytest failure
set identical to HEAD worktree (23 pre-existing rule_engine/strategic_brain, +16 new
passing tests here).

## Traps hit (→ PITFALLS)

- Oracle sentences with embedded quoted rules end **inside** the closing quote
  ("…if able.""): a trailing `\..$` pattern never matches. Dump the concrete bucket
  sentence byte-for-byte before authoring the regex.
- Raw-string double-quoted patterns: `\"` KEEPS the backslash (regex sees `\"`, fine)
  but writing `\\.` yields literal-backslash-dot in the value — over-escaping silently
  zero-matches. Test `fullmatch` against the JSON sentence immediately.
- Test-file import blocks are case-sorted with `QX` first (b4 house style); inserting an
  import at the top breaks ruff I001.
