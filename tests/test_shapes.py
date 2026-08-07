"""Candidate payment-vector generators: even, balloon, staircase."""

from __future__ import annotations

from feasibility.constraints import is_valid_payment_vector
from feasibility.models import CreditorRules
from feasibility.shapes import balloon_candidates, even_candidates, staircase_candidates


def _rules(**overrides) -> CreditorRules:
    base = dict(
        max_terms=12,
        max_payments=12,
        min_payment_cents=1000,
        max_token_pays=6,
        min_payment_tiers=[],
        even_pays=False,
        is_ballooning_allowed=False,
        max_segments=2,
        bank_fee_cents=0,
        program_fee_pct=0.0,
    )
    base.update(overrides)
    return CreditorRules(**base)


def test_even_splits_as_equally_as_possible_with_remainder_on_latest():
    rules = _rules()
    [vector] = even_candidates(10, 3, rules)
    assert vector == [3, 3, 4]
    assert sum(vector) == 10
    assert vector == sorted(vector)


def test_even_exact_division_needs_no_remainder():
    rules = _rules()
    [vector] = even_candidates(9000, 3, rules)
    assert vector == [3000, 3000, 3000]


def test_balloon_pins_early_payments_at_floor_and_absorbs_remainder():
    rules = _rules(min_payment_cents=2500)
    [vector] = balloon_candidates(30000, 5, rules)
    assert vector[:-1] == [2500, 2500, 2500, 2500]
    assert vector[-1] == 30000 - 4 * 2500
    assert vector[-1] > vector[-2]


def test_balloon_omitted_when_it_would_be_degenerate():
    # If pinning everything but the last at the floor already leaves the
    # last payment no larger than the one before it, it isn't a real balloon.
    rules = _rules(min_payment_cents=2500)
    assert balloon_candidates(2500 * 5, 5, rules) == []


def test_balloon_requires_at_least_two_payments():
    rules = _rules()
    assert balloon_candidates(10000, 1, rules) == []


def test_staircase_flat_candidate_when_evenly_divisible():
    rules = _rules(max_segments=1)
    candidates = staircase_candidates(9000, 3, rules)
    assert [3000, 3000, 3000] in candidates


def test_staircase_respects_max_segments_cap_of_one():
    rules = _rules(min_payment_cents=1000, max_segments=1)
    # 10000 over 3 payments isn't evenly divisible, so a max_segments=1
    # (flat-only) creditor genuinely has no staircase candidate here.
    candidates = staircase_candidates(10000, 3, rules)
    assert candidates == []


def test_staircase_generalizes_to_three_distinct_levels():
    """Regression guard for the two-level ceiling in the earlier design: with
    two tiers forcing three distinct floor bands, only a 3-segment staircase
    can hit the exact total, and max_segments must actually allow it."""
    rules = _rules(
        min_payment_cents=1000,
        min_payment_tiers=[(3, 2000), (5, 4000)],
        max_segments=3,
    )
    candidates = staircase_candidates(14000, 6, rules)
    three_level = [c for c in candidates if len(set(c)) == 3]
    assert three_level, candidates
    for vector in three_level:
        assert is_valid_payment_vector(vector, rules)
        assert sum(vector) == 14000


def test_staircase_max_segments_two_cannot_find_the_three_level_solution():
    rules = _rules(
        min_payment_cents=1000,
        min_payment_tiers=[(3, 2000), (5, 4000)],
        max_segments=2,
    )
    assert staircase_candidates(14000, 6, rules) == []


def test_every_generated_candidate_is_internally_consistent():
    rules = _rules(min_payment_cents=1500, min_payment_tiers=[(3, 3000)], max_segments=2)
    for k in range(1, 7):
        for vector in staircase_candidates(37500, k, rules):
            assert len(vector) == k
            assert sum(vector) == 37500
            assert vector == sorted(vector)
