import pandas as pd
import requests
import streamlit as st
from supabase import create_client

st.set_page_config(page_title="AI Finance Copilot", page_icon="📒", layout="wide")
API = st.secrets["API_URL"]
sb = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_ANON_KEY"])


def call_api(path, question):
    with st.spinner(
        "Thinking... (the first request may take up to a minute while the server wakes up)"
    ):
        r = requests.post(
            f"{API}{path}",
            json={"question": question},
            timeout=120,
            headers={"Authorization": f"Bearer {st.session_state.token}"},
        )
    r.raise_for_status()
    return r.json()


def auto_chart(df):
    if len(df.columns) != 2 or df.empty:
        return
    x, y = df.columns
    df[y] = pd.to_numeric(df[y], errors="coerce")
    if df[y].isna().all():
        return
    data = df.set_index(x)[y]
    st.line_chart(data) if ("month" in x or "date" in x) else st.bar_chart(data)


if "token" not in st.session_state:
    st.title("📒 AI Finance Copilot for Malaysian SMEs")
    with st.form("login"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Log in"):
            try:
                res = sb.auth.sign_in_with_password(
                    {"email": email, "password": password}
                )
                st.session_state.token = res.session.access_token
                st.rerun()
            except Exception:
                st.error("Login failed. Check your email and password.")
    st.stop()

st.title("📒 AI Finance Copilot")
tab_data, tab_docs = st.tabs(["Ask your data", "E-invoicing help"])

with tab_data:
    q = st.text_input(
        "Ask about your sales, invoices or expenses",
        placeholder="Which customers paid late most often this year?",
    )
    if st.button("Ask", key="ask_data") and q:
        res = call_api("/chat/sql", q)
        st.write(res["answer"])
        if res.get("rows"):
            df = pd.DataFrame(res["rows"], columns=res["columns"])
            auto_chart(df.copy())
            st.dataframe(df, use_container_width=True)
        with st.expander("SQL used"):
            st.code(res.get("sql") or "", language="sql")

with tab_docs:
    q2 = st.text_input(
        "Ask about e-invoicing rules",
        placeholder="My shop makes RM1.5 million a year. Do I need to issue e-Invoices?",
    )
    if st.button("Ask", key="ask_docs") and q2:
        res = call_api("/chat/docs", q2)
        st.write(res["answer"])
        st.caption(
            "Sources: "
            + " · ".join(
                f"[{c['n']}] {c['source']} v{c['version']}, p. {c['page']}"
                for c in res["citations"]
            )
        )
