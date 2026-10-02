# 08 — Compiler batch C5: phantom play-permission suppression + PREVENT_EFFECT (2026-10-02)

Target: roadmap batches 3+5 fused. Baseline HEAD `7f3879a` (23a). Three cards, three
outcomes: **Tampering** (compiler emission + one executor consumer), **Furious Rise**
(pure compiler suppression), **Rin and Seri** (STOP with written spec — premise falsified).
Golden law held: C1-form audited set-equality vs `/tmp/golden_pre_c5/` — movers were
EXACTLY 2 of 305 (`52b3a979…` Furious Rise, `e6ae536a…` Tampering); PC-4 0 diffs.

## 1. Destructive Tampering — can't-block clause becomes PREVENT_EFFECT

`_build_bullet_cant_block` (templates_b5c.py:1913ff) previously emitted a junk
shape; it now emits the real **`PREVENT_EFFECT`** verb with a universal condition
(the clause bans *any* blocker of the designated creature "this turn" =
`DurationEot`), plus `DeclareBlockersEvent` import. The block lane consumes it
via the replacement veto — **no `IS_ANY_TARGET` in the filter**, so the stale
`targets=(cog,)` that option 1's record inherits (from `_v_prevent` materializing
targets out of the designation) is inert here.

**Executor consumer fix (the one sanctioned engine edit)** — `_pair_vetoed`
(replacements.py:828) gated ALL replacements on `self._source_alive(rec.source)`.
Tampering is a sorcery: by the declare-blockers step it sits in the graveyard and
the veto silently died. Detach analysis settled the design question:
`binding._lifecycle` calls `detach_source` **only** on `from_state == ZONE_BATTLEFIELD`
— stack→GY never detaches — so the liveness gate itself was the sole blocker, not
detachment. Fix is the narrowest exemption:

> `if not isinstance(rec.duration, DurationEot) and not self._source_alive(rec.source): return False`

Static carriers (`duration=None`) KEEP the gate; Eot records expire exclusively via
`sweep_at_eot` (tag `"Eot"`), so the exemption cannot leak a veto past the turn.
Pins: `TestDurationEotSourceExemption` ×4 (test_executor_r21a.py:260) incl. graveyard
Eot veto lives, flying complement still vetoes after `layers.recompute()`.

**Out-of-scope finding (documented, not fixed):** Tampering's option-1 branch choice
requires an artifact designation the compiled IR never collects — branch entanglement
stays a compiler-campaign backlog item.

## 2. Furious Rise — anaphoric play-permission suppressed at assembly

The card's "you may play that card" outcome compiled into a 52-line phantom
activated-ability node (a `play` permission read as an ability of Furious Rise
itself). Compiler-side suppression: `_is_result_anaphoric_cast_permission`
(compiler.py:1035) recognizes a cast-permission outcome whose permission target is
result-anaphoric ("that card"), and the assembly pass (compiler.py:1477) DROPS it
with an explicit `KNOWN-GAP (play permission)` note — honest suppression beats a
phantom node; the play-permission lane itself is future engine+compiler work.

Golden `52b3a979…` shrinks by exactly the phantom. Refusal pins verified in the
promoted **negative** pack `furious_rise_activation.json`: idx0 →
`illegal activation: ability:not_activated`, idx1 → `no ability idx 1`; expectations
avoid the trigger lane entirely (`hand 0:1` accounts for the upkeep draw; ward library).

**Engine-batch observation (out of scope, recorded):** the end-step creature-4+ trigger
compiles to `TurnPhaseEvent(phase=END_TURN, controller=YOU)` and attaches fine — the
clock fires the phase event, but the existential condition
`FAnd(TYPE_EQ Creature, POWER_GE 4, CONTROLLER_IS YOU)` can never match because phase
events carry `subject=None`. End-step existential-condition triggers never queue in the
harness. This is an executor matching-semantics gap, not an emission defect.

## 3. Rin and Seri — STOP with spec; roadmap ingest premise FALSIFIED

The roadmap claimed the corpus text was an ingest that needed the +1/+1 statics and
dies triggers restored. It is not: `MTG_bot/data/M21.json` text == the **M21 print
#278 verbatim** (gatherer.wizards.com/M21/en-us/278/rin-and-seri-inseparable ·
scryfall.com/card/m21/278/rin-and-seri-inseparable), which genuinely OMITS those
clauses — they live on other printings (DKA/DMU family). So `unparsed=()` is honest,
the compiler emits the correct print, and the suspect's redness was pure **pack
hygiene** (no `mana` key for the +1/+1 counters cost, bogus Pridemalkin `targets`).

Disposition: suspect rm'd; corrected positive pack
`tools/scenarios/rin_and_seri_cast_triggers.json` pins what the printed M21 card
actually does (cast-trigger +1/+1 exchange + the legendary-dies clause absent — ward).
The 23a-era **GAIN_LIFE-split activation backlog remains open** (frozen-IR law;
dual-slot synthesis PITFALL stands); the guard is pinned by `rin_seri_static_guard`.

## Gates (all in order, all green)

audit set-equality (2 movers as predicted) → measure_grammar PC-3 0 / PC-4 0 verified
→ scenarios **300/300**, suspects 7→4 files, **0/4** → pytest **2312 + 3 subtests,
0 failed** → catalog **0/10 no repin** → games **0 crash classes**, 100 decisive 48/52,
mean_turns 33.49 = exact Δ0 vs 23a → pyright **Δ0 new** (6 pre-existing Counter FPs in
run_scenarios.py, untouched lines) → ruff **Δ0 NEW** (HEAD-borne BLE001/I001 identical;
HEAD copy must live INSIDE the repo — `/tmp` worktree silently loses config, 23a rail).
