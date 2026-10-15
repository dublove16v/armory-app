"""Sign-in gate for Armory. Only user `luke` may enter; nothing renders before sign-in.

Mode 1 (shared ABW login): if the app's Secrets has the same [auth] block as the
work apps (store_repo + github_token), luke's password is checked against the
shared abw-users list.
Mode 2 (fallback): Secrets has
    ARMORY_PASSWORD_HASH = "pbkdf2_sha256$<iter>$<salt hex>$<hash hex>"
Make one with:  python armory_auth.py
If neither is set, the app stays locked.
"""
import base64, hashlib, hmac, json

import streamlit as st

ALLOWED = "luke"


def _pbkdf2(pw, salt_hex, iters):
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt_hex), int(iters)).hex()


def _check_shared(pw):
    import requests
    a = dict(st.secrets["auth"])
    base = str(a.get("api_base") or "https://api.github.com").rstrip("/")
    r = requests.get(f"{base}/repos/{a['store_repo']}/contents/users.json", timeout=10,
                     headers={"Authorization": f"Bearer {a['github_token']}", "Accept": "application/vnd.github+json"})
    r.raise_for_status()
    rec = json.loads(base64.b64decode(r.json()["content"]).decode())["users"].get(ALLOWED)
    if not rec or "hash" not in rec:
        return False
    return hmac.compare_digest(_pbkdf2(pw, rec["salt"], rec.get("iter", 200_000)), rec["hash"])


def _check_hash(pw, stored):
    try:
        algo, iters, salt, h = str(stored).split("$")
    except ValueError:
        return False
    return algo == "pbkdf2_sha256" and hmac.compare_digest(_pbkdf2(pw, salt, iters), h)


def _mode():
    try:
        a = st.secrets["auth"]
        if a.get("store_repo") and a.get("github_token"):
            return "shared"
    except Exception:
        pass
    try:
        if st.secrets.get("ARMORY_PASSWORD_HASH"):
            return "hash"
    except Exception:
        pass
    return None


def require_login():
    if st.session_state.get("armory_user") == ALLOWED:
        with st.sidebar:
            if st.button("Sign out"):
                st.session_state.pop("armory_user", None)
                st.rerun()
        return ALLOWED
    mode = _mode()
    st.title("Armory")
    if not mode:
        st.error("App locked: sign-in isn't set up. Add ARMORY_PASSWORD_HASH (or the shared [auth] block) in Secrets.")
        st.stop()
    with st.form("armory_login"):
        user = st.text_input("Username").strip().lower()
        pw = st.text_input("Password", type="password")
        go = st.form_submit_button("Sign in")
    if go:
        ok = False
        if user == ALLOWED and pw:
            try:
                ok = _check_shared(pw) if mode == "shared" else _check_hash(pw, st.secrets["ARMORY_PASSWORD_HASH"])
            except Exception:
                st.error("Couldn't reach the login list. Try again in a minute.")
                st.stop()
        if ok:
            st.session_state["armory_user"] = ALLOWED
            st.rerun()
        st.error("Wrong username or password.")
    st.stop()


if __name__ == "__main__":
    import getpass, secrets
    pw = getpass.getpass("Password for luke: ")
    salt, iters = secrets.token_hex(16), 200_000
    print(f'ARMORY_PASSWORD_HASH = "pbkdf2_sha256${iters}${salt}${_pbkdf2(pw, salt, iters)}"')
