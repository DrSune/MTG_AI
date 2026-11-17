"""Put fault A back into a copy of the engine: _cease_tokens spares a token that a waiting trigger
names (7c5598f8^'s TriggerBinder.pending_references: the source, the event's subject and cause,
a gathered event's objects, a reflexive trigger's carried bindings).

    make_mutant_a.py <copy root>
"""
import sys
from pathlib import Path

path = Path(sys.argv[1]) / "MTG_bot" / "core" / "executor" / "__init__.py"
text = path.read_text()
old = "                    if world.cards[card].identity.is_token:\n"
new = "                    if world.cards[card].identity.is_token and card not in _fault_a_pending(self):\n"
assert text.count(old) == 1
text = text.replace(old, new)
text += '''

def _fault_a_pending(ex):
    """Fault A put back (7c5598f8^ binding.pending_references)."""
    from MTG_bot.core.executor.events import KIND_REFLEXIVE

    out = set()
    waiting = [(p.source, p.event, p.gathered) for p in ex.binder.firings.values()]
    waiting += [
        (o.source, o.event, o.ctx.binding_handles("gathered"))
        for o in ex.stack.frames
        if o.spell_kind == "TRIGGERED"
    ]
    for source, event, gathered in waiting:
        out.add(source)
        for handle in (getattr(event, "subject", None), getattr(event, "cause", None)):
            if isinstance(handle, Handle):
                out.add(handle)
        out.update(gathered or ())
    carried = [p.carried.bindings for p in ex.binder.firings.values() if p.carried is not None]
    carried += [
        o.ctx.bindings
        for o in ex.stack.frames
        if o.spell_kind == "TRIGGERED" and o.event.kind == KIND_REFLEXIVE
    ]
    for bindings in carried:
        for value in bindings.values():
            for handle in [value] if isinstance(value, Handle) else list(value or ()):
                if isinstance(handle, Handle):
                    out.add(handle)
    return out
'''
path.write_text(text)
print("patched", path)
