# K1 reading rules, written 2026-10-27 16:46:42 CET BEFORE any K1 result was seen

Metric: effect-lane R² (the lanes a card's own entry cannot explain), test rows.
Floor = "state" encoder; seen-card reference = the same encoder on the "random" split.

1. Sanity: on cards/compound/M20/ZNR, "name" must sit within ~0.02 of the state floor
   (unseen cards are <unk>). If not, the setup leaks identity and every other number is void.
2. Atoms transfer (F1 not fatal at this scale) if ir-bag or ir-seq on "cards" AND on "M20"
   keeps >= 60% of its random-split gain over the floor:
   (R2_split - R2_floor_split) / (R2_random - R2_floor_random) >= 0.6.
3. Compositional gap (F1 real) if, for the best IR encoder, the compound-split retained gain is
   below half of its cards-split retained gain.
4. Atoms vs text (F2 at zero pretraining): IR helps if ir-bag beats text-bag on M20 and on
   compound by >= 0.02 effect-lane R². Equal within 0.02 = no evidence either way.
5. Structure: ir-seq beats ir-bag on compound by >= 0.02 = order and structure matter.
6. ZNR is reported but not decisive: its compiled cards use atoms M21 never does
   (BackFace, kicker, party; arch_probe).
