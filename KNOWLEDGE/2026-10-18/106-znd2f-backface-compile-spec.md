# 106 — ZND-2f BINDING SPEC (compile half): BackFace tree node — faces become ENCODED; playability stays LOCKED on an open world-rules question

Date: 2026-10-18. Ground facts (executed today, this-world canonical data only): 36 ZNR MDFCs (all
back faces are LANDS: 25× "This land enters tapped.", 33× "{T}: Add {X}", 5× pay-3-life enter pairs,
= ~8 distinct shapes already inside template reach); **zero text anywhere states how the back face is
cast or played** — no foretell (this world lacks it), no cycling, no "cast either face" clause. The
real-world ZNR either-face permission is a SET-RULE, and this world's set rules are not derivable
from card data. → Playability = owner-rules question (surfaced in session report); this wave does
NOT decide it and cannot regress it.

## Binding decisions
1. **§11 zero-loss now**: back-face components are semantically significant (they alter outcomes if
   the face ever enters) and are currently encoded NOWHERE (compiler never reads back_face; /96 made
   measurement see them — encoding still blind). This wave closes the encoding gap.
2. **Carrier = one new Ability node `BackFace(face_name, abilities: tuple[Ability, ...])`** — a card's
   encoding contains its own components (§11); the face is the card's own second face, NOT an
   interaction-acquired state. Additive-only: serializer omits-if-empty/absent ⇒ M21 goldens
   byte-identical (305 files). Nested tree reuses the existing vocabulary — no new effect atoms
   expected (pay-3-life-enter-pair rides existing R-lane shapes; if a shape genuinely fails, it
   registers as a residual, not a new atom, unless the ledger proves an atom is missing).
3. **Compiler lane**: compile back_face sentences through the SAME tolerant machinery, fold results
   into `BackFace`; face sentences count into PC-2 numerator for real now (denominator already +71
   since /96). Census/histogram unchanged in shape (rows already tagged [face B]).
4. **Engine stays face-blind HONESTLY**: the ability walker gets an explicit `BackFace` branch that
   registers NOTHING (loud no-op, never a silent default fall-through — this is the §10 phantom
   defense); any card whose engine-supported verdict would depend on face content must remain
   verdict-only-from-front-face (engine_support fold must see BackFace as inert and say so).
5. **Tree encoder SHOWS the node** (§10 static visibility): the model sees the face exists + its
   components; no dynamic ask is created by this wave (no phantom decisions), and no ask that the
   world rules would need is hidden (no blindness — there is no legal face-play decision today).
6. **DEFERRED (owner-gated)**: face playability — legality cast/play lanes, face-zone state, "cast
   back face" cost handling, play-order semantics. Type-1, awaits the world-rules answer; a
   follow-up spec will carry the engine design THEN.

## Gates
New tests: MDFC compile produces BackFace with expected nested IR (≥1 card per major face shape);
single-faced cards byte-identical trees (M21 305 + ZNR non-face cards); serializer round-trip of a
BackFace; engine walker registers nothing from a BackFace (probe: MDFC in play = front-only
abilities, loud skip trace); ZNR PC-2 uplift lands (expect ≈ +44–64 sentences of 71 — residuals
ledgered); PC-1: a card whose ONLY gap was its face compiles whole; determinism double-run; core
suite; M21 byte-ident incl. corpus re-encode (11 files, diff 0); pyright/ruff.
Dispatch only after sibling b7 wave commits (single-writer compiler law).

## SPEC-AMENDED by adversarial gate (same day) — SPEC-NO-GO original, 4 breaks, amendments BINDING
1. **UNDER-SCOPED premise broken (probe-executed):** the pay-3-life pair ("As this land enters, you
   may pay 3 life." + "If you don't, it enters tapped.") compiles to ZERO abilities SILENTLY
   (OK-verdict, abilities=[]) — no template exists; only 2 of the ~8 face shapes are actually in
   template reach. MAY+replacement+IF_YOU_DONT-anaphor is its own template+atom wave = **ZND-2f2**
   (10 sentences), NOT part of this wave. This wave = 61 sentences (25 enters-tapped + 36 add-mana).
   (Repo-level side-finding worth its own pitfall line: OK-verdict-with-empty-abilities is a silent
   no-op class in the tolerant compile loop.)
2. **Numbers corrected:** add-mana faces = **36** (W8 B8 G7 R6 U5), uplift = **61/71 exactly**;
   face sentences must be TAGGED in the verb histogram — `coverage.py:411` flat `walk(result.card)`
   would silently merge face ADD_MANA×36 into `verb_counts`/PC-6/PC-8 untagged. Census histograms
   are NOT unchanged.
3. **The gate was on the wrong surface.** Registration lanes are strict-isinstance (structurally
   inert); the real leak is **`walk()` generic dataclass descent** (ability_tree.py:4617-4619) into
   BackFace children → `games.py:282` `verbs = walk(record)` would set `produces_mana=True` from an
   UNPLAYABLE face {T}: Add {B} — a live §10 phantom (the gold:false shape). BINDING amendment:
   every `walk()`-consumer gate — `games.py:282` must exclude the BackFace subtree;
   `compiler.py:2179` engine_support flat verb fold must EXCLUDE BackFace subtree (today it's
   coincidentally safe; a future unsupported face verb would silently drop front-face-supported
   cards from engine supply). Gate tests assert PRODUCES_MANA + engine_support invariance, not
   "walker registers nothing".
4. **"Tree encoder SHOWS the node" is vacuous** (no card IR reaches the prompt — packrec_v2.py:68-75
   is handle/name/tapped/counters only). Reworded: visibility = **serializer tag** only until the
   card-IR prompt lane exists; the claim may not be used as review cover.
§9 check passed (container, not operation; fields extensible Type-2). Playability stays owner-gated
unchanged. SPEC-GO after these amendments; still dispatch-gated on single-writer compiler surface.
