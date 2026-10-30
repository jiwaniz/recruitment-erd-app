from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from app_core import db, queries as Q, ui

ui.page_header("Reports", "Reports built from live database records, with filters and CSV export")
ui.show_flash()

REPORTS = ["Candidate report", "Vacancy report", "Application status report", "Interview report",
           "Recruitment funnel", "Hiring report", "Department summary"]
report = st.selectbox("Choose a report", REPORTS)
st.divider()

if report == "Candidate report":
    df = Q.candidates()
    if df.empty:
        st.info("No candidate data.")
    else:
        c1, c2 = st.columns(2)
        only_applied = c1.checkbox("Only candidates who have applied", value=False)
        skill = c2.text_input("Skill contains")
        if only_applied:
            df = df[df["applications"] > 0]
        if skill:
            df = df[df["skills"].fillna("").str.contains(skill, case=False)]
        ui.metrics([("Candidates", len(df)), ("With applications", int((df["applications"] > 0).sum())),
                    ("Average applications each", f"{df['applications'].mean():.2f}" if len(df) else "0")])
        ui.show_table(df, "candidate_report.csv", key="dl_r1")
        if not df.empty:
            fig = px.histogram(df, x="applications", nbins=6, color_discrete_sequence=[ui.PRIMARY])
            fig.update_layout(height=280, margin=dict(l=0, r=0, t=10, b=0), xaxis_title="Applications per candidate")
            st.plotly_chart(fig, width="stretch")

elif report == "Vacancy report":
    df = Q.vacancies()
    if df.empty:
        st.info("No vacancy data.")
    else:
        dept = st.multiselect("Department", sorted(df["department_name"].unique()))
        if dept:
            df = df[df["department_name"].isin(dept)]
        df = df.assign(fill_rate_pct=(df["hires"] / df["headcount"] * 100).round(0))
        ui.metrics([("Vacancies", len(df)), ("Total headcount", int(df["headcount"].sum())), ("Hired", int(df["hires"].sum())),
                    ("Open positions", int(df["open_positions"].sum()))])
        ui.show_table(df.drop(columns=["requisition_status"]), "vacancy_report.csv", key="dl_r2")
        fig = px.bar(df, x="job_title", y=["hires", "open_positions"], barmode="stack",
                     color_discrete_sequence=[ui.COLORS[2], ui.COLORS[3]])
        fig.update_layout(height=320, margin=dict(l=0, r=0, t=10, b=0), xaxis_title="", yaxis_title="Positions")
        st.plotly_chart(fig, width="stretch")

elif report == "Application status report":
    df = Q.applications()
    if df.empty:
        st.info("No application data.")
    else:
        c1, c2 = st.columns(2)
        d1 = c1.date_input("Applied from", value=pd.to_datetime(df["date_applied"]).min().date())
        d2 = c2.date_input("Applied to", value=date.today())
        dd = pd.to_datetime(df["date_applied"]).dt.date
        df = df[(dd >= d1) & (dd <= d2)]
        by_dept = df.pivot_table(index="department_name", columns="status", values="application_id", aggfunc="count", fill_value=0)
        by_dept["Total"] = by_dept.sum(axis=1)
        st.markdown("**Applications by department and status**")
        ui.show_table(by_dept.reset_index(), "application_status_by_department.csv", key="dl_r3a")
        by_src = df.pivot_table(index="source_name", columns="status", values="application_id", aggfunc="count", fill_value=0)
        by_src["Total"] = by_src.sum(axis=1)
        st.markdown("**Applications by source and status**")
        ui.show_table(by_src.reset_index(), "application_status_by_source.csv", key="dl_r3b")
        cnt = df.groupby("status").size().reset_index(name="applications")
        fig = px.bar(cnt, x="status", y="applications", color="status", color_discrete_map=ui.STATUS_COLORS)
        fig.update_layout(showlegend=False, height=300, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, width="stretch")

elif report == "Interview report":
    df = Q.interviews()
    if df.empty:
        st.info("No interview data.")
    else:
        rnd = st.multiselect("Round", ["HR", "Technical", "Managerial", "Final"])
        if rnd:
            df = df[df["round_type"].isin(rnd)]
        summary = df.groupby("round_type").agg(interviews=("interview_id", "count"), avg_rating=("avg_rating", "mean"),
                                               completed=("status", lambda s: int((s == "Completed").sum()))).reset_index()
        summary["avg_rating"] = summary["avg_rating"].round(2)
        st.markdown("**Summary by round**")
        ui.show_table(summary, "interview_summary.csv", key="dl_r4a")
        st.markdown("**All interviews**")
        ui.show_table(df.drop(columns=["panel_size"]), "interview_report.csv", key="dl_r4b")
        fig = px.bar(summary, x="round_type", y="avg_rating", range_y=[0, 5], color_discrete_sequence=[ui.COLORS[5]])
        fig.update_layout(height=280, margin=dict(l=0, r=0, t=10, b=0), xaxis_title="")
        st.plotly_chart(fig, width="stretch")

