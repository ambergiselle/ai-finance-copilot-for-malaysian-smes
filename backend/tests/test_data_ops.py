from datetime import date

import pandas as pd
import pytest

from app.data_ops import (
    invoice_status,
    normalise,
    validate_expenses,
    validate_invoices,
)

GOOD = {
    "invoice_no": "INV-1",
    "customer_name": "Kedai Ali",
    "issue_date": "2026-09-01",
    "due_date": "01/10/2026",
    "paid_date": "",
    "total": "RM1,060.00",
}


def make(rows):
    return normalise(pd.DataFrame(rows))


def test_valid_invoice_parses_dates_and_money():
    rows, errors = validate_invoices(make([GOOD]))
    assert errors == []
    assert rows[0]["due_date"] == date(2026, 10, 1)
    assert str(rows[0]["total"]) == "1060.00"


def test_bad_date_is_reported_with_row_number():
    _, errors = validate_invoices(make([{**GOOD, "issue_date": "31/02/2026"}]))
    assert errors[0].startswith("Row 2")


def test_duplicate_invoice_numbers_rejected():
    _, errors = validate_invoices(make([GOOD, GOOD]))
    assert "more than once" in errors[0]


def test_missing_column_raises():
    with pytest.raises(ValueError):
        validate_invoices(make([{"invoice_no": "INV-1"}]))


def test_unknown_expense_category_rejected():
    _, errors = validate_expenses(
        make(
            [
                {
                    "date": "2026-09-01",
                    "category": "holiday",
                    "description": "",
                    "amount": "100",
                }
            ]
        )
    )
    assert "category" in errors[0]


def test_status_from_dates():
    today = date(2026, 10, 19)
    assert invoice_status(date(2026, 10, 1), None, today) == "overdue"
    assert invoice_status(date(2026, 11, 1), None, today) == "issued"
    assert invoice_status(date(2026, 10, 1), date(2026, 9, 30), today) == "paid"
