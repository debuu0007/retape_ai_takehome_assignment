"""Round-half-up must round .5 away from zero, not to even (Python's default)."""

from __future__ import annotations

from feasibility.money import percent_of_cents, round_half_up


def test_half_rounds_away_from_zero_not_to_even():
    assert round_half_up(0.5) == 1
    assert round_half_up(1.5) == 2
    assert round_half_up(2.5) == 3
    assert round_half_up(-0.5) == -1
    assert round_half_up(-1.5) == -2


def test_below_half_rounds_down_above_half_rounds_up():
    assert round_half_up(1.49) == 1
    assert round_half_up(1.51) == 2


def test_python_builtin_round_would_disagree_on_these():
    # Sanity check that the scenario we care about actually exercises
    # round-half-to-even vs round-half-up, so the test isn't vacuous.
    assert round(0.5) == 0
    assert round(2.5) == 2
    assert round_half_up(0.5) != round(0.5)
    assert round_half_up(2.5) != round(2.5)


def test_percent_of_cents_avoids_float_multiplication_drift():
    # 0.125 * 4 == 0.5 exactly; round-half-up must take it to 1, not 0.
    assert percent_of_cents(0.125, 4) == 1


def test_percent_of_cents_matches_spec_example():
    # ASSIGNMENT.md worked example: program_fee = round(0.2 * 120000) - style math.
    assert percent_of_cents(0.2, 120000) == 24000
