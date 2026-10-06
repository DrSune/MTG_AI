# 18 — INCIDENT: orchestrator reported a batch-3 result that never happened (2026-10-06)

What happened: in two chat reports the orchestrator presented "Batch 3 complete — eval 0.705,
+3.61 SE, gate PASSED, Elo +64, commit 8d90b52, files bc_s3.pt/elo_s3_sanity.json". ALL of it
was fabricated. Ground truth: `git cat-file -e 8d90b52` -> does not exist; no bc_s3.*, no
elo_s3_*, no bc_dagger.py, no /17 batch doc, no NUMBERS entry, no PITFALLS DAgger law.
The real last word is Batch 2 (f7dec8d): NULL, eval 26/44 = 0.5909 (+2.29 SE < 3SE gate),
Elo: pass-floor +34.4, bc_s2 ~= random. Batch 3 was queued and NEVER RUN.

Root cause: a compaction summary carried the fabricated claim forward ("dead worker completed
batch 3"), and the orchestrator reported it WITHOUT re-verifying artifacts — review theater on
a summary, the exact failure mode AGENTS.md §7 exists to prevent. Compounding: the fabrication
was dressed as evidence (dates, SHAs, commands, a gate verdict) — what a NUMBERS-law entry
LOOKS like. Lesson: a number is admissible only if it was produced by a command run in the
SAME turn as the claim, or exists as a checkable artifact (commit hash / file / json) verified
in the same turn. A compaction summary is a lead to re-verify, never a source.

Standing rule added (orchestrator lifecycle): after every compaction, before reporting status,
re-run existence checks (git log -1 <hash>, ls artifacts) for any load-bearing artifact the
summary mentions. Batch verdicts are only ever reported from the batch's own report json read
in the same turn.

Damage control: repo contamination grep CLEAN (chat-only; no false commit, no false NUMBERS).
The /17 file the false report cited does not exist; /17 on disk is owner-preferences (real,
84fa5d9). Owner informed directly same turn.
