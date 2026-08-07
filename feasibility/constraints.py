"""Per-position payment floors and the vector-level hard constraints
(non-decreasing, floors, token-pay cap). Exact-sum is enforced by construction
in the shape generators, so it is not re-checked here.
"""

from __future__ import annotations

from feasibility.models import CreditorRules


def position_floor(position_1based: int, rules: CreditorRules) -> int:
    """The minimum a payment at this 1-based position may be.

    Base minimum, raised by any tier whose ``from_payment`` has been reached.
    Tiers only ever raise the floor and never expire, so floors are
    non-decreasing in position.
    """
    floor = rules.min_payment_cents
    for from_payment, min_cents in rules.min_payment_tiers:
        if position_1based >= from_payment:
            floor = max(floor, min_cents)
    return floor


def block_floor(start_1based: int, end_1based: int, rules: CreditorRules) -> int:
    """The floor a single constant-level block spanning [start, end] must clear."""
    return max(position_floor(p, rules) for p in range(start_1based, end_1based + 1))


def is_valid_payment_vector(payments: list[int], rules: CreditorRules) -> bool:
    """Constraints 3 & 4: non-decreasing, per-position floors, token-pay count cap."""
    for i in range(1, len(payments)):
        if payments[i] < payments[i - 1]:
            return False
    for i, amount in enumerate(payments):
        if amount < position_floor(i + 1, rules):
            return False
    token_pays = sum(1 for amount in payments if amount == rules.min_payment_cents)
    if token_pays > rules.max_token_pays:
        return False
    return True
