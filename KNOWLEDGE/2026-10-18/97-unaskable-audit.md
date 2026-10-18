# 97 — Un-askable eval-item audit (runbook step 4, R3 /85 program)

Instrument: `tools/eval/unaskable_audit.py` (new, READ-ONLY elsewhere;
dynamic lane replays each item's pack through `puzzle_cert.extract_items`,
static lane = pack-union golden-tree shape reachability).
Run: `systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 bash -c
'.venv/bin/python tools/eval/unaskable_audit.py --out tools/eval/unaskable_audit.json'`

**Headline: eval-side un-askable items = 0/58.** All 58 eval items
(33 eval families) had their asks SURFACE under current code
(44 packs replayed, 0 failures, 0 gold drift). No degradation to static-only
needed; static backstop agrees (57 askable + 1 n-a: Stray Aurochs, ZNR card
with no M21 golden).

**Residue is train-side only:** 11/199 corpus items fail-registered
(ask-kind: may 6, choose 3, name 1, target 1; verdicts: true-no-decision 7,
null-degenerate-observable 3, engine-semantics-gap 1; cards: Chandra ×2 pair,
Liliana's Devotee, Runed Halo, Destructive Tampering, Tempered Veteran,
Tolarian Kraken ×3).

**/25-era backlog: burned down.** /24 survivors Meteorite (target+mana),
Read the Tides (choose×2), Waker of Waves (one_of), Havoc Jester
(sacrifice+target ×2) all now live-askable — the /29–43 atomization plus
/62 act-sense (+19 items) and /63 clause closure did it.
Eval-side card-level blind spot: `basri_ket_x_experimental_overload.json`
is designation-lane (CAST-time consumed, no menu ask) for Experimental
Overload.
