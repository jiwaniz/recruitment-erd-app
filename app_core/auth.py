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
    for key in ("user", "login_fails", "locked_until", "_forgot"):
        st.session_state.pop(key, None)
    st.rerun()


def _config_login(identifier: str, password: str):
    """Fallback used until the account tables exist: users come from secrets / APP_USERS."""
    info = get_users_config().get((identifier or "").strip().lower())
    if info and verify_password(password, info.get("password_hash", "")) and info.get("role") in ROLE_LEVEL:
        return {"user_id": None, "username": identifier.strip().lower(), "role": info["role"],
                "display_name": info.get("display_name", identifier), "email": info.get("email"),
                "employee_id": info.get("employee_id"), "must_change_password": False, "preferences": {},
                "created_date": None, "last_login": None, "is_active": True}, ""
    return None, "Invalid username/email or password."


def _sign_in_form(db_mode: bool):
    with st.form("login", clear_on_submit=False):
        ident = st.text_input("Username or email", placeholder="you@example.com")
        pw = st.text_input("Password", type="password")       # Streamlit adds a show / hide (eye) button
        submitted = st.form_submit_button("Sign In", type="primary", width="stretch")
    if submitted:
        if not ident.strip() or not pw:
            st.error("Enter your username (or email) and your password.")
            return
        if time.time() < st.session_state.get("locked_until", 0):
            st.warning(f"Too many failed attempts. Try again in {int(st.session_state['locked_until'] - time.time())} seconds.")
            return
        if db_mode:
            from . import accounts
            user, error = accounts.login(ident, pw)
        else:
            user, error = _config_login(ident, pw)
        if user:
            st.session_state["user"] = user
            st.session_state.pop("login_fails", None)
            st.rerun()
        fails = st.session_state.get("login_fails", 0) + 1
        st.session_state["login_fails"] = fails
        if fails >= MAX_FAILS:
            st.session_state.update(locked_until=time.time() + LOCK_SECONDS, login_fails=0)
        st.error(error)
    if db_mode:
        if st.button("Forgot password?", type="tertiary"):
            st.session_state["_forgot"] = True
            st.rerun()
    else:
        st.caption("Forgot your password? Ask an administrator. Self-service reset needs the account upgrade (see AUTH_SETUP.md).")


def _forgot_form():
    from . import accounts, emailer
    from .services import ServiceError
    st.subheader("Forgot password")
    st.caption("Enter the email address of your account and we will send you a reset link.")
    if not emailer.is_configured():
        st.warning("Password reset by email is not set up on this server yet. Please ask an administrator for a temporary password.")
    with st.form("forgot"):
        email = st.text_input("Email address")
        ok = st.form_submit_button("Send reset link", type="primary", width="stretch")
    if ok and emailer.is_configured():
        try:
            st.success(accounts.request_reset(email))
        except ServiceError as exc:
            st.error(str(exc))
    if st.button("Back to sign in", type="tertiary"):
        st.session_state.pop("_forgot", None)
        st.rerun()


def _reset_form(token: str):
    from . import accounts
    from .services import ServiceError
    st.subheader("Choose a new password")
    if not accounts.token_user(token):
        st.error("This reset link is invalid, expired or has already been used.")
    else:
        st.caption("At least 10 characters, with at least 3 of: lowercase, uppercase, digit, symbol.")
        with st.form("reset"):
            new = st.text_input("New password", type="password")
            confirm = st.text_input("Confirm new password", type="password")
            ok = st.form_submit_button("Reset password", type="primary", width="stretch")
        if ok:
            try:
                st.success(accounts.reset_password(token, new, confirm))
                st.query_params.clear()
                st.session_state.pop("_forgot", None)
                return
            except ServiceError as exc:
                st.error(str(exc))
    if st.button("Back to sign in", type="tertiary"):
        st.query_params.clear()
        st.rerun()


def login_page() -> bool:
    """Branded login page with Sign In, Forgot Password and Reset Password. Returns True when signed in."""
    if current_user():
        return True
    from . import accounts
    db_mode = accounts.accounts_enabled()
    _, mid, _ = st.columns([1, 1.4, 1])
    with mid:
        st.markdown("<div class='login-title'>🧑‍💼 Recruitment Management System</div>", unsafe_allow_html=True)
        st.caption("Sign in to manage vacancies, candidates, interviews and hiring.")
        token = st.query_params.get("reset_token")
        if token and db_mode:
            _reset_form(token)
        elif db_mode and st.session_state.get("_forgot"):
            _forgot_form()
        elif not get_users_config() and not db_mode:
            st.error("No users are configured yet. See README.md, 'Create the login users'.")
        else:
            _sign_in_form(db_mode)
    return False


def refresh_session():
    """Re-read the signed-in user's role/status from the database on every page load (RBAC cannot go stale)."""
    user = current_user()
    if user and user.get("user_id"):
        from . import accounts
        fresh = accounts.reload_user(user["user_id"])
        if fresh is None:
            st.session_state.pop("user", None)
            st.session_state["_flash"] = ("warning", "Your account was deactivated or removed. Please sign in again.")
            st.rerun()
        st.session_state["user"] = fresh
