"""Copies of objects (CR 707; DESIGN_ATOM_ONTOLOGY §18).

One value, ``CopyOf``, names what is copied and the copy effect's exceptions; two verbs put the
copy in one of three places:

* ``CREATE_TOKEN(tokens=CopyOf)``: a token that's a copy (CR 707.5, created as one, 111.1);
* ``COPY(source=CopyOf)``: copies of a spell or an ability put onto the stack (CR 707.10), never
  cast or activated, each its copier's, with new targets if the effect says so (707.10c);
* ``COPY(source=CopyOf, cards=..., duration=...)``: permanents that become copies, a layer-1
  effect (CR 613.2a, ``layers.LayerRegistry`` kind "copy").

The engine's characteristics of an object are its identity (``CardState.identity``: name, type
line, colours, mana cost, P/T, loyalty, printed keywords; what the network reads too) and its
compiled record (its abilities, ``binder.handle_record``). Its copiable values (CR 707.2) are
those two as they are now, layer 1 applied (707.3: a copy of a copy); never its counters, status,
attachments or other effects, which live on the handle and stay with it. So a copy reads as the
card it copies, oracle id and all.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from MTG_bot.core.ability_tree import (
    TYPE_LINE_KINDS,
    CardRecord,
    CopyOf,
    Keyword,
    KeywordAbility,
    QConst,
    Selector,
    SelectorMode,
    ZoneKind,
)
from MTG_bot.core.executor.decisions import site_digest
from MTG_bot.core.executor.events import KIND_ABILITY_ACTIVATED
from MTG_bot.core.executor.quantity import ExecCtx
from MTG_bot.core.identity import CardIdentity, Handle
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_STACK

if TYPE_CHECKING:  # pragma: no cover - typing-only, dodges the import cycle
    from MTG_bot.core.executor import Executor
    from MTG_bot.core.executor.stack import StackObject

#: An object's copiable values (CR 707.2): its identity and its compiled record (None: no
#: abilities, a vanilla token).
Values = tuple[CardIdentity, "CardRecord | None"]


def copied_objects(ctx: ExecCtx, sel: Selector) -> list[Handle]:
    """The object ``sel`` names for a copy: "this creature" is the ability's source wherever it
    went (read as it last existed if it left, CR 608.2h), anything else what the selector resolves
    to now, an anaphor's object even if it moved (its information is read)."""
    from MTG_bot.core.executor.selectors import (
        _filter_is_self_referential,
        resolve_selector,
    )

    if sel.referent is None and sel.mode is SelectorMode.CHOOSE and _filter_is_self_referential(
        sel.filter
    ):
        return [ctx.source]
    return resolve_selector(sel, ctx, info=True)


def values_of(executor: Executor, handle: Handle, on_battlefield: bool) -> Values | None:
    """The copiable values of ``handle`` (CR 707.2, 707.3): as it is now, or, when it was expected
    on the battlefield (``on_battlefield``) and has left it, as it last existed there (CR 608.2h,
    ``Executor.departed_lki``). None for an object with neither (a token gone with no record)."""
    from MTG_bot.core.executor.legality import spell_record

    state = executor.world.cards.get(handle)
    here = state is not None and executor.world.zone_of(handle).kind == ZONE_BATTLEFIELD
    lki = executor.departed_lki.get(handle)
    if lki is not None and lki.identity is not None and (state is None or (on_battlefield and not here)):
        record = lki.record if lki.record is not None else executor.binder.records.get(
            lki.identity.oracle_id
        )
        return lki.identity, record
    if state is None:
        return None
    return state.identity, spell_record(executor, handle)


def copiable_values(ctx: ExecCtx, copy: CopyOf) -> Values | None:
    """The values a copy of ``copy.source`` takes, its exceptions applied (CR 707.9a-b: they become
    part of the copy's copiable values). None when nothing is there to copy (a target that
    became illegal, CR 608.2b)."""
    assert ctx.executor is not None
    objects = copied_objects(ctx, copy.source)
    if not objects:
        return None
    sel = copy.source
    # Where the object was expected (CR 608.2h): a permanent ("this creature", "target creature",
    # a trigger's creature) on the battlefield; the card an instruction just moved where it is.
    on_battlefield = sel.referent == "event" or (
        sel.referent is None and any(z.kind is ZoneKind.BATTLEFIELD for z in sel.zones)
    )
    values = values_of(ctx.executor, objects[0], on_battlefield)
    if values is None or not copy.has_exceptions:
        return values
    return with_exceptions(values, copy)


