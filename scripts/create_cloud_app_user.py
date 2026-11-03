"""
Create (or update) the limited database account that the web application uses in the cloud.

Run it ONCE with the ADMIN connection settings in your environment (DB_HOST, DB_PORT, DB_NAME,
DB_USER=avnadmin, DB_PASSWORD, DB_SSL_CA) and the new account's password in NEW_APP_DB_PASSWORD:

    $env:NEW_APP_DB_PASSWORD="a-strong-password-for-the-app-account"
    python scripts/create_cloud_app_user.py

The account gets SELECT, INSERT, UPDATE, DELETE on the current database only (no DROP / ALTER / CREATE).
Running it again just resets the password and re-applies the permissions.
"""
import os
import pathlib
import sys

from sqlalchemy import text

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from app_core.db import get_engine, db_name   # noqa: E402

user = os.environ.get("NEW_APP_DB_USER", "rms_app")
password = os.environ.get("NEW_APP_DB_PASSWORD", "")
if len(password) < 12:
    sys.exit("Set NEW_APP_DB_PASSWORD to a password of at least 12 characters first.")
if not user.replace("_", "").isalnum():
    sys.exit("NEW_APP_DB_USER may only contain letters, digits and underscores.")

db = db_name()
if not db.replace("_", "").isalnum():
    sys.exit("Unexpected database name.")

with get_engine().begin() as conn:
    conn.execute(text(f"CREATE USER IF NOT EXISTS '{user}'@'%' IDENTIFIED BY :pw"), {"pw": password})
    conn.execute(text(f"ALTER USER '{user}'@'%' IDENTIFIED BY :pw"), {"pw": password})
    conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON `{db}`.* TO '{user}'@'%'"))
    grants = [r[0] for r in conn.execute(text(f"SHOW GRANTS FOR '{user}'@'%'"))]

print(f"Account '{user}' is ready on database '{db}'. Its permissions:")
for g in grants:
    print("  ", g)