elif report == "Recruitment funnel":
    stages = ["Applied", "Screening", "Interviewing", "Assessment", "BackgroundCheck", "Offered", "Hired"]
    jobs = Q.vacancies()
    pick = st.selectbox("Vacancy", ["All vacancies"] + [f"#{r.job_id} - {r.job_title}" for r in jobs.itertuples()]) if not jobs.empty else "All vacancies"
    if pick == "All vacancies":
        f = db.q("SELECT new_status AS stage, COUNT(DISTINCT application_id) AS applications FROM application_status_history GROUP BY new_status")
    else:
        jid = int(pick.split(" - ")[0].lstrip("#"))
        f = db.q("""SELECT h.new_status AS stage, COUNT(DISTINCT h.application_id) AS applications
                    FROM application_status_history h JOIN application a ON a.application_id = h.application_id
                    JOIN job_posting p ON p.posting_id = a.posting_id WHERE p.job_id = :j GROUP BY h.new_status""", j=jid)
    funnel = pd.DataFrame({"stage": stages}).merge(f, on="stage", how="left").fillna(0)
    funnel["applications"] = funnel["applications"].astype(int)
    top = funnel["applications"].iloc[0]
    funnel["conversion_from_applied_pct"] = (funnel["applications"] / top * 100).round(1) if top else 0
    funnel["conversion_from_previous_pct"] = (funnel["applications"] / funnel["applications"].shift(1) * 100).round(1)
    if top == 0:
        st.info("No pipeline data for this selection.")
    else:
        ui.show_table(funnel, "recruitment_funnel.csv", key="dl_r5")
        fig = px.funnel(funnel, x="applications", y="stage", color_discrete_sequence=[ui.PRIMARY])
        fig.update_layout(height=380, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, width="stretch")
        st.caption("A candidate is counted once at every stage reached (from the status history).")

elif report == "Hiring report":
    df = db.q("""
        SELECT c.candidate_name, j.job_title, d.department_name, s.source_name, a.date_applied,
               DATE(h.changed_date) AS hired_on, DATEDIFF(h.changed_date, a.date_applied) AS days_to_hire,
               o.salary_offered, j.salary_range_min, j.salary_range_max, o.start_date, ob.status AS onboarding_status
        FROM application a
        JOIN application_status_history h ON h.application_id = a.application_id AND h.new_status = 'Hired'
        JOIN candidate c ON c.candidate_id = a.candidate_id
        JOIN job_posting p ON p.posting_id = a.posting_id JOIN job j ON j.job_id = p.job_id
        JOIN department d ON d.department_id = j.department_id JOIN source s ON s.source_id = p.source_id
        LEFT JOIN job_offer o ON o.application_id = a.application_id AND o.status = 'Accepted'
        LEFT JOIN onboarding ob ON ob.offer_id = o.offer_id
        WHERE a.status = 'Hired' ORDER BY h.changed_date DESC""")
    if df.empty:
        st.info("No candidates have been hired yet.")
    else:
        ui.metrics([("Hires", len(df)), ("Average days to hire", f"{df['days_to_hire'].mean():.0f}"),
                    ("Average salary offered", ui.pkr(df["salary_offered"].mean()))])
        ui.show_table(df, "hiring_report.csv", key="dl_r6")
        fig = px.bar(df, x="candidate_name", y="days_to_hire", color="department_name")
        fig.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0), xaxis_title="")
        st.plotly_chart(fig, width="stretch")

else:
    df = db.q("""
        SELECT d.department_id, d.department_name, d.location,
               (SELECT COUNT(*) FROM employee e WHERE e.department_id = d.department_id) AS employees,
               (SELECT COUNT(*) FROM requisition_request r WHERE r.department_id = d.department_id) AS requisitions,
               (SELECT COALESCE(SUM(r.requested_headcount),0) FROM requisition_request r WHERE r.department_id = d.department_id
                   AND r.status IN ('Approved','Closed')) AS approved_headcount,
               (SELECT COUNT(*) FROM job j WHERE j.department_id = d.department_id) AS vacancies,
               (SELECT COUNT(*) FROM application a JOIN job_posting p ON p.posting_id = a.posting_id JOIN job j ON j.job_id = p.job_id
                   WHERE j.department_id = d.department_id) AS applications,
               (SELECT COUNT(*) FROM interview i JOIN application a ON a.application_id = i.application_id
                   JOIN job_posting p ON p.posting_id = a.posting_id JOIN job j ON j.job_id = p.job_id
                   WHERE j.department_id = d.department_id) AS interviews,
               (SELECT COUNT(*) FROM application a JOIN job_posting p ON p.posting_id = a.posting_id JOIN job j ON j.job_id = p.job_id
                   WHERE j.department_id = d.department_id AND a.status = 'Hired') AS hires
        FROM department d ORDER BY d.department_name, d.location""")
    only = st.checkbox("Hide departments with no recruitment activity", value=True)
    if only:
        df = df[(df["requisitions"] > 0) | (df["applications"] > 0)]
    if df.empty:
        st.info("No department activity.")
    else:
        ui.show_table(df, "department_summary.csv", key="dl_r7")
        fig = px.bar(df, x="department_name", y=["applications", "interviews", "hires"], barmode="group")
        fig.update_layout(height=340, margin=dict(l=0, r=0, t=10, b=0), xaxis_title="")
        st.plotly_chart(fig, width="stretch")
