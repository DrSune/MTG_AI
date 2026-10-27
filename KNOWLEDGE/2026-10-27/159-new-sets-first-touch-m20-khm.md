# 159 — New sets: M20 and KHM brought in, sealed, and measured at first touch (2026-10-27)

Owner request (2026-10-27): progress the project, including adding new sets. This session (the
`mtg-ai` Claude session) takes the **new-sets lane**. It does not touch the local agent's day queue
(/154: T-G5, §3.1.4, the ZNR `1+*` gap) or the RL pilot.

## Lane rules while night-3 is armed
`tools/ops/rl_window.sh` fingerprints every non-test `.py`/`.pt` under `MTG_bot/`, `tools/eval` and
`tools/training` in the working tree. A change there before tonight's 23:59 export aborts the pilot
("PIN DRIFT", exit 3). This lane's commits to `main` are data, `tools/audit`, reports and docs
only. After this commit the tree still hashes to the PIN `8ef64d61…`, checked with the real
`/usr/bin/find` and `/usr/bin/sort`. In this session's shell, `find`, `grep` and `sort` are
wrapper functions that fail on some flags.

Compiler and engine fixes go to branch `sets/onboarding` in the worktree `../MTG_AI-sets`. They
merge to `main` after the night-3 export. **That merge changes the payload fingerprint, so the
next window needs the usual re-smoke and explicit re-pin.** The local agent's T-G5 change to
`ab_duel.py` needs one anyway.

## What was added
- `MTG_bot/data/M20.json` (Core Set 2020) and `MTG_bot/data/KHM.json` (Kaldheim): MTGJSON v5
  `5.3.0+20261026`. Both checked against this world's Scryfall with
  `tools/audit/new_set.py verify`, following /92's canonical-source law. Reports are in
  `reports/set_source_{M20,KHM}.json`.

  | Set | Names | Records / printing IDs | Oracle text (incl. faces) | Tokens |
  |---|---|---|---|---|
  | M20 | 329/329 | 345/345 | 345/345 | 12/12 |
  | KHM | 305/305 | 440 records, 407/407 printing IDs | 440/440 | 23/23 |

  Owner sign-off on the source is still pending, as it is for ZNR.
- `tools/audit/new_set.py first-touch`: the sealed first-touch protocol from REVIEW §3.2.
  - Pool entries fall into three groups:
    - **carry-over:** a reprint by oracle ID, or the same sentence-shape tuple as a card in
      M21/ZNR;
    - **dev:** cards a grammar round may read;
    - **test:** sealed by `sha256("<SET>-sealed-v1:<oracle_id>")`, 40% of entries.
  - Test numbers print only with `--sealed-read --reason`. Each sealed read is appended to
    `reports/sealed_reads_<SET>.tsv`.
  - The report holds the dev register only.
  - "Unseen shape" means a sentence whose shape (self-name replaced by `~`, digits by `N`) never
    occurs in M21 or ZNR. PC-2 on unseen shapes is the parser half of tied rank 1.

## First touch: zero code changes, HEAD `0046627`

| | M20 (near: core set) | KHM (far) |
|---|---|---|
| Entries carry-over / dev / test | 79 / 157 / 105 | 32 / 180 / 116 |
| PC-1 whole | 0.305 (104/341) | 0.125 (41/328) |
| PC-1 dev / test | 0.096 / 0.133 | 0.039 / 0.026 |
| PC-1 carry-over | 0.949 | 0.969 |
| PC-2 whole | 0.422 | 0.304 |
| PC-2 on **unseen** shapes (whole) | **0.080** (31/387) | **0.111** (72/648) |
| PC-2 on seen shapes (whole) | 0.890 | 0.880 |
| Compile crashes / shape gaps | 0 / 2 | 6 / 3 |
| Engine can deal the set | yes: castable pool 249, of which **91** fully compiled | **no**: `compile_supply` raises |

**Reading.**
- On cards whose text is new, the compiler fully compiles 11% of M20 (29/262) and 3% of KHM
  (10/296). It parses about 8–11% of sentence shapes it has not seen before.
- So "auto-extend with zero code changes" (tied rank 1) is not met at the parser level. The grammar
  is a library of sentence shapes, which is REVIEW A-5's finding, now measured on two sets the
  compiler never saw.
- M20's dealable pool would put 158 partly compiled cards into games (B-28).

**The cheapest general gaps** in the M20 dev register (207 of its 211 shapes occur once):
- keyword lines carrying reminder text: `Flying (This creature can't be blocked…)` ×5;
- keyword lists: `Flying, haste`, `Deathtouch, lifelink`. This is ZND-4a: `KeywordOutcome` holds
  one keyword.
- "This spell can't be countered." ×3;
- `Enchanted creature gets +N/+N.` ×3.

## Robustness bugs found
A crash census over M21, ZNR, M20, M19, KHM, THB, ELD and IKO compiled every card and caught
anything other than `StateCorruptionError`. M19, THB, ELD and IKO were fetched to a scratch
directory and are not in the repo. ELD and IKO stop at ingest (B-39), so their cards were never
compiled.
- **B-36:** in `templates_b3.py:994-1017`, the `B3-grant-kw-*` patterns accept any lowercase word,
  but `_KW_MAP` (`:90`) holds four keywords. "…gains haste…" raises `KeyError` and takes down the
  whole set compile and supply. Seen on M19 Goblin Motivator and KHM Axgard Cavalry. This is why
  KHM cannot be dealt.
- **B-37:** Vehicles. `CardRecord` raises `ValueError` "non-creatures cannot have P/T"
  (`compiler.py:2205`) instead of an honest refusal. Five KHM vehicles and one THB.
- **B-38:** emblem attachment raises when the planeswalker is a back face
  (`coverage.py:363`, `ability_tree.py:3361`; KHM Valki // Tibalt). It is pool-level, which is why
  the tool sums its groups instead of measuring the whole set.
- **B-39:** ingest refuses ELD and IKO (`ingest.py:652`, "duplicate oracle id maps to two
  different cards"). Printings of one token (ELD Food ×4, IKO Human Soldier) differ only in
  `relatedCards.reverseRelated`, the list of other cards that create the token. That is metadata
  about other cards, not the token's characteristics, so the dedup should not treat it as
  corruption.
- **B-40:** PC-2 counts a shape-gap card's front sentences as *matched*. They sit in the
  denominator but never in the unparsed queue (`coverage.py` `measure_pool`). PC-1 counts the same
  card against coverage. The effect is small: 1 card in ZNR, 2 in M20, 3 in KHM.

## Next in this lane
Grammar round S-1 on the M20 dev split, in the worktree:
- the B-36 to B-39 crash fixes;
- general keyword lines (reminder text, lists).

Gates for the round:
- M21 goldens byte-identical;
- ZNR PC numbers non-decreasing;
- packs 428/428;
- exactly one sealed read when the round ends.

The merge waits for the night-3 export.
