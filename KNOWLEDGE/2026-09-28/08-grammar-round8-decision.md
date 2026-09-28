# 2026-09-28 · 08 — Grammar round 8 BINDING spec (decision-surface fidelity + residual families)

Status: BINDING (analyst draft re-anchored + orchestrator-verified at HEAD 95dea3a: QAtLeast L684 /
Quantity union L700; QBinOp L303 DIV already documents round-up=(n+1)//2 → Peer needs NO new op;
TokenSpec _SPECS L3115, _OMIT_IF_EMPTY tag-map L3296-3318 has NO TokenSpec row (dual registration
needed); CostDeltaReduceGeneric L1794; ThisTurnKind L315; emblem standalone-assembly at
compiler.py:1115+; CAST+CHOOSE+OptionalEffect precedent b4:680). Conventions C1–C16 in force.
Phase plan (autonomous per /04): 8-A grammar → 8-B fidelity flip pass (dedicated golden audit) →
8-C coverage batch (21 rows) → measure. F-MANA family (Vodalian, Orrery-spend-any; MANA_POLICY
verb) DEFERRED to R9: executor-heavy mana-pay semantics for 1-card unlock.

## Grammar items (8-A, all additive; ability_tree.py + tests in test_ability_tree_r9.py — offset rule)

- R8-1 (F1/C-1): `@dataclass QAtMost(n:int>=1)` after QAtLeast + `Quantity` union += QAtMost +
  `_SPECS "QAtMost":(("n","int"),)` + `_QUANTITY_TAGS`. Selector TARGET-mode validation already
  permits (only rejects QUnbounded, L786-793 verified). TARGET docstring amended per C17.
- R8-2 (F2/C-2): `TokenSpec.color: str | None = None` TRAILING field; `_SPECS["TokenSpec"] +=
  ("color","opt:str")`; `_OMIT_IF_EMPTY += "TokenSpec": frozenset({"color"})` (dict currently has
  no TokenSpec row — add). Same pattern for R8-4 flags.
- R8-3 (F3/C-3): AtomArgs color vocabulary += "ANY" (L1908 site) — "mana of any one color".
- R8-4: `TokenSpec.enters_tapped: bool|None`, `enters_attacking: bool|None` trailing; specs/omit
  registration shared with R8-2 (Basri Ket [−2] tokens).
- R8-5 (F4): `_VERB_ROLES[DEAL_DAMAGE]` += optional "source","recipient" roles (AtomArgs
  serialization carries them; no new _SPECS field).
- R8-6: FAtomPred.IS_EXILED_WITH_SOURCE (slots: none needed — evaluated against source of
  ability; anchor enum tail) — HoF/Idol "cards exiled with/this way" permission scoping.
- R8-7: Verb.GET_EMBLEM (roles {emblem_ref?} — NONE: card-level emblem attach already exists
  (compiler:1115 two-pass); verb is a marker + optional Selector-free) per C19.
- R8-8: Verb.PLAY_LAND_EXTRA (roles {count False, duration False}) — Azusa "play two additional
  lands". (Name to implementer's judgment; docstring cites Azusa.)
- R8-9: FAtomPred.CONTROLLER_COUNT_GT (two-count comparison slots {left_filter, right_filter}
  — Garruk "controls more creatures than you"; if FAtom lacks dual-filter slots, prefer
  QBin/Quantity-compare via Conditional pred — implementer picks minimal additive shape).
- R8-10: ThisTurnKind.NONCOMBAT_DAMAGE member (Chandra's Incinerator {X} where X=total).
- R8-11: QProp COUNTER_COUNT referent tuple (L618-622) += "target" (Invigorating Surge
  double-counters-on-target). Validation-only.

## Conventions (new, binding)

- C17 TARGET-up-to = TARGET mode + `QAtMost(n)`: legal designation 1..n (targeted), resolves
  0..remaining (executor clamp). REJECTED alternatives: SelectorMode.TARGET_UP_TO (duplicates
  target semantics; can't cap counters), CHOOSE-for-targeted (would erase legal-target
  distribution — C15-violation). Resolution-time "up to N" (non-targeted, e.g. "fights up to
  one") STAYS CHOOSE.
- C18: "was <type>" = TYPE_EQ with referent="result" (value-at-antecedent-event snapshot;
  executor snapshots; r8-canonical).
- C19: emblem rows = GET_EMBLEM verb marker; quoted inner text NEVER enters IR payload — the
  emblem pool-entry's own compiled abilities are the payload via card-level attach (mandate /04 §2).

## 8-B fidelity flip pass (after 8-A, before 8-C)

Flip lossy→faithful in EXISTING templates (each: docstring note updated, goldens move — dedicated
re-baseline audit, abilities/keywords/... payload-only rule, vs pre-8B snapshot):
- F1: 10 targeted "up to" templates TARGET-QConst→QAtMost: b2a:2060,2246,2274; b5b:2356,2388,2466;
  b5c:2365,2440,2450,2995. KEEP CHOOSE at b5c:3014, b5c:2607 (resolution-time).
- F2: token rows with color text — b2a ~5 + b2b ~4 sites (only M21-text-bearing rows; report exact
  list).
- F3: 2 any-color ADD_MANA rows ("C"→"ANY").
- F4: ~2 b2b noncombat damage rows + Nine Lives recipient ("to you" restored, lossy note removed).
Acceptance: pre-8A grammar phase 0 golden diffs; post-8-B every changed golden diff explained by
exactly one flip family; PC-1/PC-2 UNCHANGED (fidelity ≠ coverage); PC-3 0; suite green.

## 8-C coverage batch (21 rows per analyst D5 — bucket owners verified)

b5c 5 (emblems ×3, perms ×2) · b4 5 (Azusa, cast-them, Furious Rise, Teferi gate; Orrery-spend
OUT) · b3 1 (Idol may-cast) · b2b 1 (Kraken "When you do" — event binding: antecedent "you may
pay {1}" → re-examine with R8 grammar: if still no clean event, stays withdrawn — 1 shape) ·
b5b 5 (Ooze was-type C18, Round-up-each-time, Peer QBin draw+life, Invigorating double,
Garruk-compare) · + Shrine-cost (b5c), Incinerator (b4), Basri [−2] token-flags (b5c) as
per D5 rows. C15/C16 per-row decision lines. Prediction: PC-1 274→~289/305 (0.9475), PC-2
599→~620/639, queue 40→~19/19, orphans +2 (GET_EMBLEM used, PLAY_LAND_EXTRA used; precedent).

## Registered-DEFER → R9 queue (19 shapes)

as-though ×3 · activation-window ("Activate only as a sorcery/if…" ×2) · additional-trigger ·
quoted-token-abilities (Whale) · reveal-until dig ×2 (no CardRevealed event) · Chrome same-name ·
Mangara set-relation · Enthralling target-legality · Frost Breath untap-step scope (Step.UNTAP) ·
Orrery per-color draw · Subira delayed-trigger-in-duration · F-MANA ×2 (moved this round) ·
E-artifact quote row (split change refused — denominator frozen).
