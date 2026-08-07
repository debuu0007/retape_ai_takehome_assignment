"""Payment cadence: EOM default, EOM/day-preserving recurrence, horizon cutoff."""

from __future__ import annotations

from datetime import date

from feasibility.cadence import cadence_dates
from feasibility.models import Client, Offer


def _client(last_draft_date: date, first_draft_date: date = date(2026, 1, 1)) -> Client:
    return Client(
        draft_amount_cents=10000,
        draft_day=1,
        first_draft_date=first_draft_date,
        last_draft_date=last_draft_date,
        as_of_date=date(2025, 12, 31),
        current_balance_cents=0,
        ledger=[],
    )


def test_defaults_to_end_of_month_when_first_payment_date_omitted():
    client = _client(last_draft_date=date(2026, 6, 1))
    offer = Offer("C", 1, 1, 0.5, first_payment_date=None)
    dates = cadence_dates(client, offer)
    assert dates[0] == date(2026, 1, 31)


def test_true_eom_cadence_crosses_a_leap_february():
    client = _client(last_draft_date=date(2026, 4, 30))
    offer = Offer("C", 1, 1, 0.5, first_payment_date=date(2026, 1, 31))
    dates = cadence_dates(client, offer)
    assert dates == [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)]


def test_mid_month_day_is_clamped_to_shorter_months():
    client = _client(last_draft_date=date(2026, 3, 31))
    offer = Offer("C", 1, 1, 0.5, first_payment_date=date(2026, 1, 31))
    dates = cadence_dates(client, offer)
    # Jan 31 is treated as true-EOM (it *is* the last day of its month), so
    # this only exercises clamping when the seed day isn't itself EOM.
    seed_offer = Offer("C", 1, 1, 0.5, first_payment_date=date(2026, 1, 30))
    seed_dates = cadence_dates(client, seed_offer)
    assert seed_dates == [date(2026, 1, 30), date(2026, 2, 28), date(2026, 3, 30)]


def test_horizon_is_inclusive_at_last_draft_date_exclusive_after():
    client = _client(last_draft_date=date(2026, 3, 15))
    offer = Offer("C", 1, 1, 0.5, first_payment_date=date(2026, 1, 15))
    dates = cadence_dates(client, offer)
    assert dates == [date(2026, 1, 15), date(2026, 2, 15), date(2026, 3, 15)]
    assert date(2026, 4, 15) not in dates
