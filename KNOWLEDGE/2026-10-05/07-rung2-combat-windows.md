# 07 — Rung 2: the combat-instant response window (landed 2026-10-05)

Batch 2 of the response-window arc (`02-response-window-design.md` §F).
Engine: one call-site in `combat_step`. Rig: one ask lane + two expect
lanes. Corpus: 8 packs incl. negative twins. Compiler/goldens untouched.

## A. The engine window

`MTG_bot/core/executor/__init__.py::combat_step`, inserted BETWEEN the
post-declare-blockers `_settle()` and the damage step `_combat_damage()`:

```python
if self.attackers:
    open_combat_window(self)
```

* `open_combat_window` (stack.py) asks each seat **once, in player order**
  (active first, CR 506.4 reading) via `executor.decisions.take(vocab, tag)`.
* **Vocab gate** re-applies the four Rung-1 rules verbatim (they exist
  because of the seed-16/96 crash class), narrowed to COMBAT relevance:
  1. INSTANT kind + tree contains a `_COMBAT_INSTANT_ATOMS` verb
     (`DEAL_DAMAGE`, `MODIFY_PT`, `SET_PT`) + `spell_castable`;
  2. verb closure ⊆ `HANDLERS`;
  3. designable: exactly one target slot with `min_count<=1<=max_count`,
     every candidate token checked via `validate_target_selection`;
  4. modeless (a `Choose` node is skipped).
* **Token shape:** `<card handle>@<target handle>` — the target rides
  INSIDE the word (burn answers the whole population; no forced
  auto-designation). Vocab = `("PASS",) + tuple(sorted(options))`.
* **Journal:** reuses `KIND_WINDOW_OPEN`/`KIND_WINDOW_PASS`, subject
  `None`, cause = seat, `cause_verb="COMBAT_WINDOW"`, site tag
  `cw:<seat handle>:<digest>`, digest = `site_digest(("combat-window",
  str(clock)))`. Zero-vocab seat: NO ask, NO row (C15). The window itself
  does not bump `fired` — casts settle internally (SBA + triggers), the
  Rung-1 nesting of their counter windows is free.
* **Documented narrowing (pinned by `cw_single_round`):** ONE priority
  round, no re-asks. A real CR 510 multi-pass window hands priority back
  after each answer; this rung does not — the un-answered kill-shot
  ordering stands as engine debt, pinned rather than hidden.

## B. The negative-power discovery (real crash, honest fix)

First games gate after landing: seeds 10/73 crashed
`ValueError: QConst: negative quantity rejected: -1` in
`_combat_damage_atom`. Culprit (instrumented repro): **Carrion Grub** —
its own BLOCKED trigger records a raw `-4/-4` Eot delta on the ledger,
and the base line pushes effective power to **-1** before the damage
step. The lane only guarded `if not power:` (zero/None).

