# 207 — Card onboarding: what M21, M20 and FDN taught, for the next sets

**Context.** The owner (2026-11-14): "Make sure you learn from your/agents work on cards, so we
make less mistakes/good quality faster in the future for other sets."

What this note draws on:
- the card notes 173-177, 184, 201, 203, 204 and 206, and the gate log
  (`docs/DESIGN_ATOM_ONTOLOGY.md` §9);
- the verdicts and answer keys of the ten blind rounds whose files survive (2026-11-05 to 11-13);
- the 117 agent briefs, 157 agent transcripts and 47 follow-up messages of session `2e18468a`;
- the git history of the card records and the M21 goldens.

The M21 campaign's own verdicts (2026-10-29/30) were lost with `/tmp` in the 11-02 reboot, so
that campaign is counted from its notes.

**State on 2026-11-14:** M21 275 of 285 cards verified, M20 277 of 329, FDN 184 of 517 (736
records verified).

Evidence: `reports/card_lessons_2026-11-14/`. `ledger.py` holds one row per fault and prints the
§1 tallies; the README there lists the measurement scripts and their inputs.

## 1. The numbers first

| Measure | Value |
|---|---|
| Faults found by the card work, 10-29 to 11-13 (one row per cause) | **189** |
| ... made in the engine / the compiler / the IR / the tools / by a mapper | 111 / 38 / 27 / 9 / **4** |
| ... caught by the blind verifier / a mapper's own trace / a gate round / a fixer building another fix / hunts, crashes, audits, reviews / G3, G0 | 91 / 30 / 19 / 16 / 26 / 7 |
| ... played by cards already verified (escapes) | 22 (19 engine, 2 compiler, 1 IR) |
| Planted faults caught by blind verifiers | **176 of 176** (M21 85, FDN round 1 16, later rounds 75) |
| Real cards judged WRONG | M21 campaign 89 of 360 (25%); FDN round 1 12 of 71 (17%); rounds since 11-05 26 of 490 (5%): 14 engine, 8 IR gaps, 3 mapper records, 1 tool fault (the probe hid an ask) |
| Cards OK in review but blocked by G3 until more packs or a G3 rule came | 112: M21 55, FDN 12, M20 15, waves 1-1e 30 of 72 |
| Stamps re-made after a tree change; cards that left a pool for a while | 34; 12 (wave 2A's merge) |
| Duplicate reviews: cards reviewed in two or three of the home sets, same tree bytes | 62 cards, 85 extra reviews |
| Agent time per verified card | about 3 agent-minutes when no component is new, about 49 when it waits on IR or engine work (§4) |

### By fault class

Plants count the answer keys (75); G3 counts the critical survivors in the apply logs of the six
rounds with logs (68).

| Class | Faults | Made in | Caught by | Plants | G3 survivors | Escapes |
|---|---|---|---|---|---|---|
| Other engine rules (combat, stack, state-based actions, protection) | 41 | engine 40, compiler 1 | verifier 24, hunt 5, mapper 5, gate 3, crash 2, fixer 2 | - | - | 3 |
| IR gaps (no node, or two encodings accepted) | 21 | IR 15, compiler 6 | verifier 10, gate 8, mapper 2, crash 1 | - | - | 0 |
| Targets and counts ("up to", "any number", target vs all) | 20 | engine 14, compiler 4, mapper 2 | verifier 10, mapper 5, crash 2, fixer 1, review 1, G3 1 | 5 | 18 | 4 |
| Compiler grammar (a sentence misread or dropped) | 18 | compiler 17, mapper 1 | verifier 13, audit 2, mapper 2, G0 1 | - | - | 0 |
| Who acts, or whose (controller, direction) | 17 | engine 9, IR 5, compiler 2, mapper 1 | verifier 5, mapper 4, fixer 3, gate 3, audit 1, hunt 1 | **29** | 20 | 3 |
| Zone or ownership | 15 | engine 14, compiler 1 | verifier 5, fixer 3, G3 2, hunt 2, mapper 2, review 1 | 3 | 3 | 4 |
| Order and timing | 13 | engine 10, IR 2, compiler 1 | verifier 6, mapper 4, hunt 2, gate 1 | - | 1 | 2 |
| Once versus each | 11 | engine 9, IR 2 | fixer 4, verifier 4, mapper 1, review 1, gate 1 | - | 1 | 3 |
| Costs | 10 | engine 6, compiler 3, IR 1 | verifier 4, audit 2, review 2, fixer 1, mapper 1 | 6 | 3 | 2 |
| Durations | 9 | engine 7, IR 2 | verifier 4, mapper 4, hunt 1 | 3 | 4 | 0 |
| Tools (probe, runner, G3, cardtool) | 9 | tools | G3 2, fixer 2, gate 2, verifier 2, G0 1 | - | - | 0 |
| An optional "may" | 5 | compiler 3, engine 2 | verifier 4, gate 1 | - | 1 | 1 |
| Amounts (one too many or few) | in the classes above | | | **29** | 17 | |

**The cheapest stage that could have caught each fault:**
- a pack: 56;
- the probe's trace, read: 56;
- an engine test: 32;
- a gate round: 26;
- a static check of the tree against the text: 15;
- G0: 4.

**Readings.**
- **The engine, not the mapping, is where the faults are.** Mappers made 4 of 189. 111 were rules
  faults, and the blind verifier and the mappers' own traces found 70 of them. So reading traces
  pays most.
- **The trees' faults cluster in a few kinds:** who acts, numbers and costs (64 of 75 plants),
  a compiled sentence dropped or misread, and a validator that accepted a second encoding.
  - A static check catches most of the first group with no agent at all (§5.1).
  - Gate rounds catch the last kind: 7 of their 14 MAJOR findings were a second encoding or a
    role allowed where it means nothing.
- **The escapes came from engine facts the review could not see.** Examples:
  - DESTROY ignored indestructible;
  - lifelink made one event per recipient;
  - a stolen permanent kept its old controller in its records;
  - "This spell costs less" never applied in games.

  Fixers building other fixes found 8 of the 22, game reviews 5. Stamps stay honest only if the
  cards a merge touches are re-reviewed.

## 2. The process costs

- **G3 round trips.**
  - 112 cards passed review but had a critical mutant that no pack told apart.
  - In waves 1-1e the coordinator sent 11 follow-up messages naming 30 cards.
  - Each trip took about an hour of wall time: 64-68 minutes from the follow-up message to the
    stamp in waves 1, 1b, 1c and 1e. The verifier agents spent 135 active minutes in all,
    follow-ups included.
  - Some survivors were equivalent mutants, closed by rules in `gates.mutants` instead: 18 rules on
    10-29/30, dead roles on 11-12, twin targets on 11-13. Finding the wave-2 ones took 158
    agent-minutes.
- **Re-verification.**
  - 34 stamps were re-made because a tree changed: 16 record re-maps (3 mapper fixes, 13 IR
    migrations such as `once_per_event`, `arrange` and reflexive triggers), and compiled trees.
  - Wave 2A's merge took the pools from M21 270, M20 257 and FDN 175 down to 264, 253 and 173.
    The re-verification won them back within hours.
- **Merges of parallel lanes.**
  - On 11-12/13, 15 lanes merged into main (12 of them card work), and lanes merged main 11
    times to catch up.
  - `gates.is_critical` and the BACKLOG conflicted in text.
  - Two correct fixes (`arrange` and the owner's library) turned one pack red in meaning; only
    `tools/check.sh` on the merged tree saw it (203 §3).
- **Duplicate work.** 62 cards were verified in two or three of M21, M20 and FDN with the same tree
  bytes, by different reviewers 59 times: 85 reviews that reprint reuse would have saved.

## 3. What worked, and must stay

- **Plants in every batch.** 176 of 176 caught keeps the blind review's rate measured. Two per
  batch, on verified cards appearing nowhere else in it.
- **The two-person rule and another model family.** Sonnet verifiers caught every plant at about
  1.3 active minutes and 4.3k output tokens a packet. Opus verifiers took about 1.0 minute and
  5.0k tokens.
- **Census first, by missing piece.** Wave 3's census turned M20's 55 castable-unverified cards
  into three packages, built widest first in gate rounds 8-10, beside one ungated engine track.
- **An adversarial gate round for every IR change.** Rounds 4-10 found 14 MAJOR in branches whose
  suites were green, plus a FATAL in round 10's pre-gate review (verified Basri Ket's -2 crashed).
- **Fresh-eyes reviews of engine diffs**, and red teams of each fix wave. The red team of the
  11-05 second wave rated 13 of its 18 fixes solid and found 4 partial and 1 regression (184 §7).
- **Re-verifying the cards a merge touches, and blast radius by script:** trees changed, verified
  in and out, 300-600 seeded replays.
- **Root-cause fixes with a test that fails before.**
- **The pack runner's strictness:** unknown lanes and unoffered decision words fail a pack.
  Verifiers also make every pack fail a wrong expectation once, and use verified supporting cards.
- **Lessons and known faults in the next wave's brief.** The second M20 mapping wave, given them,
  took 36-41 minutes a batch against 39-51.

## 4. Where the time goes, and the reuse levers

**Time per card** (active agent-minutes from the transcripts: gaps of at most 15 minutes between
an agent's messages).

| Phase | Agents | Active minutes | Per unit |
|---|---|---|---|
| Mapping, M20 11-05 (237 cards: 152 written, 82 needs-atom, 3 skipped) | 10 | 414 | 1.75 per card, 7.5k output tokens |
| Blind review, opus (465 packets, 11-05/06) | 14 | 452 | 0.97 per packet, 5.0k tokens |
| Blind review, sonnet (100 packets, waves 1-1e, follow-ups included) | 8 | 135 | 1.35 per packet, 4.3k tokens |
| G3 kill packs (18 cards) | 2 | 39 | 2.2 per card sent |
| IR and engine fixers, backlog waves 11-12/13 | 13 | 1,530 | 118 per lane |
| Gate reviewers, rounds 4-10 | 7 | 281 | 40 per round, 20 per MAJOR |
| G3 rule work (equivalent mutants) | 4 | 158 | |

**Readings.**
- **The bulk.** M20 and FDN on 11-05/06 took 987 agent-minutes (476 more for that day's engine
  fixes and red teams) for 371 first stamps: **about 3 agent-minutes a card**.
- **The tail.** The card backlog of 11-12/13 took 2,141 agent-minutes for 44 first stamps:
  **about 49 a card**. Fixes took 71%, gate rounds 13%, G3 rule work 7%, verification 6% and the
  census 2%.
- So a set's pace is decided by how many of its cards wait on new components, and by how well
  the census groups them.

**Reprint reuse** (`cardtool verify --reprint-of`, built here, §5.3).
- 404 printings in the 16 other ingested sets share their oracle id and printed text (`text_sha`)
  with a card verified in M21, M20 or FDN: 182 distinct cards, 9.4% of those sets' 4,308 cards.
- Every one builds the home stamp's tree bytes in its own set. 340 are compiled cards, so the
  compiler alone gives the same tree; 64 are mapped cards, which take the home record's tree.
- Per set: M19 66, M14 31, M10 30, M13 30, M11 28, M12 27, M15 26, ORI 24, IKO 24, 10E 23,
  WAR 22, DOM 19, THB 16, ZNR 15, ELD 14, KHM 9. FDN itself holds 6 cards verified only in M20.
- **None reused a stamp before this note.** The `verified` supply reads only its own set's
  records (`games.compile_supply` → `load_records(set_code)`).
- The dry run of the new path, records written to a scratch directory: **402 of the 404** would
  be stamped. The other 2 (ZNR Spitfire Lagac, DOM Tatyova, Benthic Druid, both verified in FDN)
  carry round 10's "each occurrence" mutant, which their FDN packs predate (ontology §14).

**Near-reuse (slots).** 7,597 rules sentences of the 3,799 unverified cards with text in those 16
sets, reprints left out, compared with the 812 sentences of the verified cards. The name is `~`;
digits and number words, colour words, type words and coloured mana symbols are slots.

| Sentence | Parses today | Does not parse |
|---|---|---|
| word for word a verified card's sentence | 1,831 | 246 |
| a verified sentence with other slot values | 307 | 150 |
| no verified analog | 513 | 4,550 |

- Cards: 717 parse whole. 584 have every sentence verified word for word or by slot, and 416 of
  those word for word.
- Of the 3,082 partly compiled cards, 103 (3.3%) have a verified analog for every unparsed
  sentence, 55 of them only through a slot.
- The commonest unparsed slot variants:
  - "Look at the top N cards of your library." (12);
  - "Other <type> you control get +N/+N." (10);
  - "Draw N cards." (10). Today "Draw two cards." parses, while "Draw three cards.", "Destroy all
    creatures.", "Counter target creature spell." and "Draw a card, then discard a card." do not.
- **The frame generaliser** (a template made from a verified tree by freeing its slots: King
  goal 1b, zero code for practised primitives) would cover 396 of 4,946 unparsed sentences (8%)
  and make 103 cards whole. Its value is in taking the template-per-wording work off the
  compiler for those shapes. 92% of the unparsed sentences have no verified analog, so most new
  cards still need the grammar or new components.
- A design question for the owner and a gate round; not built here. The 246 unparsed sentences
  that match a verified mapped card word for word are a cheaper first step: `similar` could offer
  the verified mapped trees, from the records' clause paths, as exemplars.

## 5. What was built (this branch)

### 5.1 Four lints in G0 (`tools/cards/lints.py`)
They check the tree against the printed text. They run in `cardtool try`, `write` and `verify`
(a G0 failure). Tests: `tools/cards/test_lints.py`.

**The checks:**
- `players`:
  - an opponent-side player in the tree needs opponent wording in the text, and opponent wording
    needs an opponent-side player in the tree;
  - a designated player needs its own words ("target player", "target opponent");
  - "<subject> <verb>s" needs an atom of that verb acting for that side;
  - "<subject> <verb>s" with no atom of that verb at all is a dropped instruction.
- `costs`: every printed activated ability's cost ("{3}{U}, {T}, Sacrifice this creature:",
  "Equip {3}", "[+1]:") equals a top-level activated ability's cost, part for part, and the tree
  has no activation the text does not print.
- `amounts`: the tree holds no number of 2 or more that the text never prints ("half", "twice"
  and "{G}{G}" count).
- `carrier`: a permanent spell's cast carrier holds no effect. The one accepted exception is an
  Aura's "You control enchanted creature.".

**False positives.** 0 findings over the 736 verified cards, with one listed exception: Massacre
Wurm's TARGET_PLAYER antecedent, divergence D18, whose fold is BACKLOG B-114.

**The historical defects each one flags,** in their own trees from git
(`tools/cards/testdata/lint_history.json`):
- FDN Pilfer's first record, "target opponent" as any player (`players`, fa6e00bc~1);
- M21 Necromentia's Zombies given to the caster (`players`, golden f6642f44~1);
- M21 Peer into the Abyss's dropped life loss (`players`, golden 13c169ae~1);
- M21 Azusa's free repeatable activation, which the network used 9 times a turn (`costs`, golden
  1f112e2e~1);
