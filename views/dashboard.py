import pandas as pd
import plotly.express as px
import streamlit as st

from app_core import db, ui

ui.page_header("Dashboard", "Live recruitment KPIs calculated from the database")
ui.show_flash()

k = db.q("""
    SELECT (SELECT COUNT(*) FROM candidate) AS candidates,
           (SELECT COUNT(*) FROM job) AS vacancies,
           (SELECT COUNT(DISTINCT job_id) FROM job_posting WHERE status = 'Active') AS open_vacancies,
           (SELECT COUNT(*) FROM application) AS applications,
           (SELECT COUNT(*) FROM interview) AS interviews,
           (SELECT COUNT(*) FROM application WHERE status = 'Hired') AS hires,
           (SELECT COUNT(*) FROM job_offer) AS offers,
           (SELECT COUNT(*) FROM job_offer WHERE status = 'Accepted') AS accepted,
           (SELECT COUNT(*) FROM job_offer WHERE status IN ('Accepted','Declined')) AS answered,
           (SELECT COUNT(*) FROM requisition_request WHERE status = 'PendingApproval') AS pending_req,
           (SELECT COUNT(*) FROM interview WHERE interview_date >= NOW() AND interview_date < NOW() + INTERVAL 7 DAY) AS upcoming,
           (SELECT COALESCE(SUM(r.requested_headcount), 0) FROM requisition_request r WHERE r.status = 'Approved') AS seats
""").iloc[0]

if int(k["candidates"]) == 0 and int(k["applications"]) == 0:
    st.info("The database has no recruitment records yet. Add candidates and applications to see statistics here.")

ui.metrics([("Candidates", f"{int(k['candidates']):,}"), ("Vacancies", f"{int(k['vacancies']):,}",
            "Jobs created from approved requisitions"), ("Applications", f"{int(k['applications']):,}"),
            ("Interviews", f"{int(k['interviews']):,}"), ("Hires", f"{int(k['hires']):,}")])

tth = db.scalar("""SELECT AVG(DATEDIFF(h.changed_date, a.date_applied)) FROM application a
                   JOIN application_status_history h ON h.application_id = a.application_id AND h.new_status = 'Hired'
                   WHERE a.status = 'Hired'""")
rate = (k["accepted"] / k["answered"] * 100) if k["answered"] else None
ui.metrics([("Open vacancies", f"{int(k['open_vacancies'])}", "Vacancies with at least one Active posting"),
            ("Offer acceptance", f"{rate:.0f}%" if rate is not None else "n/a", "Accepted / (Accepted + Declined)"),
            ("Avg. time to hire", f"{float(tth):.0f} days" if tth is not None and pd.notna(tth) else "n/a",
             "Application date to hire date"),
            ("Requisitions awaiting approval", f"{int(k['pending_req'])}"),
            ("Interviews in next 7 days", f"{int(k['upcoming'])}")])

st.divider()
left, right = st.columns(2)

with left:
    st.subheader("Recruitment pipeline (candidates who reached each stage)")
    stages = ["Applied", "Screening", "Interviewing", "Assessment", "BackgroundCheck", "Offered", "Hired"]
    reached = db.q("""SELECT new_status AS stage, COUNT(DISTINCT application_id) AS applications
                      FROM application_status_history GROUP BY new_status""")
    if reached.empty:
        st.info("No pipeline data yet.")
    else:
        funnel = pd.DataFrame({"stage": stages}).merge(reached, on="stage", how="left").fillna(0)
        fig = px.funnel(funnel, x="applications", y="stage", color_discrete_sequence=[ui.PRIMARY])
        fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=360)
        st.plotly_chart(fig, width="stretch")

with right:
    st.subheader("Application status distribution (today)")
    dist = db.q("SELECT status, COUNT(*) AS applications FROM application GROUP BY status ORDER BY applications DESC")
    if dist.empty:
        st.info("No applications yet.")
    else:
        fig = px.pie(dist, names="status", values="applications", hole=0.5, color="status",
                     color_discrete_map=ui.STATUS_COLORS)
        fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=360)
        st.plotly_chart(fig, width="stretch")

