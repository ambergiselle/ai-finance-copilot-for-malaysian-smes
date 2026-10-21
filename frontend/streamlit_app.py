import pandas as pd
import requests
import streamlit as st
from supabase import create_client

st.set_page_config(page_title="AI Finance Copilot", page_icon="📒", layout="wide")
API = st.secrets["API_URL"]
sb = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_ANON_KEY"])

EXPENSE_CATEGORIES = [
    "rent",
    "salaries",
    "supplies",
    "utilities",
    "marketing",
    "maintenance",
    "other",
]
INVOICE_TEMPLATE = pd.DataFrame(
    [
        {
            "invoice_no": "INV-0001",
            "customer_name": "Syarikat Contoh Sdn Bhd",
            "issue_date": "2026-09-01",
            "due_date": "2026-10-01",
            "paid_date": "2026-09-28",
            "total": "1060.00",
        },
        {
            "invoice_no": "INV-0002",
            "customer_name": "Kedai Runcit Ali",
            "issue_date": "2026-09-05",
            "due_date": "2026-10-05",
            "paid_date": "",
            "total": "250.50",
        },
    ]
).to_csv(index=False)
EXPENSE_TEMPLATE = pd.DataFrame(
    [
        {
            "date": "2026-09-01",
            "category": "rent",
            "description": "Shop rent September",
            "amount": "3500.00",
        },
        {
            "date": "2026-09-15",
            "category": "utilities",
            "description": "TNB electricity bill",
            "amount": "420.80",
        },
    ]
).to_csv(index=False)


def api(method, path, **kwargs):
    with st.spinner(
        "Working... (the first request may take up to a minute while the server wakes up)"
    ):
        return requests.request(
            method,
            f"{API}{path}",
            timeout=120,
            headers={"Authorization": f"Bearer {st.session_state.token}"},
            **kwargs,
        )


def check(r):
    """Return the response body, or show a clear message and stop."""
    if r.status_code == 401:
        st.session_state.clear()
        st.warning("Your session expired. Please refresh the page and log in again.")
        st.stop()
    if r.status_code in (400, 403, 404, 409, 413, 422):
        detail = r.json().get("detail")
        st.error(
            detail
            if isinstance(detail, str)
            else "Please check the values you entered."
        )
        st.stop()
    if not r.ok:
        st.error("Something went wrong on the server. Please try again in a minute.")
        st.caption(f"Status {r.status_code}")
        st.stop()
    return r.json()


def show_import_result(res):
    if res["errors"]:
        st.error(f"Nothing was saved. {res['error_count']} row(s) need fixing:")
        for e in res["errors"]:
            st.write("- " + e)
        return
    message = f"Saved {res['imported']} row(s)."
    if res.get("skipped_duplicates"):
        message += (
            f" Skipped {res['skipped_duplicates']} invoice(s) that were already saved."
        )
    load_records.clear()
    st.success(message)


