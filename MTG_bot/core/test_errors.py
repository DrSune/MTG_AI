"""Tests for the typed engine error hierarchy.

The point of these tests is the contract, not the classes: every engine
failure is a *typed* exception that is a subclass of EngineError, carries a
message, and can carry machine-readable context. That is what lets the EC-1
gate turn "the engine threw" into a diagnosis instead of a swallowed log line.
"""

import unittest

from MTG_bot.core.errors import (
    EngineError,
    IllegalMoveError,
    UnknownCardError,
    UnsupportedAbilityError,
    TargetingError,
    InfiniteLoopError,
    StateCorruptionError,
)


class TestHierarchy(unittest.TestCase):
    def test_every_specific_error_is_an_engine_error(self):
        for cls in (
            IllegalMoveError,
            UnknownCardError,
            UnsupportedAbilityError,
            TargetingError,
            InfiniteLoopError,
            StateCorruptionError,
        ):
            self.assertTrue(issubclass(cls, EngineError), f"{cls.__name__} must subclass EngineError")

    def test_base_catches_all(self):
        # A gate that catches EngineError must catch every specific failure.
        errors = [
            IllegalMoveError("x"),
            UnknownCardError("x"),
            UnsupportedAbilityError("x"),
            TargetingError("x"),
            InfiniteLoopError("x"),
            StateCorruptionError("x"),
        ]
        for err in errors:
            with self.assertRaises(EngineError):
                raise err

    def test_context_is_machinereadable(self):
        err = IllegalMoveError("cannot cast", context={"move": "cast", "seat": 0})
        self.assertEqual(err.context["move"], "cast")
        self.assertEqual(err.context["seat"], 0)

    def test_with_context_merges(self):
        err = TargetingError("bad target").with_context(card="Blasphemous Act", target="a land")
        self.assertEqual(err.context["card"], "Blasphemous Act")
        self.assertEqual(err.context["target"], "a land")

    def test_default_context_is_empty_dict(self):
        err = StateCorruptionError("invariant broke")
        self.assertEqual(err.context, {})

    def test_infinite_loop_kind(self):
        err = InfiniteLoopError("mandatory loop", kind="mandatory")
        self.assertEqual(err.kind, "mandatory")
        self.assertTrue(issubclass(InfiniteLoopError, EngineError))

    def test_str_includes_context(self):
        err = IllegalMoveError("cannot cast", context={"seat": 2})
        s = str(err)
        self.assertIn("IllegalMoveError", s)
        self.assertIn("cannot cast", s)
        self.assertIn("seat=2", s)


if __name__ == "__main__":
    unittest.main()
