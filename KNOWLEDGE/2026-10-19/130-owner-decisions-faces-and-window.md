# 130 — OWNER DECISIONS (2026-10-19, owner message ~21:3x): FACE PLAYABILITY = real-world rules; R1 WINDOW AUTHORIZED via detached script; generalization tests on new checkpoints; stopped-session's watch work absorbed

Date: 2026-10-19, owner message (verbatim intent captured). Binding. Resolves the two questions
/106 §6 and /94 §1 left open; absorbs the stopped session `ses_f1b6a989` ("Continue work on MTG",
last words: "0.59 GiB, gate sealed, runbook watcher polling for the next night window. Holding.").

## 1. MDFC FACE PLAYABILITY — owner: "Yes back faces are real, treat them normally how they work
## in real life." ⇒ REAL-WORLD CR SEMANTICS ADOPTED for double-faced permanents.
Operational meaning for THIS world (census: all 36 ZNR backs are LANDS; 6 land fronts, 23 spell +
8 creature fronts): the land face of an MDFC in hand may be PLAYED per normal land rules (land-play
counter shared); the front face is cast as normal; a permanent lives with the face it entered with
(abilities/state of the ACTIVE face only); back faces are never CAST (they are lands; the /117
FaceCastAbsentError stays for cast-lanes). ZND-2f's encode-only law lifts into playability
(engine wave /131). The pay-3-life pair (5 cards) must reach full fidelity — the §10 blindness that
was acceptable while faces were dead becomes a real gap now that they play ⇒ ZND-2f2 grammar lane
(may+entering-replacement+IF_YOU_DONT) ships WITH the playability wave.

## 2. R1 CAPACITY WINDOW — owner: "Yes use the GPU... swap out and swap in, in one script, since
## you cannot fix it while you are away... or hand this off to a tmux session you give the
## responsibility to deal with it." ⇒ AUTHORIZED + METHOD DIRECTIVE: a single detached script
## (tmux), NOT an agent-on-the-engine doing the swap (the swapper would kill itself — the engine
## serves every agent session). AGENTS.md engine-law exception: this is owner-authorized, scripted,
## with guaranteed engine-restart trap; no live agent session ever runs docker stop.
Spec per /85 + /94 + /80: engine DOWN → S4 (35M) × 3 seeds on episodes_champ_big.jsonl, DEFAULT
LONG epochs (owner: "nice to have long running training"), 2h/arm guard, then engine-still-down
evals: eval_ckpt gates + /128 set-split generalization meter (fresh=ZNR) + duels vs frozen frontier
bsh_S3a_s3_best → ledger + NUMBERS → engine UP (trap: restart on ANY exit path) → gateway health +
plugin-log checks per /94 checklist. Hard restart deadline morning.
The 55M dense arm stays SKIPPED (spec says "no new machinery"; its definition is batch-10 lane).

## 3. STOPPED-SESSION WORK — its whole mission (memory-gated night-window execution + status
## freshness) IS item 2; the new script inherits its runbook duty. No separate workstream.

## Wave queue unlocked by this note:
- /131 ZND-2g face-playability engine wave (+ ZND-2f2 grammar) — dispatch-gated on single-writer
  (tree clean at write time; sibling waves all committed).
- r1_window script (tools/ops/) scheduled tonight.
