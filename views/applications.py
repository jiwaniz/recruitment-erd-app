from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from app_core import auth, db, queries as Q, services as S, ui

def _open_app(row):
    st.session_state["man_app"] = int(row["application_id"])
    ui.notify("success", f"{row['candidate_name']}: open the 'Manage an application' tab.")


ui.page_header("Applications", "Link candidates to vacancies and track every application through the pipeline")
ui.show_flash()
can_edit = auth.has_role("recruiter")
STAGES = ["Applied", "Screening", "Interviewing", "Assessment", "BackgroundCheck", "Offered", "Hired", "Rejected", "Withdrawn"]

t_pipe, t_all, t_new, t_manage = st.tabs(["Pipeline", "All applications", "New application", "Manage an application"])
apps = Q.applications()

with t_pipe:
    if apps.empty:
        st.info("No applications yet.")
    else:
        jobs = ["All vacancies"] + sorted(apps["job_title"].unique())
        pick = st.selectbox("Vacancy", jobs, key="pipe_job")
        df = apps if pick == "All vacancies" else apps[apps["job_title"] == pick]
        counts = df.groupby("status").size().reindex(STAGES, fill_value=0).reset_index(name="applications")
        cols = st.columns(len(STAGES))
        for col, r in zip(cols, counts.itertuples()):
            col.metric(r.status, int(r.applications))
        fig = px.bar(counts, x="status", y="applications", color="status", color_discrete_map=ui.STATUS_COLORS)
        fig.update_layout(showlegend=False, xaxis_title="", height=320, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, width="stretch")

with t_all:
    if apps.empty:
        st.info("No applications yet.")
    else:
        c1, c2, c3, c4 = st.columns(4)
        vac = c1.multiselect("Vacancy", sorted(apps["job_title"].unique()), key="a_vac")
        cand = c2.text_input("Candidate name", key="a_cand")
        stat = c3.multiselect("Status", STAGES, key="a_stat")
        src = c4.multiselect("Source", sorted(apps["source_name"].unique()), key="a_src")
        d1, d2 = st.columns(2)
        dfrom = d1.date_input("Applied from", value=pd.to_datetime(apps["date_applied"]).min().date(), key="a_from")
        dto = d2.date_input("Applied to", value=date.today(), key="a_to")
        df = apps
        if vac:
            df = df[df["job_title"].isin(vac)]
        if cand:
            df = df[df["candidate_name"].str.contains(cand, case=False, na=False)]
        if stat:
            df = df[df["status"].isin(stat)]
        if src:
            df = df[df["source_name"].isin(src)]
        d = pd.to_datetime(df["date_applied"]).dt.date
        df = df[(d >= dfrom) & (d <= dto)]
        ui.show_table(df, "applications.csv", key="apps", label_col="candidate_name", actions=[("Manage application", _open_app)])

with t_new:
    if not can_edit:
        st.info("Your role is read-only.")
    else:
        posts = Q.postings()
        active = posts[posts["status"] == "Active"]
        if active.empty:
            st.warning("There are no Active postings to apply to.")
        else:
            with st.form("new_app"):
                cand = ui.select_pair("Candidate", Q.candidates_list(), "na_cand")
                pm = {int(r.posting_id): f"#{r.posting_id} - {r.job_title} via {r.source_name}" for r in active.itertuples()}
                pid = st.selectbox("Job posting", list(pm), format_func=pm.get)
                when = st.date_input("Date applied", value=date.today())
                by = ui.select_pair("Recorded by", Q.employees(("Recruiter", "HRAdmin")), "na_by", allow_none=True, none_label="- system / me -")
                if ui.submit("Create application"):
                    S.call(S.create_application, cand, int(pid), when, by)
                    st.rerun()