def my_data_extras(biz):
    """Day 7: PDF extraction with review, quick add, mark as paid and delete all data."""
    st.divider()
    st.subheader("Extract from invoice PDFs")
    st.write(
        "Upload up to 5 PDF invoices at a time. Only PDFs made by software work for now, "
        "not scans or photos."
    )
    label = st.radio(
        "These PDFs are",
        ["Sales invoices I issued", "Bills from my suppliers"],
        horizontal=True,
    )
    pdf_kind = "sales" if label.startswith("Sales") else "bill"
    pdfs = st.file_uploader(
        "Invoice PDFs", type="pdf", accept_multiple_files=True, key="pdf_upload"
    )
    if pdfs and st.button("Extract", key="extract"):
        results = []
        for f in pdfs[:5]:
            r = api(
                "POST",
                "/extract/invoice",
                data={"kind": pdf_kind},
                files={"file": (f.name, f.getvalue(), "application/pdf")},
            )
            results.append(
                r.json()
                if r.ok
                else {"file": f.name, "error": f"Status {r.status_code}"}
            )
        st.session_state.extracted = {"kind": pdf_kind, "results": results}

    extracted = st.session_state.get("extracted")
    if extracted:
        for x in extracted["results"]:
            if x.get("error"):
                st.warning(f"{x['file']}: {x['error']}")
        ok = [x for x in extracted["results"] if not x.get("error")]
        if ok:
            if extracted["kind"] == "sales":
                review = pd.DataFrame(
                    [
                        {
                            "invoice_no": x["invoice_no"],
                            "customer_name": x["counterparty"],
                            "issue_date": x["issue_date"],
                            "due_date": x["due_date"],
                            "paid_date": "",
                            "total": x["total"],
                            "tax": x["tax"],
                        }
                        for x in ok
                    ]
                )
                config = {}
            else:
                review = pd.DataFrame(
                    [
                        {
                            "date": x["issue_date"],
                            "category": "supplies",
                            "description": f"Bill {x['invoice_no']} from {x['counterparty']}",
                            "amount": x["total"],
                        }
                        for x in ok
                    ]
                )
                config = {
                    "category": st.column_config.SelectboxColumn(
                        "category", options=EXPENSE_CATEGORIES
                    )
                }
            st.write(
                "**Check every row against the PDF and fix anything wrong before saving.** "
                "For sales invoices that are already paid, fill in paid_date."
            )
            edited = st.data_editor(
                review,
                column_config=config,
                num_rows="dynamic",
                use_container_width=True,
                key="review",
            )
            if st.button("Save", key="save_review"):
                res = check(
                    api(
                        "POST",
                        "/import/rows",
                        json={
                            "kind": extracted["kind"],
                            "rows": edited.fillna("").astype(str).to_dict("records"),
                        },
                    )
                )
                show_import_result(res)
                if not res["errors"]:
                    del st.session_state.extracted

    st.divider()
    st.subheader("Quick add")
    with st.expander("Add one invoice"), st.form("quick_add"):
        q_no = st.text_input("Invoice number")
        q_customer = st.text_input("Customer name")
        q_issue = st.date_input("Issue date")
        q_due = st.date_input("Due date")
        q_total = st.number_input("Total (RM)", min_value=0.0, step=10.0)
        q_is_paid = st.checkbox("Already paid")
        q_paid = st.date_input("Paid date (if paid)")
        if st.form_submit_button("Save invoice"):
            row = {
                "invoice_no": q_no,
                "customer_name": q_customer,
                "issue_date": str(q_issue),
                "due_date": str(q_due),
                "paid_date": str(q_paid) if q_is_paid else "",
                "total": str(q_total),
            }
            show_import_result(
                check(
                    api("POST", "/import/rows", json={"kind": "sales", "rows": [row]})
                )
            )
    with st.expander("Mark an invoice as paid"), st.form("mark_paid"):
        p_no = st.text_input("Invoice number", key="paid_no")
        p_date = st.date_input("Paid date", key="paid_date")
        if st.form_submit_button("Mark as paid"):
            invoice_path = requests.utils.quote(p_no.strip(), safe="")
            check(
                api(
                    "POST",
                    f"/invoices/{invoice_path}/paid",
                    json={"paid_date": str(p_date)},
                )
            )
            st.success(f"{p_no} marked as paid.")
            load_records.clear()

    st.divider()
    st.subheader("Danger zone")
    confirm = st.checkbox(
        "I understand this permanently deletes all my customers, invoices and transactions"
    )
    if st.button("Delete all my data", disabled=not confirm, key="delete_all"):
        check(api("DELETE", "/data"))
        st.success("All your data has been deleted.")
        load_records.clear()


def tidy_dates(df):
    """Show date columns as readable text, like 'May 2026'."""
    for col in df.columns:
        if "month" in col or "date" in col:
            parsed = pd.to_datetime(df[col], errors="coerce", utc=True)
            if parsed.notna().all():
                df[col] = parsed.dt.strftime("%b %Y" if "month" in col else "%d %b %Y")
    return df


def auto_chart(df):
    if len(df.columns) != 2 or df.empty:
        return
    x, y = df.columns
    df[y] = pd.to_numeric(df[y], errors="coerce")
    if df[y].isna().all():
        return
    if "month" in x or "date" in x:
        fmt = "%Y-%m" if "month" in x else "%Y-%m-%d"
        df[x] = pd.to_datetime(df[x], errors="coerce", utc=True).dt.strftime(fmt)
        st.line_chart(df.set_index(x)[y], height=300)
    else:
        st.bar_chart(df.set_index(x)[y], height=300)


@st.cache_data(ttl=60, show_spinner="Loading your records...")
def load_records(token, kind):
    r = requests.get(
        f"{API}/records/{kind}",
        timeout=120,
        headers={"Authorization": f"Bearer {token}"},
    )
    r.raise_for_status()
    return r.json()