def with_exceptions(values: Values, copy: CopyOf) -> Values:
    """``values`` with the copy effect's exceptions: "a Nightmare in addition to its other types"
    adds the subtype to the type line, "has haste and <ability>" the keyword and the ability to
    the record (a vanilla token's record is made for them)."""
    identity, record = values
    type_line = identity.type_line
    if copy.subtypes:
        face, faces, back = type_line.partition(" // ")  # a two-faced card's front face's line
        head, dash, subtypes = face.partition(" — ")
        words = subtypes.split() if dash else []
        words += [s for s in copy.subtypes if s not in words]
        type_line = f"{head} — {' '.join(words)}{faces}{back}"
    if record is None:
        record = _bare_record(identity)
    keywords = record.keywords + tuple(
        KeywordAbility(keyword=k) for k in copy.keywords
        if all(kw.keyword is not k for kw in record.keywords)
    )
    record = replace(
        record,
        type_line=type_line,
        subtypes=record.subtypes + tuple(s for s in copy.subtypes if s not in record.subtypes),
        keywords=keywords,
        abilities=record.abilities + copy.abilities,
    )
    return replace(identity, type_line=type_line), record


def _bare_record(identity: CardIdentity) -> CardRecord:
    """The record of an object that has none, a vanilla token: its identity's characteristics and
    no ability, for a copy that gains some (CR 707.9a)."""
    head, _, subtypes = identity.type_line.partition(" — ")
    words = head.split()
    power = QConst(int(identity.power)) if identity.power not in (None, "") else None
    toughness = QConst(int(identity.toughness)) if identity.toughness not in (None, "") else None
    return CardRecord(
        oracle_id=identity.oracle_id,
        name=identity.name,
        type_line=identity.type_line,
        types=tuple(w for w in words if w in TYPE_LINE_KINDS and w not in _SUPERTYPES),
        subtypes=tuple(subtypes.split()),
        supertypes=tuple(w for w in words if w in _SUPERTYPES),
        colors=identity.colors,
        color_identity=frozenset(identity.colors),
        mana_cost=None,
        mana_value=identity.cmc or 0,
        power=power,
        toughness=toughness,
        loyalty=None,
        keywords=tuple(
            KeywordAbility(keyword=Keyword[k]) for k in identity.keywords if k in Keyword.__members__
        ),
        abilities=(),
        is_token=identity.is_token,
    )


_SUPERTYPES = frozenset({"Basic", "Legendary", "Ongoing", "Snow", "World"})


# ------------------------------------------------------------------ the stack (CR 707.10)


def stack_object(
    executor: Executor, ctx: ExecCtx, handle: Handle, of_event: bool
) -> StackObject | None:
    """The spell or ability on the stack that ``handle`` names. A target ("copy target instant or
    sorcery spell") is one on the stack now: one that left it is no legal target (CR 608.2b).
    The trigger's event (``of_event``: "copy that spell|ability") is the object that cast or
    activation put on the stack, as it last existed there once it left (CR 608.2h: "copy that
    spell" after it was countered still copies it), never a later cast of the same card or
    another activation: a spell's frame pushed at or before the cast row, the ability's frame its
    activation pushed (``legality.activate``; the event's subject is the permanent). None for an
    object with none (a mana ability never uses the stack, CR 605.3b)."""
    stack = executor.stack
    if not of_event:
        return next((f for f in stack.frames if f.handle == handle), None)
    event = ctx.event
    frames = [*stack.frames, *stack.left]
    if event.kind == KIND_ABILITY_ACTIVATED:
        idx = event.activation[0]
        made = [
            f for f in frames
            if f.spell_kind == "ACTIVATED" and f.source == event.subject and f.ability_idx == idx
            and f.controller == event.cause and f.declared_clock >= event.clock
        ]
        return min(made, key=lambda f: f.declared_clock, default=None)
    cast = [f for f in frames if f.handle == handle and f.declared_clock <= event.clock]
    return max(cast, key=lambda f: f.declared_clock, default=None)


