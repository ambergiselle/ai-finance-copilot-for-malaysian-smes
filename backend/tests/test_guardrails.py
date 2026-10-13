from app.agents.sql_agent import validate_sql
import pytest


def test_allows_simple_select():
    assert "LIMIT 200" in validate_sql("select * from invoices").upper()


def test_blocks_delete():
    with pytest.raises(ValueError):
        validate_sql("delete from invoices")


def test_blocks_multiple_statements():
    with pytest.raises(ValueError):
        validate_sql("select 1; drop table invoices")


def test_blocks_unknown_table():
    with pytest.raises(ValueError):
        validate_sql("select * from auth.users")
