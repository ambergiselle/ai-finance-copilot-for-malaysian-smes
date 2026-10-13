import psycopg

from .config import settings


def app_query(sql: str, params: tuple = ()) -> list[dict]:
    """Trusted queries written by the app"""
    with psycopg.connect(settings.database_url) as conn:
        cur = conn.execute(sql, params)
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def run_safe_sql(sql: str, business_id, params: tuple = ()):
    """Untrusted SQL: read-only role, one business, only, with 5 seconds limit"""
    with psycopg.connect(settings.agent_database_url) as conn, conn.transaction():
        conn.execute("set local statement_timeout = '5s'")
        conn.execute(
            "select set_config('app.business_id', %s, true)", (str(business_id),)
        )
        cur = conn.execute(sql, params)
        cols = [d.name for d in cur.description]
        return cols, cur.fetchall()