- M20 Keldon Raider's orphaned "If you do, draw a card." on its cast (`carrier`, rebuilt from its
  mapper's report);
- for `amounts`, the planted shape: wave 1's M20 Ancestral Blade making two Soldiers, rebuilt
  from its answer key, and 15 more of the amount plants.

**On planted faults.** Rebuilt from the answer keys on today's trees, the lints flag **46 of 72**
plants with no agent at all:
- who acts: 25 of 28;
- costs: 5 of 5;
- amounts: 16 of 28.

Missed: target to all (5), until end of turn (3), zones (3), 12 amounts, 3 controllers on cards
whose text names opponents.

**On the 4,665 unverified cards of the 19 sets.**
- On fully compiled cards, 2 findings, both real and known: M21 Conspicuous Snoop's and Radha's
  free activations, the class the network once used.
- On partly compiled cards the findings mark the unparsed sentences, as they should: a mapper's
  draft must clear them.
- 26 partly compiled cards of 11 sets hold an effect on a permanent's cast carrier. These are
  orphaned sentences of the class fixed on 11-05: WAR Teferi, Time Raveler draws a card as it is
  cast. They are in the BACKLOG.

### 5.2 The verifier's G3 round trip (`cardtool survivors`)
After writing a verdict, the verifier runs
`cardtool survivors SET "Card" --verdict v.json`.

