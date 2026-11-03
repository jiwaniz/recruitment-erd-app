"""
Authentication / account tests (service level). Needs: ADMIN connection in ADMIN_DB_USER/ADMIN_DB_PASSWORD for the migration
step, normal app connection in DB_* and APP_USERS in the environment. Uses a local SMTP sink (aiosmtpd) as the email service.
WARNING: modifies the target database (use a scratch copy).
"""
import json, os, pathlib, re, subprocess, sys, threading, time
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import streamlit as st
from aiosmtpd.controller import Controller
from sqlalchemy import text

RESULTS = []
def check(name, cond, extra=""):
    RESULTS.append((name, bool(cond)))
    print(("  PASS " if cond else "  FAIL ") + name + (f"  [{extra}]" if (extra and not cond) else ""))

def expect_err(fn, *a, contains="", exc=None):
    from app_core.services import ServiceError
    try:
        fn(*a)
    except (exc or (ServiceError, PermissionError)) as e:
        return contains.lower() in str(e).lower()
    return False

# ---------------------------------------------------------------- 1. migration is additive only
env_admin = {**os.environ, "DB_USER": os.environ["ADMIN_DB_USER"], "DB_PASSWORD": os.environ["ADMIN_DB_PASSWORD"]}
out = subprocess.run([sys.executable, str(ROOT / "scripts/apply_auth_migration.py")], env=env_admin, capture_output=True, text=True)
print(out.stdout.strip().splitlines()[-2:] if out.stdout else out.stderr[-300:])
check("migration adds 3 tables and leaves every existing table's row count identical", out.returncode == 0 and "identical row counts" in out.stdout)
out2 = subprocess.run([sys.executable, str(ROOT / "scripts/apply_auth_migration.py")], env=env_admin, capture_output=True, text=True)
check("migration is re-runnable (idempotent, no drops)", out2.returncode == 0)

# ---------------------------------------------------------------- 2. import existing users (roles + hashes preserved)
imp = subprocess.run([sys.executable, str(ROOT / "scripts/import_users.py"), "--email", "admin=admin@test.example",
                      "--email", "recruiter=rec@test.example", "--email", "viewer=view@test.example"], capture_output=True, text=True)
check("existing users imported", imp.returncode == 0 and imp.stdout.count("imported") == 3, imp.stderr[-200:])
from app_core import accounts, auth, db, emailer, services as S
class _R:
    def __init__(self, rows): self.rows = rows
    def scalar(self): return self.rows[0][0] if self.rows else None
    def first(self): return self.rows[0] if self.rows else None
    def __iter__(self): return iter(self.rows)
def qx(stmt, params=None):
    with db.get_engine().connect() as c:
        return _R(c.execute(stmt, params or {}).fetchall())
cfg = json.loads(os.environ["APP_USERS"])
rows = {r[0]: (r[1], r[2]) for r in qx(text("SELECT username, role, password_hash FROM app_user"))}
check("roles and password hashes preserved exactly", all(rows[u][0] == cfg[u]["role"] and rows[u][1] == cfg[u]["password_hash"] for u in cfg))
check("old logins still work after import (same password)", accounts.login("admin", "Admin#2026")[0] is not None)

# ---------------------------------------------------------------- SMTP sink
inbox = []
class Handler:
    async def handle_DATA(self, server, session, envelope):
        import email
        msg = email.message_from_bytes(envelope.content)                      # decode like a real mail client
        inbox.append((envelope.rcpt_tos, msg.get_payload(decode=True).decode("utf8", "replace")))
        return "250 OK"
ctl = Controller(Handler(), hostname="127.0.0.1", port=8025); ctl.start()
os.environ.update(EMAIL_HOST="127.0.0.1", EMAIL_PORT="8025", EMAIL_FROM="noreply@test.example", EMAIL_SECURITY="none")
os.environ["APP_BASE_URL"] = "https://rms.test.example"
check("email service reports configured", emailer.is_configured())

def as_user(u):
    st.session_state = {"user": u}
    auth.current_user = lambda: st.session_state.get("user")
    accounts.current_user = auth.current_user

def uid(name): return qx(text("SELECT user_id FROM app_user WHERE username=:u"), {"u": name}).scalar()
admin, _ = accounts.login("admin", "Admin#2026")
as_user(admin)

# ---------------------------------------------------------------- 3. login behaviour
u1, m1 = accounts.login("admin@test.example", "Admin#2026")
check("login works with email as well as username", u1 is not None)
_, m_wrong = accounts.login("admin", "wrong"); _, m_unknown = accounts.login("nobody", "wrong")
check("wrong password and unknown user give the SAME generic message", m_wrong == m_unknown == accounts.GENERIC_LOGIN_ERROR)
for _ in range(5): accounts.login("viewer", "bad-pass-1")
u_lock, m_lock = accounts.login("viewer", "Viewer#2026")
check("account locks after 5 failures (even the correct password is refused)", u_lock is None and "try again" in m_lock.lower(), m_lock)
S_unlock = accounts.unlock_user(uid("viewer"))
check("administrator can unlock; user can sign in again", accounts.login("viewer", "Viewer#2026")[0] is not None)

