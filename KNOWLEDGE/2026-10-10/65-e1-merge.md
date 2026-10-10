# 65 — E1 merge: one {controller-direction} axis (CONTROLLER_IS), event-field & BF-seat folds

Charter: AGENTS.md §9 (merge ledger E1 — "direction must have ONE encoding"; today split
between `event.controller` ControllerRef fields and `FAtomPred.CONTROLLER_IS` subject
filters). Executed 2026-10-10 per the approved adversarially-audited design package.

## The surviving axis (target encoding)
CONTROLLER_IS = live-controller read: `executor/selectors.controller_of` (quantity.py
:848-867 evaluator) consults the executor's GAIN_CONTROL overlay; player-subject
self-rule (`binding._player_subject_verdict`, binding.py:228 + quantity.py player-branch)
makes the atom honest when the subject IS a seat. Every direction in a card tree is now
`FAtom(pred=CONTROLLER_IS, who=YOU|OPPONENT|TARGET_PLAYER|referent-Selector)`.

## FOLD A — event `controller` fields -> per-event actor Filter slot
New slot on the six event classes: `actor: Filter | None = None` (omit-if-empty;
evaluated with `eval_filter` over the JOURNALLED ACTOR HANDLE, which each event row
already carries). Folded template output is always the pure atom
`FAtom(CONTROLLER_IS, who=<ref>)`; `ControllerRef.ANY` folds to `actor=None` (no
direction). Golden sites: 42 (43 nodes; the one ANY-direction TurnPhase node omits).

| Event class (old field)              | actor handle (journal source)                                | golden sites |
|--------------------------------------|--------------------------------------------------------------|--------------|
| TurnPhaseEvent.controller            | active player — `event.phase[1]`                             | 22 YOU + 1 ANY→None |
| CardDrawnEvent.controller            | drawer — `event.draw[0]`                                     | 7 YOU |
| SacrificeEvent.controller            | sacrificer — journalled `owner_before` of the SACRIFICE move (engine's frozen attribution) | 1 YOU |
| LoyaltyActivatedEvent.controller     | activator — `event.cause` (CR 606.3 seat)                    | 1 YOU |
| LifeGainedEvent.controller           | gaining player — `event.subject`                             | 3 YOU |
| CastSpellEvent.controller            | caster — `event.cast[0]`                                     | 6 YOU + 2 OPPONENT |

StepEvent keeps its ControllerRef: emitted by NO template and present in NO golden
(pool has no step-level triggers, ability_tree.py:798) — it is dead surface, zero
style-A sites in trees; folding it would be churn, deleting it is out of scope.
No event ever carried OWNER/ALL_OPPONENTS direction in goldens (verified scan).

## FOLD B — BATTLEFIELD enumeration seats -> BF-ANY + CONTROLLER_IS filter
The battlefield is ONE shared zone; `Zone(BATTLEFIELD, <seat>)` in an ENUMERATION seat
re-encoded direction as a container (style A, GAIN_CONTROL-blind: `enumerate_zone`
loops per-seat entries = zone-owner reads, selectors.py:145-220). Fold:
`zone -> Zone(BATTLEFIELD, ANY)` and `filter -> FAnd((orig..., FAtom(CONTROLLER_IS,
who=<seat>)))` — most seat selectors ALREADY carried the matching CONTROLLER_IS atom
(the zone seat was redundant direction); sites without it gain the atom. Overlay-aware
read comes free via the evaluator's controller_of.

Golden BF-seat census (156 non-ANY seats): YOU 152, TARGET_PLAYER 2, OPPONENT 1,
ALL_OPPONENTS 1. Split by parent slot:
- FOLD (enumeration seats, ~75 golden nodes): Selector.zone YOU 72 + TARGET_PLAYER 1
  (Teferi, Timeless Voyager; filter already CONTROLLER_IS TARGET_PLAYER) +
  ALL_OPPONENTS 1 (Waker of Waves; filter already CONTROLLER_IS OPPONENT — per-opponent
  match == ALL_OPPONENTS enumeration in the two-seat model); verb-atom Selector values
  in AtomArgs.pairs (incl. Transmogrify s1 exile-target BF-ANY — unchanged);
  count/search-pred seats: FAtom MOVED_TO_ZONE_THIS_TURN.from_zone YOU 1 (Barrin s2 —
  fold per package: the journalled-move matcher re-reads it as an event-endpoint…
  see KEEP note below), SEARCH-atom enumeration zones.
- KEEP (NOT direction — container/address/assignment semantics):
  * `Zone.controller` on per-player kinds (HAND/GRAVEYARD/LIBRARY/…): true containers.
  * ZoneChangeEvent endpoints (`to_zone` YOU 66 / `to_zone` OPPONENT 1 / `from_zone`
    YOU 1): scoped against the JOURNALLED owner_before/after (`_zone_matches`,
    binding.py:1030-1053) — an ownership endpoint, not a control read. OWNER is
    exactly right there.
  * Verb destinations (`("destination"/"source", Zone)` pairs, `_v_move_zone`
    verbs.py:252, CR 302.2b): the destination zone's controller IS the mover-side
    assignment the verb implements (put-into-play UNDER <ref>), not a filter.
  * `CastSpellEvent.from_zone(_not)` (binding.py:992-1005): endpoint scopes the CASTER.
  * Verb `("controller", ControllerRef)` role pairs (verbs.py:387, legality.py
    1412/1464): verb-argument seats (whose library/library-mill etc.), resolved by the
    handler, not a tree filter.
  * PLAYER zones: seat enumeration by definition.
  * CostModifier.controller_ref: static cost-modifier applicability metadata.
  NOTE: the design package's "YOU 152" is the whole-seat census (the KEEP endpoints are
  the 66+12 majority of it); the FOLD operates on the enumeration subset. This
  reconciliation was verified against the golden parent-slot scan, not assumed.

