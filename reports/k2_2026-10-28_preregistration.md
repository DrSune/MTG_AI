# K2 reading rules, written 2026-10-28 00:27:00 CET BEFORE any K2 model was trained

Question (owner, 2026-10-27/28): does the network that plays a card know what its components
mean? Can it make the card's choices well ("when to choose what it can choose ... what it means to
sacrifice") on cards it never trained on, built from components it has seen? The live policy reads
card names (tools/training/ab_duel.py:572-578), so for an unseen card it has nothing.

## Data (tools/k2/gen.py)
- 60 uniformly random games per set, on 18 castable pools. M14 cannot be dealt.
- Every target, sacrifice, discard, may, choose and one_of ask is collected. Dual lands' mana colour
  choices are skipped. Each option is tried by replay from the same seed and answers, and the board
  is scored at the next clean boundary.
- Only data quality was looked at before this file: kinds, and the share of informative decisions.

## Label
- The probe's value of a board, from the asking seat: Δ(life difference) + 0.5 Δ(power+toughness
  difference) + 1.5 Δ(creature-count difference) + Δ(hand difference) + Δ(land difference)
  − 0.5 Δ(own tapped − opponent's tapped).
- The best options are those within 0.01 of the maximum. A decision is informative when the
  maximum and minimum differ by more than 0.01; only informative decisions are used.
- This is the probe's definition of a good choice, hand-made and not a strength claim. K2 measures
  whether a choice rule transfers to unseen cards, not whether it is optimal.

## Students (tools/k2/train.py)
- All students get the same inputs: the board summary, the ask kind, and each option's object (side,
  zone, card types, P/T, tapped, token, or the option word).
- They differ only in the source card, the card whose ability asks:
  - **none** (floor);
  - **name**, an oracle-id embedding with unk-dropout 0.1, so it learns a fallback (today's policy);
  - **components**, the IR bag from tools/k1 card_inputs (K1c's best card encoder).
- Same budget and seed for all.

## Split and metric
- Held out: 20% of source oracle ids (sha256 "k2:<oid>" < 0.2).
- A seen-source test slice: 10% of the remaining decisions, by hash.
- Metric: top-1 accuracy, counting a pick as correct when it is one of the best options. Paired 95%
  intervals resample source cards (1000 draws).

## Rules
1. **Sanity.** On held-out sources, name − none must lie within ±0.03. If not, identity leaks or the
   fallback is broken; report, and do not read rule 2.
2. **Components transfer.** components − none on held-out sources has a paired 95% interval above 0.
   Report the retained share: (comp − none)_held-out / (comp − none)_seen.
3. **Names don't transfer.** name − none: above 0 on seen sources, about 0 on held-out ones. This
   is the cost of today's name-reading policy on unseen cards.
4. **Headline.** components − name on held-out sources, with its paired interval.
5. **By kind (descriptive).** target and may separately.
