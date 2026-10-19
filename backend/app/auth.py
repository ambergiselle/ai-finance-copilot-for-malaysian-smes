from functools import lru_cache
from typing import Annotated, Any

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import create_client

from .config import settings
from .db import app_query

bearer = HTTPBearer()


@lru_cache
def supabase_client():
    return create_client(settings.supabase_url, settings.supabase_anon_key)


def current_user(creds: Annotated[HTTPAuthorizationCredentials, Depends(bearer)]) -> Any:
    try:
        return supabase_client().auth.get_user(creds.credentials).user
    except Exception as e:  # any failure here means the token can't be trusted
        raise HTTPException(status_code=401, detail="Invalid or expired token") from e


CurrentUser = Annotated[Any, Depends(current_user)]


def current_business(user: CurrentUser) -> dict:
    rows = app_query(
        "select id, name, industry from businesses where owner_id = %s", (user.id,)
    )
    if not rows:
        raise HTTPException(status_code=404, detail="business_not_set_up")
    return rows[0]


Business = Annotated[dict, Depends(current_business)]


def writable_business(biz: Business) -> dict:
    if biz["name"] == settings.demo_business_name:
        raise HTTPException(
            status_code=403,
            detail="The demo account is read-only. Sign up to use your own data.",
        )
    return biz


WritableBusiness = Annotated[dict, Depends(writable_business)]