if "token" not in st.session_state:
    st.title("📒 AI Finance Copilot for Malaysian SMEs")
    login_tab, signup_tab = st.tabs(["Log in", "Sign up"])
    with login_tab, st.form("login"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Log in"):
            try:
                res = sb.auth.sign_in_with_password(
                    {"email": email, "password": password}
                )
                st.session_state.token = res.session.access_token
            except Exception:  # noqa: BLE001
                st.error("Login failed. Check your email and password.")
    with signup_tab, st.form("signup"):
        new_email = st.text_input("Email", key="signup_email")
        new_password = st.text_input(
            "Password (at least 8 characters)", type="password", key="signup_password"
        )
        if st.form_submit_button("Create account"):
            if len(new_password) < 8:
                st.error("Use at least 8 characters for your password.")
            else:
                try:
                    res = sb.auth.sign_up(
                        {"email": new_email, "password": new_password}
                    )
                    if res.session:
                        st.session_state.token = res.session.access_token
                    else:
                        st.success(
                            "Account created. Check your email to confirm it, then log in."
                        )
                except Exception as e:  # noqa: BLE001
                    st.error(f"Sign-up failed: {e}")
    if "token" in st.session_state:
        st.rerun()
    st.stop()

if "business" not in st.session_state:
    r = api("GET", "/me")
    if r.status_code == 404:
        st.title("📒 Set up your business")
        with st.form("setup"):
            name = st.text_input("Business name")
            industry = st.selectbox(
                "Industry", ["F&B", "Retail", "Services", "Education", "Other"]
            )
            submitted = st.form_submit_button("Save")
        if submitted:
            st.session_state.business = check(
                api("POST", "/business", json={"name": name, "industry": industry})
            )
            st.rerun()
        st.stop()
    st.session_state.business = check(r)

biz = st.session_state.business
st.title(f"📒 {biz['name']}")
with st.sidebar:
    st.caption("AI Finance Copilot for Malaysian SMEs")
    if st.button("Log out"):
        st.session_state.clear()
        st.rerun()

tab_data, tab_docs, tab_mine, tab_records = st.tabs(
    ["Ask your data", "E-invoicing help", "My data", "Records"]
)

with tab_data:
    q = st.text_input(
        "Ask about your sales, invoices or expenses",
        placeholder="Which customers paid late most often this year?",
    )
    if st.button("Ask", key="ask_data") and q:
        res = check(api("POST", "/chat/sql", json={"question": q}))
        st.write(res["answer"])
        if res.get("rows"):
            df = pd.DataFrame(res["rows"], columns=res["columns"])
            auto_chart(df.copy())
            st.dataframe(tidy_dates(df), use_container_width=True)

with tab_docs:
    q2 = st.text_input(
        "Ask about e-invoicing rules",
        placeholder="My shop makes RM1.5 million a year. Do I need to issue e-Invoices?",
    )
    if st.button("Ask", key="ask_docs") and q2:
        res = check(api("POST", "/chat/docs", json={"question": q2}))
        st.write(res["answer"])
        st.caption(
            "Sources: "
            + " · ".join(
                f"[{c['n']}] {c['source']} v{c['version']}, p. {c['page']}"
                for c in res["citations"]
            )
        )

with tab_mine:
    if biz.get("read_only"):
        st.info(
            "This is the read-only demo account, so saving is turned off. Sign up to load your own data."
        )
    st.subheader("Import from CSV")
    st.write(
        "Download a template, fill it in Excel, save it as CSV, then upload it. "
        "Dates can be YYYY-MM-DD or DD/MM/YYYY. Leave paid_date empty for unpaid invoices."
    )
    c1, c2 = st.columns(2)
    c1.download_button(
        "Invoice template", INVOICE_TEMPLATE, "invoices_template.csv", "text/csv"
    )
    c2.download_button(
        "Expense template", EXPENSE_TEMPLATE, "expenses_template.csv", "text/csv"
    )
    kind = st.radio(
        "What are you uploading?", ["invoices", "expenses"], horizontal=True
    )
    up = st.file_uploader("CSV file", type="csv", key="csv_upload")
    if up is not None:
        try:
            st.dataframe(pd.read_csv(up, dtype=str).head(10), use_container_width=True)
        except Exception:  # noqa: BLE001 - preview only; the server does the real checks
            st.warning("Couldn't preview this file. It may not be a valid CSV.")
        if st.button("Import", key="import_csv"):
            show_import_result(
                check(
                    api(
                        "POST",
                        f"/import/csv/{kind}",
                        files={"file": (up.name, up.getvalue(), "text/csv")},
                    )
                )
            )
    my_data_extras(biz)

with tab_records:
    try:
        inv = pd.DataFrame(load_records(st.session_state.token, "invoices"))
        exp = pd.DataFrame(load_records(st.session_state.token, "expenses"))
    except requests.RequestException:
        st.error("Couldn't load your records. Please try again in a minute.")
        st.stop()

    if inv.empty and exp.empty:
        st.info("No records yet. Add invoices or expenses in the My data tab.")
        st.stop()

    c1, c2, c3 = st.columns(3)
    if not inv.empty:
        unpaid = inv[inv["status"].isin(["issued", "overdue"])]
        c1.metric("Still owed to you", f"RM{unpaid['total'].astype(float).sum():,.2f}")
        c2.metric("Overdue invoices", int((inv["status"] == "overdue").sum()))
    if not exp.empty:
        month = pd.Timestamp.today().strftime("%Y-%m")
        this_month = exp[exp["date"].astype(str).str.startswith(month)]
        c3.metric(
            "Expenses this month", f"RM{this_month['amount'].astype(float).sum():,.2f}"
        )

    st.subheader("Invoices")
    if inv.empty:
        st.caption("No invoices yet.")
    else:
        status = st.selectbox(
            "Status", ["all", "overdue", "issued", "paid", "cancelled"]
        )
        shown = inv if status == "all" else inv[inv["status"] == status]
        st.caption(f"{len(shown)} invoice(s). Showing the latest 500.")
        st.dataframe(shown, use_container_width=True, hide_index=True)

    st.subheader("Expenses")
    if exp.empty:
        st.caption("No expenses yet.")
    else:
        st.dataframe(exp, use_container_width=True, hide_index=True)
