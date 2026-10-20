"""Generate 10 sample invoice PDFs and their ground truth for testing extraction."""

import json
import random
from datetime import date, timedelta
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

random.seed(7)
OUT = Path("data/sample_invoices")
OUT.mkdir(parents=True, exist_ok=True)
BUSINESS = "Kopitiam Ah Seng"
CUSTOMERS = [
    "Pusat Tuisyen Bestari",
    "Restoran Selera Kita",
    "Syarikat Wong Holdings",
    "Kedai Runcit Aminah",
    "Bengkel Kereta Jaya",
]
SUPPLIERS = [
    "Syarikat Bekalan Maju Sdn Bhd",
    "Kedai Pembungkusan Lee",
    "Percetakan Cahaya Enterprise",
    "Gas Bersatu Trading",
    "Ladang Sayur Segar Sdn Bhd",
]

truth = []
for i in range(10):
    kind = "sales" if i < 5 else "bill"
    issue = date(2026, 9, 1) + timedelta(days=random.randint(0, 25))
    due = issue + timedelta(days=30)
    subtotal = round(random.uniform(100, 5000), 2)
    tax = round(subtotal * 0.06, 2)
    total = round(subtotal + tax, 2)
    number = (
        f"INV-2026-{i + 1:03d}"
        if kind == "sales"
        else f"BILL-{random.randint(1000, 9999)}"
    )
    seller = BUSINESS if kind == "sales" else SUPPLIERS[i - 5]
    buyer = CUSTOMERS[i] if kind == "sales" else BUSINESS
    lines = [
        seller,
        "No. 12, Jalan SS2/24, 47300 Petaling Jaya, Selangor",
        "",
        f"INVOICE NO: {number}",
        f"Date: {issue:%d/%m/%Y}",
        f"Due date: {due:%d/%m/%Y}",
        "",
        f"Bill to: {buyer}",
        "",
        "Description                              Amount (RM)",
        f"Goods and services                       {subtotal:,.2f}",
        f"SST 6%                                   {tax:,.2f}",
        f"TOTAL PAYABLE                            {total:,.2f}",
    ]
    path = OUT / f"{number}.pdf"
    pdf = canvas.Canvas(str(path), pagesize=A4)
    y = 800
    for line in lines:
        pdf.drawString(60, y, line)
        y -= 20
    pdf.save()
    truth.append(
        {
            "file": path.name,
            "kind": kind,
            "invoice_no": number,
            "counterparty": buyer if kind == "sales" else seller,
            "issue_date": issue.isoformat(),
            "due_date": due.isoformat(),
            "total": f"{total:.2f}",
            "tax": f"{tax:.2f}",
        }
    )

Path("eval").mkdir(exist_ok=True)
Path("eval/pdf_truth.json").write_text(json.dumps(truth, indent=2))
print(f"Wrote {len(truth)} PDFs to {OUT}")