c1, c2, c3 = st.columns(3)
with c1:
    st.subheader("Requisition status")
    d = db.q("SELECT status, COUNT(*) AS requisitions FROM requisition_request GROUP BY status")
    if d.empty:
        st.info("No requisitions yet.")
    else:
        fig = px.bar(d, x="status", y="requisitions", color="status", color_discrete_map=ui.STATUS_COLORS)
        fig.update_layout(showlegend=False, margin=dict(l=0, r=0, t=10, b=0), height=300)
        st.plotly_chart(fig, width="stretch")
with c2:
    st.subheader("Posting status")
    d = db.q("SELECT status, COUNT(*) AS postings FROM job_posting GROUP BY status")
    if d.empty:
        st.info("No postings yet.")
    else:
        fig = px.bar(d, x="status", y="postings", color="status", color_discrete_map=ui.STATUS_COLORS)
        fig.update_layout(showlegend=False, margin=dict(l=0, r=0, t=10, b=0), height=300)
        st.plotly_chart(fig, width="stretch")
with c3:
    st.subheader("Applications by source")
    d = db.q("""SELECT s.source_name, COUNT(*) AS applications FROM application a
                JOIN job_posting p ON p.posting_id = a.posting_id JOIN source s ON s.source_id = p.source_id
                GROUP BY s.source_name ORDER BY applications DESC""")
    if d.empty:
        st.info("No applications yet.")
    else:
        fig = px.bar(d, x="applications", y="source_name", orientation="h", color_discrete_sequence=[ui.COLORS[1]])
        fig.update_layout(yaxis=dict(autorange="reversed", title=""), margin=dict(l=0, r=0, t=10, b=0), height=300)
        st.plotly_chart(fig, width="stretch")

c4, c5 = st.columns(2)
with c4:
    st.subheader("Applications by department")
    d = db.q("""SELECT d.department_name, COUNT(*) AS applications FROM application a
                JOIN job_posting p ON p.posting_id = a.posting_id JOIN job j ON j.job_id = p.job_id
                JOIN department d ON d.department_id = j.department_id GROUP BY d.department_name ORDER BY applications DESC""")
    if d.empty:
        st.info("No applications yet.")
    else:
        fig = px.bar(d, x="department_name", y="applications", color_discrete_sequence=[ui.PRIMARY])
        fig.update_layout(xaxis_title="", margin=dict(l=0, r=0, t=10, b=0), height=320)
        st.plotly_chart(fig, width="stretch")
with c5:
    st.subheader("Interviews by round and average rating")
    d = db.q("""SELECT i.round_type AS round, COUNT(DISTINCT i.interview_id) AS interviews,
                       ROUND(AVG(ev.rating), 2) AS avg_rating
                FROM interview i LEFT JOIN interview_evaluation ev ON ev.interview_id = i.interview_id
                GROUP BY i.round_type""")
    if d.empty:
        st.info("No interviews yet.")
    else:
        d["round"] = pd.Categorical(d["round"], ["HR", "Technical", "Managerial", "Final"], ordered=True)
        d = d.sort_values("round")
        fig = px.bar(d, x="round", y="interviews", text="avg_rating", color_discrete_sequence=[ui.COLORS[2]])
        fig.update_traces(texttemplate="avg %{text}", textposition="outside")
        fig.update_layout(xaxis_title="", margin=dict(l=0, r=0, t=20, b=0), height=320)
        st.plotly_chart(fig, width="stretch")

st.subheader("Open positions by vacancy")
from app_core import queries as Q          # noqa: E402
v = Q.vacancies()
if v.empty:
    st.info("No vacancies yet.")
else:
    open_v = v[v["open_positions"] > 0][["job_id", "job_title", "department_name", "headcount", "hires", "open_positions",
                                          "applications", "vacancy_status"]]
    ui.show_table(open_v, key="dash_open")
