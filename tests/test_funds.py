"""Part 2: minimum lump sum / monthly increment, guardrails, and minimality."""

from __future__ import annotations

from datetime import date

from feasibility.engine import evaluate_offer, find_best_schedule
from feasibility.models import load_case


def test_case2_minima_match_expected_values():
    client, offer, rules = load_case("cases/case2_infeasible_minima")
    result = evaluate_offer(client, offer, rules)
    assert result.feasible is False
    af = result.additional_funds
    assert af.lump_sum.amount_cents == 10000
    assert af.lump_sum.within_guardrail is True
    assert af.monthly_increment.amount_cents == 2500
    assert af.monthly_increment.num_drafts == 5
    assert af.monthly_increment.within_guardrail is True


def test_lump_sum_is_minimal_one_cent_less_is_infeasible():
    client, offer, rules = load_case("cases/case2_infeasible_minima")
    result = evaluate_offer(client, offer, rules)
    lump = result.additional_funds.lump_sum
    extra = ((lump.date, lump.amount_cents - 1),)
    assert find_best_schedule(client, offer, rules, extra) is None


def test_monthly_increment_is_minimal_one_cent_less_is_infeasible():
    client, offer, rules = load_case("cases/case2_infeasible_minima")
    result = evaluate_offer(client, offer, rules)
    increment = result.additional_funds.monthly_increment
    future_credit_dates = sorted(
        e.date for e in client.ledger if e.type == "credit" and e.date > client.as_of_date
    )
    extra = tuple((d, increment.amount_cents - 1) for d in future_credit_dates)
    assert find_best_schedule(client, offer, rules, extra) is None


def test_lump_sum_guardrail_breach_is_reported():
    # Force an enormous deficit relative to a tiny offer total so the
    # required lump necessarily exceeds 65% of the offer total.
    client, offer, rules = load_case("cases/case2_infeasible_minima")
    rules.min_payment_cents = 10_000_000  # unpayable floor -> huge deficit
    result = evaluate_offer(client, offer, rules)
    af = result.additional_funds
    assert af.lump_sum.within_guardrail is False
    assert af.lump_sum.reason != ""


def test_monthly_increment_guardrail_breach_is_reported():
    client, offer, rules = load_case("cases/case2_infeasible_minima")
    rules.min_payment_cents = 10_000_000
    result = evaluate_offer(client, offer, rules)
    af = result.additional_funds
    assert af.monthly_increment.within_guardrail is False
    assert af.monthly_increment.reason != ""


def test_lump_sum_lands_on_the_earliest_relevant_date():
    client, offer, rules = load_case("cases/case2_infeasible_minima")
    result = evaluate_offer(client, offer, rules)
    future_dates = [e.date for e in client.ledger if e.type == "credit" and e.date > client.as_of_date]
    assert result.additional_funds.lump_sum.date == min(future_dates + [offer.first_payment_date])