# ---------------------------------------------------------------- 4. password policy
check("policy rejects short / single-class / common / username-containing passwords",
      all(accounts.validate_password(p, "admin", "a@b.co") for p in ["Ab1!", "alllowercaseletters", "Password123", "xxAdminxx#9999"])
      and not accounts.validate_password("Tr1cky-Horse-Stapler", "admin", "a@b.co"))

# ---------------------------------------------------------------- 5. change password
as_user(accounts.login("recruiter", "Recruit#2026")[0])
check("change password: wrong current password rejected", expect_err(accounts.change_password, "nope", "New-Passw0rd!x", "New-Passw0rd!x", contains="current password is incorrect"))
check("change password: mismatch rejected", expect_err(accounts.change_password, "Recruit#2026", "New-Passw0rd!x", "Different-1!x", contains="do not match"))
check("change password: weak rejected", expect_err(accounts.change_password, "Recruit#2026", "short1!", "short1!", contains="at least 10"))
check("change password: same as current rejected", expect_err(accounts.change_password, "Recruit#2026", "Recruit#2026", "Recruit#2026", contains="different"))
msg = accounts.change_password("Recruit#2026", "New-Passw0rd!x", "New-Passw0rd!x")
check("change password succeeds; new works, old no longer works",
      "changed" in msg and accounts.login("recruiter", "New-Passw0rd!x")[0] and not accounts.login("recruiter", "Recruit#2026")[0])
check("stored password is a salted hash, never plain text",
      qx(text("SELECT password_hash FROM app_user WHERE username='recruiter'")).scalar().startswith("pbkdf2_sha256$")
      and "New-Passw0rd" not in json.dumps([list(r) for r in qx(text("SELECT * FROM app_user"))], default=str)
      and "New-Passw0rd" not in json.dumps([list(r) for r in qx(text("SELECT * FROM auth_event"))], default=str))

# ---------------------------------------------------------------- 6. profile and preferences
accounts.update_profile("Recruiter Renamed", "rec.new@test.example")
check("profile update works (name + email)", qx(text("SELECT full_name, email FROM app_user WHERE username='recruiter'")).first() == ("Recruiter Renamed", "rec.new@test.example"))
check("profile update rejects an email used by another account", expect_err(accounts.update_profile, "X", "admin@test.example", contains="already used"))
check("a user cannot change their own role (profile update has no role path)", qx(text("SELECT role FROM app_user WHERE username='recruiter'")).scalar() == "recruiter")
accounts.save_preferences({"landing_page": "Candidates", "compact_tables": True})
check("preferences saved", accounts.reload_user(uid("recruiter"))["preferences"] == {"landing_page": "Candidates", "compact_tables": True})

# ---------------------------------------------------------------- 7. RBAC on every admin function
calls = [(accounts.create_user, ("x1", "x1@t.example", "X", "viewer", None)), (accounts.update_user, (1, "A", "a@t.example", "admin", None)),
         (accounts.set_active, (1, False)), (accounts.admin_reset_password, (1,)), (accounts.unlock_user, (1,))]
rec_ok = all(expect_err(f, *a, contains="admin", exc=PermissionError) for f, a in calls)
as_user(accounts.login("viewer", "Viewer#2026")[0])
view_ok = all(expect_err(f, *a, contains="admin", exc=PermissionError) for f, a in calls)
check("backend refuses every admin function for recruiter and viewer roles", rec_ok and view_ok)

# ---------------------------------------------------------------- 8. admin user management
as_user(accounts.login("admin", "Admin#2026")[0])
msg = accounts.create_user("new.hire", "new.hire@test.example", "New Hire", "viewer", None)
tmp = re.search(r"Temporary password .*?: (\S+)$", msg).group(1)
nu, _ = accounts.login("new.hire", tmp)
check("admin creates user; temp password works once and forces a password change", nu is not None and nu["must_change_password"])
check("duplicate username/email rejected on create", expect_err(accounts.create_user, "new.hire", "z@t.example", "Z", "viewer", None, contains="already in use"))
check("only existing roles can be assigned", expect_err(accounts.create_user, "bad.role", "br@t.example", "B", "superuser", None, contains="existing role"))
accounts.update_user(uid("new.hire"), "New Hire", "new.hire@test.example", "recruiter", None)
check("admin changes a role", accounts.reload_user(uid("new.hire"))["role"] == "recruiter")
accounts.set_active(uid("new.hire"), False)
check("deactivated account cannot sign in and is dropped from live sessions",
      accounts.login("new.hire", tmp)[0] is None and accounts.reload_user(uid("new.hire")) is None)
