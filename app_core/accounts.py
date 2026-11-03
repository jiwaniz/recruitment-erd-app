"""
Database-backed accounts: login, lockout, password policy, change / reset password, profile, admin user management.

Security rules implemented here
* Passwords are stored only as salted PBKDF2-SHA256 hashes. Reset tokens are stored only as SHA-256 hashes, expire after
  30 minutes and can be used once. Nothing sensitive is written to logs or the audit table.
* Login and "forgot password" never reveal whether an email / username exists.
* Five wrong passwords lock an account for 15 minutes (stored in the database, so it cannot be bypassed by a new session).
* Every administrator action calls require_role("admin") on the server side.
"""
import hashlib
import json
import re
import secrets
import string

import streamlit as st
from sqlalchemy import text

from . import db, emailer
from .auth import ROLE_LEVEL, current_user, hash_password, require_role, verify_password
from .config import get_base_url
from .services import EMAIL_RE, ServiceError, _need, _text

MAX_FAILS, LOCK_MINUTES, RESET_MINUTES = 5, 15, 30
RESET_PER_EMAIL_HOUR, RESET_TOTAL_HOUR = 3, 20
COMMON = {"password", "password1", "password123", "123456789", "1234567890", "qwerty123", "admin12345",
          "letmein123", "welcome123", "iloveyou123", "changeme123"}
USERNAME_RE = re.compile(r"^[a-z0-9_.\-]{3,50}$")
GENERIC_LOGIN_ERROR = "Invalid username/email or password."
GENERIC_RESET_MESSAGE = ("If that email address is registered, a password reset link has been sent. "
                         "It expires in 30 minutes.")


def accounts_enabled() -> bool:
    try:
        return int(db.scalar("SELECT COUNT(*) AS n FROM information_schema.tables "
                             "WHERE table_schema = DATABASE() AND table_name = 'app_user'")) > 0
    except Exception:                                              # noqa: BLE001
        return False


# ---------------------------------------------------------------- helpers
def _one(conn, sql, **p):
    return conn.execute(text(sql), p).mappings().first()


def _run(conn, sql, **p):
    return conn.execute(text(sql), p)


def _event(conn, etype, username=None, user_id=None, detail=None):
    _run(conn, "INSERT INTO auth_event (event_type, username, user_id, detail) VALUES (:t, :u, :i, :d)",
         t=etype, u=(username or "")[:150] or None, i=user_id, d=(detail or "")[:255] or None)


def _user_dict(r) -> dict:
    prefs = r["preferences"]
    if isinstance(prefs, (str, bytes)):
        try:
            prefs = json.loads(prefs)
        except ValueError:
            prefs = {}
    return {"user_id": r["user_id"], "username": r["username"], "display_name": r["full_name"], "email": r["email"],
            "role": r["role"], "employee_id": r["employee_id"], "is_active": bool(r["is_active"]),
            "must_change_password": bool(r["must_change_password"]), "created_date": r["created_date"],
            "last_login": r["last_login"], "preferences": prefs or {}}


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def temp_password() -> str:
    pools = [string.ascii_lowercase, string.ascii_uppercase, string.digits, "!@#$%^&*-_"]
    chars = [secrets.choice(p) for p in pools] + [secrets.choice("".join(pools)) for _ in range(10)]
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def validate_password(pw: str, username: str = "", email: str = "") -> list[str]:
    problems = []
    if len(pw) < 10:
        problems.append("at least 10 characters")
    if sum(bool(re.search(p, pw)) for p in (r"[a-z]", r"[A-Z]", r"\d", r"[^A-Za-z0-9]")) < 3:
        problems.append("at least 3 of: lowercase, uppercase, digit, symbol")
    low = pw.lower()
    if low in COMMON:
        problems.append("not a commonly used password")
    for part in (username, email.split("@")[0] if email else ""):
        if part and len(part) >= 3 and part.lower() in low:
            problems.append("must not contain your username or email name")
            break
    return problems


def _check_new_password(pw, confirm, username="", email=""):
    _need(pw == confirm, "The new password and its confirmation do not match.")
    problems = validate_password(pw, username, email)
    _need(not problems, "The new password needs: " + "; ".join(problems) + ".")


