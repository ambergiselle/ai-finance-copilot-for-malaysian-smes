import io

from pydantic import BaseModel, Field
from pypdf import PdfReader

from ..llm import make_llm

MAX_PAGES = 3
MAX_CHARS = 6000  # keeps each invoice to about 2,000 tokens

EXTRACT_PROMPT = """You extract fields from one Malaysian invoice.
The app user's business is {business}. This document is a {kind_label}.
- invoice_no: the invoice or bill number exactly as printed.
- counterparty: {counterparty_rule}
- issue_date and due_date: return as YYYY-MM-DD. Malaysian invoices usually print DD/MM/YYYY.
- total: the final amount payable including tax, as a plain number without RM or commas.
- tax: the total SST or other tax as a plain number. Use 0 if no tax is shown.
First decide whether the document is an invoice or bill. If it is not, set is_invoice to false and leave every other field empty.
If a field is not on the document, leave it empty. Never guess."""

KINDS = {
    "sales": (
        "sales invoice the user issued to a customer",
        "the customer the invoice is billed to, not {business}",
    ),
    "bill": (
        "bill the user received from a supplier",
        "the supplier who issued the bill, not {business}",
    ),
}


class ExtractedInvoice(BaseModel):
    is_invoice: bool = Field(
        default=False,
        description="True only if the document is an invoice, bill or receipt",
    )
    invoice_no: str | None = Field(default=None, description="Invoice or bill number")
    counterparty: str | None = Field(
        default=None, description="Customer or supplier name"
    )
    issue_date: str | None = Field(
        default=None, description="Invoice date as YYYY-MM-DD"
    )
    due_date: str | None = Field(
        default=None, description="Due date as YYYY-MM-DD, if shown"
    )
    total: str | None = Field(
        default=None, description="Total payable in RM, including tax"
    )
    tax: str | None = Field(default=None, description="Total tax in RM, 0 if none")


extract_llm = make_llm().with_structured_output(ExtractedInvoice)


def pdf_text(data: bytes) -> str:
    pages = list(PdfReader(io.BytesIO(data)).pages)[:MAX_PAGES]
    return "\n".join(p.extract_text() or "" for p in pages)[:MAX_CHARS]


def extract_invoice(data: bytes, kind: str, business: str) -> dict:
    text = pdf_text(data)
    if len(text.strip()) < 30:
        return {"error": "No text found. Scanned PDFs and photos aren't supported yet."}
    kind_label, rule = KINDS[kind]
    prompt = EXTRACT_PROMPT.format(
        business=business,
        kind_label=kind_label,
        counterparty_rule=rule.format(business=business),
    )
    result = extract_llm.invoke([("system", prompt), ("human", text)]).model_dump()
    if not result.pop("is_invoice") or not (result["invoice_no"] or result["total"]):
        return {"error": "This doesn't look like an invoice or bill."}
    return result
