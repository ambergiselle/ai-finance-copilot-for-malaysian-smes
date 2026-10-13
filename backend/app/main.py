from fastapi import Depends, FastAPI
from pydantic import BaseModel

from .auth import current_business
from .db import run_safe_sql

app = FastAPI(title="AI Finance Copilot for Malaysian SMEs")


class ChatRequest(BaseModel):
    question: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/me")
def me(biz: dict = Depends(current_business)):
    return biz


@app.get("/invoices")
def invoices(status: str = "overdue", biz: dict = Depends(current_business)):
    cols, rows = run_safe_sql(
        "select invoice_no, issue_date, due_date, total, status from invoices "
        "where status = %s order by due_date limit 50",
        biz["id"],
        (status,),
    )
    return [dict(zip(cols, r)) for r in rows]


@app.post("/chat/sql")
def chat_sql(req: ChatRequest, biz: dict = Depends(current_business)):
    return {"answer": "coming on Day 3"}


@app.post("/chat/docs")
def chat_docs(req: ChatRequest, biz: dict = Depends(current_business)):
    return {"answer": "coming on Day 4"}