# ---------------------------------------------------------------- login
def login(identifier: str, password: str) -> tuple[dict | None, str]:
    ident = (identifier or "").strip().lower()
    with db.get_engine().begin() as conn:
        r = _one(conn, "SELECT * FROM app_user WHERE username = :i OR LOWER(email) = :i", i=ident)
        if not r:
            verify_password(password, "pbkdf2_sha256$1$AAAA$AAAA")          # keep timing similar
            _event(conn, "login_failed", ident, None, "unknown user")
            return None, GENERIC_LOGIN_ERROR
        locked = _one(conn, "SELECT locked_until > NOW() AS L, TIMESTAMPDIFF(MINUTE, NOW(), locked_until) AS m "
                            "FROM app_user WHERE user_id = :u", u=r["user_id"])
        if locked["L"]:
            _event(conn, "login_blocked", r["username"], r["user_id"], "account locked")
            return None, f"Too many failed attempts. Try again in {int(locked['m']) + 1} minute(s)."
        if not verify_password(password, r["password_hash"]):
            fails = r["failed_logins"] + 1
            if fails >= MAX_FAILS:
                _run(conn, "UPDATE app_user SET failed_logins = 0, locked_until = NOW() + INTERVAL :m MINUTE WHERE user_id = :u",
                     m=LOCK_MINUTES, u=r["user_id"])
                _event(conn, "account_locked", r["username"], r["user_id"], f"{LOCK_MINUTES} minutes")
            else:
                _run(conn, "UPDATE app_user SET failed_logins = :f WHERE user_id = :u", f=fails, u=r["user_id"])
            _event(conn, "login_failed", r["username"], r["user_id"], "wrong password")
            return None, GENERIC_LOGIN_ERROR
        if not r["is_active"]:
            _event(conn, "login_blocked", r["username"], r["user_id"], "deactivated")
            return None, "This account is deactivated. Please contact an administrator."
        _run(conn, "UPDATE app_user SET failed_logins = 0, locked_until = NULL, last_login = NOW() WHERE user_id = :u", u=r["user_id"])
        _event(conn, "login_ok", r["username"], r["user_id"])
        r = _one(conn, "SELECT * FROM app_user WHERE user_id = :u", u=r["user_id"])
        return _user_dict(r), ""


def reload_user(user_id: int) -> dict | None:
    """Fresh copy from the database (role changes and deactivation take effect on the next page load)."""
    with db.get_engine().connect() as conn:
        r = _one(conn, "SELECT * FROM app_user WHERE user_id = :u", u=user_id)
    return _user_dict(r) if r and r["is_active"] else None


def _me():
    u = current_user()
    _need(u and u.get("user_id"), "You must be signed in with a database account.")
    return u


# ---------------------------------------------------------------- self-service
def change_password(current: str, new: str, confirm: str) -> str:
    u = _me()
    _need(current and new and confirm, "Fill in all three password fields.")
    with db.transaction() as conn:
        r = _one(conn, "SELECT password_hash, username, email FROM app_user WHERE user_id = :u FOR UPDATE", u=u["user_id"])
        _need(verify_password(current, r["password_hash"]), "The current password is incorrect.")
        _need(new != current, "The new password must be different from the current one.")
        _check_new_password(new, confirm, r["username"], r["email"])
        _run(conn, "UPDATE app_user SET password_hash = :h, must_change_password = 0 WHERE user_id = :u",
             h=hash_password(new), u=u["user_id"])
        _run(conn, "UPDATE password_reset_token SET used_at = NOW() WHERE user_id = :u AND used_at IS NULL", u=u["user_id"])
        _event(conn, "password_changed", r["username"], u["user_id"])
    st.session_state["user"]["must_change_password"] = False
    return "Your password was changed."


def update_profile(full_name: str, email: str) -> str:
    u = _me()
    full_name = _text(full_name, "Full name", 100)
    email = _text(email, "Email", 150).lower()
    _need(EMAIL_RE.match(email), "Enter a valid email address.")
    with db.transaction() as conn:
        _need(not _one(conn, "SELECT 1 AS x FROM app_user WHERE LOWER(email) = :e AND user_id <> :u", e=email, u=u["user_id"]),
              "That email address is already used by another account.")
        _run(conn, "UPDATE app_user SET full_name = :n, email = :e WHERE user_id = :u", n=full_name, e=email, u=u["user_id"])
        _event(conn, "profile_updated", u["username"], u["user_id"])
    st.session_state["user"].update(display_name=full_name, email=email)
    return "Profile updated."


def save_preferences(prefs: dict) -> str:
    u = _me()
    allowed = {"landing_page": str(prefs.get("landing_page", "Dashboard")), "compact_tables": bool(prefs.get("compact_tables"))}
    with db.transaction() as conn:
        _run(conn, "UPDATE app_user SET preferences = :p WHERE user_id = :u", p=json.dumps(allowed), u=u["user_id"])
    st.session_state["user"]["preferences"] = allowed
    return "Preferences saved."


