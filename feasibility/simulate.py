"""Chronological ledger simulation with greedy, earliest-possible program-fee
collection — the mechanical expression of the "front-load the fee" objective
(ASSIGNMENT.md §6): at every cadence date, collect as much of the remaining
program fee as the balance allows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from feasibility.models import Client, CreditorRules


@dataclass
class ScheduleRow:
    date: date
    creditor_payment_cents: int
    program_fee_cents: int
    bank_fee_cents: int
    balance_cents: int


@dataclass
class LedgerTimeline:
    """The parts of a solve that are invariant across every candidate payment
    vector: the committed future ledger, split by type, and the full
    chronological set of dates anything can happen on. Built once per solve
    (and once per Part-2 binary-search probe) instead of per candidate."""

    credits: dict[date, int]
    debits: dict[date, int]
    dates: list[date]
    cadence_index: dict[date, int]


def build_timeline(
    client: Client, cadence: list[date], extra_credits: tuple[tuple[date, int], ...] = ()
) -> LedgerTimeline:
    credits: dict[date, int] = {}
    debits: dict[date, int] = {}
    for entry in client.ledger:
        if entry.date > client.as_of_date:
            target = credits if entry.type == "credit" else debits
            target[entry.date] = target.get(entry.date, 0) + entry.amount_cents
    for entry_date, amount in extra_credits:
        credits[entry_date] = credits.get(entry_date, 0) + amount

    dates = sorted(set(credits) | set(debits) | set(cadence))
    cadence_index = {d: i for i, d in enumerate(cadence)}
    return LedgerTimeline(credits, debits, dates, cadence_index)


def simulate(
    payments: list[int],
    rules: CreditorRules,
    timeline: LedgerTimeline,
    start_balance: int,
    fee_total: int,
) -> tuple[list[ScheduleRow], tuple[int, ...]] | None:
    """Walk the timeline once, applying credits before debits on each date
    (constraint: same-day ordering). Returns ``(rows, fee_score)`` if the
    balance never goes negative and the full program fee is collected by the
    horizon, else ``None``.

    ``fee_score`` is the cumulative fee collected as of each date in the
    (candidate-independent) timeline — comparing it lexicographically across
    candidates ranks how front-loaded each one is, and every candidate for a
    given solve shares the same timeline, so the comparison is always
    apples-to-apples regardless of how many payments each candidate uses.
    """
    k = len(payments)
    balance = start_balance
    fee_remaining = fee_total
    cumulative_fee = 0
    rows: list[ScheduleRow] = []
    fee_score: list[int] = []

    for d in timeline.dates:
        balance += timeline.credits.get(d, 0)
        balance -= timeline.debits.get(d, 0)
        if balance < 0:
            return None

        creditor_payment = bank_fee = fee_here = 0
        idx = timeline.cadence_index.get(d)
        if idx is not None:
            if idx < k:
                creditor_payment = payments[idx]
                bank_fee = rules.bank_fee_cents
                balance -= creditor_payment + bank_fee
            if balance < 0:
                return None
            if fee_remaining > 0:
                fee_here = min(fee_remaining, balance)
                balance -= fee_here
                fee_remaining -= fee_here
            if creditor_payment or fee_here:
                rows.append(ScheduleRow(d, creditor_payment, fee_here, bank_fee, balance))

        cumulative_fee += fee_here
        fee_score.append(cumulative_fee)

    if fee_remaining != 0:
        return None
    return rows, tuple(fee_score)
