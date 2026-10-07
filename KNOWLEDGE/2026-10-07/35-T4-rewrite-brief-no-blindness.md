# 35 — T4 brief: full atomization rewrite under the menu-visibility law (owner 12:18)

Owner's law (§10): atomized components must NEVER leave the model blind to the options it
will actually have. Components carry mandatory sub-slots ({damage} ALWAYS has {how much};
same heal/draw/discard/mill), combinable with source/instruction axes ({from: your hand |
opponent's hand | all hands/decks | this card}), and the ENCODING is what tells the model
which options exist: {heal X} without "to which menu" = transfer gap by construction.

Current blindness inventory (evidence in /26 /30 /32 /33 /34): silent CHOOSE picks (170 goldens,
partially fixed: 13 search picks now ask; k-of-n machinery ready); attack = N binary asks,
attacker-set never shown as one decision; scry within-group order pinned (verbs.py:1013);
mana AMOUNT never askable (only colour); cw/counter menu derived but PASS-fused; zone verbs
MILL/DISCARD/EXILE bake the menu endpoints into the NAME; Verb enum fuses
{effect|policy|operation} ontologies; phantom asks: garruk emblem gold:false, single-
candidate decisions; LifeGained lacks amount slot (/32).

T4 phases (each gated, owner sign-off between):
P0 DESIGN SPEC (1 delegation): atom ontology {operation | effect | policy}; every atom =
record with slots {op, quantity(+bound source), source-zone, dest/menu-zone, filter,
count-tag, duration, per-choice effect bundle}; NO-BLINDNESS AUDIT TABLE per atom: static
token form vs dynamic ask shape; no-decision nodes declared as such. Zero code.
P1 VOCAB+ENCODER MIGRATION: one grammar for tree-render AND obs-words (same tokens static==
dynamic); re-encode episodes (vocab rebuild = retrain consequence accepted); replay pins
byte-extend (first-seen order law).
P2 GOLDEN REGEN + REVALIDATION: full compile + golden regen, cert v5, eval_split v5, packs
migrate (phantom asks get gold or honest no-decision declaration), all suites green,
sweep re-baseline v5.
P3 PAYOFF MEASUREMENT: previously-blind fail-core mechanics now askable -> eval item
recovery count; per-atom volume census (owner's volume hypothesis, /30 transfer test);
§8 protocol updated with blindness audit per set.
Cost honesty: P1-P2 is the biggest single program of the campaign; T3 must land first
(household legality unification is a P0 input).

AMENDED 13:47 owner clarifications (binding): (a) board-separation law (AGENTS §11) — no
cross-card interaction in card encodings, live menus carry interaction truth; (b) every T4
stage MUST report what doesn't fit current components (gap ledger with significance
criterion: alters legal options or state outcomes) — gaps identify component coverage as
much as card encoding errors. Zero semantic loss is the target, zero is acceptable.