# ---------------------------------------------------------------- forgot / reset password (logged out)
def request_reset(email: str) -> str:
    """Always returns the same message, whether or not the address is registered."""
    email = (email or "").strip().lower()
    _need(EMAIL_RE.match(email), "Enter a valid email address.")
    with db.get_engine().begin() as conn:
        per = _one(conn, "SELECT COUNT(*) AS n FROM auth_event WHERE event_type = 'reset_requested' AND username = :e "
                         "AND event_time > NOW() - INTERVAL 1 HOUR", e=email)["n"]
        tot = _one(conn, "SELECT COUNT(*) AS n FROM auth_event WHERE event_type = 'reset_requested' "
                         "AND event_time > NOW() - INTERVAL 1 HOUR")["n"]
        _event(conn, "reset_requested", email)
        if per >= RESET_PER_EMAIL_HOUR or tot >= RESET_TOTAL_HOUR:
            return GENERIC_RESET_MESSAGE                                   # silently rate limited
        r = _one(conn, "SELECT user_id, username FROM app_user WHERE LOWER(email) = :e AND is_active = 1", e=email)
        if not r:
            return GENERIC_RESET_MESSAGE
        token = secrets.token_urlsafe(32)
        _run(conn, "UPDATE password_reset_token SET used_at = NOW() WHERE user_id = :u AND used_at IS NULL", u=r["user_id"])
        _run(conn, "INSERT INTO password_reset_token (user_id, token_hash, expires_at) VALUES (:u, :h, NOW() + INTERVAL :m MINUTE)",
             u=r["user_id"], h=hash_token(token), m=RESET_MINUTES)
        link = f"{get_base_url()}/?reset_token={token}"
        try:
            emailer.send(email, "Reset your Recruitment Management System password",
                         f"Hello,\n\nUse this link to choose a new password (valid for {RESET_MINUTES} minutes, one use only):\n\n{link}\n\n"
                         "If you did not request this, you can ignore this email; your password will not change.\n")
            _event(conn, "reset_email_sent", r["username"], r["user_id"])
        except Exception as exc:                                            # noqa: BLE001
            _event(conn, "reset_email_failed", r["username"], r["user_id"], type(exc).__name__)
    return GENERIC_RESET_MESSAGE


def token_user(token: str) -> dict | None:
    if not token:
        return None
    with db.get_engine().connect() as conn:
        return _one(conn, """SELECT t.token_id, u.user_id, u.username, u.email FROM password_reset_token t
                             JOIN app_user u ON u.user_id = t.user_id
                             WHERE t.token_hash = :h AND t.used_at IS NULL AND t.expires_at > NOW() AND u.is_active = 1""",
                    h=hash_token(token))


def reset_password(token: str, new: str, confirm: str) -> str:
    with db.transaction() as conn:
        r = _one(conn, """SELECT t.token_id, u.user_id, u.username, u.email FROM password_reset_token t
                          JOIN app_user u ON u.user_id = t.user_id
                          WHERE t.token_hash = :h AND t.used_at IS NULL AND t.expires_at > NOW() AND u.is_active = 1
                          FOR UPDATE""", h=hash_token(token or ""))
        _need(r, "This reset link is invalid, expired or has already been used. Please request a new one.")
        _check_new_password(new, confirm, r["username"], r["email"])
        _run(conn, "UPDATE app_user SET password_hash = :h, must_change_password = 0, failed_logins = 0, locked_until = NULL "
                   "WHERE user_id = :u", h=hash_password(new), u=r["user_id"])
        _run(conn, "UPDATE password_reset_token SET used_at = NOW() WHERE user_id = :u AND used_at IS NULL", u=r["user_id"])
        _event(conn, "password_reset", r["username"], r["user_id"])
    return "Your password was reset. You can now sign in."


# ---------------------------------------------------------------- administrator functions
def list_users():
    return db.q("""SELECT user_id, username, full_name, email, role, employee_id, is_active, must_change_password,
                   last_login, created_date FROM app_user ORDER BY user_id""")


def recent_events(limit: int = 100):
    return db.q(f"SELECT event_time, event_type, username, detail FROM auth_event ORDER BY event_id DESC LIMIT {int(limit)}")


def _other_active_admins(conn, user_id) -> int:
    return _one(conn, "SELECT COUNT(*) AS n FROM app_user WHERE role = 'admin' AND is_active = 1 AND user_id <> :u", u=user_id)["n"]


