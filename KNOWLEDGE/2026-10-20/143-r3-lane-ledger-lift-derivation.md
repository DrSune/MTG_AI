# 143 — R3 phase 1: lane ledger committed + LIFT-NOW derivation (2026-10-20)

Executes /141 §Phase-1. Generator `tools/audit/r3_lane_ledger.py` (ported from the
session audit script, RULES/classify preserved verbatim incl. the documented dead
`count == "QUnbounded"` branch) regenerates `reports/r3_blindness.json`
**byte-identically** (`cmp` PASS; ensure_ascii, indent=1, no trailing newline).

## Measurements
- CHOOSE-node lanes: **L-Silent 161 / L-B 27 / L-Other 5**.
- V4′ pre-upgrade baseline diffs: NONE (count-only lane).
- LIFT-NOW per /141 §6 three rules: **14 cards / 14 nodes** —
  - firstn (Site A, `selectors.resolve_selector` CHOOSE fold): Alpine Houndmaster
    (SEARCH LIB:YOU), Cultivate (SEARCH LIB:YOU), Kinetic Augur (HAND:YOU),
    Rewind (UNTAP BF:ANY), Ugin, the Spirit Dragon (HAND:YOU) — 5 nodes;
  - disco (Site B/C, `legality` CostDiscard plan+pay lanes): Demonic Embrace,
    Ghostly Pilferer, Niambi Esteemed Speaker, Sanctum of Shattered Heights,
    Seasoned Hallowblade, Sparkhunter Masticore, Thrill of Possibility,
    Tormenting Voice (ZNR) — 8 nodes, all HAND:YOU QConst;
  - saptap (Site B/C, CostTap lane): Shacklegeist — 1 node, BATTLEFIELD ANY with
    CONTROLLER_IS-YOU filter pin (choosability pinned by the filter, public zone).

## FINDING vs /141's "15 cards / 17 nodes"
The spec's arithmetic is internally inconsistent: its own exclusion sentence
removes Bad Deal + Waker +1 from the first-n lane it had just added them to
(double-count), and **Run Afoul** is excluded on executor ground truth — the
ledger's `legal_chooser` field says "effect controller / payer" but the same
ledger row's own `text_excerpt` reads "Target opponent sacrifices a creature of
their choice…" (the OPPOSED player is the CR chooser; direction is unencoded in
the IR → ZND-9/ZND-7 seat-in-tag lane, exactly the Run Afoul precedent class).
Rule-derived verdict: 14/14. Held L-B (13): 7 QUnbounded (ONE_OF lane raises
NotImplementedError on them — deferring is the honest lane), Goremand /
Liliana's Steward / Mind Rot + Run Afoul (opponent choosers → ZND-9), Bad Deal +
Waker +1 (merged multi-seat HAND:ANY → ZND-7(a)).

## Runtime wiring ground truth recovered from compiled pools (drives phases 2-3)
All 14 nodes resolve through THREE lift sites only:
1. `selectors.resolve_selector` CHOOSE fold (`ordered[:k]`, :575-579) — opt-in
   flag from the EFFECT-role lanes only (role_handles non-cast branch +
   verbs pool line); quantity-count / legality / query callers stay silent.
2. `legality.build_payment_plan` CostTap target branch `tap.extend(cands[:need])`
   + CostDiscard branch `discard.extend(cands[:need])` — record
   tap_options/discard_options exactly like r22a `sacrifice_options`.
3. `legality.pay_costs` — re-open the choice when len(pool) > need with seat-in
   ask keys `tap:<seat>:<source>:<digest>` / `discard:<seat>:<source>:<digest>`
   (sacrifice precedent :1420-1440); forced segments keep the witness pick
   byte-identically; hand-built plans (default ()) pay the frozen path.

Pre-compiled-bytes snapshot for the Δ0 headline: `/tmp/opencode/r3_compiled_pre.json`
(M21 305 cards sha256 52ae7619…, ZNR 281 cards sha256 e8965a74…, gaps 0/1).

---

## Evidence copy (R3 diff-gate follow-up, 2026-10-20 — rows above point here)

Verification evidence is committed under `KNOWLEDGE/2026-10-20/artifacts/`
(the `/tmp/opencode/...` paths named above are ephemeral working copies):

- `r3-red-prechange.log` — battery RED-first state before wiring (6F/11P).
- `r3-fuzz-run1.json` / `r3-fuzz-run2.json` — ZNR fuzz `--games 40` same-seed
  double-run (outcome-identical; only `seconds` timing fields differ).
- `r3-compiled-pre.json` — the Δ0 snapshot (M21 `52ae7619…`, ZNR `e8965a74…`).
  Reproducing command (re-hashes the CURRENT compile and must print those
  shas — this is the Δ0 law, re-executed and matched 2026-10-20):
  `.venv/bin/python -c "import hashlib,sys; sys.path[:0]=['.','tools/audit']; from MTG_bot.core.ability_tree import canonical_json; import ontology_conformance as oc; [print(s, hashlib.sha256(''.join(canonical_json(v['cards'][o]) for o in sorted(v['cards'])).encode()).hexdigest()) for s,v in sorted(oc.compile_pools().items())]"`
- `r3gate-v4-extinction-pre-fix.log` / `-post-fix.log` — FIX-1 (BREAK-R3-1)
  red→green chain of the V4′ extinction probes.
