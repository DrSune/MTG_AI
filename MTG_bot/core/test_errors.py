"""Tests for the typed engine errors: a message, machine-readable context, and a str that shows both."""

import unittest

from MTG_bot.core.errors import EngineError, StateCorruptionError


class TestHierarchy(unittest.TestCase):
    def test_state_corruption_is_an_engine_error(self):
        with self.assertRaises(EngineError):
            raise StateCorruptionError("x")

    def test_context_is_machinereadable(self):
        err = StateCorruptionError("card missing name", context={"field": "name", "seat": 0})
        self.assertEqual(err.context["field"], "name")
        self.assertEqual(err.context["seat"], 0)

    def test_default_context_is_empty_dict(self):
        self.assertEqual(StateCorruptionError("invariant broke").context, {})

    def test_str_includes_context(self):
        s = str(StateCorruptionError("cannot cast", context={"seat": 2}))
        self.assertIn("StateCorruptionError", s)
        self.assertIn("cannot cast", s)
        self.assertIn("seat=2", s)


if __name__ == "__main__":
    unittest.main()
