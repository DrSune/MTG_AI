# 114 — ZND-4 EVIDENCE: the one-row-away census — 102 of the 197 residue cards sit one sentence from compiling; PC-1 lever analysis (evidence file, no round bound yet)

Method: `reports/grammar_2026-10-19_ZNR.json` unparsed_queue, front-face rows only, grouped by card.
Reproduce: python3 — group `norm(name)` rows, `len(rows)==1` ⇒ 102 cards.

## Why this matters (PC-1 mechanics)
PC-1 = 84/282 (0.2979) counts cards with ZERO unparsed rows. The register's remaining 353 rows sit on
197 cards; 102 of them carry EXACTLY ONE unparsed sentence. Every row cleared on a one-away card is a
FLIP (+1/282 = +0.0035 PC-1 each) — vs. multi-row cards where a cleared row moves only PC-2. The
round design inverts: pick shapes BY CARD YIELD, not by row count.

## Shape clusters among the 102 (from /tmp/opencode analysis at 14c4af2)
- **[2] Equip activation** `Equip {2}{R} ({2}{R}: Attach to target creature you control. Equip only
  as a sorcery.)` (Scavenged Blade, Skyclave Pick-Axe) — SURPRISE: the equip-EtB tail landed in ZND-2
  (T2) but the equip ACTIVATION ability stays unparsed; the b6/b7 attach machinery exists → reuse-first
  audit first, likely template-cheap. Other equipment cards carry this row too as non-singleton.
- **[2] EtB gain-N-life** (Turntimber Ascetic, Skyclave Cleric) — trivially close in the b7/b8 idiom
  (life-gain tail exists for other events).
- **[~97] singletons** — the real cost: e.g. Kabira Takedown "damage equal to the number of creatures
  you control to target creature or planeswalker" (census×DEAL_DAMAGE — QCount already exists), Emeria
  Captain bare "Flying, vigilance" keyword-continuation ROW (keyword static exists — why unparsed?
  comma-continuation parse), Skyclave Shade graveyard-Landfall-cast (ZND-2 landfall head + graveyard
  zone + manifest-adjacent cast lane), "It's still a land." (3 cards, ANIMATE-lane tail),
  "During turns other than yours..." (off-turn PT window), "that blocked this turn" (history filter),
  modal "Choose one" ×3 Inscriptions + "If this spell was kicked, choose any number instead" ×3
  (kick×modal interaction = the /105 effect-lane family).

## ZND-4 round-design options (Type-1 choice — needs the spec gate, /101 form)
(a) **FLIP SWEEP round**: batch template shapes ranked by flips (the singleton families grouped by
executor-lane affinity: census-damage, keyword-continuation parse, still-a-land tail, off-turn window,
blocked-this-turn filter) — highest PC-1 per unit engine risk, template-only where lanes exist.
(b) **Kick-effect-lane round** (the /105 withheld family: "If this spell was kicked, choose any number
instead" + manifest/permits) — needs effect-vocabulary additions (spec-gated).
(c) FACE-B residue 10 rows (ZND-2f deferred set) — back-face round follow-up; PC-1-neutral.
First move at spec time: per-card reuse audit per singleton (the /101 lesson — several "singletons"
may share an EXISTING lane the parser just doesn't route — e.g. bare keyword rows may be a parse
gap, not a vocabulary gap).

## Registered facts
- one-row-away cards: **102**; multi-row residue cards: 95; total residue rows (front): 343; face-B: 10.
- Max theoretical PC-1 from the 102 alone: 84→186 = 0.6596 (upper bound, obviously unreachable; the
  round harvests the lane-backed subset).
- Baseline command: `tools/measure_grammar.py --set ZNR` @ commit 14c4af2, 2026-10-19.
