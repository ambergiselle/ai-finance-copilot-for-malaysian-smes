from datetime import date
from typing import Annotated, Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .agents.invoice_extractor import extract_invoice
from .agents.rag_chain import ask_docs
from .agents.sql_agent import ask_data
from .auth import Business, CurrentUser, WritableBusiness
from .config import settings
from .data_ops import (
    delete_all_data,
    mark_paid,
    read_csv,
    refresh_overdue,
    rows_to_df,
    run_import,
)
from .db import app_query, run_safe_sql

app = FastAPI(title="AI Finance Copilot for Malaysian SMEs")
MAX_CSV_BYTES = 2_000_000
MAX_PDF_BYTES = 5_000_000


class ChatRequest(BaseModel):
    question: str


class BusinessIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    industry: str = Field(default="Other", max_length=50)


class ReviewedRows(BaseModel):
    kind: Literal["sales", "bill"]
    rows: list[dict]


class PaidIn(BaseModel):
    paid_date: date


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/me")
def me(biz: Business):
    return {**biz, "read_only": biz["name"] == settings.demo_business_name}


@app.post("/business")
def create_business(body: BusinessIn, user: CurrentUser):
    name = body.name.strip()
    if name.lower() == settings.demo_business_name.lower():
        raise HTTPException(
            status_code=400, detail="Please choose a different business name."
        )
    if app_query("select id from businesses where owner_id = %s", (user.id,)):
        raise HTTPException(status_code=409, detail="Your business is already set up.")
    return app_query(
        "insert into businesses (owner_id, name, industry) values (%s, %s, %s) "
        "returning id, name, industry",
        (user.id, name, body.industry),
    )[0]


@app.get("/invoices")
def invoices(biz: Business, status: str = "overdue"):
    cols, rows = run_safe_sql(
        "select invoice_no, issue_date, due_date, total, status from invoices "
        "where status = %s order by due_date limit 50",
        biz["id"],
        (status,),
    )
    return [dict(zip(cols, r)) for r in rows]


@app.post("/chat/sql")
def chat_sql(req: ChatRequest, biz: Business):
    refresh_overdue(biz["id"])
    return ask_data(req.question, biz["id"])


@app.post("/chat/docs")
def chat_docs(req: ChatRequest, biz: Business):
    return ask_docs(req.question)


@app.post("/import/csv/{kind}")
async def import_csv(
    kind: str, file: Annotated[UploadFile, File()], biz: WritableBusiness
):
    if kind not in ("invoices", "expenses"):
        raise HTTPException(status_code=404, detail="Unknown import type.")
    data = await file.read()
    if len(data) > MAX_CSV_BYTES:
        raise HTTPException(status_code=413, detail="The file is larger than 2 MB.")
    try:
        return run_import(kind, read_csv(data), biz["id"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.post("/import/rows")
def import_rows(body: ReviewedRows, biz: WritableBusiness):
    kind = "invoices" if body.kind == "sales" else "expenses"
    try:
        return run_import(kind, rows_to_df(body.rows), biz["id"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.post("/extract/invoice")
async def extract(
    kind: Annotated[Literal["sales", "bill"], Form()],
    file: Annotated[UploadFile, File()],
    biz: Business,
):
    data = await file.read()
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="The PDF is larger than 5 MB.")
    try:
        return {"file": file.filename, **extract_invoice(data, kind, biz["name"])}
    except Exception:  # noqa: BLE001 - unreadable PDF or model failure: ask for manual entry
        return {
            "file": file.filename,
            "error": "Couldn't read this invoice. Please enter it with Quick add instead.",
        }


@app.post("/invoices/{invoice_no}/paid")
def invoice_paid(invoice_no: str, body: PaidIn, biz: WritableBusiness):
    if not mark_paid(biz["id"], invoice_no, body.paid_date):
        raise HTTPException(
            status_code=404, detail="No unpaid invoice with that number."
        )
    return {"status": "paid"}


@app.delete("/data")
def delete_data(biz: WritableBusiness):
    delete_all_data(biz["id"])
    return {"status": "deleted"}


@app.get("/records/invoices")
def list_invoices(biz: Business):
    refresh_overdue(biz["id"])
    cols, rows = run_safe_sql(
        "select i.invoice_no, c.name as customer, i.issue_date, i.due_date, i.paid_date, "
        "i.total, i.status from invoices i join customers c on c.id = i.customer_id "
        "order by i.issue_date desc limit 500",
        biz["id"],
        (),
    )
    return [dict(zip(cols, r)) for r in rows]


@app.get("/records/expenses")
def list_expenses(biz: Business):
    cols, rows = run_safe_sql(
        "select txn_date as date, category, description, amount from transactions "
        "where type = 'expense' order by txn_date desc limit 500",
        biz["id"],
        (),
    )
    return [dict(zip(cols, r)) for r in rows]
