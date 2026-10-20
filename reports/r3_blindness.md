# R3 silent-CHOOSE blindness audit (M21+ZNR) — 2026-10-20
Full ledger: `/tmp/opencode/r3_blindness.json` (per node: card, ability, path, resolver w/ code cite, lane). Read-only; repo untouched.

## Census
**193 nodes / 146 cards** (M21 145/104, ZNR 48/42), `compile_pools()` + card-root dataclass walk (incl. emblem) — **reproduces the V4′ freeze baseline, zero diffs**. §8's "174" = CHOOSE inside the capped top-40 branching rows of `reports/ontology_census_2026-10-19.json`, nodes conflated with cards (full-cap: 192; +1 emblem = 193).

## Lanes (193; every L-A cites its executor rule)
| Lane/rule | n | Representative | Resolver |
|---|---|---|---|
| L-A self-designation | 108 | Basri's Aegis | r20c IS_SOURCE carve-back, selectors.py:896-910 |
| L-A referent-bound | 48 | Waker emblem | selectors.py:419-452 |
| L-B first-n effect | 18 | Cultivate, Mind Rot, Ugin | ordered[:count], selectors.py:575-579 |
| L-B discard-cost | 8 | Thrill of Possibility | plan-time cands[:need], legality.py:801-830 |
| L-A library-top | 3 | Conspicuous Snoop | verbs.py:233-245 idiom |
| L-C sacrifice-cost | 5 | Village Rites | **already asked**, r22a 14b lane, legality.py:1407-1440. Deviation: L-C = "surfaced elsewhere", no §10 violation |
| L-A seat-singleton | 2 | Runed Halo | PLAYER:YOU = one seat |
| L-B tap-cost | 1 | Shacklegeist | cands[:need], no tap_options lane, legality.py:756-770 |

**L-B = 27 nodes / 24 cards.** Opponent-chooser subset: Goremand ab0, Liliana's Steward, Mind Rot, Necromentia, Run Afoul. *Correctness finding (not a lane):* Bad Deal & Waker +1 discard resolve first-n of the **merged** all-player hands (`HAND:ANY`, no EachPlayer wrapper, verbs.py:156-200); text says "each opponent discards two".

## Eval collision
ZNR holdout's 6 fresh cards: zero CHOOSE (clean). L-B cards only in `holdout_znr_first.json` `seen.cards`. Live eval item: `unaskable_audit.json` `Alpine Houndmaster|…|step0|may#0`. ~50 packs cover L-B cards; Thrill's is forced-population (gold robust).

## Smallest ask-shape + wave
Sequential picks + STOP token, reusing the `choose:<source>:<digest>` vocab site (avoids C15 enumeration):
```
CURRENT  Cultivate Atom(SEARCH): selector{mode:CHOOSE, count:QConst 2,
         filter:SUPERTYPE_EQ"Basic", zones:[LIBRARY:YOU]}   ← silent first-2
PROPOSED + ask{key:"choose:cultivate:<digest>", pick:"1..2+STOP",
         menu:"live-legality query", default:engine-first2}
Rewind UNTAP QConst 4 → "1..4+STOP";  Thrill CostDiscard 1 → "1+none"
```
**Wave:** IR bytes **0** (encoding unchanged; ask is runtime legality-surface) + new ask sites in ~50 packs needing decision-supply + replay/ask_log digest re-pins where multi-option CHOOSE is asserted.

## Freeze verdict: **(ii)** lift L-B-derived shapes, checker allow-rules
(iii) moot — capability exists (14b channel, ONE_OF k-of-n NONE-stop, query.py:184). (i) rejected: re-opens 158+ self/referent phantom emissions (§10), which must encode as no-decision. (ii) lifts exactly the 27 real choices, preserves gold, keeps L-A frozen.
