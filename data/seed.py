import os
import random
import uuid
from datetime import date, timedelta
from decimal import Decimal

import psycopg
from dotenv import load_dotenv
from faker import Faker

load_dotenv()
fake = Faker()
random.seed(42)

BUSINESSES = [
    ("Kopitiam Ah Seng", "F&B"),
    ("Kedai Hardware Lim", "Retail"),
    ("Bright Minds Tuition Centre", "Education"),
]
START, END = date(2025, 10, 1), date(2026, 9, 30)
PREFIX = ["Syarikat", "Kedai", "Perniagaan", "Restoran", "Bengkel", "Pusat"]
SUFFIX = ["Sdn Bhd", "Enterprise", "Trading", "Holdings"]
EXPENSES = {
    "rent": 4000,
    "salaries": 12000,
    "supplies": 3000,
    "utilities": 800,
    "marketing": 600,
    "maintenance": 400,
}


def rand_day(month_start):
    return month_start + timedelta(days=random.randint(0, 27))


def money(x):
    return Decimal(str(round(x, 2)))


with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
    for biz_name, industry in BUSINESSES:
        biz_id = uuid.uuid4()
        conn.execute(
            "insert into businesses (id, name, industry) values (%s, %s, %s)",
            (biz_id, biz_name, industry),
        )

        customers = []
        for i in range(30):
            cid = uuid.uuid4()
            name = f"{random.choice(PREFIX)} {fake.last_name()} {random.choice(SUFFIX)}"
            customers.append((cid, i < 3))
            conn.execute(
                "insert into customers (id, business_id, name, email) values (%s, %s, %s, %s)",
                (cid, biz_id, name, fake.company_email()),
            )

        inv_no, month, month_index = 1, START, 0
        while month <= END:
            festive = month.month in (12, 1, 2)  # yearend and Chinese New Year spike
            for _ in range(random.randint(15, 25) * (2 if festive else 1)):
                cid, late = random.choice(customers)
                issue = rand_day(month)
                due = issue + timedelta(days=30)
                subtotal = money(random.uniform(50, 3000))
                tax = money(float(subtotal) * 0.06)
                total = subtotal + tax
                paid = due + timedelta(
                    days=random.randint(20, 75) if late else random.randint(-10, 5)
                )
                if paid > END:
                    paid, status = None, ("overdue" if due < END else "issued")
                else:
                    status = "paid"
                inv_id, ref = uuid.uuid4(), f"INV-{inv_no:05d}"
                conn.execute(
                    """insert into invoices (id, business_id, customer_id, invoice_no, issue_date,
                       due_date, paid_date, subtotal, tax, total, status)
                       values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        inv_id,
                        biz_id,
                        cid,
                        ref,
                        issue,
                        due,
                        paid,
                        subtotal,
                        tax,
                        total,
                        status,
                    ),
                )
                if paid:
                    conn.execute(
                        """insert into transactions (business_id, txn_date, type, category,
                           description, amount, invoice_id)
                           values (%s, %s, 'income', 'sales', %s, %s, %s)""",
                        (biz_id, paid, f"Payment for {ref}", total, inv_id),
                    )
                inv_no += 1

            for category, base in EXPENSES.items():
                if category == "utilities":
                    base *= 1 + 0.05 * month_index  # rising cost pattern
                conn.execute(
                    """insert into transactions (business_id, txn_date, type, category, description, amount)
                       values (%s, %s, 'expense', %s, %s, %s)""",
                    (
                        biz_id,
                        rand_day(month),
                        category,
                        f"{category.title()} {month:%b %Y}",
                        money(base * random.uniform(0.9, 1.1)),
                    ),
                )

            month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
            month_index += 1

print("Seed complete")
