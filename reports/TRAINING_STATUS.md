# TRAINING STATUS
- updated: 2026-10-18 13:1x
- state: ACTIVE — R3 mainline (ZNR grammar waves via sibling session), R1 watcher armed, eval audits clear
- real state docs: reports/STATUS.md + reports/FRONTIER.md + KNOWLEDGE/2026-10-18/94 (owner decisions)
- ops log: reports/training_ops.log | runs jsonl: reports/training_runs.jsonl
- updated: 2026-10-19 04:3x (engine/grammar lane, orchestrator overnight run):
  committed: ZND-1f kick model-visible (d549af6) · ZND-1g X-kicker cost lane (5e826be) · ZND-2f BackFace encode ff041a1 (PC-2 0.4669, faces ENCODED, playability OWNER-GATED — world texts carry no face-cast mechanism, owner question in /106) · blink WAS_KICKED entry-provenance + fuzz honesty lane 1b7b9bf · HAS_KICKER 12c d193fe1
  fuzz program: tools/eval/znr_engine_smoke.py, baseline 7.5% crash -> 0/60; 500-game deep sweep RUNNING bg (/tmp/opencode/fuzz500.log); shadow preflight bsh_S3a_s3_best vs teacher on ZNR RUNNING bg (/tmp/opencode/shadow_preflight.log)
  numbers: ZNR PC-1 0.2411 · PC-2 0.4669 (339/726) · packs 409/409 · core 2672+36 · deckable 267
  open owner questions: (1) MDFC face playability in this world (set-rule absent from card texts — /106); (2) R1 capacity window still unused (engine never went down)
  pending lanes: sibling ZND-3 party LIVE (ability_tree dirty); compiler fold-gate proposals /112 await grammar-surface owner; ZND-2f2 pay-3-life pair queued
- updated: 2026-10-19 07:0x (end of overnight autonomous run — full narrative KNOWLEDGE/2026-10-19/118):
  HEADLINE-1: fuzz FINAL: ZNR 2000 + M21 2000 games, ZERO crashes both eras (baseline 7.5%/1.4%); all classes pinned (412/412 packs, core+tools 2953+36st; 1 fail + 1 collect-error = sibling B9 WIP)
  HEADLINE-2: FIRST GENERALIZATION BASELINE: bsh_S3a_s3_best (frozen M21-era) vs teacher on ZNR 40g: 18-22, 0 crashes, 100% decisive -> reports/shadow_ZNR_bshS3a3_vs_teacher_2026-10-19.json
  OWNER QUESTIONS (blockers): (1) MDFC back-face playability = set-rule in this world? (/106; encoded, never playable until answered) (2) R1 capacity window still unused
  sibling waves live: B9/party (tree shows PC-1 0.3688/PC-2 0.5413 pre-commit); /112+/116 compiler-lane proposals handed off (Beyeen one already landed via their B9)
- updated: 2026-10-19 14:1x (late-window delta, end of autonomous run): generalization ERA PARITY (/123 2x2 grid committed 99c5edc) · ZND-4d ever-live while-statics fixed c527014 (gate 6-axis GO) · cast-payability legality landed 1c3dac6 after 3 gate rounds (round-2 NO-GO had real B1-B3; round-3 re-gate withdrew its OWN 27-red claim as stale-pycache artifact — reds must survive a fresh rerun to be admissible, PITFALLS) · deep fuzz cap-400 1000/era 0 crashes · packs 415/415 · core 2824+36st · sibling live on ontology-R1a wave (149-file tree, hands off). OPEN OWNER QUESTIONS UNCHANGED: MDFC world-rule (/106), R1 window (/94).
