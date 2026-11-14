"""The fault ledger of the card-onboarding waves, 2026-10-29 to 2026-11-13 (KNOWLEDGE/2026-11-14/207).

One row per fault (one cause, however many cards it touched), from the notes' fix tables
(KNOWLEDGE 173-177, 184, 201, 203, 204, 206), the gate log (docs/DESIGN_ATOM_ONTOLOGY.md §9), the
verdict files of the verification rounds and the M20 mappers' reports. Planted faults are not here
(they are counted from the rounds' answer keys). Columns:

- cls: players (wrong controller or direction), count (once vs each), cost, may, duration, targets
  (target counts, "up to", "any number", target vs all), zone (zone or ownership), order,
  engine (other rules faults), grammar (a compiler template misreading or dropping text),
  ir (no node or field for the meaning, or one the IR accepts with two encodings), tool
  (probe, runner, G3 or cardtool itself);
- made: where it was introduced (mapper, compiler, ir, engine, tool);
- caught: verifier (blind G2), mapper (its own trace or packs), g0, g3, gate (an adversarial gate
  round or its pre-gate review), fixer (building another fix), hunt (a bug hunt), review (a game
  review), crash (a crashed or voided game), audit (the M21 fidelity audit, KNOWLEDGE 175);
- cheapest: the cheapest stage that could have caught it: lint (static text-against-tree check,
  tools/cards/lints.py), g0, probe (the G1 trace read), pack, engine-test, gate;
- escape: 1 when a verified card played it.

    python3 reports/card_lessons_2026-11-14/ledger.py     # the tallies of note 207 §1
"""

from collections import Counter

