# 99 — TICKET (engine lane): parse_pt('1+*') raises StateCorruptionError -> get_supply("engine","ZNR") cannot build; ZNR-era eval/shadow/duels ALL blocked by this one card

Date: 2026-10-18 13:3x. Found while adding `--set` to gameplay_eval_v2 (committed default-invariant, M21 2-game smoke EXIT=0). Repro (scoped 1G): get_supply("engine","ZNR") -> StateCorruptionError: parse_pt: unexpected value '1+*' (Nighthawk Scavenger; /93 certified as the ONLY non-digit P/T in the pool — "class exhausted" was about the CENSUS's tolerance, but the SUPPLY path has no tolerance).
Semantics for the fixer (§11 significance): read the card's oracle text in MTG_bot/data/ZNR.json — '1+*' is this world's variable-power form; the parse must not drop it silently (corruption law = correct behavior); options belong to the engine lane (supply-level exclusion-list w/ census-consistent shape_gaps reporting vs. parse_pt variable form).
Repro pinned: `.venv/bin/python -c 'from MTG_bot.core.executor.games import get_supply; get_supply("engine","ZNR")'`
Owner of fix: sibling compiler wave (engine semantics); my lane keeps eval ready: gameplay_eval_v2 now carries --set (gated, default SET_CODE=M21).

RESOLVED: 2026-10-18 (engine lane, ZND-1e sibling task). Fix = SUPPLY-LEVEL
shape-gap EXCLUSION, not a parse_pt variable form: the '*' is defined by
"the number of card types among cards in your opponents' graveyards" — a
DERIVED CENSUS QUANTITY the frozen Quantity grammar cannot express (§9: no
atom to fold into; encoding it is a grammar round, so a parse kludge would
lie about the atomics). Repro exits 0. Mechanics: strict compile_pool
untouched; get_supply catches StateCorruptionError PER CARD, excludes the
refusing card and registers census-consistent ShapeGap rows (card, name,
error) + a loud stderr line "supply[ZNR]: shape-gap exclusion ..." — never
silent (§11: gap ledger, not swallowed). M21 byte-untouched: gaps == ().
Tests: ShapeGapSupplyExclusionTest (test_executor_games.py): supply builds;
Nighthawk excluded AND registered (exactly 1 gap row — a 2nd row means a new
shape crash got swallowed, that is a finding); M21 pins hold (engine_ids 301,
deckable 281). Repro post-fix: `.venv/bin/python -c 'from
MTG_bot.core.executor.games import get_supply;
get_supply("engine","ZNR")'` EXIT=0, ZNR engine deckable 267 (see /100).
