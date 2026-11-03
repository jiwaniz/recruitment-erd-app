"""
Apply the (approved) authentication migration. Run with ADMIN connection settings (DB_USER with CREATE TABLE rights).
It adds three new tables, checks that every existing table still has exactly the same row count, and changes nothing else.

    python scripts/apply_auth_migration.py
"""
import pathlib
import sys

from sqlalchemy import text

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from app_core.db import get_engine, db_name   # noqa: E402
from load_sample_database import split_statements   # noqa: E402

NEW = {"app_user", "password_reset_token", "auth_event"}


def counts(conn):
    names = [r[0] for r in conn.execute(text("SELECT table_name AS n FROM information_schema.tables WHERE table_schema = DATABASE() AND table_type = 'BASE TABLE'"))]
    return {n: conn.execute(text(f"SELECT COUNT(*) FROM `{n}`")).scalar() for n in names if n.lower() not in NEW}


eng = get_engine()
with eng.connect() as c:
    before = counts(c)
print(f"Database {db_name()}: {len(before)} existing tables checked before the migration.")
sql = (ROOT / "database" / "migrations" / "001_auth_tables.sql").read_text(encoding="utf8")
with eng.begin() as c:
    for stmt in split_statements(sql):
        c.execute(text(stmt))
with eng.connect() as c:
    after = counts(c)
    created = {r[0].lower() for r in c.execute(text("SELECT table_name AS n FROM information_schema.tables WHERE table_schema = DATABASE()"))} & NEW
assert before == after, "Row counts changed - this must never happen"
print(f"Created / present: {sorted(created)}. All {len(after)} existing tables have identical row counts. Done.")
