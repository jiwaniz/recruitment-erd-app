"""
Load the schema and sample data into the database that your configuration points at
(.env locally, or Streamlit secrets / environment variables for a cloud database).

    python scripts/load_sample_database.py            # creates the tables and fills them
    python scripts/load_sample_database.py --drop     # first DROPS all tables listed in the schema (asks to confirm)

Use the cloud files for a cloud database such as Aiven. The account you use here needs permission to
CREATE tables (the default admin account that the provider gives you is fine). The web application
itself should later use a limited account (see DEPLOYMENT_GUIDE.md).
"""
import argparse
import pathlib
import sys

from sqlalchemy import text

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from app_core.db import get_engine, db_name   # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1] / "database" / "cloud"
TABLES = ["onboarding", "offer_approval", "job_offer", "background_check", "assessment", "interview_evaluation",
          "interview_participant", "interview", "screening", "application_status_history", "application", "referral",
          "candidate_skill", "resume", "candidate", "job_skill", "job_posting", "job", "requisition_approval",
          "requisition_request", "employee", "assessment_type", "rejection_reason", "skill", "source", "location",
          "employment_type", "designation", "department"]


def split_statements(sql: str):
    """Split a SQL script on ';' while ignoring semicolons inside quoted text and comments."""
    out, buf, quote, i = [], [], None, 0
    while i < len(sql):
        ch = sql[i]
        if quote:
            buf.append(ch)
            if ch == "\\" and i + 1 < len(sql):
                buf.append(sql[i + 1]); i += 1
            elif ch == quote:
                if i + 1 < len(sql) and sql[i + 1] == quote:   # doubled quote
                    buf.append(sql[i + 1]); i += 1
                else:
                    quote = None
        elif ch in ("'", '"', "`"):
            quote = ch; buf.append(ch)
        elif ch == "-" and sql.startswith("--", i):
            j = sql.find("\n", i)
            i = len(sql) if j == -1 else j
            continue
        elif ch == ";":
            stmt = "".join(buf).strip()
            if stmt:
                out.append(stmt)
            buf = []
        else:
            buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--drop", action="store_true", help="drop the recruitment tables first")
    args = ap.parse_args()
    eng = get_engine()
    print(f"Target database: {db_name()}")
    if args.drop:
        if input("This DELETES the recruitment tables in that database. Type YES to continue: ") != "YES":
            sys.exit("Cancelled.")
        with eng.begin() as conn:
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
            for t in TABLES:
                conn.execute(text(f"DROP TABLE IF EXISTS `{t}`"))
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
    for name in ("01_schema_cloud.sql", "02_data_cloud.sql"):
        stmts = split_statements((ROOT / name).read_text(encoding="utf8"))
        print(f"{name}: {len(stmts)} statements")
        with eng.begin() as conn:          # one transaction per file: it either loads completely or not at all*
            for s in stmts:
                conn.execute(text(s.replace(":", "\\:")))   # a colon in text must not be read as a bind parameter
        print("  done")
    print("Sample database loaded. (*DDL statements commit automatically in MySQL.)")


if __name__ == "__main__":
    main()
