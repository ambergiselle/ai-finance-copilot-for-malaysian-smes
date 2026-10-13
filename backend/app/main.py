from fastapi import Depends, FastAPI
from pydantic import BaseModel

from .auth import current_business
from .db import run_safe_sql
from .agents.sql_agent import ask_data

app = FastAPI(title="AI Finance Copilot for Malaysian SMEs")


class ChatRequest(BaseModel):
    question: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/me")
def me(biz: dict = Depends(current_business)):  # noqa: B008
    return biz


@app.get("/invoices")
def invoices(status: str = "overdue", biz: dict = Depends(current_business)):  # noqa: B008
    cols, rows = run_safe_sql(
        "select invoice_no, issue_date, due_date, total, status from invoices "
        "where status = %s order by due_date limit 50",
        biz["id"],
        (status,),
    )
    return [dict(zip(cols, r)) for r in rows]


@app.post("/chat/sql")
def chat_sql(req: ChatRequest, biz: dict = Depends(current_business)):  # noqa: B008
    return ask_data(req.question, biz["id"])


@app.post("/chat/docs")
def chat_docs(req: ChatRequest, biz: dict = Depends(current_business)):  # noqa: B008
    return {"answer": "coming on Day 4"}
