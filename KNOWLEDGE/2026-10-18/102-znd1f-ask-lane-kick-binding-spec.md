# 102 — ZND-1f BINDING SPEC: kick becomes MODEL-VISIBLE — `card:N+kick` candidate token with cost grounding; the ask lane stops collapsing the two priced casts

Date: 2026-10-18. Closes the last §10 gap registered by /100 (ask-lane presentation). Binding facts
(reader-mapped 2026-10-18, file:line verified there): legality emits BOTH priced cast rows (ZND-1e),
but (a) `PolicyActDriver._menu` gameplay_eval_v2.py:325 dedupes by handle -> kicked rows dropped from
the presented menu; (b) `cand_words_v2` bc_data_v2.py:327 produces IDENTICAL spans for base/kicked
rows of one card; (c) collector.py provider (l.203) records candidates as bare handle strings ->
two rows collapse to one string; (d) games.py RandomPolicy (l.529) casts without a kick flag ->
collected episodes can never contain a kick decision. Engine already accepts kicked casts
(games.py:578 stack.cast(kicked=)).

## Encoding decisions (binding)
1. **Candidate token**: kicked cast = `<handle>+kick` (e.g. `card:17+kick`). Base handle UNCHANGED —
   additive-only tokenizer (§8): pools without kicker produce byte-identical candidates everywhere.
2. **Grounding (§10 menu-visibility)**: the kicked candidate's word span MUST carry the kicker-cost
   grounding (read the card's KickerAbility cost — static tree data, same vocabulary as the card row).
   A bare suffix with no cost visible = phantom-style blindness; span-vs-span the two rows differ.
3. **Order**: base row before kicked row (deterministic sort, (handle, kicked) canonical).
4. **Resolution**: every consumer that maps a candidate token back to a cast must resolve the suffix
   to the row's `kicked` and pass it to the cast path (rig `take_acts`; RandomPolicy cast lane — it
   picks among ROWS, cast with that row's flag).
5. **Anti-phantom**: only rows `legal_casts` returned are ever presented (affordability is engine
   truth); no consumer synthesizes kick rows.

## Lanes this touches (claim posted here before dispatch, per /95+ coordination law)
tools/eval/gameplay_eval_v2.py (sibling eval lane — stale since 17:13, claim here), tools/training/
collector.py + bc_data_v2.py (tokenizer surface — §8), MTG_bot/core/executor/games.py RandomPolicy
cast lane (engine lane, mine). NOT templates/compiler (sibling b7 wave live).

## Gates (binding)
New unit tests: menu emits both rows (un-kicked dedupe regression dies); token->row round-trip incl.
suffix; cand_words spans DIFFER and the kicked span grounds the cost; collector candidate strings
distinguish + chosen_idx consistent; RandomPolicy episode contains >=1 kicked cast on a rigged pool;
**M21 byte-identity: candidate/span encoding of every existing corpus item unchanged (double-encode
diff = 0)**; 402 scenario packs untouched; core suite green; deterministic double-run; pyright/ruff.
Adversarial gate on the DIFF before commit (§8/§10 tokenizer surface = Type-1).
