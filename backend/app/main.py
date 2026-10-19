from typing import Annotated

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .agents.rag_chain import ask_docs
from .agents.sql_agent import ask_data
from .auth import Business, CurrentUser, WritableBusiness
from .config import settings
from .data_ops import read_csv, refresh_overdue, run_import
from .db import app_query, run_safe_sql

app = FastAPI(title="AI Finance Copilot for Malaysian SMEs")
MAX_CSV_BYTES = 2_000_000


class ChatRequest(BaseModel):
    question: str


class BusinessIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    industry: str = Field(default="Other", max_length=50)


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
