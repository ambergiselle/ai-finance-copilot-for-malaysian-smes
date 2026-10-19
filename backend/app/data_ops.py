"""Trusted write operations: parse, validate and save a business's own data."""

import io
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import pandas as pd
import psycopg

from .config import settings

MAX_ROWS = 2000
INVOICE_COLUMNS = [
    "invoice_no",
    "customer_name",
    "issue_date",
    "due_date",
    "paid_date",
    "total",
]
EXPENSE_COLUMNS = ["date", "category", "description", "amount"]
EXPENSE_CATEGORIES = {
    "rent",
    "salaries",
    "supplies",
    "utilities",
    "marketing",
    "maintenance",
    "other",
}
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y")


def blank(value: str) -> bool:
    return value.strip().lower() in ("", "none", "nan", "nat")


def normalise(df: pd.DataFrame) -> pd.DataFrame:
    df = df.fillna("").astype(str)
    df.columns = [str(c).strip().lower() for c in df.columns]
    if df.empty:
        raise ValueError("The file has no rows.")
    if len(df) > MAX_ROWS:
        raise ValueError(
            f"The file has {len(df)} rows. The limit is {MAX_ROWS} per upload."
        )
    return df


def read_csv(data: bytes) -> pd.DataFrame:
    df = pd.read_csv(
        io.BytesIO(data), dtype=str, keep_default_na=False, encoding="utf-8-sig"
    )
    return normalise(df)


def rows_to_df(rows: list[dict]) -> pd.DataFrame:
    return normalise(pd.DataFrame(rows))


def parse_date(value: str, field: str, required: bool = True) -> date | None:
    if blank(value):
        if required:
            raise ValueError(f"{field} is required")
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(
        f"{field} '{value}' is not a valid date (use YYYY-MM-DD or DD/MM/YYYY)"
    )


def parse_money(value: str, field: str, allow_zero: bool = False) -> Decimal:
    if blank(value):
        raise ValueError(f"{field} is required")
    try:
        amount = Decimal(value.replace("RM", "").replace(",", "").strip())
    except InvalidOperation:
        raise ValueError(f"{field} '{value}' is not a number") from None
    if not amount.is_finite():
        raise ValueError(f"{field} '{value}' is not a number")
    amount = amount.quantize(Decimal("0.01"))
    if amount < 0 or (amount == 0 and not allow_zero):
        raise ValueError(f"{field} must be more than 0")
    return amount


def invoice_status(due: date, paid: date | None, today: date | None = None) -> str:
    if paid:
        return "paid"
    return "overdue" if due < (today or date.today()) else "issued"


