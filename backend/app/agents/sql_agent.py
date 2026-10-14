import time

import psycopg
import sqlglot
from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field
from sqlglot import exp

from ..config import settings
from ..db import run_safe_sql

ALLOWED_TABLES = {"businesses", "customers", "invoices", "transactions"}
TODAY = "2026-09-30"  # must match END in data/seed.py

SYSTEM_PROMPT = f"""You write PostgreSQL queries for a Malaysian small business finance app.
Assume today is {TODAY}. Amounts are in Malaysian Ringgit (RM).

Tables:
- businesses(id, name, industry)
- customers(id, business_id, name, email)
- invoices(id, business_id, customer_id, invoice_no, issue_date, due_date, paid_date,
  subtotal, tax, total, status)
  status is one of: issued, paid, overdue, cancelled. paid_date is null when unpaid.
  Days late = paid_date - due_date.
- transactions(id, business_id, txn_date, type, category, description, amount, invoice_id)
  type is income or expense. Expense categories: rent, salaries, supplies, utilities,
  marketing, maintenance. Income category: sales.

Rules:
- Return exactly one SELECT statement. Never modify data.
- Rows are already restricted to the current business; do not filter by business_id.
- Use clear column aliases. For trends, group by date_trunc('month', ...) and alias it month.
- If the user asks to add, change or delete data, do not attempt it. Instead return:
  select 'I can only read your data. I cannot add, change or delete records.' as message

Examples:
Q: How much revenue did I make last month?
SQL: select sum(amount) as revenue from transactions where type = 'income'
     and txn_date >= date '2026-09-01' and txn_date < date '2026-10-01'
Q: Which customers owe me money?
SQL: select c.name, sum(i.total) as amount_owed from invoices i
     join customers c on c.id = i.customer_id where i.status = 'overdue'
     group by c.name order by amount_owed desc
"""

ANSWER_PROMPT = (
    "You explain query results to a small business owner in 2-4 short sentences. "
    "Use RM for money. Do not mention SQL. If there are no rows, say so plainly."
    "Never offer to add, change or delete data; you can only read it."
)


class SQLQuery(BaseModel):
    sql: str = Field(description="A single PostgreSQL SELECT statement")


llm = init_chat_model(settings.llm_model, model_provider="google_genai", temperature=0)
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
    messages = [("system", SYSTEM_PROMPT), ("human", question)]
    sql, error = None, None
    for attempt in range(max_retries + 1):
        try:
            result = sql_llm.invoke(messages)
            if result is None:
                raise ValueError("Model returned no SQL query.")
            sql = result.sql
            safe_sql = validate_sql(sql)
            cols, rows = run_safe_sql(safe_sql, business_id)
            break
        except (RuntimeError, TypeError, ValueError, psycopg.Error) as e:
            error = str(e)
            messages += [
                ("ai", sql or ""),
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

    preview = [dict(zip(cols, r)) for r in rows[:50]]
    answer = llm.invoke(
        [
            ("system", ANSWER_PROMPT),
            (
                "human",
                (
                    f"Question: {question}\n"
                    f"Total rows returned: {len(rows)} (showing first {len(preview)})\n"
                    f"Result rows: {preview}"
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
