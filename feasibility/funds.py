"""Part 2: minimum extra funding (lump sum and monthly increment) that turns
an infeasible offer feasible.

Feasibility is monotone in added cash — giving the account more money on any
date it already has an event can only help, never hurt, a chronological
balance-≥-0 simulation — so each minimum is found by binary search over a
solver that is otherwise a black box.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from feasibility.models import Client, CreditorRules, Offer
from feasibility.money import round_half_up


def _feasible_at(
    amount: int,
    extra_builder: Callable[[int], tuple[tuple[date, int], ...]],
    solve: Callable[[tuple[tuple[date, int], ...]], object],
) -> bool:
    return solve(extra_builder(amount)) is not None


def minimal_extra_cents(
    upper_bound: int,
    extra_builder: Callable[[int], tuple[tuple[date, int], ...]],
    solve: Callable[[tuple[tuple[date, int], ...]], object],
) -> int:
    """Smallest integer amount in ``[0, upper_bound]`` for which
    ``solve(extra_builder(amount))`` finds a feasible schedule, assuming
    ``upper_bound`` itself is feasible (the caller must guarantee this)."""
    lo, hi = 0, upper_bound
    while lo < hi:
        mid = (lo + hi) // 2
        if _feasible_at(mid, extra_builder, solve):
            hi = mid
        else:
            lo = mid + 1
    return lo


def deficit_upper_bound(
    client: Client, offer_total: int, program_fee: int, rules: CreditorRules
) -> int:
    """A cash amount comfortably large enough that adding it must make the
    offer feasible: cover the full offer, the full program fee, every
    possible bank fee, and every already-committed debit, plus one cent of
    slack against rounding at the boundary."""
    committed_debits = sum(e.amount_cents for e in client.ledger if e.type == "debit")
    max_bank_fees = rules.bank_fee_cents * min(rules.max_payments, rules.max_terms)
    return offer_total + program_fee + max_bank_fees + committed_debits + 1


def lump_sum_date(client: Client, cadence: list[date]) -> date:
    """The earliest date anything happens — an earlier lump is weakly more
    useful than a later one (it is available for strictly more of the
    simulation), so placing it here minimizes the required amount. Falls back
    to the horizon if the account and cadence are otherwise empty."""
    future_credits = [e.date for e in client.ledger if e.type == "credit" and e.date > client.as_of_date]
    candidates = future_credits + cadence
    return min(candidates) if candidates else client.last_draft_date


def future_draft_dates(client: Client) -> list[date]:
    return sorted(
        e.date for e in client.ledger if e.type == "credit" and e.date > client.as_of_date
    )


def guardrail_caps(offer: Offer, client: Client, offer_total: int) -> tuple[int, int]:
    """(lump_sum_cap, monthly_increment_cap) per ASSIGNMENT.md §8."""
    lump_cap = round_half_up(0.65 * offer_total)
    increment_cap = max(10000, round_half_up(0.40 * client.draft_amount_cents))
    return lump_cap, increment_cap