**Blindness is kept by a lock.**
- The first run locks the judgments: the sha256 of the verdict, its probe sha and each clause's
  status and issue goes into the verdict's `lock` and into `locks.jsonl` beside it.
- Only then does it list the critical mutants that none of the verdict's packs kills. Each comes
  with the kind of pack that killed that operator in the waves' follow-ups, and the part of the
  tree it changes.
- The verifier adds packs (evidence may grow) and runs it again until nothing is listed.
- A judgment changed after the lock is refused, by `survivors` and by `verify`. A second lock of
  the same verdict shows in the ledger, whose first entry counts. So a change is detectable even
  when the lock field is rewritten.
- Plants are scored from the locked verdicts.

It reuses `verify`'s own G3 code (`uncovered_survivors`, factored out of `cmd_verify`). Tests in
`tools/cards/test_cards.py`: the lock, the list, a pack clearing it, a changed judgment refused by
both commands, and a re-lock caught.

### 5.3 Reprint reuse (`cardtool verify SET "Card" --reprint-of HOME`)
It goes through the existing stamping path, `cmd_verify`, which writes the record.

**It stamps only when all of these hold:**
- the home record is verified and its stamp still matches the home set's tree;
- the card's printed facts here equal the home record's (`text_sha`);
- the tree built here, with the home record's `ir` when it has one, has the home stamp's
  `tree_sha`;
