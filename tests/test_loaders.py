"""Loader hardening: missing field, bad JSON, missing file, bad date all
surface as a structured InvalidCaseError instead of a raw traceback.
"""

from __future__ import annotations

import json

import pytest

from feasibility.models import InvalidCaseError, load_client, load_creditor_rules, load_offer


def test_missing_file_raises_invalid_case_error(tmp_path):
    with pytest.raises(InvalidCaseError, match="file not found"):
        load_client(tmp_path / "does_not_exist.json")


def test_malformed_json_raises_invalid_case_error(tmp_path):
    p = tmp_path / "client.json"
    p.write_text("{not valid json")
    with pytest.raises(InvalidCaseError, match="invalid JSON"):
        load_client(p)


def test_missing_required_field_raises_invalid_case_error(tmp_path):
    p = tmp_path / "offer.json"
    p.write_text(json.dumps({"creditor": "X", "current_balance_cents": 100}))
    with pytest.raises(InvalidCaseError, match="original_balance_cents"):
        load_offer(p)


def test_bad_date_raises_invalid_case_error(tmp_path):
    p = tmp_path / "client.json"
    p.write_text(
        json.dumps(
            {
                "draft_amount_cents": 100,
                "draft_day": 1,
                "first_draft_date": "not-a-date",
                "last_draft_date": "2026-01-01",
                "as_of_date": "2025-12-31",
                "current_balance_cents": 0,
            }
        )
    )
    with pytest.raises(InvalidCaseError, match="first_draft_date"):
        load_client(p)


def test_bad_first_payment_date_on_offer_raises(tmp_path):
    p = tmp_path / "offer.json"
    p.write_text(
        json.dumps(
            {
                "creditor": "X",
                "current_balance_cents": 100,
                "original_balance_cents": 100,
                "settlement_pct": 0.5,
                "first_payment_date": "not-a-date",
            }
        )
    )
    with pytest.raises(InvalidCaseError, match="first_payment_date"):
        load_offer(p)


def test_non_integer_field_raises_invalid_case_error(tmp_path):
    p = tmp_path / "rules.json"
    p.write_text(
        json.dumps(
            {
                "max_terms": "twelve",
                "max_payments": 12,
                "min_payment_cents": 2500,
                "max_token_pays": 6,
                "bank_fee_cents": 500,
                "program_fee_pct": 0.2,
            }
        )
    )
    with pytest.raises(InvalidCaseError, match="max_terms"):
        load_creditor_rules(p)
