import json
import sys
import time
from pathlib import Path

sys.path.insert(0, "backend")
from app.agents.invoice_extractor import extract_invoice  # noqa: E402
from app.data_ops import parse_date, parse_money  # noqa: E402

FIELDS = ["invoice_no", "counterparty", "issue_date", "due_date", "total", "tax"]


def same(field, got, want):
    if got in (None, ""):
        return False
    try:
        if field in ("issue_date", "due_date"):
            return parse_date(str(got), field).isoformat() == want
        if field in ("total", "tax"):
            return parse_money(str(got), field, allow_zero=True) == parse_money(
                want, field, allow_zero=True
            )
    except ValueError:
        return False
    return str(got).strip().lower() == want.strip().lower()


truth = json.loads(Path("eval/pdf_truth.json").read_text())
correct = {f: 0 for f in FIELDS}
for t in truth:
    data = Path("data/sample_invoices", t["file"]).read_bytes()
    got = extract_invoice(data, t["kind"], "Kopitiam Ah Seng")
    result = {f: same(f, got.get(f), t[f]) for f in FIELDS}
    for f in FIELDS:
        correct[f] += result[f]
    print(t["file"], result)
    time.sleep(20)  # stay under Groq's tokens-per-minute limit

for f in FIELDS:
    print(f"{f}: {correct[f]}/{len(truth)}")
print(f"Field-level accuracy: {sum(correct.values()) / (len(truth) * len(FIELDS)):.0%}")
