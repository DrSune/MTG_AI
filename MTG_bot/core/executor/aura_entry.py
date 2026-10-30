"""V32 (2026-10-29): what an Aura enchants when it enters without being cast.

CR 303.4f: if an Aura is entering the battlefield under a player's control by any means other than
by resolving as an Aura spell, and the effect putting it onto the battlefield doesn't specify what
it will enchant, that player chooses, as it enters, a legal object or player according to its enchant
ability. The choice is not targeting, so hexproof does not exclude anything. CR 303.4d: an Aura can't
enchant itself. CR 303.4g: with nothing legal to enchant, the Aura stays in its current zone (from
the stack it goes to its owner's graveyard instead).

The choice is an explicit ask of that player, ``enchant:<aura>:<digest>`` over the live legal hosts
(one host is taken without an ask, never a phantom). The caller moves the Aura and attaches it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from MTG_bot.core.ability_tree import FAnd, Filter, Keyword
from MTG_bot.core.executor.decisions import site_digest
from MTG_bot.core.executor.legality import ctx_for, spell_record
from MTG_bot.core.executor.offers import offer_or_autopick
from MTG_bot.core.executor.quantity import eval_filter

if TYPE_CHECKING:  # pragma: no cover - import cycle guard only
    from MTG_bot.core.executor import Executor
    from MTG_bot.core.identity import Handle


def _enchant_filter(executor: Executor, aura: Handle) -> Filter:
    """The Aura's ENCHANT keyword restriction (CR 702.5a); any permanent when it names none."""
    record = spell_record(executor, aura)
    if record is not None:
        for ability in record.keywords:
            if ability.keyword is Keyword.ENCHANT and ability.params:
                return ability.params[0]
    return FAnd(())


def aura_entry_hosts(executor: Executor, aura: Handle, controller: Handle) -> list[Handle]:
    """The objects ``aura`` may enchant as it enters under ``controller`` (CR 303.4f): battlefield
    permanents passing its ENCHANT filter, judged with ``controller`` as "you", the Aura itself
    excluded (303.4d). A phased-out permanent is treated as though it does not exist (CR 702.26b),
    so ``Executor.battlefield`` leaves it out (R5-1 branch, where phasing lives; agreed with V32's
    author). Handle-sorted."""
    world = executor.world
    enchant = _enchant_filter(executor, aura)
    ctx = ctx_for(executor, source=aura, controller=controller)
    hosts = [
        card
        for player in world.player_order
        for card in executor.battlefield(player)
        if card != aura and eval_filter(enchant, card, ctx)
    ]
    return sorted(hosts)


def choose_aura_host(executor: Executor, aura: Handle, controller: Handle) -> Handle | None:
    """``controller``, the player the Aura enters under, chooses what it will enchant (CR 303.4f),
    asked as ``enchant:<aura>:<digest>``; one legal host is taken without an ask. None when nothing
    is legal: the Aura stays in its current zone (CR 303.4g)."""
    hosts = aura_entry_hosts(executor, aura, controller)
    if not hosts:
        return None
    vocab = tuple(str(h) for h in hosts)
    ctx = ctx_for(executor, source=aura, controller=controller)
    answer = offer_or_autopick(ctx, vocab, f"enchant:{aura}:{site_digest(vocab)}")
    return next(h for h in hosts if str(h) == answer)
