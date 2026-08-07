"""Per-position floors and the vector-level hard constraints."""

from __future__ import annotations

from feasibility.constraints import block_floor, is_valid_payment_vector, position_floor
from feasibility.models import CreditorRules


def _rules(**overrides) -> CreditorRules:
    base = dict(
        max_terms=12,
        max_payments=12,
        min_payment_cents=2500,
        max_token_pays=2,
        min_payment_tiers=[(4, 5000), (7, 8000)],
        even_pays=False,
        is_ballooning_allowed=False,
        max_segments=3,
        bank_fee_cents=500,
        program_fee_pct=0.2,
    )
    base.update(overrides)
    return CreditorRules(**base)


def test_position_floor_before_any_tier_is_base_minimum():
    rules = _rules()
    assert position_floor(1, rules) == 2500
    assert position_floor(3, rules) == 2500


def test_position_floor_applies_highest_reached_tier():
    rules = _rules()
    assert position_floor(4, rules) == 5000
    assert position_floor(6, rules) == 5000
    assert position_floor(7, rules) == 8000
    assert position_floor(100, rules) == 8000  # tiers never expire


def test_block_floor_is_max_over_the_span():
    rules = _rules()
    assert block_floor(1, 3, rules) == 2500
    assert block_floor(3, 5, rules) == 5000  # spans the tier-4 boundary


def test_non_decreasing_is_enforced():
    rules = _rules(min_payment_tiers=[])
    assert not is_valid_payment_vector([3000, 2500, 4000], rules)
    assert is_valid_payment_vector([2500, 2500, 4000], rules)


def test_floor_violation_is_rejected():
    rules = _rules()
    # position 4 requires >= 5000 but this vector only offers 3000 there.
    assert not is_valid_payment_vector([2500, 2500, 2500, 3000], rules)


def test_token_pay_cap_allows_up_to_the_limit_then_requires_strictly_more():
    rules = _rules(min_payment_tiers=[], max_token_pays=2)
    assert is_valid_payment_vector([2500, 2500, 3000], rules)
    assert not is_valid_payment_vector([2500, 2500, 2500], rules)
    assert is_valid_payment_vector([2500, 2501, 2600], rules)
