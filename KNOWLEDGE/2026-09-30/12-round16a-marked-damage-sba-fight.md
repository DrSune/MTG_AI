# Round 16a — marked damage + SBA sweep + FIGHT + the TARGET_PLAYER designation fix (2026-09-30, uncommitted)

Phase 16a of the BINDING arc-3 plan (`11-round16-combat-plan.md`). Delivers CR-accurate
damage (marks, not instant-kill), the state-based-action sweep, `Verb.FIGHT`, the first
validation packs (per-phase DoD machinery), and the mandatory trace-diff catalog
reconciliation + repin.

## 1. Semantics shipped (executor only — grammar/goldens/state.py untouched)

- **Marked damage (CR 120.4-120.6, 704.5)**: `Executor` keeps a damage ledger
  (`Executor.damage`, per-handle, per-turn). `DEAL_DAMAGE` *marks* instead of killing;
  a creature is lethal when `marks ≥ effective_toughness` — checked only at the next
  SBA sweep, never mid-atom. Ledger cleared on battlefield exit (120.6) and at cleanup
  (514.2). `effective_pt()` (layers' materialized P/T) is the toughness read.
- **SBA loop (CR 704.3)**: `_state_checks()` runs inside `_settle()` **after**
  `binder.fire_all()`, looping fire→sweep until stable. Kills are journalled
  `cause=None, cause_verb="STATE_CHECK"` (the sweep, not the damage source, kills).
  Toughness `None` ⇒ never mark-lethal; toughness ≤ 0 kills **even indestructible**
  (CR 702.12b). Indestructible suppresses only the lethal-damage check (702.5).
- **FIGHT (CR 701)**: `_v_fight` — attacker = battlefield `ctx.source`, else
  `bindings["result"][0]`, else loud raise (no silent stand-ins). Foe Selector resolved
  directly via `resolve_selector` (first-`count` Handle-sorted CHOOSE stand-in, no
  decision ask). Empty foe pool ⇒ C17 no-op. Both creatures mark each other's *current*
  P/T simultaneously. `_apply_pt` writes its `result` register (14e producer idiom).
- **Trigger designation feed**: `binding.py` trigger `_ctx` binds `"target" =
  event.cause` — the designation source consumed by "deals damage to target opponent"-
  style effects (Brash's echo).

## 2. The Brash Taunter ground-truth reversal (the round's biggest finding)

Prior working belief (M11-era memory): Brash Taunter is a 1/1 without keyword that dies
to any mark ≥ 3 and echoes to *the source's controller*. It was failing the first
brash_echo pack because it *survived* mark 3.

Probe + dump + **live Scryfall check** (https://scryfall.com/card/m21/133/brash-taunter)
disproved all of it: M21 Brash Taunter is printed **Indestructible**, "{2}{R}, {T}: This
creature fights another target creature", and its echo says "**target opponent**" — the
`MTG_bot/data/M21.json` dump is FAITHFUL (keywords=['Fight','Indestructible']). Survival
at mark 3 is *correct* behavior. **Never adjudicate card text from memory — check the
dump AND live Scryfall.** (PITFALLS updated.)

That left exactly ONE real engine bug, below. The compiler-side "hypothesis" (identity
P/T leaking past `QConst(1)`) was disproved directly: `identity_of` converts `QConst(1)`
→ `"1"` and `effective_pt` returned (1,1) correctly all along.

## 3. The TARGET_PLAYER designation bug (fixed)

`selectors.role_handles` gave bound handles precedence over any in-tree Selector — but
binding for a trigger is `event.cause`, a **CARD**. Brash's echo TARGET_PLAYER selector
therefore marked the *damage source creature* (Raging Bull) instead of its controller.

Fix, `MTG_bot/core/executor/selectors.py` (two surgical changes):
1. TARGET branch of `resolve_selector`: when `sel.zone.kind is ZoneKind.PLAYER`, a bound
   CARD handle is mapped through `ctx.world.controller_of(h)` before returning.
2. `role_handles`: `player_side` exemption — a PLAYER-zone Selector never takes the raw
   binding; it always falls through to `resolve_selector` (which does the conversion).

This is the mirror image of 14c B-16 (player handle reaching `controller_of`): bindings
win over referent-less Selectors, **except across a zone-type change (card→controller)**.

## 4. Validation packs (round-16 DoD machinery) — 3/3 PASS

`tools/run_scenarios.py` (+x) + `tools/scenarios/*.json`; run
`.venv/bin/python tools/run_scenarios.py`.
- `brash_echo`: activate Brash, fight Raging Bull (3/3) vs Brash (1/1 indestructible);
  expect life {p0:20, p1:17} (echo→opponent), Brash battlefield + Bull graveyard, damage
  marks {brash:3, bull:1}. Proves echo-player-conversion, Indestructible survival, and
  persistent nonlethal marks in one pack.
- `primal_might_fight`: `result`-register attacker + CHOOSE-foe stand-in + QX scaling.
- `nonlethal_skirmish`: Hale 1/2 fights Boggart Gripper 1/1 + end_turn ⇒ marks cleared
  at cleanup; hale battlefield, gripper graveyard, damage {} (lethal via SBA).

## 5. Gate numbers (all post-change)

- Core suite: **2034 passed, 5 subtests** (`pytest MTG_bot/core -q`; 12 new pins in
  `test_executor_damage_sba.py`, incl. the `_gated_288`→288 flip pin: gained = EXACTLY
  Brash Taunter + Primal Might, the two FIGHT cards).
- engine10 (`--seeds 10 --pool engine`): deckable **269** engine_supported **288**
  playable_engine **86** (baseline 267/286/85), survived 9/10, mean 59.6t, 1277 acts,
  cov 40, **0 crashes** (`/tmp/opencode/engine10_16b.txt`).
- Replay determinism: two engine10 runs byte-identical except the `argv` echo of `--out`.
- **engine30 GATE: 29/30 survived (96.7%), mean 59.87t, 3917 acts, cov 53 (19.7%),
  0 crashes** (`/tmp/opencode/engine30_16b.txt`) — FIGHT fired in real games, the 14f
  "arc-3 UNREACHED" wall is breached without regression.
- all10: crash set **unchanged** — sole crash remains `NotImplementedError: executor:
  verb GAIN_CONTROL not implemented` (verbs.py:1316 run_atom, seed 2, cast:Enthralling
  Hold). That is the documented **16e** boundary (plan §line 42), not a 16a regression.
- PC-1 301/305 · PC-2 634/639 · PC-3 0 · PC-4 0 — selector change is executor-side only,
  grammar goldens never moved (suite run confirms; full PC re-run not required).
- pyright 0 errors on every touched file; ruff delta 0 (`selectors.py` keeps its 12
  legacy typing-style errors == HEAD — do not bulk-fix; new files clean).

## 6. Trace-diff catalog reconciled + repinned (the 16a mandate)

`tools/traces/catalog.py {build,compare,repin}`. Pre-change `compare`: all 10 seeds
diverge, FIRST DIVERGENCE at ~entry 4 — a PLAY_LAND card-index shift. Diagnosis: the
baseline was pinned at deckable=267/engine_supported=286; FIGHT dispatch added Brash +
Primal Might to the deckable set (269/288), so the same deck-pairs seed 1409 samples a
different card multiset → the deal order shifts → *every* downstream trajectory differs
(SBA attribution and survival races are subsumed in that cascade, and are covered
independently by the unit pins + packs). This is exactly the compounding-risk case the
owner's catalog mandate anticipated.
`repin` executed: **5641 entries / 10 games** (was 5504), meta records pool=engine,
deck_pairs_seed=1409, turn_cap=60, `built` timestamp + `semantics_note` pointing at this
file. Post-repin `compare`: **0 diverging seed(s) of 10** — green baseline restored.

## 7. Known fidelity losses / boundaries (honest ledger)

- The journal attributes **one cause per atom**, so in Brash's own activation-fight the
  foe→Brash damage is journalled cause=Brash ⇒ its echo TARGET_PLAYER hits Brash's own
  controller. Card-accurate simultaneous-cause attribution = combat-core work (16b+).
- FIGHT foe selection is a Handle-sorted stand-in, not a player decision (documented).
- GAIN_CONTROL unimplemented (16e, Enthralling Hold). PHASE_OUT/COPY/counters remain
  deferred by design per the 16 plan.

## Repro commands

```bash
.venv/bin/python -m pytest MTG_bot/core -q                       # 2034 + 5 subtests
.venv/bin/python tools/run_scenarios.py                          # packs 3/3
.venv/bin/python -m MTG_bot.core.executor.games --seeds 30 --pool engine --out /tmp/opencode/engine30_16b.txt
.venv/bin/python tools/traces/catalog.py compare                 # 0 diverging of 10
```
