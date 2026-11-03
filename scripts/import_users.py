"""
Copy the existing logins (from .env APP_USERS or Streamlit secrets) into the new app_user table, keeping each user's
role and password hash. Nothing is re-hashed or changed. Each user needs an email address for password reset.

    python scripts/import_users.py --email admin=you@example.com --email supervisor=boss@example.com
"""
import argparse
import pathlib
import sys

from sqlalchemy import text

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from app_core.config import get_users_config   # noqa: E402
from app_core.db import get_engine   # noqa: E402
from app_core.services import EMAIL_RE   # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--email", action="append", default=[], help="username=email (repeat for each user)")
args = ap.parse_args()
emails = dict(x.split("=", 1) for x in args.email)
users = get_users_config()
if not users:
    sys.exit("No users found in .env / secrets.")
missing = [u for u in users if not EMAIL_RE.match(emails.get(u, ""))]
if missing:
    sys.exit("Give a valid --email username=address for: " + ", ".join(missing))
with get_engine().begin() as c:
    for uname, info in users.items():
        exists = c.execute(text("SELECT 1 FROM app_user WHERE username = :u OR email = :e"), {"u": uname, "e": emails[uname].lower()}).first()
        if exists:
            print(f"skipped {uname}: already imported")
            continue
        c.execute(text("INSERT INTO app_user (username, email, full_name, password_hash, role, employee_id) "
                       "VALUES (:u, :e, :n, :h, :r, :emp)"),
                  {"u": uname, "e": emails[uname].lower(), "n": info.get("display_name", uname), "h": info["password_hash"],
                   "r": info["role"], "emp": info.get("employee_id")})
        print(f"imported {uname} (role {info['role']})")
