"""Money helpers: explicit round-half-up (away from zero on .5).

Python's builtin ``round`` uses round-half-to-even, which the assignment
explicitly forbids for the derived amounts (offer total, program fee,
guardrail caps). Everything routes through ``round_half_up`` instead.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal


def round_half_up(value: Decimal | float | int) -> int:
    """Round ``value`` to the nearest integer, ties away from zero."""
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def percent_of_cents(pct: float, amount_cents: int) -> int:
    """``round_half_up(pct * amount_cents)`` without float multiplication drift."""
    return round_half_up(Decimal(str(pct)) * Decimal(amount_cents))
