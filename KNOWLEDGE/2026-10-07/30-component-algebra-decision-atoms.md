# 30 — Component algebra of decision atoms (analyst batch 2026-10-07, owner §9 law)

Full 4-tuple decomposition of all 17 ask-firing decision surfaces {op, menu, count, effect}:
- CLEAN skeletons: may (whether x fixed-2), target-designate binding.py:1393-1404 (the ONLY
  complete k-of-n today: QConst exact / QAtMost + NONE-stop after pick1), sacrifice k-loop
  legality.py:1326-1338 (no NONE-stop).
- FUSED axes: ONE_OF hardcoded count=1 (selectors.py:426-448, sel.count never read);
  Verb.CHOOSE raises when want!=1 (verbs.py:1398-1401); node-Choose k = ONE compound token
  (no sequential k-pick); mana ask fuses colour, amount never askable; scry pins
  within-group order (verbs.py:1013 - player's order right unobservable); attack = N binars
  (no set declaration); order reinvents vocab as str(i) index tokens; "zero" spelled 4 ways
  (NONE token / skip / empty option-set / no-ask).
- cw (stack.py:677) vs counter (stack.py:824): SAME atom, two impls -> MERGE.

VOLUME CENSUS (goldens / fired asks v2 / corpus items): sel-CHOOSE SILENT 170/0/—;
TARGET 115/34/34; ONE_OF 4/9/9; node-Choose 27/30/29; may 42/42/34; scry 12/29/29;
attack 13/2; block 8/0; mana 10; name 2; sacrifice 6; order/trample/policy/cw/counter/pay
ALL ZERO eval exercise -> at/below volume floor (owner hypothesis instrument: tiers
{high>=25, mid 6-10, floor <=2, zero}).

MERGE LEDGER (verdicts): MERGE {CHOOSE-silent + ONE_OF + Verb.CHOOSE} -> one
PICK(k over legal-set), lifts 170 silent surfaces onto the asking channel; MERGE may/pay/
cw/counter into `whether` skeleton; MERGE order into target-k-loop (vocab dtype -> handles);
MERGE cw+counter (one instant-window atom). KEEP-SEPARATE: node-Choose (menu = effect
branches, not entity set) vs entity-PICK; attack vs block (CR 508/509 menu divergence);
ALL (zero-op); RANDOM (no decision). SPLIT: choose: key namespace collision (__init__.py:862
vs verbs.py:1426).

K-OF-N SPEC (approved design, minimal diff): selector ONE_OF loop want times, menu shrinks,
site tag progress token AFTER kind prefix ("one_of:2of2:...") so NO new vocab kinds
(bc_data.py:97-106 frozen-prefix law verified); want==1 path byte-frozen (replay pins safe,
all 4 current ONE_OFs are QConst(1) verified in golden bytes); precedent loops:
binding.py:1393 + legality.py:1326. Packs get +k scripted answers; cert per-ask granularity
already exists. Episodes re-encode; no re-architecture.

TRANSFER-TEST (owner's volume hypothesis, all data exists): tag eval items by ask_kind x
card atom profile; per-atom accuracy vs fired-volume census, card-cluster bootstrap CIs;
k-of-n atom enters at volume 0 -> predicted near-floor transfer until packs seed it.
