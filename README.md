# Armory

Airsoft locker: guns, parts, and receipt spend. Sign-in required; only the owner can use it.

Receipts are not in this repo. They load after sign-in from a private Supabase table (`armory_receipts`, RLS on, server key only).

## Streamlit secrets

```toml
ARMORY_PASSWORD_HASH = "pbkdf2_sha256$200000$<salt>$<hash>"   # make with: python armory_auth.py
SUPABASE_URL = "https://<project>.supabase.co"
SUPABASE_KEY = "<server key>"
```

Run locally: `pip install -r requirements.txt && streamlit run app.py`
