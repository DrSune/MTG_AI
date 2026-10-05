# 06-rung1-counter-window — Rung-1 response window shipped (2026-10-05, uncommitted, HEAD 3c79d3c)

**Scope**: engine instant-speed counter window + `COUNTER_SPELL` verb + honest `unless`-kickback
(Ruling A), 8 wave-7 counter packs, wave-7 census artifact, vocab-gate crash fix.

## 1. The window (engine)
- `stack.py` loop **6b**: after `_settle()` of a resolving spell/ability trigger window, before the
  pop, any player holding a hand card whose compiled tree contains a `COUNTER_SPELL` atom
  (`_tree_has_counter`) is asked on the 14b channel with tag `counter:<seat>:<digest>`.
- Vocabulary = **executable offers only** — see §3. Empty vocab ⇒ no ask, silent pop (no row).
- A counter resolves via `verbs.py:_v_counter_spell`: spell object gets `SpellObject.countered`,
  goes to its owner's graveyard, never resolves; counter's own tree runs (Rewind untaps after).
- Kickback (`Seq[COUNTER, UNLESS | unless-pay]`): after the COUNTER atom the payer is asked
  `pay:<payer>:<digest>` with `["PAY"]` iff `mana_payable`; **unpayable ⇒ no ask at all**
  (Ruling A: never demand the impossible). Rig fallback = PASS, journalled.
- Journal kinds: `WINDOW_OPEN` (data = vocab), `WINDOW_PASS`, `COUNTER`, `KICKBACK`
  (data `('PAY',)` / `('PASS',)`).

## 2. Ruling A (binding)
- Handler implements kickback itself; rig `pay:` lane missing ⇒ PASS + KICKBACK row.
- PC-7 stays honest: **301/305 supported, 46 verbs**. No census inflation for the window.

## 3. THE VOCAB GATE (the engine-critical lesson of this batch)
First 100-seed games run after the window landed produced **2 NEW crashes** (10-04 baseline was
0): seed 16 `executor: cast: illegal target selection: selection:off_population:card:38`
(stack.py `_plan_cast_designation`) and seed 96 `a multi-target Choose spell must declare its
mode`. Both were the window's **nested cast** (stack.py:660) executing an offer the vocab had
promised but the designation pipeline could not deliver.

Root cause: `spell_castable` is **target-blind** — it checks mana + timing + card-level legality,
never the current target population. Offering a hand card in a vocab that promises executability
is a contract; RandomPolicy answered and the cast crashed.

Fix = `_counter_vocab(executor, seat, frame_handle)` gates every offer on **4 rules**:
1. tree contains a counter atom AND `spell_castable`;
2. **verb closure ⊆ HANDLERS** (`_tree_verb_closure` walks Seq/Chooses/branches; a tree with any
   unsupported verb — e.g. Sublime Epiphany's `COPY` — is not offered);
3. **designable now**: `spell_target_slots(...)` + `validate_target_selection(slots[0],
   (frame_handle,))` — Miscast (Instant/Sorcery filter) is never offered at a creature spell;
4. exactly **one TARGET slot, modeless** — a multi-target `Choose` fan cannot declare its mode
   through the window channel.

Regression pins (test_executor_rung1.py, file now **12/12**):
`test_frame_filter_excludes_the_offer` (instant-only counter vs creature spell ⇒ no ask, spell
resolves to battlefield) and `test_unsupported_closure_excludes_the_offer`
(`Seq[COUNTER, COPY(source=any_target())]` ⇒ no ask, shock resolves).

## 4. Card facts that bound the packs (verified against goldens)
- **Cancel** `7d00fb28` {1}{U}{U} — clean counter. **Miscast** `e08c71aa` {U}, unless {3}, filter
  **FOr(Instant,Sorcery)** — cannot counter creature spells. **Lofty Denial** `d799a2c4` {1}{U},
  unless {1}, filter **TYPE_EQ Creature** — counters **creature spells ONLY** (the pack casts a
  real Staunch Shieldmate 1/1 for {W}). **Rewind** `bb27bfdf` {2}{U}{U},
  `Seq[COUNTER, UNTAP(CHOOSE ≤4 lands)]` — with ≤4 tapped lands the CHOOSE issues **no ask**.
  **Sublime Epiphany** `56148ae7` — unsupported (COPY), stays PC-7 excluded; vocab-gate #2 now
  also keeps it out of live windows.

## 5. Gates
- Scenarios **347/347** (339→+8 wave-7 packs, zero regressions). Full core suite **2379 passed + 2
  subtests**. rung1 file 12/12.
- Games `--seeds 100 --pool all` (deck-pairs-seed 1409): **0 crash classes**, 97 decisive + 2 turn
  cap + 1 draw-out, mean_turns **33.93**. Window stats from journal replay: **19 WINDOW_OPEN /
  10 WINDOW_PASS / 7 COUNTER / 2 KICKBACK (both PAY)** — arithmetic exact (19=10+7+2); mean offer
  vocab 2.11, max 3.
- wave7 census `tools/audit/wave7.json` (`wave_builder.py --wave7`, lint OK): 5 counter cards =
  4 covered + 1 gate-excluded (Sublime) + 0 cohort.
- pyright: **0 errors** on all changed/new files (pre-existing noise elsewhere untouched);
  ruff **Δ0** (rung1 I001×2 + B023 fixed this session; run_scenarios BLE001 pre-existing).