with t_manage:
    if apps.empty:
        st.info("No applications yet.")
    else:
        am = {int(r.application_id): f"#{r.application_id} - {r.candidate_name} for {r.job_title} [{r.status}]" for r in apps.itertuples()}
        aid = int(st.selectbox("Application", list(am), format_func=am.get, key="man_app"))
        row = apps[apps["application_id"] == aid].iloc[0]
        status = row["status"]
        ui.metrics([("Candidate", row["candidate_name"]), ("Vacancy", row["job_title"]), ("Source", row["source_name"]),
                    ("Applied", str(row["date_applied"])), ("Status", status)])
        h1, h2 = st.columns(2)
        with h1:
            st.markdown("**Status history**")
            ui.small_table(Q.status_history(aid))
            st.markdown("**Screening**")
            sc = Q.app_screenings(aid)
            if not sc.empty:
                ui.small_table(sc)
            else:
                st.caption("No screening recorded.")
        with h2:
            st.markdown("**Assessments**")
            asd = Q.app_assessments(aid)
            if not asd.empty:
                ui.small_table(asd)
            else:
                st.caption("No assessments recorded.")
            st.markdown("**Background checks**")
            bg = Q.app_background(aid)
            if not bg.empty:
                ui.small_table(bg)
            else:
                st.caption("No background checks recorded.")

        if can_edit:
            st.divider()
            hr = Q.employees(("Recruiter", "HRAdmin"))
            reasons = Q.rejection_reasons()
            nexts = S.TRANSITIONS.get(status, [])
            st.markdown("#### Move to another stage")
            if not nexts:
                st.info(f"'{status}' is a final status, so it cannot be changed here.")
            else:
                if status == "BackgroundCheck":
                    st.caption("The 'Offered' stage is set automatically when all offer approvals are complete (Hiring page).")
                with st.form(f"chg_{aid}"):
                    new = st.selectbox("New status", nexts)
                    reason = ui.select_pair("Reason (required for Rejected / Withdrawn)", reasons, f"rs_{aid}", allow_none=True, none_label="- none -")
                    by = ui.select_pair("Changed by", hr, f"by_{aid}", allow_none=True, none_label="- me -")
                    if ui.submit("Update status"):
                        S.call(S.change_status, aid, new, by, reason)
                        st.rerun()
            if status in ("Applied", "Screening"):
                st.markdown("#### Record screening")
                with st.form(f"scr_{aid}"):
                    rv = ui.select_pair("Reviewer", hr, f"scr_rv_{aid}")
                    out = st.selectbox("Outcome", ["Shortlisted", "Rejected", "OnHold"])
                    score = st.slider("Score", 0, 100, 60)
                    reason = ui.select_pair("Rejection reason (if rejected)", [r for r in reasons if str(r[1]).startswith("Screening")], f"scr_rs_{aid}", allow_none=True, none_label="- none -")
                    notes = st.text_area("Notes")
                    if ui.submit("Save screening"):
                        S.call(S.add_screening, aid, rv, out, score, notes, reason)
                        st.rerun()
            if status in ("Interviewing", "Assessment"):
                st.markdown("#### Record an assessment")
                with st.form(f"asm_{aid}"):
                    typ = ui.select_pair("Assessment type", Q.assessment_types(), f"asm_t_{aid}")
                    score = st.slider("Score", 0, 100, 60, key=f"asm_s_{aid}")
                    when = st.date_input("Date", value=date.today(), key=f"asm_d_{aid}")
                    remarks = st.text_input("Remarks", key=f"asm_r_{aid}")
                    if ui.submit("Save assessment"):
                        S.call(S.add_assessment, aid, typ, score, remarks, when)
                        st.rerun()
            if status in ("Assessment", "BackgroundCheck"):
                st.markdown("#### Record a background check")
                with st.form(f"bgc_{aid}"):
                    prov = st.text_input("Provider")
                    c1, c2, c3 = st.columns(3)
                    ini = c1.date_input("Initiated", value=date.today(), key=f"bg_i_{aid}")
                    stt = c2.selectbox("Status", ["Pending", "InProgress", "Completed"], key=f"bg_s_{aid}")
                    res = c3.selectbox("Result (if completed)", ["Clear", "Flagged", "Failed"], key=f"bg_r_{aid}")
                    comp = st.date_input("Completion date (if completed)", value=date.today(), key=f"bg_c_{aid}")
                    if ui.submit("Save background check"):
                        S.call(S.add_background_check, aid, prov, ini, comp if stt == "Completed" else None, stt, res)
                        st.rerun()
