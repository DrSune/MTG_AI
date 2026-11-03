# 181: era-boundary dry-run — merge rehearsal, consumer fixes verified, re-pin list (2026-11-03)

Status: **DRY-RUN** — scratch worktree `/tmp/opencode/era_dryrun`, branch
`era/dryrun-2026-11-03` (base = main `245d756`). Nothing landed in main. The
era-boundary bundle (/177) is rehearsed end-to-end ahead of the owner's OK;
the real merge stays gated (owner's OK + gap between RL windows + re-smoke /
explicit re-pin, /177 §1). No RL window is armed (ladder closed, /179), so
the window-gap condition holds.

## 1. Merge audit (pre-merge, zero-risk)

- `git merge-tree --write-tree main cards/integration`: **exactly 1 conflict**
  — `MTG_bot/bench/test_duel.py::test_uniform_beats_pass_on_the_same_deals`
  (main: turn_cap=30 reformat vs branch: V2 re-pin turn_cap=60 + the CR 500.5
  "mana empties as each step and phase ends" comment). Resolution: **take the
  branch side** — the V2 re-pin is semantically correct under the new engine;
  the main-side change was formatting only. Everything else auto-merges.
- `cards/integration` = 178 commits ahead of main, stable since
  2026-10-30 10:44 (local == origin; tip `84c3bd9` = merge of origin/main
  into the branch).
- Post-merge MTG_bot tree == branch tip **byte-identical** (main's
  contribution since c251d46 is KNOWLEDGE/reports only) ⇒ the merge is
  semantically clean on the engine side; any behaviour change is the
  sibling's, already measured in /177.

## 2. Consumer fixes (/177 §2) — prepared + verified

Merge commit `5bb35c5` + fixes `6bb348d` on the scratch branch:
- `tools/training/collector.py`, `tools/training/ab_duel.py`,
  `tools/eval/gameplay_eval_v2.py` provider lanes now read
  `executor.decisions.asking_seat` (set by the engine ONLY during the
  provider call; `Handle | None`) and route the ask to the policy owning that
  seat. Fallback chain: asking_seat → (GEV2 only) the v2 tag inference
  (`resolve_seat`) → active player (pre-era semantics).
- `tools/training/bc_data.py`: SITE_KINDS += `tap, discard, legend, x,
  enchant` (24 kinds; additive only, vocab extends at first sight).