- G0 with the lints and the probe pass here;
- the home packs pass, and kill every critical G3 survivor, run again in the home set, where
  their supporting cards are.

**How it stays keyed to the IR bytes.** The new record's `verified.tree_sha` is `tree_sha` of the
card as built here, and `is_verified` honours it only while the tree here has exactly those bytes
(Decision 3). The record also carries `reprint_of` and the home packs' paths.

**The probe trace here** differs from the home one only where the probe's stimuli use this set's
own cards (M19 casts Crash Through where M20 casts Raise the Alarm), so it must raise nothing but
is not compared.

`cardtool status SET` lists the candidates. Tests write to a scratch directory: M19 Cancel from
M21 (compiled) and M19 Anticipate from M20 (mapped). No real record was written: stamping is the
coordinator's, through the two-person rule's normal path.

### 5.4 The pace
`cardtool status SET [SET ...]` prints, per set:
- the cards by state;
- the reprints it can carry over;
- the verified cards by the date of their last stamp.

| Set | Last stamps by date |
|---|---|
| M21 | 10-29 129, 10-30 123, 11-12 16, 11-13 7 |
| M20 | 11-05 227, 11-06 22, 11-12 11, 11-13 17 |
| FDN | 10-29 53, 11-06 119, 11-12 5, 11-13 7 |

