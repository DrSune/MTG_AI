"""new_set.py: the seal is stable, carry-over is decided before the seal, shapes ignore self-names."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import new_set as ns


def test_the_split_is_deterministic_and_near_its_share() -> None:
    ids = [f"oid-{i}" for i in range(4000)]
    first = [ns.split_of(i, "M20-sealed-v1") for i in ids]
    assert first == [ns.split_of(i, "M20-sealed-v1") for i in ids]
    share = first.count("test") / len(first)
    assert abs(share - ns.TEST_SHARE) < 0.03
    # A different salt is a different seal, not a relabelling of the same one.
    other = [ns.split_of(i, "KHM-sealed-v1") for i in ids]
    assert sum(a != b for a, b in zip(first, other)) > 1000


def test_a_shape_hides_the_cards_own_names_and_numbers() -> None:
    names = ("Ajani, Inspiring Leader", "Ajani")
    assert (
        ns.shape("When Ajani enters, you gain 3 life and draw 2 cards.", names)
        == "When ~ enters, you gain N life and draw N cards."
    )
    # Other cards' names stay: "Ajani's Pridemate" is not a self-reference of a card named Ajani.
    assert ns.shape("Search for Ajani's Pridemate.", ("Ajani",)) == "Search for ~'s Pridemate."
    assert ns.shape("Search for Ajanis.", ("Ajani",)) == "Search for Ajanis."


def test_loyalty_brackets_and_minus_signs_normalise_like_scryfall() -> None:
    assert ns._norm("[+1]: Draw.\n[−3]: Exile.") == ns._norm("+1: Draw.\n-3: Exile.")
    assert ns._norm("[-X]: Do it.") == "-X: Do it."
    assert ns._norm("Add {G}  (mana).") == "Add {G} (mana)."