def create_user(username, email, full_name, role, employee_id) -> str:
    require_role("admin")
    username = (username or "").strip().lower()
    _need(USERNAME_RE.match(username), "Username: 3-50 characters, lowercase letters, digits, dot, dash or underscore.")
    email = _text(email, "Email", 150).lower()
    _need(EMAIL_RE.match(email), "Enter a valid email address.")
    full_name = _text(full_name, "Full name", 100)
    _need(role in ROLE_LEVEL, "Choose an existing role.")
    pw = temp_password()
    with db.transaction() as conn:
        _need(not _one(conn, "SELECT 1 AS x FROM app_user WHERE username = :u OR LOWER(email) = :e", u=username, e=email),
              "That username or email is already in use.")
        uid = _run(conn, """INSERT INTO app_user (username, email, full_name, password_hash, role, employee_id, must_change_password)
                            VALUES (:u, :e, :n, :h, :r, :emp, 1)""", u=username, e=email, n=full_name, h=hash_password(pw),
                   r=role, emp=employee_id).lastrowid
        _event(conn, "user_created", username, uid, f"by {current_user()['username']}")
    return f"User '{username}' created. Temporary password (shown once, must be changed at first sign-in): {pw}"


def update_user(user_id, full_name, email, role, employee_id) -> str:
    require_role("admin")
    full_name = _text(full_name, "Full name", 100)
    email = _text(email, "Email", 150).lower()
    _need(EMAIL_RE.match(email), "Enter a valid email address.")
    _need(role in ROLE_LEVEL, "Choose an existing role.")
    with db.transaction() as conn:
        r = _one(conn, "SELECT username, role FROM app_user WHERE user_id = :u FOR UPDATE", u=user_id)
        _need(r, "User not found.")
        _need(not _one(conn, "SELECT 1 AS x FROM app_user WHERE LOWER(email) = :e AND user_id <> :u", e=email, u=user_id),
              "That email address is already used by another account.")
        if r["role"] == "admin" and role != "admin":
            _need(user_id != current_user()["user_id"], "You cannot remove your own administrator role.")
            _need(_other_active_admins(conn, user_id) > 0, "At least one active administrator must remain.")
        _run(conn, "UPDATE app_user SET full_name = :n, email = :e, role = :r, employee_id = :emp WHERE user_id = :u",
             n=full_name, e=email, r=role, emp=employee_id, u=user_id)
        _event(conn, "user_updated", r["username"], user_id, f"by {current_user()['username']}; role {r['role']} -> {role}")
    return "User updated."


def set_active(user_id, active: bool) -> str:
    require_role("admin")
    with db.transaction() as conn:
        r = _one(conn, "SELECT username, role FROM app_user WHERE user_id = :u FOR UPDATE", u=user_id)
        _need(r, "User not found.")
        if not active:
            _need(user_id != current_user()["user_id"], "You cannot deactivate your own account.")
            _need(r["role"] != "admin" or _other_active_admins(conn, user_id) > 0, "At least one active administrator must remain.")
        _run(conn, "UPDATE app_user SET is_active = :a WHERE user_id = :u", a=1 if active else 0, u=user_id)
        _event(conn, "user_activated" if active else "user_deactivated", r["username"], user_id, f"by {current_user()['username']}")
    return f"User '{r['username']}' {'activated' if active else 'deactivated'}."


def admin_reset_password(user_id) -> str:
    require_role("admin")
    pw = temp_password()
    with db.transaction() as conn:
        r = _one(conn, "SELECT username FROM app_user WHERE user_id = :u FOR UPDATE", u=user_id)
        _need(r, "User not found.")
        _run(conn, "UPDATE app_user SET password_hash = :h, must_change_password = 1, failed_logins = 0, locked_until = NULL WHERE user_id = :u",
             h=hash_password(pw), u=user_id)
        _run(conn, "UPDATE password_reset_token SET used_at = NOW() WHERE user_id = :u AND used_at IS NULL", u=user_id)
        _event(conn, "admin_reset", r["username"], user_id, f"by {current_user()['username']}")
    return f"Password reset for '{r['username']}'. Temporary password (shown once, must be changed at next sign-in): {pw}"


def unlock_user(user_id) -> str:
    require_role("admin")
    with db.transaction() as conn:
        _run(conn, "UPDATE app_user SET failed_logins = 0, locked_until = NULL WHERE user_id = :u", u=user_id)
        _event(conn, "user_unlocked", None, user_id, f"by {current_user()['username']}")
    return "Account unlocked."
