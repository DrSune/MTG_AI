# 23 — Volume batch: 16 blindspot packs, corpus v3 (owner-approved, 2026-10-06/07)

## Verdict
16 new gold-decision packs (11 mechanics + 5 chained-ask ladders) authored against compiled-pool
twins of the 12 eval-blindspot mechanics, all runner-green, certifying **+34 items**:
corpus **119 → 153 items**, **E_active 103 → 133** (SE 0.0493 → 0.0434), **l1_ready 4 → 15**,
punish_inaction 104 → **138**, offenders 0, no_discrimination 0. Packs **371/371**. Engine untouched.

## The ask-kind grammar law (empirical, supersedes prior assumptions)
Only **`take_decision`-channel** asks become certifiable corpus items. Recorded vocabularies:
- `may` → ('fire','skip'); `one_of` → card handles; `target` → ('card:N'/'player:N', …);
  `sacrifice` → own-permanent handles; `choose`/snout → ('0','1',…) or option words;
  `mana` → ('W','U','B','R','G','C'); `scry` → ('top','bottom');
  `attack` → ('ATTACK','DECLINE') — answerable from the decisions queue even when the attacker is
  absent from the attack map (null=DECLINE); `block` → attacker handles + 'NONE' (queue-answered).

**NOT items (zero asks ever fire — honest gaps, do not author packs claiming them):**
- Modal spell MODE (Return to Nature, Destructive Tampering): no mode ask; cast legality error
  `count_below_min:0<1` if designated targets aren't supplied at cast — mode never chosen.
- Combat-window `cw:` shock casts (Lightning Strike in combat): resolved inside the window, no
  take_decision — a `cw` recorder sees only the surrounding attack ask.
- Cultivate search: engine auto-takes the first eligible library card, no ask.
- Fierce Empath / Solemn-Simulacrum-style search pick: only the `may` ask is an item; the search
  auto-take takes the LAST-entered eligible library card (library-list ordering, engine-deterministic).
- Any single-candidate ask: auto-taken silently (e.g. Hobblefiend sac with 1 creature).
- Palladium Myr / Traitorous Greed twins: no ask fires at all.

## null-word trap (cost 2 offenders at cert)
`null_word` = first PASS_WORD present in vocab else `vocab[0]`. For `scry`, `mana`, `choose`/binary
vocabs there is no PASS word, so **null = vocab[0]** = 'top' / 'W' / '0'. A gold scripted equal to
vocab[0] yields `null==gold` → `no_discrimination`. Rule: **gold must differ from vocab[0] on every
ask**. Sanctum shrine color ask: gold must be G/U/B/R/C, never W.

## Roster (16 packs, 34 items; per-pack ask kinds)
mechanics: trufflesnout_life_bait choose×2 (gold≠'0'); pridemalkin_counter_sculpt target;
kitesail_freebooter_split_hand choose; see_the_truth_gem_pinned one_of; arsonist_pair_burn
target×2; treasure_color_terror mana×2 (gold 'B'/'U'); sanctum_harvest_u_not_w mana('U')+scry('bottom');
empath_big_game_pick may('fire'); temple_malady_sculpt scry('bottom', order-lane falsifier);
megalodon_attack_sculpt attack+scry (queue-answered "ATTACK"); hobble_bond_victim sacrifice.
ladders: jester_double_sac (sac,target×2); snout_pride_arson (choose,target×3);
burn_and_bonds (target,choose,target,choose); sculpt_and_sac (scry,sacrifice,mana);
double_bonds (choose,target,choose,target).

## Deterministic capture method (library lanes)
Named `zone:"library"` cards sit UNDER the 6 auto "Library i" cards; seeded shuffle is deterministic
per world-seed but named-top placement was not found in 80 seeds → **run the gold line, capture the
final library order, hardcode the exact lane** (wildcard `"*"` exists, TOP-first). Used by
temple_malady_sculpt and megalodon_attack_sculpt.

## Dropped as item-less (kept OUT, per evidence): return_to_nature_exile_mode,
tampering_artifact_choice, ladder_tampering_bonds, ladder_window_tricks, ladder_tutor_loot_prison,
ladder_cultivate_bond_bolt, ladder_combat_devils.

## Regeneration chain (all re-run this batch)
1. `.venv/bin/python tools/audit/puzzle_cert.py --rollouts 200` → `tools/audit/puzzle_corpus.json`
   (v2 kept as `tools/audit/puzzle_corpus.v2.json`).
2. eval_split: 74 v2 family assignments FROZEN; 3 new families assigned by index%5 in the
   regenerated 77-sort → **Havoc Jester EVAL, Hobblefiend train, Spined Megalodon EVAL**;
   now 32 eval / 45 train families, **103 train + 50 eval items** (eval_l1_ready 2).
3. `.venv/bin/python -m tools.training.packrec_v2` → `episodes_v2.jsonl`
   (**111 eps / 177 asks / 153 gold lines**, ground rows 76, handle ground 157/189, choose-digit 59/62).
4. BPTT audit: **max seq 1008 ≤ cap 1024** unchanged (longest new ladder 813); no split change.
5. test_bc_v2.py pins updated 119→153, (87,103)→(157,189), (43,45)→(59,62), 51→76 (dated comments).

## Gates (all executed)
run_scenarios **371/371**; pytest MTG_bot/core **2391 passed + 2 subtests**; tools/audit
**74 passed**; tools/training **71 passed**.

## Engine behavior traps hit this batch
- Lands/Temples entering via `play` are UNTAPPED (Temple self-tap ask pattern: expect tapped False).
- `deal_damage` is one-way (no combat retaliation) and does NOT tap the source; zero-damage entries
  are absent from the damage lane entirely.
- `Elite Inquisitor` is not in the compiled pool (M21.json ⊂ subset: no Terror/Fatal Push/
  Ultimate Price/Drag Under); black removal twin = **Eliminate {1}{B}**; green 1-drop twin =
  **Skyway Sniper {G}**.
- Synthetic cards need explicit `zone`+`controller` or setup raises `KeyError: 'controller'`;
  `cmc` key gates eligibility (default 2 silently narrows vocab, e.g. Fierce Empath → ('skip',)).
- `rm -rf /tmp/...` is permission-denied (matches `rm -rf /*`); clear staging dirs via
  `python -c "import shutil; shutil.rmtree(...)"`.
