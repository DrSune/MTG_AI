# 128 — ZNR eval packs + first TRUE set-level generalization score (fresh=ZNR)

**Date:** 2026-10-19 · **Session lane:** ZNR eval packs (entry was requested as "127"; a
sibling compiler wave filed `127-r1a-construction-canonicalization-landed.md` first, so this
occupies 128 — content unchanged).
**Owner artifacts (all NEW, none committed):** 13 packs
`tools/scenarios/znr_eval_*.json`; meter JSON `tools/eval/holdout_znr_first.json`
(both lanes embedded); engine + `tools/**` untouched.

## 1. The packs (13, replay 13/13 PASS; tools suite 271/271, 0 failures)
Real-ZNR-card first entry per pack, oracle text from `MTG_bot/data/ZNR.json`, gold
hand-certified from ORACLE TEXT with CR cites in each pack `note` (kicker 702.27a,
landfall 603.8b, sickness 302.6, haste 702.10, triggers 603.2, PT-stack layer 7c, may 701.4).

| lane | packs |
|---|---|
| kicker | might_of_murasa, ghastly_gloomhunter, scorch_rider (haste+kick), tazeem_roilmage |
| landfall | makindi_ox, hellhound_jerboa, nectarpot_lagac, felidar (counters), scute_swarm (token) |
| EtB tails | survivor_etb_counter, oran_rief_ooze_etb_counter (controller-filtered menu) |
| spell-kind / misc | rockslide_spellkind_triangle (B10), windrider_may_draw (may+forced-discard) |

## 2. Cert table (`puzzle_cert.certify_pack`, rollouts=200, /tmp only — shared puzzle_corpus.json NOT written)
10 puzzle items from 6 packs. **oracle=1.0 on all 10; null=0.0 on all 10 (0 offenders);
l1_ready=1** (rockslide step0, rand 0.035 — the only item under the random ceiling).

| item (pack:step:ask) | rand | gold | ncand |
|---|---|---|---|
| makindi_ox:step0:target | 0.575 | card:3 | 2 |
| makindi_ox:step1:target | 0.510 | card:4 | 2 |
| oran_rief_ooze:step0:target | 0.345 | card:1 (self) | 3 |
| rockslide:step0:target | **0.035 (l1)** | player:1 | 4 |
| rockslide:step2:target | 0.200 | player:1 | 5 |
| survivor:step0:target | 0.130 | card:0 | 3 |
| survivor:step1:target | 0.195 | card:2 | 4 |
| roilmage:step0:target | 0.465 | card:3 | 2 |
| windrider:step1:may | 0.130 | fire | 2 |
| windrider:step1:one_of | 0.290 | card:3 | 4 |

First-run offenders (ooze/roilmage/windrider, class *null-pick-equals-gold*: illegal-word
fallback lands on vocab[0]=gold) fixed by moving gold off the menu head; re-certified clean.

## 3. First TRUE set-level GAP (`holdout_report --split set --fresh-sets ZNR`)
**Verbatim lane is DEGENERATE** (frozen corpus: 0 ZNR items; `mtg_bot.db` M21-only ⇒
n_fresh=0) — kept as evidence in `tools/eval/holdout_znr_first.json` (`verbatim_lane` key;
seen accs reproduce 86's gate numbers exactly: bc9 0.7638 / bsh 0.6432 / bc10 0.7588, n=199).
**Patched lane** (from /tmp): packrec episodes for the 6 item-packs appended to a /tmp copy of
`episodes_v2.jsonl`, cert items appended to a /tmp copy of `puzzle_corpus.json`
(`join_corpus` pack-name-keyed, order-independent; gold-line/item counts byte-aligned),
`card_sets()` monkeypatched to map the 6 ZNR names → ZNR; `score()`/bootstrap UNCHANGED.
Checkpoints never saw ZNR ⇒ fresh side = true set-level generalization.

| ckpt | seen (n=199) | fresh (n=10) | GAP | SE | CI95 |
|---|---|---|---|---|---|
| bc9_S3_s1 | 0.7638 | 0.30 | **−0.464** | 0.151 | [−0.759, −0.169] |
| bsh_S3a_s1 | 0.6432 | 0.30 | **−0.343** | 0.147 | [−0.632, −0.054] |
| bc10_S3a_s1 | 0.7588 | **0.50** | **−0.259** | 0.189 | [−0.630, +0.112] |

Per-item color: **bc9 and bsh predict IDENTICALLY on all 10 fresh items** (shared positional
mode, pred≈idx1/2 bias); both get only survivor-step1 + windrider-may. bc10 additionally gets
makindi step0, rockslide step0 (the `player:1` spell-kind ask!), roilmage, windrider one_of.
Era net on fresh: **bc10 > bc9 = bsh** (+0.20), while seen-order is bc9 ≥ bc10 — the first
evidence that the B10 spell-kind era generalizes OOD better than it scores in-distribution.
**Caveats:** n=10 items / 6 cards → SEs are huge; direction, not magnitude; partial-compile
(§4) means the fresh side tests only the compiled half of each card; regeneration of the
shared corpus/DB is owed to the sibling compiler wave before this lane becomes the standing meter.

## 4. Gap ledger (gold-vs-engine; packs skipped or half-asserted, gold never bent to engine)
- `Skyclave Pick-Axe`: compiles 3 abilities but NO SpellAbility carrier ⇒ `cast:not_a_spell` (untestable).
- `Tazeem Raptor`, `Zulaport Duelist`: creature EtB triggers DROPPED (SpellAbility-only compile).
- `Fissure Wizard` MISCOMPILED: may-discard clause dropped ⇒ unconditional DRAW on spell.
- `Oran-Rief Ooze` attack trigger DROPPED (EtB only) ⇒ combat half not asserted.
- `Pressure Point` tap clause DROPPED (DRAW only).
- Ambiguous mandatory spell target NEVER asks: engine raises `count_below_min` instead (silent auto-designation only when unique).
- `Nighthawk Scavenger` shape-gap exclusion at supply load (`parse_pt '1+*'`) — printed every load, benign-but-open.
- ("Roil" card in an earlier draft was MY fabrication — never existed in ZNR; pack deleted pre-cert.)
- Confirmed WORKING: landfall through op `"enter"`, Scute Swarm token lane, PT-grant stacking (Murasa 10/10 = oracle).

**Commands:** `tools/run_scenarios.py --dir tools/scenarios` (scoped), `pytest tools -q`,
cert+meter lanes reproducible from `/tmp/opencode/znr_eval_lane/{cert_run,record_znr,meter_patched}.py`
(session-scoped; regenerate via the recipes above if /tmp is cleared).
