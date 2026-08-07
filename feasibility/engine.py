"""Orchestrates the modules in this package into ``evaluate_offer``.

Pipeline for Part 1 (feasibility + schedule):
  cadence dates -> per-shape candidate payment vectors (shapes.py)
  -> hard-constraint validation (constraints.py)
  -> chronological simulation with greedy fee front-loading (simulate.py)
  -> keep the most front-loaded feasible candidate, across every shape the
     creditor flags make eligible, in priority order.

Part 2 (infeasible) reuses the exact same solver as a black box inside a
binary search over added cash (funds.py), since feasibility only gets easier
as more cash is added.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from feasibility.cadence import cadence_dates
from feasibility.constraints import is_valid_payment_vector
from feasibility.funds import (
    deficit_upper_bound,
    future_draft_dates,
    guardrail_caps,
    lump_sum_date,
    minimal_extra_cents,
)
from feasibility.models import Client, CreditorRules, Offer
from feasibility.money import percent_of_cents
from feasibility.shapes import SHAPE_GENERATORS
from feasibility.simulate import ScheduleRow, build_timeline, simulate


@dataclass
class FundsOption:
    amount_cents: int
    within_guardrail: bool
    reason: str
    # lump-sum only:
    date: date | None = None
    # monthly-increment only:
    num_drafts: int | None = None


@dataclass
class AdditionalFunds:
    lump_sum: FundsOption
    monthly_increment: FundsOption


@dataclass
class Result:
    feasible: bool
    pay_shape_used: str | None = None
    schedule: list[ScheduleRow] | None = None
    additional_funds: AdditionalFunds | None = None

    def to_dict(self) -> dict:
        out: dict = {"feasible": self.feasible, "pay_shape_used": self.pay_shape_used}
        out["schedule"] = (
            [
                {
                    "date": r.date.isoformat(),
                    "creditor_payment_cents": r.creditor_payment_cents,
                    "program_fee_cents": r.program_fee_cents,
                    "bank_fee_cents": r.bank_fee_cents,
                    "balance_cents": r.balance_cents,
                }
                for r in self.schedule
            ]
            if self.schedule is not None
            else None
        )
        if self.additional_funds is None:
            out["additional_funds"] = None
        else:
            def opt(o: FundsOption) -> dict:
                d = {
                    "amount_cents": o.amount_cents,
                    "within_guardrail": o.within_guardrail,
                    "reason": o.reason,
                }
                if o.date is not None:
                    d["date"] = o.date.isoformat()
                if o.num_drafts is not None:
                    d["num_drafts"] = o.num_drafts
                return d

            out["additional_funds"] = {
                "lump_sum": opt(self.additional_funds.lump_sum),
                "monthly_increment": opt(self.additional_funds.monthly_increment),
            }
        return out


def _eligible_shapes(rules: CreditorRules) -> list[str]:
    """Which shapes the creditor flags make eligible, in trial priority order.
    ``even_pays`` forces even payments outright. Otherwise, when ballooning is
    allowed it is tried first (the purest expression of front-loading — every
    early payment at its floor) with staircase as a fallback if no balloon is
    feasible; when it isn't allowed, staircase is the only option."""
    if rules.even_pays:
        return ["even"]
    if rules.is_ballooning_allowed:
        return ["balloon", "staircase"]
    return ["staircase"]


def find_best_schedule(
    client: Client,
    offer: Offer,
    rules: CreditorRules,
    extra_credits: tuple[tuple[date, int], ...] = (),
) -> tuple[str, list[ScheduleRow]] | None:
    """The core solver: the most front-loaded feasible schedule, or ``None``
    if no valid schedule exists at all. ``extra_credits`` lets Part 2 probe
    "what if this much extra cash landed on these dates" without duplicating
    any of this logic."""
    cadence = cadence_dates(client, offer)
    kmax = min(rules.max_payments, rules.max_terms, len(cadence))
    if kmax < 1:
        return None

    total = percent_of_cents(offer.settlement_pct, offer.current_balance_cents)
    if total <= 0:
        return None
    fee = percent_of_cents(rules.program_fee_pct, offer.original_balance_cents)

    # The timeline (committed ledger + cadence dates) is identical for every
    # candidate in this solve, so building it once both saves work and gives
    # every candidate's fee-score tuple the same length for a fair comparison.
    timeline = build_timeline(client, cadence, extra_credits)
    start_balance = client.current_balance_cents

    for shape in _eligible_shapes(rules):
        generate = SHAPE_GENERATORS[shape]
        best: tuple[tuple[int, ...], list[ScheduleRow]] | None = None
        for k in range(1, kmax + 1):
            for vector in generate(total, k, rules):
                if len(vector) != k or sum(vector) != total or any(p < 0 for p in vector):
                    continue
                if not is_valid_payment_vector(vector, rules):
                    continue
                outcome = simulate(vector, rules, timeline, start_balance, fee)
                if outcome is None:
                    continue
                rows, fee_score = outcome
                if best is None or fee_score > best[0]:
                    best = (fee_score, rows)
        if best is not None:
            return shape, best[1]
    return None


def evaluate_offer(client: Client, offer: Offer, rules: CreditorRules) -> Result:
    """Evaluate a single offer. See ASSIGNMENT.md for the full specification."""
    solved = find_best_schedule(client, offer, rules)
    if solved is not None:
        shape, rows = solved
        return Result(feasible=True, pay_shape_used=shape, schedule=rows)

    total = percent_of_cents(offer.settlement_pct, offer.current_balance_cents)
    fee = percent_of_cents(rules.program_fee_pct, offer.original_balance_cents)
    upper_bound = deficit_upper_bound(client, total, fee, rules)

    def solve_with(extra: tuple[tuple[date, int], ...]):
        return find_best_schedule(client, offer, rules, extra)

    cadence = cadence_dates(client, offer)
    lump_date = lump_sum_date(client, cadence)
    lump_amount = minimal_extra_cents(upper_bound, lambda amt: ((lump_date, amt),), solve_with)

    drafts = future_draft_dates(client)
    increment_amount = minimal_extra_cents(
        upper_bound, lambda amt: tuple((d, amt) for d in drafts), solve_with
    )

    lump_cap, increment_cap = guardrail_caps(offer, client, total)
    return Result(
        feasible=False,
        schedule=None,
        additional_funds=AdditionalFunds(
            lump_sum=FundsOption(
                amount_cents=lump_amount,
                within_guardrail=lump_amount <= lump_cap,
                reason=(
                    ""
                    if lump_amount <= lump_cap
                    else f"lump sum {lump_amount} exceeds 65% of offer total ({lump_cap})"
                ),
                date=lump_date,
            ),
            monthly_increment=FundsOption(
                amount_cents=increment_amount,
                within_guardrail=increment_amount <= increment_cap,
                reason=(
                    ""
                    if increment_amount <= increment_cap
                    else f"increment {increment_amount} exceeds cap ({increment_cap})"
                ),
                num_drafts=len(drafts),
            ),
        ),
    )
