import time
from datetime import date

import sqlglot
from pydantic import BaseModel, Field
from sqlglot import exp

from ..db import run_safe_sql
from ..llm import make_llm

ALLOWED_TABLES = {"businesses", "customers", "invoices", "transactions"}


SYSTEM_PROMPT = """You write PostgreSQL queries for a Malaysian small business finance app.
Assume today is {today}. Amounts are in Malaysian Ringgit (RM).

Tables:
- businesses(id, name, industry)
- customers(id, business_id, name, email)
- invoices(id, business_id, customer_id, invoice_no, issue_date, due_date, paid_date,
  subtotal, tax, total, status)
  status is one of: issued, paid, overdue, cancelled. paid_date is null when unpaid.
  Days late = paid_date - due_date.
- transactions(id, business_id, txn_date, type, category, description, amount, invoice_id)
  type is income or expense. Expense categories: rent, salaries, supplies, utilities,
  marketing, maintenance, other. Income category: sales.

Rules:
- Return exactly one SELECT statement. Never modify data.
- Rows are already restricted to the current business; do not filter by business_id.
- An invoice was paid late when paid_date - due_date > 7.
  For "who pays late most often", rank customers by the share of their paid invoices
  that were late, and also show the late count.
- Use clear column aliases. For trends, group by date_trunc('month', ...) and alias it month.
- If the user asks to add, change or delete data, do not write SQL. Fill in refusal instead.
- The invoices table only holds money customers owe the user. The app does not track
  money the user owes suppliers. If asked who the user owes, about unpaid bills, or about
  payables, do not write SQL. Fill in refusal instead.

Examples:
Q: How much revenue did I make last month?
SQL: select sum(amount) as revenue from transactions where type = 'income'
     and txn_date >= date '2026-09-01' and txn_date < date '2026-10-01'
Q: Which customers owe me money?
SQL: select c.name, sum(i.total) as amount_owed from invoices i
     join customers c on c.id = i.customer_id where i.status = 'overdue'
     group by c.name order by amount_owed desc
Q: Which customers paid late most often?
SQL: select c.name,
       count(*) filter (where i.paid_date - i.due_date > 7) as late_invoices,
       count(*) as paid_invoices,
       round(100.0 * count(*) filter (where i.paid_date - i.due_date > 7) / count(*), 1) as late_pct
     from invoices i join customers c on c.id = i.customer_id
     where i.paid_date is not null and i.paid_date >= date '2026-01-01'
     group by c.name
     having count(*) filter (where i.paid_date - i.due_date > 7) > 0
     order by late_pct desc, late_invoices desc
"""

ANSWER_PROMPT = (
    "You explain query results to a small business owner in 2-4 short sentences. "
    "Use RM for money. Do not mention SQL. If there are no rows, say so plainly and suggest adding data in the My data tab. "
    "If the question asks to add, change or delete data, reply in one sentence that you "
    "can only read data, and do not list any rows. Never offer to change data. "
    "You may only see a preview of the rows: use the total row count you are given."
)

OUT_OF_SCOPE = (
    "I can only answer questions about your own sales, invoices, customers "
    "and expenses, and I can't add, change or delete data."
)


class SQLQuery(BaseModel):
    sql: str | None = Field(
        default=None, description="A single PostgreSQL SELECT statement"
    )
    refusal: str | None = Field(
        default=None,
        description="Fill this instead of sql in two cases: (1) the user asks to add, change or "
        "delete data: say you can only read their data; (2) the user asks what they owe "
        "suppliers: say the app only tracks money customers owe them, and supplier bills are "
        "saved as expenses. One or two sentences. Leave sql empty.",
    )


llm = make_llm()
sql_llm = llm.with_structured_output(SQLQuery)


def validate_sql(sql: str) -> str:
    parsed = sqlglot.parse(sql, read="postgres")
    if len(parsed) != 1 or not isinstance(parsed[0], exp.Select):
        raise ValueError("Only one SELECT statement is allowed.")
    stmt = parsed[0]
    cte_names = {cte.alias for cte in stmt.find_all(exp.CTE)}
    tables = {t.name for t in stmt.find_all(exp.Table)} - cte_names
    if not tables <= ALLOWED_TABLES:
        raise ValueError(f"Tables not allowed: {sorted(tables - ALLOWED_TABLES)}")
    if not stmt.args.get("limit"):
        stmt = stmt.limit(200)
    return stmt.sql(dialect="postgres")


def ask_data(question: str, business_id, max_retries: int = 2) -> dict:
    start = time.time()
    messages = [
        ("system", SYSTEM_PROMPT.format(today=date.today().isoformat())),
        ("human", question),
    ]
    sql, error = None, None
    for attempt in range(max_retries + 1):
        sql = None
        try:
            result = sql_llm.invoke(messages)
            if result.refusal and not result.sql:
                return {
                    "answer": result.refusal,
                    "sql": None,
                    "columns": [],
                    "rows": [],
                    "retries": attempt,
                    "latency_s": round(time.time() - start, 2),
                }
            sql = result.sql
            safe_sql = validate_sql(sql)
            cols, rows = run_safe_sql(safe_sql, business_id)
            break
        except Exception as e:  # noqa: BLE001 - any failure (LLM, sqlglot, DB) feeds the retry loop
            error = str(e)
            if "tool_use_failed" in error:  # model replied in plain text instead of SQL
                return {
                    "answer": OUT_OF_SCOPE,
                    "sql": None,
                    "columns": [],
                    "rows": [],
                    "retries": attempt,
                    "latency_s": round(time.time() - start, 2),
                }
            if sql:  # only feed query errors back, not network or rate-limit errors
                messages += [
                    ("ai", sql),
                    (
                        "human",
                        f"That query failed with this error:\n{error}\nReturn a corrected query.",
                    ),
                ]
    else:
        return {
            "answer": "Sorry, I couldn't answer that one. Try rephrasing.",
            "sql": sql,
            "error": error,
            "retries": max_retries,
            "columns": [],
            "rows": [],
            "latency_s": round(time.time() - start, 2),
        }

    preview = [dict(zip(cols, r)) for r in rows[:20]]  # 20 rows keeps tokens down
    answer = llm.invoke(
        [
            ("system", ANSWER_PROMPT),
            (
                "human",
                (
                    f"Question: {question}\n"
                    f"Total rows: {len(rows)}\n"
                    f"First {len(preview)} rows: {preview}"
                ),
            ),
        ]
    ).text
    return {
        "answer": answer,
        "sql": safe_sql,
        "columns": cols,
        "rows": [list(r) for r in rows],
        "retries": attempt,
        "latency_s": round(time.time() - start, 2),
    }