accounts.set_active(uid("new.hire"), True)
check("admin can reactivate", accounts.reload_user(uid("new.hire")) is not None)
check("admin cannot demote or deactivate themselves", expect_err(accounts.update_user, uid("admin"), "A", "admin@test.example", "viewer", None, contains="own administrator")
      and expect_err(accounts.set_active, uid("admin"), False, contains="own account"))
msg = accounts.admin_reset_password(uid("new.hire"))
tmp2 = re.search(r"Temporary password .*?: (\S+)$", msg).group(1)
check("admin password reset issues a new temporary password and forces change", accounts.login("new.hire", tmp2)[0]["must_change_password"] and not accounts.login("new.hire", tmp)[0])
# last-active-admin guard: simulate a stale session of an admin whose account was just deactivated
with db.get_engine().begin() as c:
    c.execute(text("UPDATE app_user SET role='admin' WHERE username='new.hire'"))
    c.execute(text("UPDATE app_user SET is_active=0 WHERE username='admin'"))
check("the last active administrator cannot be demoted or deactivated",
      expect_err(accounts.update_user, uid("new.hire"), "New Hire", "new.hire@test.example", "viewer", None, contains="at least one active administrator")
      and expect_err(accounts.set_active, uid("new.hire"), False, contains="at least one active administrator"))
with db.get_engine().begin() as c:
    c.execute(text("UPDATE app_user SET is_active=1 WHERE username='admin'"))
    c.execute(text("UPDATE app_user SET role='recruiter' WHERE username='new.hire'"))

# ---------------------------------------------------------------- 9. forgot / reset password with the email service
st.session_state = {}; auth.current_user = lambda: None
inbox.clear()
msg_unknown = accounts.request_reset("nobody@test.example"); time.sleep(.3)
msg_known = accounts.request_reset("view@test.example"); time.sleep(.5)
check("reset request answers identically for unknown and registered emails", msg_unknown == msg_known == accounts.GENERIC_RESET_MESSAGE)
check("email sent only to the registered address", len(inbox) == 1 and inbox[0][0] == ["view@test.example"])
token = re.search(r"reset_token=(\S+)", inbox[0][1]).group(1)
check("email link uses the configured base URL", "https://rms.test.example/?reset_token=" in inbox[0][1])
allrows = json.dumps([list(r) for r in qx(text("SELECT * FROM password_reset_token"))], default=str)
check("only a SHA-256 hash of the token is stored (raw token is not in the database)", token not in allrows and accounts.hash_token(token) in allrows)
check("token valid before use", accounts.token_user(token) is not None)
check("weak new password rejected and token stays valid", expect_err(accounts.reset_password, token, "weak", "weak", contains="at least 10") and accounts.token_user(token))
check("mismatch rejected", expect_err(accounts.reset_password, token, "Brand-New-Pass9!", "Other-New-Pass9!", contains="do not match"))
accounts.reset_password(token, "Brand-New-Pass9!", "Brand-New-Pass9!")
check("password reset works; user can sign in with the new password", accounts.login("viewer", "Brand-New-Pass9!")[0] is not None)
check("token is single-use (reuse rejected)", expect_err(accounts.reset_password, token, "Another-Pass-77!", "Another-Pass-77!", contains="invalid, expired"))
inbox.clear(); accounts.request_reset("view@test.example"); time.sleep(.4)
t_old = re.search(r"reset_token=(\S+)", inbox[0][1]).group(1)
accounts.request_reset("view@test.example"); time.sleep(.4)
t_new = re.search(r"reset_token=(\S+)", inbox[1][1]).group(1)
check("a new request invalidates the previous token", accounts.token_user(t_old) is None and accounts.token_user(t_new) is not None)
with db.get_engine().begin() as c: c.execute(text("UPDATE password_reset_token SET expires_at = NOW() - INTERVAL 1 MINUTE WHERE used_at IS NULL"))
check("expired token rejected", accounts.token_user(t_new) is None and expect_err(accounts.reset_password, t_new, "Another-Pass-77!", "Another-Pass-77!", contains="invalid, expired"))
inbox.clear()
for _ in range(4): accounts.request_reset("rec.new@test.example")
time.sleep(.6)
check("rate limit: at most 3 reset emails per address per hour", len(inbox) == 3)
ctl.stop(); inbox.clear()
check("SMTP outage does not leak or crash (still the generic message)", accounts.request_reset("admin@test.example") == accounts.GENERIC_RESET_MESSAGE)
ev = [r[0] for r in qx(text("SELECT event_type FROM auth_event"))]
check("security events are recorded (login, lock, reset, email failure)", {"login_ok", "login_failed", "account_locked", "password_reset", "reset_email_failed"} <= set(ev))
check("employee/recruitment tables untouched by account activity",
      qx(text("SELECT COUNT(*) FROM candidate")).scalar() == 184)

failed = [n for n, ok in RESULTS if not ok]
print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
if failed:
    print("FAILED:", failed); sys.exit(1)
