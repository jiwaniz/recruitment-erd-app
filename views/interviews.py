from datetime import date, datetime, time, timedelta

import pandas as pd
import streamlit as st

from app_core import auth, queries as Q, services as S, ui

def _open_iv(row):
    st.session_state["mi"] = int(row["interview_id"])
    ui.notify("success", f"{row['candidate_name']}: open the 'Update / feedback' tab.")


ui.page_header("Interviews", "Schedule interviews, manage the panel and record feedback")
ui.show_flash()
can_edit, is_admin = auth.has_role("recruiter"), auth.has_role("admin")
ROUNDS = ["HR", "Technical", "Managerial", "Final"]
MODES = ["Virtual", "Onsite", "Phone"]

t_list, t_sched, t_manage = st.tabs(["Interview schedule", "Schedule an interview", "Update / feedback"])
iv = Q.interviews()

with t_list:
    if iv.empty:
        st.info("No interviews have been scheduled yet.")
    else:
        up = iv[iv["status"] == "Scheduled"]
        ui.metrics([("Total interviews", len(iv)), ("Scheduled (upcoming)", len(up)),
                    ("Awaiting feedback", int((iv["status"] == "Awaiting feedback").sum())),
                    ("Completed", int((iv["status"] == "Completed").sum()))])
        c1, c2, c3, c4 = st.columns(4)
        rnd = c1.multiselect("Round", ROUNDS, key="i_round")
        stat = c2.multiselect("Status", ["Scheduled", "Awaiting feedback", "Completed"], key="i_stat")
        text = c3.text_input("Candidate or job", key="i_txt")
        mode = c4.multiselect("Mode", MODES, key="i_mode")
        d1, d2 = st.columns(2)
        dfrom = d1.date_input("From", value=iv["interview_date"].min().date(), key="i_from")
        dto = d2.date_input("To", value=max(date.today() + timedelta(days=30), iv["interview_date"].max().date()), key="i_to")
        df = iv
        if rnd:
            df = df[df["round_type"].isin(rnd)]
        if stat:
            df = df[df["status"].isin(stat)]
        if mode:
            df = df[df["mode"].isin(mode)]
        if text:
            df = df[df["candidate_name"].str.contains(text, case=False) | df["job_title"].str.contains(text, case=False)]
        df = df[(df["interview_date"].dt.date >= dfrom) & (df["interview_date"].dt.date <= dto)]
        ui.show_table(df, "interviews.csv", key="iv", label_col="candidate_name", actions=[("Open feedback / update", _open_iv)])

with t_sched:
    if not can_edit:
        st.info("Your role is read-only.")
    else:
        apps = Q.applications()
        ready = apps[apps["status"] == "Interviewing"]
        if ready.empty:
            st.warning("No application is currently in the 'Interviewing' stage. Shortlist a candidate first (Applications page).")
        else:
            with st.form("sched"):
                am = {int(r.application_id): f"#{r.application_id} - {r.candidate_name} for {r.job_title}" for r in ready.itertuples()}
                aid = st.selectbox("Application", list(am), format_func=am.get)
                c1, c2, c3, c4 = st.columns(4)
                rnd = c1.selectbox("Round", ROUNDS)
                d = c2.date_input("Date", value=date.today() + timedelta(days=1))
                t = c3.time_input("Time", value=time(11, 0))
                mode = c4.selectbox("Mode", MODES)
                emps = Q.employees()
                panel = st.multiselect("Panel members", [e[0] for e in emps], format_func=dict(emps).get)
                if ui.submit("Schedule interview"):
                    S.call(S.schedule_interview, int(aid), rnd, datetime.combine(d, t), mode, panel)
                    st.rerun()

with t_manage:
    if iv.empty:
        st.info("No interviews yet.")
    else:
        im = {int(r.interview_id): f"#{r.interview_id} - {r.candidate_name}, {r.round_type} ({r.interview_date:%d %b %Y}) [{r.status}]" for r in iv.itertuples()}
        iid = int(st.selectbox("Interview", list(im), format_func=im.get, key="mi"))
        row = iv[iv["interview_id"] == iid].iloc[0]
        ui.metrics([("Candidate", row["candidate_name"]), ("Vacancy", row["job_title"]), ("Round", row["round_type"]),
                    ("When", f"{row['interview_date']:%d %b %Y %H:%M}"), ("Status", row["status"])])
        pn, ev = Q.panel(iid), Q.evaluations(iid)
        a, b = st.columns(2)
        a.markdown("**Panel**")
        with a: ui.small_table(pn)
        b.markdown("**Feedback received**")
        if not ev.empty:
            with b: ui.small_table(ev)
        else:
            b.caption("No feedback yet.")
        if can_edit:
            st.divider()
            st.markdown("#### Record feedback")
            with st.form(f"fb_{iid}"):
                pm = {int(r.employee_id): r.employee_name for r in pn.itertuples()}
                who = st.selectbox("Evaluator (panel member)", list(pm), format_func=pm.get)
                c1, c2 = st.columns(2)
                rating = c1.slider("Rating (1 = poor, 5 = excellent)", 1, 5, 3)
                rec = c2.selectbox("Recommendation", ["StrongHire", "Hire", "NoHire", "StrongNoHire"], index=1)
                com = st.text_area("Comments")
                if ui.submit("Save feedback"):
                    S.call(S.record_evaluation, iid, int(who), rating, rec, com)
                    st.rerun()
            st.markdown("#### Reschedule / change the panel")
            with st.form(f"upd_{iid}"):
                c1, c2, c3 = st.columns(3)
                d = c1.date_input("Date", value=row["interview_date"].date())
                t = c2.time_input("Time", value=row["interview_date"].time())
                mode = c3.selectbox("Mode", MODES, index=MODES.index(row["mode"]))
                emps = Q.employees()
                panel = st.multiselect("Panel members", [e[0] for e in emps], default=[int(x) for x in pn["employee_id"]],
                                       format_func=dict(emps).get)
                if ui.submit("Save changes"):
                    S.call(S.update_interview, iid, datetime.combine(d, t), mode, panel)
                    st.rerun()
        if is_admin:
            st.markdown("#### Delete interview")
            st.caption("Only possible while no feedback has been submitted.")
            sure = st.checkbox("I confirm this interview should be deleted.", key=f"deliv_{iid}")
            if st.button("Delete interview", disabled=not sure, key=f"deliv_btn_{iid}"):
                S.call(S.delete_interview, iid)
                st.rerun()
