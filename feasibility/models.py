"""Data models, JSON loaders, and date helpers for the feasibility take-home.

Everything money-related is in integer cents. Dates are ``datetime.date``.
You are free to use, ignore, or rewrite anything in this file. The only hard
requirements are the input/output shapes described in ASSIGNMENT.md.
"""

from __future__ import annotations

import json
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal

EntryType = Literal["credit", "debit"]


@dataclass(frozen=True)
class LedgerEntry:
    date: date
    amount_cents: int
    type: EntryType


@dataclass
class Client:
    draft_amount_cents: int
    draft_day: int
    first_draft_date: date
    last_draft_date: date
    as_of_date: date
    current_balance_cents: int
    ledger: list[LedgerEntry] = field(default_factory=list)


@dataclass
class Offer:
    creditor: str
    current_balance_cents: int
    original_balance_cents: int
    settlement_pct: float
    # Optional. When omitted, default to the end of the month of first_draft_date
    # (see default_first_payment_date()).
    first_payment_date: date | None = None


@dataclass
class CreditorRules:
    max_terms: int
    max_payments: int
    min_payment_cents: int
    max_token_pays: int
    min_payment_tiers: list[tuple[int, int]]  # [(from_payment_1based, min_cents), ...]
    # Two independent creditor flags (both default False):
    #   even_pays            -> every creditor payment must be equal (ballooning is irrelevant).
    #   is_ballooning_allowed -> the final payment may absorb the remainder (a "balloon").
    # When NOT ballooning (and not even), the payment structure is bounded to at most
    # `max_segments` distinct payment levels so it can't fan out into an arbitrarily
    # complex staircase. The actual shape is whatever the objective produces
    # (maximize fee collected upfront / keep creditor payments low early).
    even_pays: bool
    is_ballooning_allowed: bool
    max_segments: int
    bank_fee_cents: int
    program_fee_pct: float


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def end_of_month(d: date) -> date:
    return date(d.year, d.month, monthrange(d.year, d.month)[1])


def is_end_of_month(d: date) -> bool:
    return d.day == monthrange(d.year, d.month)[1]


def add_months(d: date, n: int) -> date:
    """Shift a date by ``n`` whole months, clamping the day to month length."""
    total = (d.year * 12 + (d.month - 1)) + n
    year, month = divmod(total, 12)
    month += 1
    day = min(d.day, monthrange(year, month)[1])
    return date(year, month, day)


def default_first_payment_date(client: Client) -> date:
    """Default creditor first-payment date: end of the first draft's month (EOM)."""
    return end_of_month(client.first_draft_date)


def monthly_payment_dates(start: date, count: int) -> list[date]:
    """Generate ``count`` monthly dates from ``start``.

    If ``start`` is the last day of its month, every generated date is the last
    day of its month (true EOM cadence). Otherwise the day-of-month is preserved
    (clamped to month length).
    """
    if count <= 0:
        return []
    eom = is_end_of_month(start)
    out: list[date] = []
    for i in range(count):
        d = add_months(start, i)
        out.append(end_of_month(d) if eom else d)
    return out


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

class InvalidCaseError(ValueError):
    """A case file is missing, unreadable, or has a malformed/missing field.

    Carries the offending ``path`` and a human-readable ``reason`` so a caller
    (the CLI, or a future service layer) can report a structured error
    instead of a raw ``KeyError``/``ValueError``/``JSONDecodeError`` traceback.
    """

    def __init__(self, path: str | Path, reason: str):
        self.path = str(path)
        self.reason = reason
        super().__init__(f"{self.path}: {reason}")


def _read_json(path: str | Path) -> dict:
    p = Path(path)
    try:
        text = p.read_text()
    except FileNotFoundError as e:
        raise InvalidCaseError(path, "file not found") from e
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise InvalidCaseError(path, f"invalid JSON ({e})") from e


def _require(raw: dict, field: str, path: str | Path):
    if field not in raw:
        raise InvalidCaseError(path, f"missing required field {field!r}")
    return raw[field]


