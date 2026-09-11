"""Tests for pre-flight check P11: all RNG seeded, streams separated.

The load-bearing test here is test_consuming_one_stream_does_not_perturb_another. The other
tests would pass under a single global seed; that one would not, and it is the property the
protocol actually needs. docs/TRAINING_REVIEW_PROTOCOL.md says P11 to P13 gate the entire
protocol, and the reason is that without stream separation an A/B comparison silently
measures the wrong thing: changing a hyperparameter changes how many numbers its stream
consumes, which shifts every later draw from any stream it shares.
"""

import hashlib

import pytest

from MTG_bot.utils import rng


def _seeded(master=12345):
    rng.seed_all(master, seed_frameworks=False)


def test_same_master_seed_reproduces_every_stream():
    _seeded()
    first = {n: [rng.stream(n).random() for _ in range(5)] for n in rng.STREAM_NAMES}
    _seeded()
    second = {n: [rng.stream(n).random() for _ in range(5)] for n in rng.STREAM_NAMES}
    assert first == second


def test_streams_are_distinct_from_each_other():
    """Guards against every name aliasing onto one generator, which would look seeded and
    reproduce perfectly while providing none of the separation P11 asks for."""
    _seeded()
    seqs = {n: tuple(rng.stream(n).random() for _ in range(5)) for n in rng.STREAM_NAMES}
    assert len(set(seqs.values())) == len(rng.STREAM_NAMES), (
        f"two streams produced identical sequences: {seqs}"
    )


def test_consuming_one_stream_does_not_perturb_another():
    """THE P11 property. Draw an arbitrary amount from exploration, then check every other
    stream is untouched.

    Before MTG_bot/utils/rng.py existed, every draw in the project came from the one global
    `random` module, so this failed: raising the exploration rate consumed a different
    number of draws and shifted every subsequent library shuffle. Two runs differing only in
    a hyperparameter faced different decks.
    """
    _seeded()
    baseline = {n: [rng.stream(n).random() for _ in range(5)]
                for n in rng.STREAM_NAMES if n != "exploration"}

    _seeded()
    for _ in range(997):                      # an arbitrary, awkward number of draws
        rng.stream("exploration").random()
    after = {n: [rng.stream(n).random() for _ in range(5)]
             for n in rng.STREAM_NAMES if n != "exploration"}

    assert after == baseline, (
        "draining the exploration stream changed another stream, so the streams are "
        "coupled and no A/B comparison between two exploration rates can conclude anything"
    )


def test_stream_seeds_are_derived_from_the_name_not_from_draw_order():
    """Pins the derivation so that adding a stream later cannot renumber existing ones.

    With sequential splitting of a parent generator, inserting a sixth stream shifts every
    stream after it and silently invalidates the reproducibility of every earlier run. This
    asserts the documented sha256(master:name) scheme instead.
    """
    master = 4242
    for name in rng.STREAM_NAMES:
        expected = int.from_bytes(
            hashlib.sha256(f"{master}:{name}".encode("utf-8")).digest()[:8], "big")
        assert rng._derive(master, name) == expected


def test_derivation_does_not_depend_on_pythonhashseed():
    """P12 requires the same seed to replay identically *in two processes*. The builtin
    hash() of a str is salted per process, so the derivation must use hashlib."""
    import subprocess, sys, textwrap
    script = textwrap.dedent("""
        from MTG_bot.utils import rng
        rng.seed_all(99, seed_frameworks=False)
        print(rng.stream("shuffle").random())
    """)
    outs = set()
    for salt in ("0", "1", "random"):
        r = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                           env={"PYTHONHASHSEED": salt, "PATH": "/usr/bin:/bin"})
        assert r.returncode == 0, r.stderr
        outs.add(r.stdout.strip().splitlines()[-1])
    assert len(outs) == 1, f"derivation varies with PYTHONHASHSEED: {outs}"


def test_unknown_stream_raises_rather_than_silently_aliasing():
    _seeded()
    with pytest.raises(KeyError, match="unknown RNG stream"):
        rng.stream("not_a_declared_stream")


def test_engine_setup_is_reproducible_under_a_seed():
    """End-to-end through the real wiring: the same master seed must deal the same game."""
    from MTG_bot.rule_engine.game_initializer import initialize_game_state
    from MTG_bot.rule_engine import vocabulary as vocab

    def deal():
        _seeded(777)
        g = initialize_game_state(list(range(1, 61)), list(range(1, 61)), shuffle=True)
        p0 = g.players[0]
        lib = g.get_entities_in_zone(p0, vocab.ID_ZONE_LIBRARY)
        hand = g.get_entities_in_zone(p0, vocab.ID_ZONE_HAND)
        starting_seat = g.players.index(g.active_player_id)
        return [c.type_id for c in lib], [c.type_id for c in hand], starting_seat

    assert deal() == deal()


def test_changing_exploration_draws_does_not_change_the_deal():
    """The same property as above, but through the real engine path, which is where it
    actually has to hold. This is the one that makes a two-arm experiment valid."""
    from MTG_bot.rule_engine.game_initializer import initialize_game_state
    from MTG_bot.rule_engine import vocabulary as vocab

    def deal(exploration_draws):
        _seeded(777)
        for _ in range(exploration_draws):
            rng.stream("exploration").random()
        g = initialize_game_state(list(range(1, 61)), list(range(1, 61)), shuffle=True)
        lib = g.get_entities_in_zone(g.players[0], vocab.ID_ZONE_LIBRARY)
        return [c.type_id for c in lib], g.players.index(g.active_player_id)

    assert deal(0) == deal(1234)


def test_auto_seed_is_recorded_so_an_unseeded_run_is_still_recoverable():
    """An unseeded run must never be silent. It auto-seeds and the seed is readable, so a
    manifest writer can record it (P1 and P11 both want the seed written down)."""
    rng._master_seed = None
    rng._streams.clear()
    rng.stream("shuffle").random()
    assert rng.get_master_seed() is not None
