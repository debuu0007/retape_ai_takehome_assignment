"""Chronological ledger simulation: same-day ordering, exact-zero balance,
fee-only dates carrying no bank fee, and fee never collected before the first
payment date.
"""

from __future__ import annotations

from datetime import date

from feasibility.engine import evaluate_offer
from feasibility.models import Client, CreditorRules, LedgerEntry, load_case
from feasibility.simulate import build_timeline, simulate


def _rules(**overrides) -> CreditorRules:
    base = dict(
        max_terms=12,
        max_payments=12,
        min_payment_cents=0,
        max_token_pays=12,
        min_payment_tiers=[],
        even_pays=False,
        is_ballooning_allowed=False,
        max_segments=2,
        bank_fee_cents=10,
        program_fee_pct=0.0,
    )
    base.update(overrides)
    return CreditorRules(**base)


def test_same_day_credit_covers_a_debit_that_would_otherwise_go_negative():
    d = date(2026, 1, 15)
    client = Client(
        draft_amount_cents=0,
        draft_day=1,
        first_draft_date=d,
        last_draft_date=d,
        as_of_date=date(2025, 12, 31),
        current_balance_cents=0,
        ledger=[LedgerEntry(d, 1000, "credit"), LedgerEntry(d, 1000, "debit")],
    )
    rules = _rules(bank_fee_cents=0)
    timeline = build_timeline(client, cadence=[])
    outcome = simulate([], rules, timeline, client.current_balance_cents, fee_total=0)
    assert outcome is not None


def test_a_fee_only_date_carries_no_bank_fee_while_payment_dates_do():
    d1, d2, d3 = date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)
    client = Client(
        draft_amount_cents=10000,
        draft_day=1,
        first_draft_date=d1,
        last_draft_date=d3,
        as_of_date=date(2025, 12, 31),
        current_balance_cents=0,
        ledger=[
            LedgerEntry(d1, 10000, "credit"),
            LedgerEntry(d2, 10000, "credit"),
            LedgerEntry(d3, 10000, "credit"),
        ],
    )
    rules = _rules(bank_fee_cents=10)
    cadence = [d1, d2, d3]
    payments = [5000]  # only the first cadence date carries a creditor payment
    timeline = build_timeline(client, cadence)
    outcome = simulate(payments, rules, timeline, client.current_balance_cents, fee_total=15000)
    assert outcome is not None
    rows, _score = outcome
    by_date = {row.date: row for row in rows}

    assert by_date[d1].creditor_payment_cents == 5000
    assert by_date[d1].bank_fee_cents == 10  # a real payment date -> bank fee applies

    assert by_date[d2].creditor_payment_cents == 0
    assert by_date[d2].bank_fee_cents == 0  # fee-only date -> no bank fee

    assert by_date[d3].creditor_payment_cents == 0
    assert by_date[d3].bank_fee_cents == 0

    assert by_date[d1].balance_cents >= 0
    assert by_date[d3].program_fee_cents + by_date[d2].program_fee_cents + by_date[d1].program_fee_cents == 15000


def test_no_fee_is_collected_before_the_first_cadence_date():
    client, offer, rules = load_case("cases/case1_feasible_even")
    result = evaluate_offer(client, offer, rules)
    first_cadence_date = result.schedule[0].date
    assert all(row.date >= first_cadence_date for row in result.schedule)
    assert first_cadence_date == offer.first_payment_date


def test_a_balance_hitting_exactly_zero_is_still_feasible():
    client, offer, rules = load_case("cases/case1_feasible_even")
    result = evaluate_offer(client, offer, rules)
    assert result.feasible is True
    assert any(row.balance_cents == 0 for row in result.schedule)
    assert all(row.balance_cents >= 0 for row in result.schedule)


def test_committed_ledger_debits_are_respected_not_modified():
    client, offer, rules = load_case("cases/case3_balloon")
    committed_debit = next(e for e in client.ledger if e.type == "debit")
    result = evaluate_offer(client, offer, rules)
    assert result.feasible is True
    # The committed 15000-cent debit lands between Jan and Feb payments;
    # the balance after Feb's payment must reflect it having been deducted.
    feb_row = next(row for row in result.schedule if row.date == date(2026, 2, 28))
    assert feb_row.balance_cents == 0
    assert committed_debit.amount_cents == 15000
