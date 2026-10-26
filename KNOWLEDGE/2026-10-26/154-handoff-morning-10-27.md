# 154 — Handoff: morning of 2026-10-27 (harvest protocol + day queue)
Written 2026-10-26 17:05 CEST. Session discontinues at the 23:59 engine stop; the next session cold-starts from this file.

## State at handoff
- Pilot: night-2 window armed 23:59/07:00 (`--gpu-train`), frozen export (PIN 7bda5549 == export_fp == tree), /152 pre-registration binding.
- Bench: RUN-L3d (duel, deals=1, masked, 27B-low) running detached in tmux `benchl3d` since 15:38 (pace ~1.4 min/ask; game-1 expected settled ~18:30–19:00, pair ~21:00; settled rows persist in the jsonl through the engine stop).
- Engine: 27B NVFP4 up until 23:59. Owner's tmux `MTG` session must never be killed; sibling sessions `claude-ced`/`claude-mtg` are not mine.

## Harvest, in order (after the engine cycle)
1. **Pilot** (`reports/rl_window_run.log`, non-HEARTBEAT lines + `/tmp/opencode/rld_n1/`):
   - Expected chain: P0 → P1 (calib; F4 + probe 60g) → P2 (collect 1000g deterministic ⇒ byte-identical to night-1's `episodes_iter1.jsonl`; **cuda audit expected GREEN in minutes**; train on GPU; **probe 200g mirror = verdict axis**).
   - Read the mirror probe against /152 (MIRROR-POSITIVE/FLAT/NEGATIVE/DIVERGENT + MOVED discriminator). Any deviation from the expected chain ⇒ the /152 branch applies (AUDIT-RED ⇒ root-cause first; honest-skip ⇒ re-arm).
   - If P2 FULLY completed (probe exists): the first completing night ⇒ the window self-wrote the PIN (verify `/tmp/opencode/RL_PILOT_PIN` provenance line) — if it did NOT write (rc≠0), pin state is unchanged (still the pre-night-2 pin, documented in /151).
   - Write the harvest entry (/155+) + NUMBERS rows; commit gate-checked.
2. **Bench** (`/tmp/opencode/bench_l3d_d1.jsonl` + `bench_duel_l3.summary.json`):
   - If ≥1 game settled: first live DUEL number — pair score vs uniform floor + cost/clock (tokens/ask, latency, forfeits, `refused_leaky`, identity block). Add the row to DESIGN_BENCHMARK §10 (next to the R row, /153) + NUMBERS + a /15x entry; copy the jsonl+summary into `reports/` (durable).
   - If 0 settled (engine stop cut it): record honestly (void-infra rows + reason), note the pace evidence; the duel lane needs a larger engine-up stretch (e.g. a morning window) — no owner scheduling needed per /153 refinement, just a quiet morning.
3. **Window state**: confirm the next arming decision — if the pilot needs another night, re-arm the same pattern (`tmux new-session -d -s rlwindow 'bash tools/ops/rl_window.sh --gpu-train'`); PIN must still match (any payload change ⇒ tripwire ⇒ re-smoke + explicit re-pin).

## Day queue after harvest (unblocked once the night outcome is known)
1. **T-G5 fix ladder** (CPU; was deferred to protect tonight's frozen export): ab_duel/elo set-plumbing + per-pair admissibility surfacing + engine git-stamp + sentinel cells + pool default. Touches `tools/training/ab_duel.py` (fingerprinted) ⇒ re-smoke (pytest + dry-run) + explicit re-pin before the NEXT window.
2. **§3.1.4**: rig active-player fallback fix + re-collect legacy data (touches `tools/eval/gameplay_eval_v2.py`, fingerprinted — same discipline).
3. **ZNR `1+*` shape gap** (logged in /153 from the rules stderr: `parse_pt: unexpected value '1+*'`, excludes Nighthawk Scavenger et al.): find the pt parser, add the unbounded form, test, re-pin.
4. **T-G1 generalization matrix**: still parked on the owner's ontology R-rounds (owner's own backlog wording); protocol memo /135 §C awaits sign-off.
5. **Bench, if the duel settled**: size the next runs per DESIGN §6 (N for the pair-score claim; the R track at confirmation size) — fit them inside engine-up stretches.

## Pending owner rulings (unchanged)
- T-G1 protocol sign-off (/135 §C home-pool law).
- ZNR source verification.
- RL window cadence vs sibling-session engine occupancy (CED lane history).

## Ops laws in force (do not re-derive)
- PITFALL /146: a dry-run that pins a config dimension cannot prove paths crossing it — smoke each live dimension in real mode before arming.
- PIN law /146/147 + /151 guard: pilot iterations run from a frozen export; payload-tree fingerprint tripwire aborts pre-engine on drift; re-pin is explicit and provenanced, never silent.
- Quiet-engine refinement /153: session KV slows completions, does not wall them; detached tmux runs with bounded counts work while the engine is up.
- /proc scan self-match trap: never pattern-match a literal that appears in your own command line (bracket trick or PID-specified checks).
- Commit only explicit own-lane paths; never `git add -A` (sibling lanes carry uncommitted files in the worktree).