def _require_int(raw: dict, field: str, path: str | Path) -> int:
    try:
        return int(_require(raw, field, path))
    except (TypeError, ValueError) as e:
        raise InvalidCaseError(path, f"field {field!r} must be an integer") from e


def _require_float(raw: dict, field: str, path: str | Path) -> float:
    try:
        return float(_require(raw, field, path))
    except (TypeError, ValueError) as e:
        raise InvalidCaseError(path, f"field {field!r} must be a number") from e


def _require_date(raw: dict, field: str, path: str | Path) -> date:
    value = _require(raw, field, path)
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as e:
        raise InvalidCaseError(path, f"field {field!r} is not a valid ISO date") from e


def _d(s: str) -> date:
    return date.fromisoformat(s)


def load_client(path: str | Path) -> Client:
    raw = _read_json(path)
    draft_amount_cents = _require_int(raw, "draft_amount_cents", path)
    draft_day = _require_int(raw, "draft_day", path)
    first_draft_date = _require_date(raw, "first_draft_date", path)
    last_draft_date = _require_date(raw, "last_draft_date", path)
    as_of_date = _require_date(raw, "as_of_date", path)
    current_balance_cents = _require_int(raw, "current_balance_cents", path)
    try:
        ledger = [
            LedgerEntry(_d(e["date"]), int(e["amount_cents"]), e["type"])
            for e in raw.get("ledger", [])
        ]
    except (KeyError, TypeError, ValueError) as e:
        raise InvalidCaseError(path, f"malformed ledger entry ({e})") from e
    return Client(
        draft_amount_cents=draft_amount_cents,
        draft_day=draft_day,
        first_draft_date=first_draft_date,
        last_draft_date=last_draft_date,
        as_of_date=as_of_date,
        current_balance_cents=current_balance_cents,
        ledger=ledger,
    )


def load_offer(path: str | Path) -> Offer:
    raw = _read_json(path)
    fpd = raw.get("first_payment_date")
    try:
        first_payment_date = date.fromisoformat(fpd) if fpd else None
    except ValueError as e:
        raise InvalidCaseError(path, f"field 'first_payment_date' is not a valid ISO date ({e})") from e
    return Offer(
        creditor=str(_require(raw, "creditor", path)),
        current_balance_cents=_require_int(raw, "current_balance_cents", path),
        original_balance_cents=_require_int(raw, "original_balance_cents", path),
        settlement_pct=_require_float(raw, "settlement_pct", path),
        first_payment_date=first_payment_date,
    )


def load_creditor_rules(path: str | Path) -> CreditorRules:
    raw = _read_json(path)
    try:
        tiers = [(int(a), int(b)) for a, b in raw.get("min_payment_tiers", [])]
    except (TypeError, ValueError) as e:
        raise InvalidCaseError(path, f"malformed min_payment_tiers ({e})") from e
    return CreditorRules(
        max_terms=_require_int(raw, "max_terms", path),
        max_payments=_require_int(raw, "max_payments", path),
        min_payment_cents=_require_int(raw, "min_payment_cents", path),
        max_token_pays=_require_int(raw, "max_token_pays", path),
        min_payment_tiers=tiers,
        even_pays=bool(raw.get("even_pays", False)),
        is_ballooning_allowed=bool(raw.get("is_ballooning_allowed", False)),
        max_segments=int(raw.get("max_segments", 4)),
        bank_fee_cents=_require_int(raw, "bank_fee_cents", path),
        program_fee_pct=_require_float(raw, "program_fee_pct", path),
    )


def load_case(case_dir: str | Path) -> tuple[Client, Offer, CreditorRules]:
    p = Path(case_dir)
    return (
        load_client(p / "client.json"),
        load_offer(p / "offer.json"),
        load_creditor_rules(p / "creditor_rules.json"),
    )


def offer_total_cents(offer: Offer) -> int:
    return round(offer.settlement_pct * offer.current_balance_cents)


def program_fee_cents(offer: Offer, rules: CreditorRules) -> int:
    return round(rules.program_fee_pct * offer.original_balance_cents)
