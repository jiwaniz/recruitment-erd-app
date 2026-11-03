import pathlib

import streamlit as st

from app_core import auth, db, ui

ui.page_header("About this system", "Technology, database status and the ERD")
ui.show_flash()

user = auth.current_user()
ok, msg = db.check_connection()
cfg_name = db.db_name()
c1, c2, c3 = st.columns(3)
c1.metric("Database", cfg_name)
c2.metric("Connection", "Online" if ok else "Offline")
c3.metric("Signed in as", f"{user['display_name']} ({user['role']})")
(st.success if ok else st.error)(msg)

st.subheader("Entity Relationship Diagram")
erd = pathlib.Path(__file__).resolve().parents[1] / "assets" / "erd_full.png"
if erd.exists():
    st.image(str(erd), caption="29 tables. Every foreign key has the same name as the primary key it references.")

st.subheader("Tables and row counts")
# MySQL 8 returns information_schema column names in capitals, so we alias and read by position
tables = db.q("SELECT table_name AS tname FROM information_schema.tables WHERE table_schema = DATABASE() AND table_type = 'BASE TABLE' ORDER BY table_name")
rows = [{"table": t, "rows": int(db.scalar(f"SELECT COUNT(*) FROM `{t}`"))} for t in tables.iloc[:, 0]]
ui.small_table(rows)

st.subheader("Roles")
st.markdown("""
| Role | Can do |
|---|---|
| viewer | View every page, filter, export CSV |
| recruiter | Everything a viewer can, plus add and edit vacancies, candidates, applications, interviews, offers |
| admin | Everything a recruiter can, plus approvals, closing requisitions and deleting records |
""")
st.caption("Built with Python, Streamlit, SQLAlchemy and MySQL.")