def validate_invoices(df: pd.DataFrame) -> tuple[list[dict], list[str]]:
    missing = [c for c in INVOICE_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {', '.join(missing)}")
    has_tax = "tax" in df.columns
    rows, errors, seen = [], [], set()
    for line, r in enumerate(df.to_dict("records"), start=2):  # row 1 is the header
        try:
            invoice_no, customer = r["invoice_no"].strip(), r["customer_name"].strip()
            if blank(invoice_no) or blank(customer):
                raise ValueError("invoice_no and customer_name are required")
            if invoice_no in seen:
                raise ValueError(
                    f"invoice_no {invoice_no} appears more than once in this file"
                )
            issue = parse_date(r["issue_date"], "issue_date")
            due = parse_date(r["due_date"], "due_date")
            paid = parse_date(r["paid_date"], "paid_date", required=False)
            total = parse_money(r["total"], "total")
            tax = Decimal("0.00")
            if has_tax and not blank(r["tax"]):
                tax = parse_money(r["tax"], "tax", allow_zero=True)
            if due < issue:
                raise ValueError("due_date is before issue_date")
            if paid and paid < issue:
                raise ValueError("paid_date is before issue_date")
            if tax > total:
                raise ValueError("tax is larger than total")
        except ValueError as e:
            errors.append(f"Row {line}: {e}")
            continue
        seen.add(invoice_no)
        rows.append(
            {
                "invoice_no": invoice_no,
                "customer_name": customer,
                "issue_date": issue,
                "due_date": due,
                "paid_date": paid,
                "subtotal": total - tax,
                "tax": tax,
                "total": total,
                "status": invoice_status(due, paid),
            }
        )
    return rows, errors


def validate_expenses(df: pd.DataFrame) -> tuple[list[dict], list[str]]:
    missing = [c for c in EXPENSE_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {', '.join(missing)}")
    rows, errors = [], []
    for line, r in enumerate(df.to_dict("records"), start=2):
        try:
            when = parse_date(r["date"], "date")
            category = (
                "other" if blank(r["category"]) else r["category"].strip().lower()
            )
            if category not in EXPENSE_CATEGORIES:
                raise ValueError(
                    f"category '{r['category']}' must be one of: "
                    f"{', '.join(sorted(EXPENSE_CATEGORIES))}"
                )
            amount = parse_money(r["amount"], "amount")
        except ValueError as e:
            errors.append(f"Row {line}: {e}")
            continue
        description = "" if blank(r["description"]) else r["description"].strip()[:200]
        rows.append(
            {
                "date": when,
                "category": category,
                "description": description,
                "amount": amount,
            }
        )
    return rows, errors


def import_invoices(business_id, rows: list[dict]) -> dict:
    imported = skipped = 0
    with psycopg.connect(settings.database_url) as conn:
        customers = {
            name.lower(): cid
            for cid, name in conn.execute(
                "select id, name from customers where business_id = %s", (business_id,)
            )
        }
        existing = {
            no
            for (no,) in conn.execute(
                "select invoice_no from invoices where business_id = %s", (business_id,)
            )
        }
        for r in rows:
            if r["invoice_no"] in existing:
                skipped += 1
                continue
            key = r["customer_name"].lower()
            if key not in customers:
                customers[key] = conn.execute(
                    "insert into customers (business_id, name) values (%s, %s) returning id",
                    (business_id, r["customer_name"]),
                ).fetchone()[0]
            invoice_id = conn.execute(
                """insert into invoices (business_id, customer_id, invoice_no, issue_date, due_date,
                   paid_date, subtotal, tax, total, status)
                   values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning id""",
                (
                    business_id,
                    customers[key],
                    r["invoice_no"],
                    r["issue_date"],
                    r["due_date"],
                    r["paid_date"],
                    r["subtotal"],
                    r["tax"],
                    r["total"],
                    r["status"],
                ),
            ).fetchone()[0]
            if r["paid_date"]:
                conn.execute(
                    """insert into transactions (business_id, txn_date, type, category, description,
                       amount, invoice_id) values (%s, %s, 'income', 'sales', %s, %s, %s)""",
                    (
                        business_id,
                        r["paid_date"],
                        f"Payment for {r['invoice_no']}",
                        r["total"],
                        invoice_id,
                    ),
                )
            existing.add(r["invoice_no"])
            imported += 1
    return {"imported": imported, "skipped_duplicates": skipped}


def import_expenses(business_id, rows: list[dict]) -> dict:
    with psycopg.connect(settings.database_url) as conn, conn.cursor() as cur:
        cur.executemany(
            """insert into transactions (business_id, txn_date, type, category, description, amount)
               values (%s, %s, 'expense', %s, %s, %s)""",
            [
                (business_id, r["date"], r["category"], r["description"], r["amount"])
                for r in rows
            ],
        )
    return {"imported": len(rows), "skipped_duplicates": 0}


def run_import(kind: str, df: pd.DataFrame, business_id) -> dict:
    """Validate every row first, and save only if all of them are valid."""
    if kind == "invoices":
        rows, errors = validate_invoices(df)
    else:
        rows, errors = validate_expenses(df)
    if errors:
        return {
            "imported": 0,
            "skipped_duplicates": 0,
            "errors": errors[:50],
            "error_count": len(errors),
        }
    if kind == "invoices":
        saved = import_invoices(business_id, rows)
    else:
        saved = import_expenses(business_id, rows)
    return {**saved, "errors": [], "error_count": 0}


def refresh_overdue(business_id) -> None:
    """Unpaid invoices past their due date become overdue."""
    with psycopg.connect(settings.database_url) as conn:
        conn.execute(
            """update invoices set status = 'overdue'
               where business_id = %s and status = 'issued' and paid_date is null
               and due_date < current_date""",
            (business_id,),
        )
