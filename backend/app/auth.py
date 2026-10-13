from functools import lru_cache

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import create_client

from .config import settings
from .db import app_query

bearer = HTTPBearer()
bearer_dependency = Depends(bearer)


@lru_cache
def supabase_client():
    return create_client(settings.supabase_url, settings.supabase_anon_key)


def current_business(cred: HTTPAuthorizationCredentials = bearer_dependency):
    try:
        user = supabase_client().auth.get_user(cred.credentials).user
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token")
    rows = app_query(
        "select id, name, industry from businesses where owner_id = %s", (user.id,)
    )
    if not rows:
        raise HTTPException(
            status_code=404, detail="No business linked to this account"
        )
    return rows[0]