## FIX-1 (rules-fix, expected diffs) — overlay awareness
Pre-fold, BF-per-seat enumeration read zone OWNER (per-seat entries; GAIN_CONTROL-blind,
verbs.py:1810 writes an overlay the seat read never consults). Post-fold, CONTROLLER_IS
reads `controller_of` = overlay wins. Scenario diffs on
`tools/scenarios/traitorous_greed.json`, `traitorous_greed_g_spinner.json`,
`enthralling_hold.json` are CORRECTED semantics (a creature under my control via a
control-steal IS "a creature I control" for enumerate/count/trigger matching, CR 611.1's
control-change layer), individually justified in the gate notes — never silenced.
New truth-table test pins the overlay semantics (see test_executor_e1_direction.py).

## FIX-2 — designation-lane scan must see folded lanes
`binding.py:1338-1345` (designation scan over `node.effect` Atom args) flagged
`reads_target_player` from `ControllerRef.TARGET_PLAYER` values and
`Zone.controller is TARGET_PLAYER`. FOLD B removes the Zone route for folded seats, so
the scan NOW ALSO matches `FAtom(CONTROLLER_IS, who=TARGET_PLAYER)` nested inside any
Filter value (incl. inside `Selector.filter`, under FAnd/FOr/FNot). Without it the flag
silently flips and the target-player designation never opens (Teferi TV / Transmogrify
lanes). New lane test pins both match-routes.

## SAFE facts (verified, why ask/training surfaces hold)
- `site_digest` = sha1 over the CANDIDATE PAYLOAD only (decisions.py:61-66): ask bytes
  are stable modulo FIX-1 behavior changes.
- `from_dict` is strict (ability_tree.py:4471-4477): old-field goldens + new code cannot
  half-load; goldens and code flip atomically within one worktree state.
- clause_audit.py has ZERO 'controller' references — its clause-shape gate is
  insensitive to this merge.

## Retraining cost (report only; orchestrator re-sweeps)
Encoder ground rows embed the IR repr -> episodes_v2 must RE-ENCODE the corpus
('controllers_is' is already in the vocab, so the token space does not change); every
existing checkpoint is stale against the new encoding.

## Census (tools/audit/atomics_census.py)
Before (2026-10-10 pre-fold, `python3 tools/audit/atomics_census.py`):
event_direction_field 42/41 trees, event_direction_controllers_is 89/63,
event_direction_both_styles 10, zone seat field 376/165.
After: direction encodes ONLY as CONTROLLER_IS (style-B count > 0; event-field and
both-styles == 0); zone.controller reclassified as informational `zone_container_seat`
(container census context, incl. kept endpoints/destinations). Final numbers below the
gate block.

## Completion (2026-10-10)

### Barrin, Central Conservatory — KEEP decision (fold-candidate rejected)
templates_b2a MOVED_TO_ZONE_THIS_TURN from_zone=BF/YOU stays a seated zone:
quantity.py:1126-1175 reads the zone-slot controllers to partition movers by owner;
folding the seat to ANY+CONTROLLER_IS would broaden the quantity semantics (the zone
node here is a QUERY SCOPE, not a selector menu). Rule of thumb recorded: a Zone node
that names a query scope with per-controller columns keeps its seat; a Zone node that
names a selector menu folds to ANY + CONTROLLER_IS in the filter.

### Final census (`python3 tools/audit/atomics_census.py`, 2026-10-10 post-E1)
event_direction_field 42/41 -> 0 (now a zero-hit tripwire), event_direction_both_styles
10 -> 0, event_direction_controllers_is 89/63 -> 173/121 (all direction traffic),
zone seat field 376/165 -> zone_container_seat 302/128 (container seats + kept
ZoneChange endpoints/destinations only), NEW tripwire battlefield_zone_seat_drift 0/0
(BF selector seats must be ANY; ZoneChangeEvent/Atom from_zone seats are legit and
excluded by parent_tag=="Selector").

### Gates (all executed 2026-10-10)
- `pytest MTG_bot/core tools/audit tools/training -q` -> 2685 passed, 2 subtests
- `python3 tools/run_scenarios.py` -> 398/398 packs (traitorous_greed trio byte-stable:
  E1 preserves observables; the expected FIX-1 diffs had already been absorbed by the
  golden regeneration)
- `python3 tools/audit/clause_audit.py` -> 589/589 mapped, 100.0% zero-loss, 0 residuals
- goldens PC-2 639/639, PC-4 0 diffs, PC-9 stable, PC-10 PASS; 91 golden files changed
- serialization pins: r5 _NEW_PINS (5) + t3/t3r2 _PINNED (planeswalker_emblem,
  token_creator) re-pinned via at.fingerprint(build()); omit-key contracts updated
  (CastSpellEvent controller->actor)

### Corpus consequence (unchanged from design, now binding)
'controllers_is' was already in vocab -> token space unchanged; episodes_v2 MUST
re-encode the corpus against the new IR repr; every checkpoint is stale for the
event-direction axis.