def put_copies(ctx: ExecCtx, copy: CopyOf, count: int, new_targets: bool) -> list[Handle]:
    """COPY with no ``cards``: ``count`` copies of the spell or ability ``copy`` names are put onto
    the stack (CR 707.10), each its copier's (the ability's controller), not cast or activated (no
    cast row: nothing that counts casts sees it, Double Vision's ordinal included), its costs
    unpaid (a copied loyalty ability removes no loyalty, CR 606.4), with the original's choices:
    modes, targets, X, kicker (CR 707.10). Choices made on resolution are not copied. With
    ``new_targets`` each copy's controller may keep or change each target (CR 707.10c). Returns
    the copies' stack handles."""
    executor = ctx.executor
    assert executor is not None
    made: list[Handle] = []
    of_event = copy.source.referent == "event"
    for handle in copied_objects(ctx, copy.source):
        frame = stack_object(executor, ctx, handle, of_event)
        if frame is None:
            continue
        for _ in range(count):
            made.append(_put_copy(executor, ctx, frame, new_targets))
    return made


def _put_copy(executor: Executor, ctx: ExecCtx, frame: StackObject, new_targets: bool) -> Handle:
    from MTG_bot.core.executor.legality import spell_record
    from MTG_bot.core.executor.stack import stack_zone

    copier = ctx.controller
    if frame.spell_kind == "TRIGGERED":
        # A triggered ability's copy keeps the context its trigger made (CR 603.3c-d); no card of
        # the copy round copies one (Strionic Resonator, Lithoform Engine bring it).
        raise NotImplementedError("executor: COPY of a triggered ability is not built")
    if frame.spell_kind == "ACTIVATED":
        handle = executor.ability_handles.allocate()
        source = frame.source
    else:
        state = executor.world.cards.get(frame.handle)
        if state is None:
            raise NotImplementedError("executor: COPY of a spell copy that has ceased to exist")
        # A copy of a spell is a spell with no card (CR 707.10), its copier's; it ceases to exist
        # anywhere but the stack (707.10a), the engine's token mark (Executor._cease_tokens).
        stack_zone(executor.world, copier)
        handle = executor.world.add_card(replace(state.identity, is_token=True), copier, ZONE_STACK)
        record = spell_record(executor, frame.handle)
        if record is not None:
            executor.binder.handle_record[handle] = record
        source = handle
    # The copy keeps the original's declaration clock: its targets are the objects chosen then and
    # its source the original's (CR 707.10, 707.10b), so one that changed zones since is a new
    # object it does not name (CR 400.7).
    copy = replace(
        frame,
        handle=handle,
        controller=copier,
        payment=None,
        from_zone=None,
        decisions=(),
        slot_designations=dict(frame.slot_designations),
        rider=None,
    )
    if new_targets and copy.declared_targets:
        _choose_new_targets(executor, ctx, copy)
    if copy.declared_targets:
        # The copy's targets are designated as it is put onto the stack, kept ones too (CR 115.2).
        executor.journal.emit_targeting(source, copier, copy.declared_targets)
    executor.stack.push(copy)
    ctx.events.append((len(ctx.events), "COPY", str(frame.handle), str(handle)))
    return handle


