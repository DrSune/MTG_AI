"""One decision model for every agent, and exact routing of engine asks to seats.

Every decision any agent makes is an ``Ask``: the main-phase action menu, a target pick, or an
engine ask (the engine's ``(vocab, what)`` demand, ``core/executor/decisions.py``). An agent
answers with an option index. The engine still validates every resulting action.

**Routing.** The deciding seat comes from the engine (``DecisionStream.asking_seat``), never
from parsing the tag alone: EachPlayer re-asks the SAME tag once per player.
For tags that also carry a seat, the two must agree, or ``AskRoutingError`` is raised. An ask
kind not in the registry raises ``UnknownAskSite`` when ``strict``, so a new engine site cannot be
answered by the wrong player in silence.

**Labels.** A card is named only if the decider may know it: it is in a zone visible to them, or
the engine offered it to them as a choice (``SeatLens.describe``). A ``name:`` ask lists the
format's card pool in a dealt game (``executor.name_pool``), public
information; it is flagged ``leaky`` only in a rig with no format, where the engine still lists
the world's cards, hidden zones included (``verbs._v_choose_name``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from MTG_bot.core.ability_tree import ActivatedAbility, SpellAbility
from MTG_bot.core.identity import Handle

if TYPE_CHECKING:
    from MTG_bot.bench.view import SeatLens
    from MTG_bot.core.ability_tree import CardRecord
    from MTG_bot.core.executor import Executor


@dataclass(frozen=True)
class Option:
    token: str  # what the engine or router receives
    label: str  # what the agent reads


@dataclass(frozen=True)
class Ask:
    seat: int
    kind: str  # "act", "target", or an engine site kind
    site: str
    prompt: str
    options: tuple[Option, ...]
    refuse: int | None = None  # index of the do-nothing option, when there is one
    leaky: bool = False

    def render(self) -> str:
        lines = [self.prompt]
        lines += [f"  [{i}] {o.label}" for i, o in enumerate(self.options)]
        return "\n".join(lines)


class UnknownAskSite(ValueError):
    pass


class AskRoutingError(RuntimeError):
    pass


#: Engine ask kinds whose tag's second field is the deciding player.
#: ``x``: an activation's X announcement, ``x:<seat>:<source>:<digest>`` (CR 602.2b -> 601.2b;
#: the menu is 0..the live bound). ``legend``: the legend rule's keep choice,
#: ``legend:<seat>:<digest>`` (CR 704.5j). ``replace``: which of several applicable replacement
#: effects applies next, ``replace:<seat>:<digest>``, asked of the affected player or the
#: controller of the affected permanent (CR 616.1); the options are the effects' sources.
#: ``mulligan`` and ``mulligan_bottom``: the London mulligan before the first turn (CR 103.5),
#: ``mulligan:<seat>:<mulligans taken>`` (keep or mulligan) and
#: ``mulligan_bottom:<seat>:<cards still to put on the bottom>`` (a card of the hand).
SEAT_IN_TAG = frozenset(
    {"target", "tap", "sacrifice", "discard", "scry", "pay", "counter", "cw", "legend", "x",
     "replace", "mulligan", "mulligan_bottom"}
)
#: Engine ask kinds keyed by an object; the decider comes from the engine hook only.
OBJECT_IN_TAG = frozenset(
    {"attack", "block", "order", "trample", "policy", "may", "mana", "choose", "one_of", "name", "enchant"}
)
SITE_KINDS = SEAT_IN_TAG | OBJECT_IN_TAG
REFUSE_TOKENS = ("PASS", "NONE", "DECLINE", "skip", "keep")
_WORDS = {
    "ATTACK": "attack",
    "DECLINE": "do not attack",
    "PASS": "pass (do nothing)",
    "PAY": "pay",
    "NONE": "no block",
    "fire": "yes, use it",
    "skip": "no",
    "top": "keep it on top",
    "bottom": "put it on the bottom",
    "AS_BLOCKED": "assign damage as though blocked",
    "UNBLOCKED": "assign damage as though unblocked",
    "keep": "keep this hand",
    "mulligan": "take a mulligan",
}
_COLORS = {"W": "white", "U": "blue", "B": "black", "R": "red", "G": "green", "C": "colorless"}


def ask_kind(what: str) -> str:
    return what.split(":", 1)[0]


def tag_handle(what: str) -> Handle | None:
    """The handle in a tag's second and third fields (``attack:card:34:17`` -> card:34)."""
    parts = what.split(":")
    if len(parts) >= 3 and parts[2].isdigit():
        return Handle(parts[1], int(parts[2]))
    return None


def resolve_ask_seat(what: str, hook_seat: Handle | None, *, strict: bool = True) -> Handle:
    kind = ask_kind(what)
    if kind not in SITE_KINDS and strict:
        raise UnknownAskSite(f"{what}: ask kind {kind!r} is not in the bench site registry")
    if hook_seat is None:
        raise AskRoutingError(f"{what}: the engine did not name the deciding seat")
    if kind in SEAT_IN_TAG:
        tagged = tag_handle(what)
        if tagged is not None and tagged != hook_seat:
            raise AskRoutingError(f"{what}: tag names {tagged}, engine names {hook_seat}")
    return hook_seat


def _handle_token(token: str) -> Handle | None:
    namespace, _, index = token.partition(":")
    if namespace in ("card", "player", "emblem") and index.isdigit():
        return Handle(namespace, int(index))
    return None