- API cross-checked against the branch: `Decisions.asking_seat` docstring
  ("a provider cannot recover the decider from the site tag alone, because
  EachPlayer re-asks the SAME tag once per player"), the sibling bench's
  strict `resolve_ask_seat` reference consumer, and the SEAT_IN_TAG /
  OBJECT_IN_TAG taxonomy in `MTG_bot/bench/protocol.py`.

### Seat-routing measurement (the fix is not speculative)

Probe: 10 collector-parity games, 591 engine asks, instrumented provider
wrapper delegating to `RandomPolicy.answer` (behaviour identical to an
uninstrumented run — pure measurement):
- **591/591 asks NAMED** by the engine (`asking_seat` set; 0 unnamed).
- **70/591 (11.9%) addressed to the NON-active player** — the pre-era v1 rig
  (route every ask to `world.active_player`) would have mis-routed all of
  them: block 61, cw 3, counter 2, target 2, choose 1, may 1.
- discard (7) all correctly active; legend/enchant did not occur in 10 games
  (low-frequency sites — they will appear in a full re-collect).

## 3. Suite on the merged tree

Environment note: `/tmp/opencode/phase1_buckets/*.json` was **wiped by the
2026-11-01 hard reboot**; the main tree fails the same 55 template tests
(pre-existing environmental breakage, NOT merge-induced). Regenerated via
`tools/gen_buckets.py` — "all pinned constraints hold" on the merged
compiler (a merge-consistency datum).

| Lane | Result (merged tree) |
|---|---|
| `pytest MTG_bot` (default markers) | 4509 passed / **2 failed** / 11 skipped / 23 xfailed / 40 deselected |
| — the 2 failures | `strategic_brain/test_model.py` (orphaned parameter tensors 3.91%; reasoning loop never iterates) — **fail identically on main pre-merge** (pre-existing, separate lane, flag in §6) |
| template bucket tests | 330/330 after bucket regen |
| `tools/run_scenarios.py` | **668/668 packs** (= /177 final-state number) |
| `pytest tools` | 302 passed / 35 skipped / **7 failed** — classified below |

The sibling's "2 failed (D3/D11 gates)" are spec items inside the ontology
battery, not separate default-suite tests; they do not fail under the
default marker selection on the merged tree (the `red_first`/`slow`
deselected set runs separately in the re-smoke procedure).

### The 7 tools failures, classified

- **Pre-existing on main (1)**: `test_bc_v3::test_elo_seed_start_builds_fresh_block`
  — fails identically pre-merge; independent lane issue, flag in §6.
- **Merge-induced (6) = the era-boundary re-pin list:**
  1. `test_duel_elo::test_elo_json_schema` — pure re-pin: the seeded-game
     outcomes shifted (cleanup discard / mana-empties); `by_name` is now
     `{random}` only, the 2026-10-30 V36 re-pin expectation is stale.
  2. `test_fork::test_expand_attack_ask` — the engine now emits the ask with
     kind `choose` where the test expects `attack` (ask-shape
     restructuring: modes at cast, per-slot targets).
  3. `test_fork::test_expand_block_ask` — same class, block side.
     (2+3: the search/fork lane needs its ask-shape pass on the new engine,
     then re-pin; /177 §2 already foreshadowed the new attack/block shapes.)
  4. `test_ontology_conformance::test_v5_live_new_branchings_are_all_census_tail_rows`
     — a NEW live Choose shape `fixed_options[3]/QConst/(Atom,Seq)` is absent
     from the pinned census ⇒ census extension (law §8 evidence).
  5. `test_ontology_conformance::test_corpus_has_no_phantoms_and_no_new_choose_emissions`
     — 34 new CHOOSE emissions/shapes on M21 campaign cards (Alpine
     Houndmaster count 2→3 + shape added; Basri Ket 2→1 + shape removed; …)
     ⇒ expected (the campaign fixed the cards toward printed text) ⇒ corpus
     re-certification.
  6. `test_k2::test_generation_is_deterministic_and_replays_never_diverge` —
     the k2 corpus on the merged engine no longer produces divergent rows ⇒
     k2-lane investigation at re-baseline.
- None of the 6 points at a bug in the consumer fixes.

## 4. Real-mode smokes (anchor net, merged engine, fixed rig)

- **ab_duel mirror, 8 games** (scratch seeds 590001–590008): **0 crashes**,
  2 draw-cap, `seat_balance_ok`. A wins 4/4 at seat 1 and 0/4 at seat 0
  (B 2W) — a small-sample seat-1 asymmetry datum on the new engine; note an
  identical-net mirror cannot distinguish seat routing, the probe in §2 is
  the routing evidence.
- **GEV2 mirror + `--rl-collect`, 4 games** (scratch seed-base 590009,
  rl-seed 4900): 2W/2L, **0 crashes, 0 illegal**, 8 episode rows with the
  full v2 schema (`what/vocab/idx/logp/obs` incl. board state) ⇒ the
  real-run collection path works on the merged engine with the fixes.

## 5. Consequence for the era execution (post owner OK, in order)

1. Merge `cards/integration` → main (1 conflict, resolution known §1).
2. Land the 4-file consumer fixes (§2; `6bb348d`).
3. Re-pin the 6 merge-induced tests (§3): #1 is a measurement update;
   #4/#5 are census/corpus re-certification (law §8 tokenizer
   re-evaluation — they are its first evidence: one new Choose shape + 34
   choose emissions); #2/#3 need the fork ask-shape pass; #6 needs k2
   investigation.
4. Re-smoke in real mode, update `RL_PILOT_PIN` explicitly, re-certify the
   puzzle corpus, re-baseline every probe, re-collect episodes.
5. Then the FINAL pre-registration for the post-merge RL v2 real runs,
   carrying the open owner items from /180: entropy-collapse treatment
   (the debug loop's sentinel caught no-entropy PPO collapse), lr/clip
   review (clip bound on 80% of minibatches offline), torch-RNG seeding
   at start, value-step budget under KL early-stop, and zero-decision-game
   handling if the corrected engine still produces them.

## 6. Flags to owner

- `strategic_brain`: 2 pre-existing failures (5 orphaned parameter tensors
  — 3.91% of the model; reasoning loop never iterates over 8 requested
  passes) — separate lane, predates the era window.
- `test_bc_v3::test_elo_seed_start_builds_fresh_block`: 1 pre-existing
  failure.
- Every hard reboot wipes `/tmp`, breaking the 55 template-bucket tests and
  any `/tmp`-pinned artifact; buckets regenerate via `tools/gen_buckets.py`
  — consider a tracked location (owner/sibling call).
- Scratch dry-run seeds 590001–590013 (8 duel + 4 collect via seed-base
  590009, rl-seed 4900) are **DRY-RUN ONLY** — never reused for production;
  the real run reserves fresh blocks ≥ 525001 per /172 §7.
