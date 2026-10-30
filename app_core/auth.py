"""
Authentication and role-based access control.

The database has no user/password table, so (per the project rules) NO schema change was made.
Users are defined in Streamlit secrets (cloud) or the APP_USERS environment variable (local):
    username -> { password_hash, role, display_name, employee_id (optional) }

* Passwords are stored only as salted PBKDF2-SHA256 hashes (create one with scripts/make_password_hash.py).
* Roles: viewer (read only) < recruiter (create/edit) < admin (approve, delete, close).
* Permissions are checked again inside every write function (services.py) with require_role(),
  so hiding a button is never the only protection.
"""
import base64
import hashlib
import hmac
import secrets
import time

import streamlit as st

from .config import get_users_config

ROLE_LEVEL = {"viewer": 1, "recruiter": 2, "admin": 3}
ITERATIONS = 390_000
MAX_FAILS, LOCK_SECONDS = 5, 60


def hash_password(password: str, iterations: int = ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return "pbkdf2_sha256${}${}${}".format(iterations, base64.b64encode(salt).decode(), base64.b64encode(dk).decode())


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_b64, hash_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt_b64), int(iters))
        return hmac.compare_digest(dk, base64.b64decode(hash_b64))
    except Exception:                                         # noqa: BLE001
        return False


def current_user() -> dict | None:
    return st.session_state.get("user")


def has_role(min_role: str) -> bool:
    user = current_user()
    return bool(user) and ROLE_LEVEL.get(user["role"], 0) >= ROLE_LEVEL[min_role]


def require_role(min_role: str):
    """Call at the top of every write operation."""
    if not has_role(min_role):
        raise PermissionError(f"This action needs the '{min_role}' role.")


def logout():
    for key in ("user", "login_fails", "locked_until"):
        st.session_state.pop(key, None)
    st.rerun()


def login_form() -> bool:
    """Render the login form. Returns True when a user is signed in."""
    if current_user():
        return True
    users = get_users_config()
    st.markdown("<div class='login-title'>Recruitment Management System</div>", unsafe_allow_html=True)
    st.caption("Please sign in to continue.")
    if not users:
        st.error("No users are configured yet. Add users to `.env` (APP_USERS) or `.streamlit/secrets.toml` "
                 "([users.*] sections). See README.md, section 'Create the login users'.")
        return False
    locked = st.session_state.get("locked_until", 0)
    if time.time() < locked:
        st.warning(f"Too many failed attempts. Try again in {int(locked - time.time())} seconds.")
        return False
    with st.form("login", clear_on_submit=False):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        ok = st.form_submit_button("Sign in", type="primary")
    if ok:
        info = users.get(username.strip().lower())
        valid = bool(info) and verify_password(password, info.get("password_hash", ""))
        if valid and info.get("role") in ROLE_LEVEL:
            st.session_state["user"] = {
                "username": username.strip().lower(),
                "role": info["role"],
                "display_name": info.get("display_name", username),
                "employee_id": info.get("employee_id"),
            }
            st.session_state.pop("login_fails", None)
            st.rerun()
        fails = st.session_state.get("login_fails", 0) + 1
        st.session_state["login_fails"] = fails
        if fails >= MAX_FAILS:
            st.session_state["locked_until"] = time.time() + LOCK_SECONDS
            st.session_state["login_fails"] = 0
        st.error("Invalid username or password.")
    return False
