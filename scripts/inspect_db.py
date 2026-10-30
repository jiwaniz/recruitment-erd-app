"""
Read-only inspection of the recruitment database.

Run it against ANY MySQL server (your local one or the cloud one):
    python scripts/inspect_db.py            # uses .env or .streamlit/secrets.toml
It only runs SELECT / SHOW / INFORMATION_SCHEMA queries. It never changes data.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sqlalchemy import text
from app_core.db import get_engine, db_name

CHECKS = {
    "Applications whose status disagrees with the last status-history row": """
        SELECT COUNT(*) FROM application a JOIN (
          SELECT h.application_id, h.new_status FROM application_status_history h
          JOIN (SELECT application_id, MAX(log_id) m FROM application_status_history GROUP BY application_id) x
            ON x.m = h.log_id) l ON l.application_id = a.application_id
        WHERE a.status <> l.new_status""",
    "Applications with no status-history rows": """
        SELECT COUNT(*) FROM application a
        WHERE NOT EXISTS (SELECT 1 FROM application_status_history h WHERE h.application_id = a.application_id)""",
    "Hired applications without an accepted offer": """
        SELECT COUNT(*) FROM application a WHERE a.status='Hired' AND NOT EXISTS
        (SELECT 1 FROM job_offer o WHERE o.application_id=a.application_id AND o.status='Accepted')""",
    "Accepted offers without an onboarding record": """
        SELECT COUNT(*) FROM job_offer o WHERE o.status='Accepted'
        AND NOT EXISTS (SELECT 1 FROM onboarding b WHERE b.offer_id=o.offer_id)""",
    "Interview evaluations by someone not on the panel": """
        SELECT COUNT(*) FROM interview_evaluation e LEFT JOIN interview_participant p
        ON p.interview_id=e.interview_id AND p.employee_id=e.employee_id WHERE p.participant_id IS NULL""",
    "Candidates without exactly one primary resume": """
        SELECT COUNT(*) FROM (SELECT c.candidate_id FROM candidate c LEFT JOIN resume r
        ON r.candidate_id=c.candidate_id AND r.is_primary=1 GROUP BY c.candidate_id HAVING COUNT(r.resume_id)<>1) t""",
    "Jobs whose requisition is not Approved/Closed": """
        SELECT COUNT(*) FROM job j JOIN requisition_request r ON r.requisition_id=j.requisition_id
        WHERE r.status NOT IN ('Approved','Closed')""",
    "Job offers above the job's maximum salary": """
        SELECT COUNT(*) FROM job_offer o JOIN application a ON a.application_id=o.application_id
        JOIN job_posting p ON p.posting_id=a.posting_id JOIN job j ON j.job_id=p.job_id
        WHERE o.salary_offered > j.salary_range_max""",
}

def q(conn, sql, **p):
    return conn.execute(text(sql), p).fetchall()

def main():
    eng = get_engine()
    db = db_name()
    out = []
    w = out.append
    with eng.connect() as c:
        w(f"# Database inspection: `{db}`\n")
        w(f"Server version: `{q(c, 'SELECT VERSION()')[0][0]}`\n")
        tables = q(c, "SELECT table_name, table_type, table_rows, engine FROM information_schema.tables "
                      "WHERE table_schema=:d ORDER BY table_name", d=db)
        w(f"## 1. Tables and views ({len(tables)})\n")
        w("| Name | Type | Engine | Rows (exact) |\n|---|---|---|---|")
        for name, ttype, _, engine in tables:
            n = q(c, f"SELECT COUNT(*) FROM `{name}`")[0][0] if ttype == "BASE TABLE" else "-"
            w(f"| {name} | {ttype} | {engine or ''} | {n} |")
        w("\n## 2. Columns, keys and defaults\n")
        for name, ttype, *_ in tables:
            w(f"### {name}\n")
            w("| Column | Type | Null | Key | Default | Extra |\n|---|---|---|---|---|---|")
            for col, ctype, nul, key, dflt, extra in q(c, "SELECT column_name, column_type, is_nullable, column_key, "
                    "column_default, extra FROM information_schema.columns WHERE table_schema=:d AND table_name=:t "
                    "ORDER BY ordinal_position", d=db, t=name):
                w(f"| {col} | {ctype} | {nul} | {key} | {'' if dflt is None else dflt} | {extra} |")
            w("")
        w("## 3. Foreign keys\n")
        fks = q(c, "SELECT k.table_name, k.column_name, k.referenced_table_name, k.referenced_column_name, k.constraint_name "
                   "FROM information_schema.key_column_usage k WHERE k.table_schema=:d AND k.referenced_table_name IS NOT NULL "
                   "ORDER BY k.table_name, k.constraint_name", d=db)
        w("| Child table | Column | Parent table | Parent column | Constraint |\n|---|---|---|---|---|")
        for t, col, pt, pc, cn in fks:
            w(f"| {t} | {col} | {pt} | {pc} | {cn} |")
        w(f"\nTotal foreign keys: **{len(fks)}**\n")
        w("## 4. Indexes and unique constraints\n")
        w("| Table | Index | Unique | Columns |\n|---|---|---|---|")
        for t, idx, nu, cols in q(c, "SELECT table_name, index_name, non_unique, GROUP_CONCAT(column_name ORDER BY seq_in_index) "
                "FROM information_schema.statistics WHERE table_schema=:d GROUP BY table_name, index_name, non_unique "
                "ORDER BY table_name, index_name", d=db):
            w(f"| {t} | {idx} | {'no' if nu else 'yes'} | {cols} |")
        w("\n## 5. Data-integrity checks (every value should be 0)\n")
        w("| Check | Violations |\n|---|---|")
        for label, sql in CHECKS.items():
            w(f"| {label} | {q(c, sql)[0][0]} |")
        w("\n## 6. Status distributions\n")
        for t, col in [("application", "status"), ("requisition_request", "status"), ("job_posting", "status"),
                       ("job_offer", "status"), ("onboarding", "status")]:
            rows = q(c, f"SELECT {col}, COUNT(*) FROM {t} GROUP BY {col} ORDER BY COUNT(*) DESC")
            w(f"- **{t}.{col}**: " + ", ".join(f"{r[0]} ({r[1]})" for r in rows))
    print("\n".join(out))

if __name__ == "__main__":
    main()