def _bullets(text: str) -> list[str]:
    return [b.strip().rstrip(".") + "." for b in text.split("•")[1:]]


def ability_line(record: CardRecord | None, oracle_text: str, idx: int) -> str | None:
    """The oracle line of activated ability ``idx``, when the mapping is unambiguous.

    Compiled abilities keep no source text, so the line is only named when the card has exactly
    one oracle line per compiled ability and the line has activated-ability syntax ("cost:
    effect"). Otherwise None, and the caller says "see the card text" rather than guess.
    """
    if record is None or not 0 <= idx < len(record.abilities):
        return None
    if not isinstance(record.abilities[idx], ActivatedAbility):
        return None
    lines = [line.strip() for line in oracle_text.split("\n") if line.strip()]
    # An effect-less SpellAbility is the synthetic cast carrier of a permanent: it has no
    # oracle line of its own, so it does not count.
    lined = [
        i
        for i, ab in enumerate(record.abilities)
        if not (isinstance(ab, SpellAbility) and ab.effect is None and not ab.additional_costs)
    ]
    if len(lines) != len(lined):
        return None
    line = lines[lined.index(idx)]
    return line if ":" in line.split("(")[0] else None


def engine_ask(
    lens: SeatLens,
    executor: Executor,
    vocab: tuple[str, ...],
    what: str,
    seat_index: int,
    *,
    context: str = "",
) -> Ask:
    """Turn an engine demand into a readable Ask for the deciding seat."""
    kind = ask_kind(what)
    subject = tag_handle(what)
    about = lens.describe(executor, subject, offered=True) if subject is not None else "the effect"

    def label(token: str) -> str:
        if "@" in token:
            spell, _, target = token.partition("@")
            hs, ht = _handle_token(spell), _handle_token(target)
            if hs is not None and ht is not None:
                return (
                    f"cast {lens.describe(executor, hs, offered=True)} "
                    f"targeting {lens.describe(executor, ht, offered=True)}"
                )
        handle = _handle_token(token)
        if handle is not None:
            if kind == "attack":  # a planeswalker this creature may attack
                return f"attack {lens.describe(executor, handle, offered=True)}"
            return lens.describe(executor, handle, offered=True)
        if kind == "attack" and token == "ATTACK" and any(_handle_token(t) for t in vocab):
            return "attack the defending player"
        if kind == "mana" and token in _COLORS:
            return f"{_COLORS[token]} mana"
        if kind == "x" and token.isdigit():
            return f"X = {token}"
        if kind == "choose" and token.isdigit() and subject is not None:
            modes = _bullets(lens.text(executor_text(lens, executor, subject)))
            if len(modes) == len(vocab):
                return f"mode: {modes[int(token)]}"
        return _WORDS.get(token, f"choice {token}" if token.isdigit() else token)

    prompts = {
        "attack": f"Declare attackers: attack with {about}?",
        "block": f"Declare blockers: block with {about}? Pick the attacker to block, or no block.",
        "may": f"{about}: use its optional effect?",
        "mana": f"{about}: choose the color of mana to add.",
        "choose": f"{about}: choose.",
        "one_of": f"{about}: choose one.",
        "target": f"{about}: choose a target.",
        "scry": "Scry: keep the next card on top, or put it on the bottom?",
        "pay": "A spell asks whether you pay its cost.",
        "counter": "A spell is on the stack: respond with a counterspell, or pass?",
        "cw": "Combat: cast an instant now, or pass?",
        "sacrifice": f"{about}: choose what to sacrifice.",
        "discard": f"{about}: choose what to discard.",
        "legend": "Legend rule: you control legendary permanents with the same name. Choose the one to keep; the others go to the graveyard.",
        "replace": "Several replacement effects apply to the same event. Choose the one that applies first; the others apply afterwards if they still can.",
        "enchant": f"{about} enters the battlefield: choose what it enchants.",
        "tap": f"{about}: choose what to tap.",
        "name": "Choose a card name.",
        "order": f"{about}: choose the damage assignment order.",
        "trample": f"{about}: choose how much excess damage to assign.",
        "x": f"{about}: announce the value of X for the ability.",
        "policy": f"{about}: choose how to assign its combat damage.",
        "mulligan": (
            "Before the first turn: keep this opening hand, or take a mulligan (shuffle your hand "
            "into your library, draw seven cards, and put one card on the bottom of your library "
            "for each mulligan taken so far, this one included)?"
        ),
        "mulligan_bottom": "Mulligan: choose a card from your hand to put on the bottom of your library.",
    }
    prompt = prompts.get(kind, f"The engine asks ({kind}): choose one.")
    if context:
        prompt = f"{prompt} {context}"
    refuse = next((i for i, t in enumerate(vocab) if t in REFUSE_TOKENS), None)
    return Ask(
        seat=seat_index,
        kind=kind,
        site=what,
        prompt=prompt,
        options=tuple(Option(t, label(t)) for t in vocab),
        refuse=refuse,
        leaky=kind == "name" and not executor.name_pool,
    )


def executor_text(lens: SeatLens, executor: Executor, handle: Handle) -> str:
    card = executor.world.cards.get(handle)
    if card is None:
        return ""
    return lens.oracle.text(card.identity.oracle_id) or (card.identity.oracle_text or "")