First stamps from git: 10-29 194, 10-30 128, 11-05 119, 11-06 252, 11-12 10, 11-13 34.

### 5.5 Docs
- `docs/PLAN_CARD_ONBOARDING.md`: the new-set playbook, with these numbers; G0's row names the
  lints.
- `docs/MAPPER_GUIDE.md`: a one-screen checklist of common mistakes ordered by frequency, and the
  verifier's last step.
- `docs/CARD_AGENT_BRIEFS.md`: templates for the verifier, mapping-wave, IR-change, gate-reviewer
  and engine-wave briefs, with the environment rules written once. CLAUDE.md's layout table
  points to it.

## 6. Next, for the owner and the coordinator
1. Stamp the reprints with `verify --reprint-of` (no agent tokens). M19's 66 would give M19 a
   verified pool, and FDN gains 6.
2. The frame generaliser is a design for a gate round (§4). Cheaper first: let `similar` offer
   the verified mapped sentences.
3. The 26 orphaned cast carriers are a compiler fault class still present in partly compiled
   trees (BACKLOG).
4. More lints the ledger suggests, each with its historical defect:
   - "Enchant <X>" without the keyword's restriction (Blanchwood Armor's first record);
   - "hexproof from" written as full hexproof (Sporeweb Weaver);
   - a phantom "may" around "any number" (Siege Striker);
   - a CAST whose empty Cost reads as free (Chandra, Heart of Fire).
