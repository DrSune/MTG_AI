# 2026-09-15 / 03 — ability_tree: grammar review fixes (player referents, Quantity count, duration role)

Follow-up to the ability-tree grammar review. `MTG_bot/core/ability_tree.py`
and `test_ability_tree.py` received three surgical fixes against the spec.
Constraint held throughout: no restructuring, no public-name renames, no
changes to the Verb or Predicate sets — only the closed tables and slot
types were widened.

## Fixes

### 1. Player referents (Commander format)

Added two enum members:

- `ZoneKind.PLAYER = "PLAYER"` — the player object itself; the only
  non-card target ("target player or players").
- `ControllerRef.TARGET_PLAYER = "TARGET_PLAYER"` — "the target player",
  the spell's target when it is a player.

`CONTROLLER_IS` now accepts `TARGET_PLAYER` in addition to `YOU` and
`OPPONENT`. The validation error reads
`FAtom: CONTROLLER_IS who must be you, opponent, or the target player`.

Why: the pool targets Commander, where player-targeting card text is legal
— "Players, you may each pay {1}..." and "the target player's library".
Without a player referent the grammar cannot express these cards at all.
The round-trip catalog gains `Zone-PLAYER` automatically via the existing
`ZoneKind` iteration, plus an explicit `Selector-target-player` and
`FAtom-CONTROLLER_IS-target-player` entry.

### 2. `FAtom.count` is now a `Quantity`

Before: `count: int = 0` (unset detected by `count == 0`).
After: `count: Quantity | None = None` (unset detected by `count is None`,
with `colors == ()` kept as the tuple analogue).

Why: a dynamic threshold is as legal as a literal — e.g. "cards with CMC
less than or equal to the number of cards in your hand" is a
`QProp("controller", CARDS_IN_HAND)` threshold, which an `int` slot
cannot express. The other threshold-taking nodes (`Selector.count`,
`Choose.count`, `Repeat.count`, `CostPutCounter.count`) were already
`Quantity`; `FAtom` was the outlier.

Timing: no golden files exist yet, so changing the serialized form now is
the "fix before goldens exist" moment — once goldens exist, this change
would have been a golden-reingest event.

Consequences:

- Unset/required-slot detection in `FAtom.__post_init__` uses
  `value is None` (colors: `== ()`); required-count predicates
  (`_FATOM_RULES`: COLOR_COUNT_GE, CMC_LE/GE, PT_LE/GE, HAS_COUNTER,
  CONTROLLER_COUNT_GE/LE) still reject a missing count.
- The static `count >= 1` rules for COLOR_COUNT_GE and HAS_COUNTER are
  narrowed to `isinstance(self.count, QConst) and self.count.value < 1` —
  a dynamic threshold cannot be statically compared and is accepted.
- `_SPECS` FAtom row: `("count", "int")` → `("count", "opt:quantity")`;
  `None` serializes as `null`, `QConst(3)` as `{"tag":"QConst","value":3}`.
  `to_dict` is generic over dataclass fields, so no other encoder change
  was needed; `from_dict` stays strict (missing/extra field raises).
- `QConst` rejects negative values at construction, so the old
  "FAtom negative count" failure case became "FAtom non-quantity count"
  (`count="2"`); new error `FAtom: count must be a Quantity, got ...`.
- `compiler.py` and `test_compiler.py` needed NO changes: their `count=`
  call sites are `Choose`/`Repeat`/`Selector`, not `FAtom` (verified by
  repo-wide grep).

New catalog entry: `FAtom-CMC_LE-dynamic-count` (dynamic `QProp`
threshold) so the dynamic-threshold path is pinned by round-trip.

### 3. `duration` role for TAP / UNTAP / MANDATE_ATTACK

`_VERB_ROLES` gains `"duration": False` (optional) for `Verb.TAP`,
`Verb.UNTAP`, and `Verb.MANDATE_ATTACK`. The duration role previously
existed only for MODIFY_PT, SET_PT, GRANT_ABILITY, GRANT_TYPE, and
PREVENT_EFFECT.

Why: a tap or untap is a temporary effect ("tapped until end of turn"),
and MANDATE_ATTACK is the continuous "these creatures attack each combat
if able". The closed role table is now complete for the effect-verb
family; the header comment records the rationale. New catalog entries:
`Atom-TAP-duration` (`DurationEot`), `Atom-UNTAP-duration`
(`DurationPermanent`), `Atom-MANDATE_ATTACK-duration`
(`DurationUntilNextTurn`).

## Test updates

- Every `count=int` FAtom call converted to `count=at.QConst(n)` —
  catalog (COLOR_COUNT_GE, CMC_LE/GE, PT_LE/GE, HAS_COUNTER,
  CONTROLLER_COUNT_GE/LE), the `_token_creator` condition, and all
  validation-case constructions.
- 6 new `_all_nodes()` catalog entries (Selector-target-player,
  FAtom-CONTROLLER_IS-target-player, FAtom-CMC_LE-dynamic-count,
  Atom-TAP/UNTAP/MANDATE_ATTACK-duration); `Zone-PLAYER` is auto-included
  by the `ZoneKind` iteration.
- 1 new validation failure case: `FAtom CONTROLLER_IS with ALL_OPPONENTS`
  (still rejected — only you/opponent/target-player are legal).

## Better-than-spec design assets (confirmed during review)

1. `AtomArgs` stores sorted pairs — the canonical fingerprint is
   construction-order independent.
2. One `FAtom` class plus the closed slot table `_FATOM_RULES` instead of
   ~40 predicate classes; the encoder tag space stays small.
3. `Zone(ANY, ANY)` multi-zone generalization — covers Necromentia-style
   "hand or graveyard" targets without a dedicated zone.
4. `QUnbounded` and `QProp("event", ...)` are not in the spec but are
   required by pool cards (unbounded "all" selections; event-based
   amounts).
5. Strict `from_dict` (unknown tag / missing field / extra field / wrong
   value type all raise) — golden re-ingest diffs will be auditable.

## Measurements

Exit gate:

```bash
cd /home/sune/Desktop/MTG_AI && source .venv/bin/activate
python -m pytest MTG_bot/core -q
/home/sune/.local/bin/pyright MTG_bot/core/ability_tree.py MTG_bot/core/test_ability_tree.py
```

| Number | Value | Command |
|---|---|---|
| core test state | **366 passed / 0 failed** (was 358) | `python -m pytest MTG_bot/core -q` |
| new parametrized tests | +8 (7 round-trip incl. auto `Zone-PLAYER` + 1 validation) | same |
| pyright ability tree | **0 errors, 0 warnings** | `/home/sune/.local/bin/pyright ability_tree.py test_ability_tree.py` |

Note: the IDE LSP may report `Import "pytest" could not be resolved` in
`test_ability_tree.py` — that is environmental (the IDE LSP lacks venv
context); the CLI pyright above resolves it with 0 errors, as it did for
the compiler package in session 4.

## Supersedes

- No baseline numbers superseded — the 358-test baseline of session 4
  still holds; this session adds 8 tests and no goldens exist yet.
- The FAtom serialization shape recorded for any future golden is the
  Quantity form (`{"tag":"QConst","value":n}` / `null`), not the old
  `int` form.