ROWS = """
B-49 noncreature permanents uncastable (45 M21 cards)|ir|compiler|verifier|g0|0
B-52 counted static P/T froze (Kinetic Augur)|engine|engine|verifier|pack|0
B-56 'died this turn' counted a Treasure|engine|engine|verifier|pack|0
B-57 'combat damage to a player' fired on a blocker (4 cards)|engine|engine|verifier|probe|0
B-59 lures never expired|duration|engine|verifier|pack|0
B-60a/b equip and Speaker at instant speed|engine|compiler|verifier|probe|0
B-60c Kitesail Freebooter's exile permanent|duration|ir|verifier|pack|0
B-61 first strikers hit the player after killing the blocker|engine|engine|verifier|pack|0
B-55 a trigger with no legal target crashed (Pirate's Cutlass, 37 soak games)|targets|engine|crash|probe|0
B-50 resolved end-of-turn grants ended with their source|duration|engine|mapper|pack|0
B-62 planeswalkers ignored 'exile instead' (Obliterating Bolt)|zone|engine|verifier|pack|0
B-53 'target player' offered only opponents|players|engine|verifier|probe|0
B-51 CHOOSE offered an empty pick|targets|engine|verifier|probe|0
B-58 a static Seq used its first selector for every step|engine|engine|verifier|probe|0
D12 SEARCH.controller written on 14 cards, left out on 15|ir|compiler|mapper|gate|0
the deciding player not asked (edicts, discards, sacrifices)|players|engine|verifier|probe|0
the legend rule|engine|engine|verifier|engine-test|0
modes chosen at resolution, not at cast|order|engine|verifier|probe|0
'up to N' could not choose zero|targets|engine|verifier|probe|0
'target player' and 'target opponent' one ref (V21)|players|ir|verifier|lint|0
an Aura put onto the battlefield chose no host|engine|engine|verifier|pack|0
no discard to seven at cleanup|engine|engine|verifier|engine-test|0
'end the turn' (CR 724.1)|engine|engine|verifier|pack|0
CHOOSE could be skipped|may|engine|verifier|probe|0
creatures could not attack planeswalkers|engine|engine|verifier|engine-test|0
defenders could not block|engine|engine|verifier|engine-test|0
an attacking bonus outlived combat|duration|engine|verifier|pack|0
per-slot targets and the damage source|targets|engine|verifier|probe|0
the mana pool never emptied|engine|engine|verifier|engine-test|0
{T} abilities ignored summoning sickness|cost|engine|verifier|engine-test|0
'any color' was more than WUBRG|engine|engine|verifier|probe|0
additional costs and targeting taxes unpaid|cost|engine|verifier|probe|0
'discard your hand' discarded one card|targets|engine|verifier|probe|0
cards went to the controller's zones; ownership changed|zone|engine|verifier|pack|0
counters, tapped status and tokens survived zone changes|zone|engine|verifier|pack|0
draws by other moves counted as draws|count|engine|verifier|probe|0
nested zone changes journalled twice|count|engine|verifier|probe|0
graveyard triggers never fired|zone|engine|verifier|pack|0
phasing as a zone change|engine|engine|verifier|pack|0
exile 'until this leaves' never returned (R5-1)|duration|ir|verifier|pack|0
extra turns not last-in first-out|order|engine|verifier|engine-test|0
planeswalkers at 0 loyalty stayed|engine|engine|verifier|engine-test|0
no X for loyalty abilities|cost|engine|verifier|probe|0
the 606.3 loyalty window|engine|engine|verifier|engine-test|0
protection only partly modelled (CR 702.16)|engine|engine|verifier|pack|0
existence checks misread (Furious Rise, Scavenging Ooze)|grammar|compiler|verifier|probe|0
'if you do' read the wrong step|may|engine|verifier|probe|0
'died this turn' not counted from events|engine|engine|verifier|pack|0
Hunter's Edge and Unleash Fury|grammar|compiler|verifier|probe|0
'hexproof from' compiled as full hexproof (Sporeweb Weaver, Garruk's Harbinger)|grammar|compiler|audit|lint|0
Peer into the Abyss dropped 'loses half their life'|grammar|compiler|audit|lint|0
Life Goes On|grammar|compiler|verifier|probe|0
Azusa's land plays a free repeatable activation (the network used it 9 times a turn)|cost|compiler|audit|lint|0
Nine Lives|grammar|compiler|verifier|probe|0
Riddleform|grammar|compiler|verifier|probe|0
Barrin, Niambi and Ghostlight|grammar|compiler|verifier|probe|0
the named tutors|grammar|compiler|verifier|probe|0
Brash Taunter and Run Afoul|grammar|compiler|verifier|probe|0
Wildwood Scourge's X counters|grammar|compiler|verifier|probe|0
Basri's delayed triggers|grammar|compiler|verifier|probe|0
Falconer Adept|grammar|compiler|verifier|probe|0
token colours (R5-11)|ir|ir|verifier|probe|0
Warden of the Woods drew when its controller targeted it (R5-6 actor)|players|ir|audit|pack|0
AbilityActivatedEvent and mana abilities (R5-7)|ir|ir|verifier|gate|0
stack objects said nothing of their kind (R5-10)|ir|ir|verifier|gate|0
Conspicuous Snoop cast from the library top at instant speed by a free activation|cost|ir|audit|lint|0
Cultivate's split|targets|compiler|verifier|probe|0
Basri Ket's -2 counted tokens|targets|compiler|verifier|probe|0
state-based actions after triggers (CR 704.3)|order|engine|verifier|pack|0
'entered this turn' per object|engine|engine|verifier|pack|0
Archfiend's Vessel's 'if you do'|may|compiler|verifier|probe|0
Necromentia's Zombies went to the caster|players|compiler|verifier|lint|0
Primal Might's up-to-one target|targets|compiler|verifier|probe|0
Speaker of the Heavens' Angel not a creature|grammar|compiler|verifier|probe|0
Experimental Overload uncastable|ir|compiler|verifier|g0|0
Rin and Seri's life gain|grammar|compiler|verifier|probe|0
Ugin's 'up to seven'|targets|compiler|verifier|probe|0
Alpine Houndmaster's find not optional|may|compiler|verifier|probe|0
'library and/or graveyard' as one zone|zone|compiler|verifier|probe|0
tapped creatures could attack|engine|engine|mapper|engine-test|0
no player-loss state-based action|engine|engine|hunt|engine-test|0
decking a draw early|engine|engine|hunt|engine-test|0
the starting player drew on turn 1|engine|engine|hunt|engine-test|0
summoning sickness skipped after a control change|engine|engine|hunt|engine-test|0
an attacker that left stayed in combat (void)|engine|engine|crash|engine-test|0
B-69 two damage replacements raised (void escape the network used)|engine|engine|crash|engine-test|0
Demonic Embrace's graveyard cast a costed no-op|zone|engine|hunt|pack|0
Equipment stayed on a non-creature|engine|engine|hunt|engine-test|0
an intervening 'if' checked only at resolution|order|engine|mapper|pack|0
'<name> deals N damage' swallowed activation costs (Elite Headhunter, Chandra Bold Pyromancer)|cost|compiler|fixer|lint|0
CR 400.7: 43 verified cards kept effects after a bounce and replay|zone|engine|mapper|pack|1
the last-known controller (Massacre Wurm on a stolen creature)|players|engine|mapper|pack|1
effects outlived their source (Mu Yanling)|duration|engine|mapper|pack|0
Frost Breath per controller (B-113)|players|engine|mapper|pack|0
SACRIFICE took the targeted object (Sorin, Imperious Bloodlord)|players|engine|mapper|pack|0
a condition judged on the source (Overgrowth Elemental)|engine|engine|mapper|pack|0
counter prevention never applied (Blightbeetle)|engine|engine|mapper|pack|0
CR 608.2b: no target recheck (88 verified cards with targets)|targets|engine|mapper|pack|1
permission casts ignored timing (Mystic Forge, Idol of Endurance)|engine|engine|mapper|pack|0
simultaneous triggers in fixed seat order (APNAP)|order|engine|hunt|engine-test|0
modal triggers designated before the mode|order|engine|mapper|probe|0
state-based actions mid-resolution|order|engine|hunt|engine-test|0
a dies trigger bound the dead creature as its target (Cavalier of Flame)|targets|engine|mapper|pack|0
'a spell that targets this' never matched (Gnarlback Rhino)|engine|engine|mapper|pack|0
'that creature's controller' opened a free player target (Synchronized Spellcraft, Chandra's Outrage)|players|compiler|mapper|lint|0
an orphaned 'If you do' on the cast (23 partly compiled cards, Keldon Raider)|grammar|compiler|mapper|lint|0
Sorin, Vampire Lord gained 4 life as it was cast|grammar|compiler|mapper|lint|0
upkeep triggers after the draw|order|engine|mapper|pack|0
a damage trigger's 'creatures you control' pumped only the dealer (Wildfire Elemental)|targets|engine|mapper|pack|0
graveyard abilities never activatable (Sanitarium Skeleton)|zone|engine|mapper|probe|0
a life-gain replacement could not read the amount (Angel of Vitality)|ir|ir|mapper|gate|0
CAST with an empty Cost read as free (Chandra, Heart of Fire)|cost|compiler|mapper|lint|0
a second copy of an emblem did nothing|count|engine|mapper|pack|0
'up to one' with no target crashed the next step (Cavalier of Dawn)|targets|engine|mapper|probe|0
control of a stolen creature ended with the Vampire (Sorin, Vampire Lord)|duration|engine|mapper|pack|0
abilities never on the stack (Tale's End, B-110)|engine|engine|verifier|probe|0
'any order' and 'random order' one tree, fixed order (B-81, arrange)|order|ir|mapper|gate|1
'any number' never asked, all taken (verified Necromentia, Siege Striker)|targets|engine|mapper|probe|1
'can't block' applied only until end of turn (Tectonic Rift)|duration|engine|mapper|pack|0
granted deathtouch and lifelink lost when the source left (regression)|duration|engine|hunt|pack|0
a dead creature kept its pump (Carrion Grub)|zone|engine|hunt|pack|0
a stolen creature's dies trigger went to its owner|players|engine|hunt|pack|0
a permanent spell read its own cost reduction (Warden of Evos Isle)|cost|engine|verifier|pack|0
hexproof worked on the stack (Sphinx of the Final Word; Sporeweb Weaver uncounterable)|engine|engine|verifier|pack|1
fetched and ramped lands made no mana|zone|engine|review|engine-test|1
'is dealt damage' triggered once per source (Sporeweb Weaver, Brash Taunter)|count|engine|review|pack|1
Volcanic Salvo's reduction unseen by the affordability check|cost|engine|review|pack|1
two-target spells never offered (Primal Might, Hunter's Edge, Rabid Bite)|targets|engine|review|probe|1
'this spell costs less' never applied in games (7 verified cards)|cost|engine|review|engine-test|1
no postcombat main phase (Raid cards dead, B-74)|engine|engine|verifier|probe|0
FDN Pilfer's record: 'target opponent' as any player|players|mapper|verifier|lint|0
FDN Blanchwood Armor's record: Enchant with no restriction (B-65)|targets|mapper|verifier|lint|0
FDN Fireshrieker's record: two SpellAbility nodes|grammar|mapper|g0|g0|0
the defender could not choose which creature obeys 'must be blocked' (Joraga Invocation)|engine|engine|verifier|probe|0
scry's kept cards in a fixed order (Octoprophet)|order|engine|verifier|probe|0
G0 asked a token for a cast carrier (9 M20 tokens)|tool|tool|g0|g0|0
Runed Halo's as-enters choice compiled as a trigger (window 2's crashes)|ir|ir|crash|probe|0
a trigger with no legal player target stayed (Vito, the fourth crash)|targets|engine|crash|probe|0
the probe tried target pairs that break 'another' (Garruk, Rookie Mistake)|tool|tool|verifier|probe|0
Drowsing Tyrannodon compiled as losing defender (B-80)|ir|compiler|verifier|gate|0
Teferi's 'can't phase in' a phantom prevention (D16)|ir|compiler|verifier|gate|0
Transmogrify took the top card (REVEAL.until)|ir|compiler|verifier|gate|0
'whenever a creature attacks' once per declaration (B-103)|count|ir|verifier|gate|0
'one or more Cats' once per Cat (Feline Sovereign, stronger)|count|ir|verifier|gate|0
a creature put onto the battlefield attacking counted as declared (B-102)|count|engine|fixer|pack|0
See the Truth's 'any order' never asked|order|ir|verifier|probe|0
the probe's combat op answered the trigger's ask unseen (Feline Sovereign judged WRONG)|tool|tool|verifier|probe|0
Goblin Ringleader's 'all revealed' mapped as a choice|targets|mapper|verifier|probe|0
Sorin, Imperious Bloodlord's reflexive trigger targeted too early (CR 603.12)|ir|ir|verifier|gate|0
Mu Yanling, Sky Dancer's emblem empty|ir|ir|verifier|probe|0
G3's equivalent mutants blocked 8 OK cards (dead roles)|tool|tool|g3|gate|0
verify overwrote earlier packs on a re-verification|tool|tool|fixer|engine-test|0
Brash Taunter's damage source stood in for its target (3 players)|players|engine|fixer|pack|1
event qualifiers re-checked as intervening 'if's (6 cards)|order|compiler|verifier|lint|1
Sorin, Vampire Lord's -8 granted to one targeted creature|targets|engine|fixer|pack|1
Mangara's departed attacker counted live|zone|engine|g3|pack|0
a stolen permanent kept its old controller in its records (53 verified cards)|players|engine|fixer|pack|1
'shuffle into its owner's library' shuffled the controller's (Cavalier of Gales)|zone|engine|g3|pack|0
verify duplicated a pack on a re-verification|tool|tool|fixer|engine-test|0
activate() accepted a targeted ability with no target|targets|engine|g3|pack|0
Siege Striker's phantom 'may' around 'any number'|may|compiler|gate|lint|1
an emblem's replacement ability crashed and never applied|engine|engine|gate|pack|0
player hexproof did not veto targets (Leyline of Sanctity, Veil of Summer)|engine|engine|fixer|pack|0
a trigger with several target slots designated one (Drakuseth; Sublime Epiphany drew for the wrong player)|players|engine|fixer|probe|0
'reveal until' left no window for 'the rest' (Vivien, Spinner of Souls)|zone|engine|fixer|pack|0
lifelink: one gain event per recipient (verified Vito, Ajani's Pridemate)|count|engine|fixer|pack|1
DESTROY killed indestructible permanents (every destroy effect)|engine|engine|fixer|engine-test|1
G3's 'up to one' twin targets live on activations|tool|tool|g3|gate|0
movers in one event saw each other only in row order (one wrath: 1 life, not 2)|count|engine|fixer|engine-test|1
three dies triggers filed as graveyard-only (Immortal Phoenix, Cavaliers)|zone|engine|fixer|engine-test|1
a per-object 'it' followed an object that changed zones (Marauding Raptor)|zone|engine|fixer|engine-test|1
one EachPlayer instruction was several events|count|engine|gate|engine-test|0
event filters read stale layers|order|engine|gate|engine-test|0
a replaced death was its own event|count|engine|fixer|engine-test|0
once_per_event accepted where it changes nothing (round 4 M1)|ir|ir|gate|gate|0
arrange accepted where it orders nothing (round 5 M1)|ir|ir|gate|gate|0
G3 lost the zone mutant of random moves (round 5 M2)|tool|tool|gate|gate|0
the network could not see which end it arranges (round 5 M4)|ir|ir|gate|gate|0
a reflexive trigger accepted anywhere; under EachPlayer it gave the life to the opponent (round 6 M1)|players|ir|gate|gate|0
the trigger-timing check one-sided (round 6 M2)|tool|tool|gate|gate|0
a subject-free qualifier had two slots (round 6 M3)|ir|ir|gate|gate|0
EachPlayer around GET_EMBLEM a second encoding (round 7 M1)|ir|ir|gate|gate|0
GET_EMBLEM's recipient open to every player ref (round 7 M2)|players|ir|gate|gate|0
the round's recipient rule false for the corpus (round 7 M4)|ir|ir|gate|gate|0
LIFE_TOTAL_GE's who in three forms (round 8 M1)|players|ir|gate|gate|0
two tokens leaving with 'the greatest power among them' crashed (round 10 M1)|engine|engine|gate|engine-test|0
'that many' looked an object up first: verified Basri Ket's -2 crashed (round 10, pre-gate FATAL)|engine|engine|gate|engine-test|1
single-object reads of a gathered register accepted (round 10, pre-gate)|ir|ir|gate|gate|0
the chosen-quality pre-gate review's three MAJOR (round 9)|ir|ir|gate|gate|0
"""

FIELDS = ("fault", "cls", "made", "caught", "cheapest", "escape")


def rows() -> list[dict]:
    out = []
    for line in ROWS.strip().splitlines():
        parts = line.split("|")
        assert len(parts) == len(FIELDS), line
        out.append(dict(zip(FIELDS, parts, strict=True)))
    return out


if __name__ == "__main__":
    rs = rows()
    print(len(rs), "faults;", sum(r["escape"] == "1" for r in rs), "played by verified cards")
    for key in ("cls", "made", "caught", "cheapest"):
        print(f"by {key}:", dict(Counter(r[key] for r in rs).most_common()))
    print("class x caught:")
    for cls, n in Counter(r["cls"] for r in rs).most_common():
        sub = [r for r in rs if r["cls"] == cls]
        print(f"  {cls:9} {n:3}  made {dict(Counter(r['made'] for r in sub))}  caught {dict(Counter(r['caught'] for r in sub))}"
              f"  cheapest {dict(Counter(r['cheapest'] for r in sub))}  escapes {sum(r['escape'] == '1' for r in sub)}")
