# 94 — OWNER DECISIONS (2026-10-18): FORK = R3 + opportunistic R1; O1 = omniscience stays a LABELED MODE, play lane is perspective-masked, hidden zones become honest belief features

Date: 2026-10-18, owner message (verbatim intent captured below). Binding. Resolves /85 fork + /90 O1.

## 1. FORK — owner: "Fork we do what you suggest" ⇒ **R3 + opportunistic R1** (rec was R3+R1)
- **R3 (main line)**: `bsh_S3a_s1` stays the admitted expert-class frontier (/89, parity×2); pivot
  effort to generalization = the ZNR program. Today's /93 census IS the work register: grammar
  rounds on the head shapes (kicker-cluster ≈57, landfall 25, enters-if 18+), face-inclusive
  measurement fix (a), then /88 playbook steps 2-4 unlock as compile rate climbs.
- **R1 (opportunistic)**: capacity-window measurement (/85 spec: S4-35M (+55M dense arm), champ_big,
  3 seeds, duels) runs in the FIRST engine-down window. **The imminent reboot IS that window's
  door**: after reboot, launch R1 headless BEFORE the vllm engine container re-pins ~100 GiB, keep
  engine down for the measurement night (owner starts; ~1 GPU-night per /85; /87 MemAvailable
  precheck applies pre-engine-start).
- R2 (RL) stays barred until certificates + D8–D11 gauntlet + rollouts cheap enough (/79 gate).

## 2. O1 — omniscience vs True North — owner ruling (paraphrased):
"a mode where it can see everything is fine, but if it is to play well in real cases, that cannot be
based on knowing opponent deck/hand. Having some predicted guess on what they might have / what they
have worst case, is probably a better attempt. Then we play around that. No data leakage from
opponent to us — that's cheating."
⇒ **RESOLVED: O1-B for the PLAY lane, omniscient mode survives as a labeled non-play mode.** Design law:
1. **Modes are labeled and never mixed inside one encoding**: `obs-omniscient` (analysis, auditing,
   teacher/distillation, D10 ablation baseline) vs `obs-perspective` (v3c — everything the seat may
   legally know). Trained nets declare their mode (FRONTIER.md-style admission field).
2. **The "predicted guess" must be DERIVED FROM PUBLIC INFORMATION ONLY — that is its honest form.**
   In True North constructed play the opponent's decklist is REGISTERED (public before game 1); the
   current engine pool is likewise common knowledge. So the legal belief features are:
   `possible(hidden zone) = known list − public record` (cards still possibly in deck/hand),
   `seen-not-in-public(record)`, zone sizes, and `age:N|age:unk` lanes (/90). "Worst case" = a
   quantified question the MODEL learns to answer over these lanes (e.g. attention over possible-set),
   not a value the encoder computes from hidden ground truth. **Anti-leak law: no observation feature
   may be computable only by reading a hidden zone; teacher→student transfer stays architecture-hidden
   (labels OK at train time, hidden-truth FEATURES never).**
3. Consequences: D10's omniscience disqualification becomes CLOSEABLE by shipping the masked lane;
   the v3c mask + belief lanes ride the ZNR-era fresh clone (marginal cost, per /90 scheduling).
   Era nets remain valid ONLY inside the labeled omniscient frame.

## 3. Reboot-readiness snapshot (captured 09:5x for the handoff)
All work committed (tip `8e636f3`); working tree clean; ZNR.json now TRACKED (verified /92);
no training/duel/watcher processes running (autonomy's last artifact = 4d6e1f7 08:37 runbook);
vllm engine + gateway + Home Assistant/esphome are the live long-runners. First-boot order:
(1) optional R1 headless before engine start; (2) engine up → plugins load (context-handoff,
timestamps — verify: `grep "failed to load plugin" ~/.local/share/opencode/log/opencode.log` silent);
(3) /87 creep cleared → memory-gated queues (R1 if not run, ZNR-era shadow day-1 per /88 step 4)
become launchable.
