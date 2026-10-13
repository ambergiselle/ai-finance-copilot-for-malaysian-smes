import os

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])
res = sb.auth.sign_in_with_password(
    {"email": os.environ["DEMO_EMAIL"], "password": os.environ["DEMO_PASSWORD"]}
)
print(res.session.access_token)
