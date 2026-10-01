# 23 — Wave-5 fix-a (r22a): own-dies trigger law, sacrifice-victim vocabulary, dies-designation gate

Batch: fix-batch **22a** of the wave-5 suspect backlog (engine editing
authorized; findings in 21/22). HEAD at start: `ae0fbe4`. Engine edits
limited to `binding.py` + `legality.py`; `state.py`, IR/goldens, findings
docs FROZEN; no commits. Final gates executed 2026-10-02.

## Verdicts (6 suspects + 2 collateral packs)

| Suspect | Verdict | Root cause / disposition |
|---|---|---|
| Deathbloom Thallid (own dies → spore) | **FIXED → promoted** | own-dies law, engine change 1 below |
| Spirit of Malevolence (own dies draw) | **FIXED → promoted** | same law |
| Goblin Arsonist (dies → any target) | **FIXED → promoted** | own-dies law + dies-designation gate (change 2); pack's combat step now scripts `decisions:["player:1"]` — the CR 603.1 designation ask fires BEFORE the may-offer |
| Pitchburn Devils (dies → any target) | **FIXED → promoted** | same gate; designation ask first, then may |
| Conclave Mentor (dies counter-replacement) | **STOP → batch 22b** | dies lane PASSES now (life 22 via the QProp leg); the remaining leg is `CounterPlacedEvent` replacement — replacement-feed for placed-counter events is binding.py:718 trigger-only today. Stays suspect, expectation byte-unchanged |
| Havoc Jester / Spellgorger (green packs) | **RE-SCRIPTED, asserts byte-unchanged** | their sacrifice costs became ASK sites (change 3). Victim word front-loaded in the decisions list (ask order: sac ask then designation ask); the old "sacrifice paid SILENTLY" notes replaced. Byte-exact asserts now PROVE the asks fired — an unfired ask spills the victim word into the next site and breaks the pack |

## Engine changes (systematic laws, 2 files, uncommitted)

1. **Own-dies law** (`binding.py::_pending_dies_detach`): a leaver's OWN
   "whenever ~ dies" binding detached before its CREATURE_DIES row was
   delivered — the trigger could never fire (CR 603.2 says it fires from
   the graveyard zone). Detach now DEFERS: the zone-change drain
   lookaheads ZC→CD adjacency, the CD row detaches only after firing, and
   an end-of-pass flush guarantees no live binding survives for a leaver.
   Survivor triggers and the deferred-detach end state are untouched
   (pinned: `binder.attached` sweep).
2. **Dies-designation gate** (`binding.py::_fire` + `_trigger_designates_target`):
   the 16a/18b fire-time `target = event.subject` anaphora pre-bind only
   applies when the effect merely READS the anaphora (referent-shaped —
   Massacre Wurm's "that player"). A trigger carrying its OWN TARGET-mode
   referent-less Selector (Arsonist/Pitchburn "any target") is detected by
   walking the effect tree (root Atoms included — `walk()` yields the
   root) and routes to the real 18b designation ask.
3. **Sacrifice-victim vocabulary** (`legality.py`): `PaymentPlan` records
   the sacrifice candidate pool; `pay_costs` ASKS through the 14b channel
   (site `sacrifice:{seat}:{source}:{digest}`, Handle-sorted vocab) when
   the pool offers a real choice; a forced pool (single candidate / self-
   sac-only) stays silent (§1.4). `build_payment_plan` itself never asks.
   No lane → `take_decision` RAISES (C15, never a default) — pinned.
   **Design ruling:** the victim is NOT honored via activation `targets`
   pre-binding — CR 601.2b (cost choice) and 601.2c (designation) are
   separate choices; the folded `targets` field conflates them. Packs are
   self-verifying under the pure-ask channel.
4. **CR 701.14a latent rule fix** (`legality.py::build_payment_plan`
   CostSacrifice branch): the bridge compiles "Sacrifice another creature"
   with a `BATTLEFIELD controller=ANY` zone + `Creature AND NOT IS_SOURCE`
   filter, so the candidate pool contained **opponent's creatures** — the
   engine could sacrifice your own creature pool widened to enemy permanents
   (previously masked by the lowest-handle auto-pick witness). Pool now
   filtered to `world.controller_of(h) == ctx.controller`.

## Harness changes (`tools/run_scenarios.py`)

- `run_pack` catches ANY ScenarioRunner setup exception → that pack's
  result line (`setup: Type: msg`), so one bad pool can't kill a sweep.
- `_combat` gained a generic `decisions` script queue popped only for
  sites no answer-map/queue claims (pack-key→handle mapping included);
  pre-16c combat packs byte-identical.

## New pins (`MTG_bot/core/test_executor_r22a.py`, 10 tests)

SacrificeVocabulary ×6 (ask+answer, forced-silent, self-sac, CR 701.14a
exclusion, no-lane raise, frozen-plan byte check) · OwnDiesTrigger ×2
(own trigger fires + deferred detach still lands; survivor twin) ·
DesignationPrebindGate ×2 (TARGET-shape asks; referent-shape never asks).
**Rig law learned the hard way:** a designation with ONE candidate is
FORCED auto-fill, no ask (§1.4/C15) — the gate pin initially starved its
own ask by leaving a single survivor; two survivors are required to make
the TARGET slot a decision.

## Gates (2026-10-02)

scenarios **278/278** (274 + 4 promotions, 2 re-scripts) · suspects
**1/21** fail-only as expected (secure_the_scene; conclave fails on the
22b counter leg only) · core suite **2249 + 3 subtests, 0 fail** (2239+10)
· PC-1 **301/305**, PC-2 **634/639**, PC-3 **0**, PC-4 **0** EXACT ·
traces **0/10 diverge, NO repin** · games **0 crash classes / 100 seeds**
(86 survived, mean 57.69) · pyright Δ0 (6 pre-existing run_scenarios
reportAssignmentType) · ruff Δ0 (2 pre-existing; new except carries
`noqa: BLE001`).

## Open for next wave

- **22b**: Conclave Mentor `CounterPlacedEvent` replacement feed (lane A).
- **New suspect observed, not yet adjudicated**: the "any target"
  designation vocabulary over-includes — the arsonist combat repro showed
  library/graveyard handles (`card:0..card:13`) in the answerable vocab.
  Candidate-population question for `query.legal_targets`/`_widen_any_target`.