def _choose_new_targets(executor: Executor, ctx: ExecCtx, copy: StackObject) -> None:
    """CR 707.10c: the copy's controller may leave any number of its targets unchanged, even an
    illegal one, and change the others to legal ones; their number does not change, and only the
    final set of targets is judged (CR 115.7d-e), so two targets may trade places (Rookie
    Mistake's +0/+2 and -2/-0: the gate's m1). Asked one target at a time, slot by slot
    (``target:<seat>:<copy>:<digest>``, the target ask's shape), the target it has first: every
    object that some final set holding the choices made so far allows there. A final set has
    no object twice in a slot (CR 115.3), no "another target" clash (stack's rule) and never the
    copy itself (CR 115.5).

    A changed target is chosen now, so the copy's targets are judged from now on (its
    ``declared_clock``); a kept one that changed zones since the original chose it is a new
    object the copy does not target (CR 400.7) and is dropped, as an illegal target is not
    affected (CR 608.2b)."""
    from MTG_bot.core.executor.query import activation_target_slots, spell_target_slots
    from MTG_bot.core.executor.returns import moved_since
    from MTG_bot.core.executor.stack import another_target_reason

    copier = copy.controller
    if copy.spell_kind == "ACTIVATED":
        slots = activation_target_slots(executor, copy.node.effect, source=copy.source, seat=copier)
        about = copy.source  # the ask names a card, as an activation's own target ask does
    else:
        slots = spell_target_slots(
            executor, copy.target_node or copy.node, spell_handle=copy.handle, seat=copier
        )
        about = copy.handle
    if not slots:
        return
    if len(slots) == 1:
        olds = [tuple(copy.declared_targets)]
    else:
        olds = [tuple(copy.slot_designations.get(repr(slot.selector), ())) for slot in slots]
    places = [(i, j) for i, group in enumerate(olds) for j in range(len(group))]
    menus = {
        (i, j): [olds[i][j], *(h for h in slots[i].candidates if h not in (copy.handle, olds[i][j]))]
        for i, j in places
    }

    def legal(chosen: dict) -> bool:
        groups = [tuple(chosen[(i, j)] for j in range(len(olds[i]))) for i in range(len(olds))]
        return all(len(set(g)) == len(g) for g in groups) and another_target_reason(slots, groups) is None

    def completes(chosen: dict, rest: list) -> bool:  # some final set holds ``chosen``
        if not rest:
            return legal(chosen)
        place, *more = rest
        return any(completes({**chosen, place: h}, more) for h in menus[place])

    chosen: dict = {}
    for k, place in enumerate(places):
        options = [h for h in menus[place] if completes({**chosen, place: h}, places[k + 1:])]
        answer = options[0]
        if len(options) > 1:
            vocab = tuple(str(h) for h in options)
            word = ctx.take_decision_of(copier, vocab, f"target:{copier}:{about}:{site_digest(vocab)}")
            answer = next(h for h in options if str(h) == word)
        chosen[place] = answer
    kept = [p for p in places if chosen[p] == olds[p[0]][p[1]]]
    gone: set = set()
    if len(kept) < len(places):  # a target changed: the copy's targets are judged from now on
        gone = {
            p for p in kept
            if chosen[p].namespace == "card"
            and moved_since(executor.journal, chosen[p], copy.declared_clock)
        }
        copy.declared_clock = executor.journal.clock
    groups = [
        tuple(sorted(chosen[(i, j)] for j in range(len(olds[i])) if (i, j) not in gone))
        for i in range(len(olds))
    ]
    copy.declared_targets = tuple(sorted({h for group in groups for h in group}))
    if len(slots) > 1:
        copy.slot_designations = {
            repr(slot.selector): group for slot, group in zip(slots, groups, strict=True)
        }


# ------------------------------------------------------------------ layer 1 (CR 613.2a)


def become_copies(ctx: ExecCtx, copy: CopyOf, target: Selector, duration: object) -> list[Handle]:
    """COPY with ``cards``: each permanent the selector names now becomes a copy of
    ``copy.source`` for ``duration`` (CR 707.2, 613.2a; the set is fixed as the effect begins, CR
    611.2c). The copiable values are taken now (the copy effect copies the object as it is when
    the effect begins), the exceptions applied, and the layer registry applies them in layer 1
    (``LayerRegistry.register_copy``). Returns the permanents."""
    from MTG_bot.core.executor.selectors import resolve_selector

    executor = ctx.executor
    assert executor is not None
    values = copiable_values(ctx, copy)
    if values is None:
        return []
    world = executor.world
    permanents = tuple(
        h for h in resolve_selector(target, ctx)
        if h in world.cards and world.zone_of(h).kind == ZONE_BATTLEFIELD
    )
    if permanents:
        executor.layers.register_copy(ctx.source, ctx.controller, permanents, values, duration)
        executor.layers.recompute()
    ctx.events.append(
        (len(ctx.events), "BECOME_COPY", values[0].name, tuple(str(h) for h in permanents))
    )
    return list(permanents)
