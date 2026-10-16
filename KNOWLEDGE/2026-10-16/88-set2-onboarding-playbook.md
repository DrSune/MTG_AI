# 88 — Set-2 (ZNR) onboarding playbook — the R3 program's first runbook, PRE-AUTHORED so the owner's verified drop-in triggers a 1-day close, not a 1-week scramble

Trigger: owner drops VERIFIED MTG_bot/data/ZNR.json (+ checksum confirmation).
Day plan (all machinery exists; commands in-line):
1. INTEGRITY: re-run the 2026-10-08 sanity battery on the new file (the one that caught the suspect file, /59); reject on any mismatch; then golden-tree ingest for the set with clause audit (§11 zero-loss): `.venv/bin/python -m tools.audit.clause_audit --set ZNR` -> gap ledger, not just a compile rate (§8 law: atomics RE-EVALUATION vs TOTAL pool — census new shapes, top-5 rule-dense cards stress proof).
2. TOKENIZER MOMENT (§8/§9/§10): new card-name lanes hit UNK under old vocabs — this is exactly the drift we measured (33.55%, /76); decide per /76: containment (vocab-from-live, proven) or digit-cure adoption (NUMTOK=1, now gated+tested). Evidence-first: run drift_probe on the frontier clone vs ZNR live asks BEFORE choosing.
3. GENERALIZATION FIRST MEASURE: `python -m tools.eval.holdout_report --ckpts <era ckpts> --split set --fresh-sets ZNR` -> first TRUE set-level unseen-card score (the founding promise, quantified at last). Era nets vs shadow clone on fresh cards — the tokeniz­er law's payoff table.
4. SHADOW DAY-1 PIPELINE (proven /77): champ_shadow gen (bsh_S3a_s1 expert, ZNR deck pairs, 48-64 games) -> trainer --episodes (vocab-from-live) -> WR-probe admission (200g teacher + mirror frontier) -> FRONTIER.md entry. One day, zero new machinery.
5. ATOMICS VERDICT: entries per §8 into NUMBERS.md (compile rate, non-representable patterns top-N, ask-kind coverage delta, eval items un-askable list). ANY material atom change = Type-1 -> adversarial gate before landing.
Risks pre-noted: (a) ZNR text shapes may break the atomics (expected per §8: first sets CHANGE atomics — budget rewrites); (b) engine pool: ZNR cards unplayable until compile green — step 1 gates everything.
