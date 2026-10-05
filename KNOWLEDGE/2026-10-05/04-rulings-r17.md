# 04 — Rulings R17-1 / R17-2 (orchestrator, 2026-10-05)

## R17-1 — Response-window unscripted asks: option (a) APPROVED
Rig-side always-installed provider with PASS fallback (tools/run_scenarios.py + games harness),
mirroring the existing DECLINE/NONE/skip combat fallbacks. Constraints (all binding):
1. The fallback lives in RIG ONLY — the engine never defaults (14b law holds).
2. Every unscripted PASS journals a visible WINDOW_PASS row — no silent defaults in traces;
   the catalog sees every window.
3. Scripted `decisions` answers take precedence; wave-7 packs script their real lines.
4. Regression expectation: ZERO of the 339 current packs holds a counter card (all five
   counters are excluded_by_flag) ⇒ zero windows in existing packs ⇒ 339 green must be
   byte-identical-provable.
5. Sublime Epiphany deferral cite amended to "counter window AND COPY-handler absent" in
   tools/audit/deferrals.json (keeps PC-11 honest under wave-7).

## R17-2 — E3 hidden-zone target leak (Volcanic Geyser): CONFIRMED — fix arc APPROVED
Real MTG "any target" = creature, planeswalker, or player — never hand/library cards. The
compiled TARGET selector zone=ANY/controller=ANY is an emission bug for the printed "any
target" idiom, not an engine-legality choice. Route (C1-form, batch "geyser-sweep"):
1. Corpus sweep: every golden TARGET selector with zone=ANY (or controller=ANY) — classify
   printed clause: "any target" idiom (restrict to creature+PW+player, battlefield) vs
   legitimately broad (printed graveyard/library/hand targets — KEEP as printed).
2. Template emission fix; audited golden moves for affected cards (printed-vs-compiled
   set-equality per card, /tmp/golden_pre_geyser/ snapshot).
3. RED-pin FIRST (Geyser candidate enumeration must show the leak, then go clean);
   re-measure masked_target_probe.py → expect 0 hidden candidates (D10 becomes a standing
   regression gate).
4. Catalog full-divergence expected (candidate sets shift RandomPolicy picks) — attribute +
   repin per /07 method; games 0-crash bar.

## Eval gates adopted from the exploit audit (standing law for any training/eval work)
D8: report robust winrate over opponent-noise band [0.5,1.0] as the HEADLINE, never vs-pure-
random. D9: rotate eval seeds; report fixed-vs-unseen delta; a policy's gain that vanishes on
unseen seeds is memorization, not skill. D10: masked-observation ablation; positive
full-vs-masked delta = hidden-info exploitation → disqualify. D11: combat-skill gains must
survive blocker randomization. Seat-swap all duel measurements (E7: 0.530 seat bias).
