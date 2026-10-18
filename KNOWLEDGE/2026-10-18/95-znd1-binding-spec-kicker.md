# 95 — ZND-1 BINDING SPEC: kicker round — reuse-first (CastSpellEvent + Conditional.else already exist); 1 enum + 1 role flag + templates

Date: 2026-10-18. Round scope per /93 fix-order (b) and owner autonomy mandate (rounds land without
per-batch approval; numbers to NUMBERS). Evidence: `reports/grammar_ZNR_2026-10-18_census.json`
unparsed_queue; kicker cluster = **86 rows / 45 cards** (18% of register; full rows dumped to
`/tmp/opencode/znd1_evidence.json`).

## Existing infrastructure verified before deciding (grep-verified 2026-10-18)
- `CastSpellEvent` (ability_tree.py:1612) — "Whenever you cast…" triggers exist.
- `TriggeredAbility.condition: Filter` narrows the event subject (documented convention :1919) —
  kicked-spell filter needs only a new predicate.
- `Conditional` (:2624) has `else_effect` — the 13 "if kicked, X **instead**" rows =
  `Conditional(WAS_KICKED, variant, base)` with zero new effect nodes.
- "if kicked, it enters with N counters" == "When it enters, if kicked, add counters" — same
  semantics, uses ETB trigger + condition; no replacement machinery, no empty-effect node needed.
- `AdditionalCostOutcome` attach lane (/09-23 hook, orphan⇒StateCorruptionError) carries optional
  cast costs; kicker = the same axis {optional extra cost} + a visibility flag.

## Grammar items (additive-only, omit-if-default serialization; M21 goldens must stay byte-identical)
- G1: `AdditionalCostOutcome.kicker: bool = False` — role marker; serialization omits when False.
- G2: `FAtomPred.WAS_KICKED` — "was kicked" state predicate on a spell object/permanent-this-spell.
  Plus `FAtomPred.HAS_KICKER` — printed "a card with a kicker ability" menus (Coralhelm Chronicler,
  Murasa Sproutling). Two enum members, one encoding each (§9 direction-unification: no field-split).

## Template registrations (buckets per existing shape-partition conventions)
- T1 declaration: `Kicker {COST}` / `Kicker {COST} (You may pay an additional {COST} as you cast
  this spell.)` → attach AdditionalCostOutcome(kicker=True) to SpellAbility (post-assembly attach
  with orphan law). Reminder text stripped upstream — declaration-only keyword capture row.
- T2 cast triggers: `Whenever you cast a kicked spell, E` → TriggeredAbility(CastSpellEvent,
  cond FAtom(WAS_KICKED, event-subject), E).
- T3 ETB-if: `When this <type> enters, if it was kicked, E` (+ `When <name> enters, if <name> was
  kicked`) → ZoneChange-ETB + WAS_KICKED condition.
- T4 cast-conditional: `When you cast this spell, if it was kicked, E` → CastSpellEvent self-filter.
- T5 spell-effect branch: `If this spell was kicked, E` → Conditional(WAS_KICKED, E, else=base
  continuation) and `If this spell was kicked, INSTEAD E'` → Conditional(WAS_KICKED, E', else=base).
- T6 counters-on-enter: `If this creature was kicked, it enters with N +1/+1 counters` → per the
  equivalence above: separate ETB trigger + condition (no else).

## Explicitly DEFERRED (gap ledger — honesty law, counted not deleted) → ZND-2
13 rows of pure-remainder deferred sub-shapes where noted; first-kicker discount (Vine Gecko,
"the first kicked spell you cast each turn" = new per-turn-counter count state + CostModifier — its
own round); Kicker {X} (Thieving Skydiver — X-announcement + kick interaction); "choose any number
instead" (kicker gate on Choose count); "Spend this mana only to cast kicked spells" (mana-restrict
filter — check existing spend-lane first); multi-mode/variant kickers (none in ZNR text, census says).

## Engine wave ZND-1e (playability, separate landing after compile round goes green)
SpellObject `kicked` flag recorded at cast when the kicker cost was paid; the KICK DECISION itself =
a decision atom per §9/{operation: may-pay} — ask lane; trigger delivery + predicate interpretation
in legality/query; engine_supported gating for kick-family until delivery lands (PC-7 honesty).

## Byte-stability + gates (binding exit criteria)
M21: PC-4 0 diffs; report content byte-identical vs `/tmp/opencode/grammar_m21_prechange.json`
(timestamp/latency exempt); core suite green; pyright 0; ruff Δ0. ZNR: PC-1/PC-2 measured uplift vs
0.1418 / 0.2809; residual kicker rows registered (not deleted); bucket pins bumped per house law.
Fresh-eyes adversarial on the DIFF + this spec after implementation, before commit.
