"""Creditor payment cadence: the monthly recurrence of payment/fee dates.

Independent of the draft schedule (see ASSIGNMENT.md §3). Uses the EOM /
day-preserving helpers already provided in ``feasibility.models``.
"""

from __future__ import annotations

from datetime import date

from feasibility.models import Client, Offer, default_first_payment_date, monthly_payment_dates

# Hard cap on generated cadence dates so a pathological horizon can't blow up
# candidate generation. 30 years of monthly dates is far beyond any realistic
# settlement plan.
MAX_CADENCE_MONTHS = 360


def cadence_dates(client: Client, offer: Offer) -> list[date]:
    """All cadence dates from ``first_payment_date`` through the horizon (inclusive)."""
    start = offer.first_payment_date or default_first_payment_date(client)
    generated = monthly_payment_dates(start, MAX_CADENCE_MONTHS)
    return [d for d in generated if d <= client.last_draft_date]