* Pre-existing latent bug: Grub crashing on a block needs NO window —
  the blocked-trigger fires at declare-blockers, damage follows
  immediately; the baseline corpus simply never had Grub block (the
  window's rng consumption shifted deal paths and surfaced it).
* Fix (`__init__.py` `_damage_wave`): `if not power or power < 0:
  continue` — damage is never negative; a non-positive dealer deals
  nothing (CR 120.7 reading).
* Pin: `test_executor_rung2.py::test_negative_power_dealer_deals_no_damage`
  (real Carrion Grub blocking; pre-fix the pin raises).
* Structural lesson for Rung 3+: **the window made P/T mutations land
  between declaration and damage**; every damage-lane consumer of
  `effective_pt` must treat the whole non-positive half-line as skip.

## C. Rig lanes (`tools/run_scenarios.py`)

* `_combat.answer()` intercepts `cw:` tags FIRST (arrival order: window
  asks precede post-damage dies asks), pops the r22a `decisions` script,
  resolves words via `_resolve_word` (pack keys, `p0`/`p1`, composite
  `a@b` recursive), and **falls back to PASS** when no word is scripted
  or the word is not in vocab (engine never defaults; rig-side only,
  owner ruling (a) precedent).
* Expect lanes: `combat_window_asks` (seat→ordered answers) and
  `combat_window_vocab` (**flat list, arrival order** — same convention
  as `window_vocab`; a seat-dict pin silently iterates keys, discovered
  the hard way).
* Edge noted: a nested `counter:` ask raised INSIDE a combat step rides
  the generic script path, not `rung1_asks` — unexercised by the corpus.

## D. Corpus (8 packs, `tools/scenarios/cw_*.json`)

| pack | shape | twin |
| --- | --- | --- |
| cw_burn_blocker | burn kills blocker pre-fight, attacker unblocked | cw_no_instant_negative |
| cw_burn_attacker | H3-REVERSAL: unblocked attacker burned pre-damage | (no ask when hand empty) |
| cw_burn_then_pump | both seats act, second vocab POST-burn state | — |
| cw_pump_threshold | pump over lethality, blocker survives marked | cw_pump_threshold_negative |
| cw_priority_burns | mutual burns, zero combat damage, **dead blocker vanishes from P1's vocab** | — |
| cw_single_round | one-round narrowing pin (PASS stands, no re-ask) | — |

Corrections learned while pinning: the damage ledger PERSISTS on
survivors (surviving blocker pins its marks; `{}` means "no marks on
anyone"); Shock is 2 damage — a 3/3 target does NOT die (two packs
needed 2-toughness bodies or extra marks).

## E. Gates (all 2026-10-05)

| gate | result |
| --- | --- |
| `tools/run_scenarios.py` | **355/355** (347 pre-existing byte-identical via PASS fallback) |
| pytest `MTG_bot/core` | **2386 passed + 2 subtests** (2379+2 baseline, +7 rung2 pins) |
| `measure_grammar --set M21` | PC-1 0.9934 / PC-2 0.9969 / PC-3 0 / PC-4 0 diffs — **Δ0**, no golden moved |
| games `--seeds 100 --pool all` | **0 crash classes**, 98 decisive (51/47) + 2 caps, mean **34.07** (was 33.93) |
| window stats (instrumented rerun) | **84 combat-window opens, 28 PASS → 56 instants cast**; counter windows 14 opens (combat lane 6× the Rung-1 lane) |
| catalog | repinned **4136 entries / 10 games**, post **0/10 diverge**, md5 `8b76978758164fddaf87fb2afdf7137c` |
| pyright | 0 new (baseline Counter/type-error noise unchanged) |
| ruff | Δ0 (N999/I001/TRY004/BLE001 all pre-existing at HEAD) |

## F. H3-pair adjudication (malefic_scythe × wildwood_scourge era premise)

Both packs hold ONLY their eponymous artifact — no instant in either
hand, so the window never asks and both stay byte-identical. The era
premise "go-wide combat is threat-free" is thereby **falsified in
general, preserved vacuously in these two packs**: threat-free now
CONDITIONALLY means "opponent's hand holds no payable combat instant".
The reversal is pinned positively by `cw_burn_attacker` (the unblocked
attacker dies before the damage step).

## G. Exploit-transfer re-measure (E1 correction)

`.venv/bin/python tools/audit/exploit/noisy_policy.py 25` post-window:

| metric | before | after |
| --- | --- | --- |
| WR vs pure-random (eps=0) | 0.820 | **0.860** |
| robust band (eps .5–1.0) | 0.590 | **0.590** |
| exploit gap | 0.230 | **0.270** |
| curve A slope | −0.314 | −0.351 |
| curve B slope | +0.281 | +0.314 |

Reading (honest, both directions reported): the window **widens the
exploit gap**. Scripted answers (targeted burn/pump) convert window
opens into wins; the uniform-random policy wastes most opens (28/84
PASS by chance, misfires elsewhere). The ROBUST FLOOR IS UNCHANGED —
Rung 2 raised the scripted ceiling and the random-policy noise surface,
not the floor. Headline vs-random numbers are now MORE inflated; Batch 3
(training re-baseline) should feed `cw:` asks to the policy learner.
