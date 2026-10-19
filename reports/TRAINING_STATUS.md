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
