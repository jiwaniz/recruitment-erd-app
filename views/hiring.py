from datetime import date, timedelta

import plotly.express as px
import streamlit as st

from app_core import auth, db, queries as Q, services as S, ui

def _open_offer(row):
    if row["status"] == "Sent":
        st.session_state["resp_offer"] = int(row["offer_id"])
        ui.notify("success", f"{row['candidate_name']}: open the 'Offer response' tab.")
    else:
        ui.notify("warning", f"Only offers with status Sent can receive a response (this one is {row['status']}).")


ui.page_header("Hiring and Selection", "Offers, approvals, selected candidates and onboarding")
ui.show_flash()
can_edit, is_admin = auth.has_role("recruiter"), auth.has_role("admin")

t_over, t_offers, t_new, t_appr, t_resp, t_onb = st.tabs(
    ["Overview", "Offers", "Create offer", "Offer approvals", "Offer response", "Onboarding"])
offers, onb = Q.offers(), Q.onboarding()

with t_over:
    hired = db.q("""
        SELECT c.candidate_name, j.job_title, d.department_name, a.date_applied,
               DATE(h.changed_date) AS hired_on, DATEDIFF(h.changed_date, a.date_applied) AS days_to_hire,
               o.salary_offered, o.start_date
        FROM application a
        JOIN application_status_history h ON h.application_id = a.application_id AND h.new_status = 'Hired'
        JOIN candidate c ON c.candidate_id = a.candidate_id
        JOIN job_posting p ON p.posting_id = a.posting_id JOIN job j ON j.job_id = p.job_id
        JOIN department d ON d.department_id = j.department_id
        LEFT JOIN job_offer o ON o.application_id = a.application_id AND o.status = 'Accepted'
        WHERE a.status = 'Hired' ORDER BY h.changed_date DESC""")
    ui.metrics([("Selected (hired) candidates", len(hired)), ("Offers made", len(offers)),
                ("Offers awaiting approval", int((offers["status"] == "PendingApproval").sum()) if not offers.empty else 0),
                ("Offers awaiting candidate reply", int((offers["status"] == "Sent").sum()) if not offers.empty else 0),
                ("Joining soon / onboarding", int((onb["status"] != "Completed").sum()) if not onb.empty else 0)])
    st.subheader("Selected candidates")
    ui.show_table(hired, "selected_candidates.csv", key="dl_hired")
    if not offers.empty:
        cnt = offers.groupby("status").size().reset_index(name="offers")
        fig = px.bar(cnt, x="status", y="offers", color="status", color_discrete_map={**ui.STATUS_COLORS, "Sent": "#0EA5E9",
                     "Accepted": "#10B981", "Declined": "#EF4444", "Withdrawn": "#64748B"})
        fig.update_layout(showlegend=False, height=280, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, width="stretch")

with t_offers:
    if offers.empty:
        st.info("No offers yet.")
    else:
        sf = st.multiselect("Status", ["Draft", "PendingApproval", "Sent", "Accepted", "Declined", "Withdrawn"], key="o_stat")
        df = offers[offers["status"].isin(sf)] if sf else offers
        ui.show_table(df, "offers.csv", key="offers", label_col="candidate_name", actions=[("Respond to offer", _open_offer)])
        oid = st.selectbox("Show approvals for offer", list(df["offer_id"]), key="o_pick") if not df.empty else None
        if oid:
            ui.small_table(Q.offer_approvals(int(oid)))

with t_new:
    if not can_edit:
        st.info("Your role is read-only.")
    else:
        apps = Q.applications()
        ready = apps[apps["status"] == "BackgroundCheck"]
        if ready.empty:
            st.warning("No application is in the 'BackgroundCheck' stage, so no offer can be prepared yet.")
        else:
            with st.form("new_offer"):
                am = {int(r.application_id): f"#{r.application_id} - {r.candidate_name} for {r.job_title}" for r in ready.itertuples()}
                aid = st.selectbox("Application", list(am), format_func=am.get)
                c1, c2 = st.columns(2)
                sal = c1.number_input("Offered salary (PKR per month)", min_value=0, step=2500, value=100000)
                start = c2.date_input("Proposed start date", value=date.today() + timedelta(days=30))
                approvers = Q.employees(("HRAdmin", "Approver"))
                chosen = st.multiselect("Approvers", [e[0] for e in approvers], format_func=dict(approvers).get)
                if ui.submit("Create offer and request approval"):
                    S.call(S.create_offer, int(aid), sal, start, chosen, None)
                    st.rerun()

with t_appr:
    ap = Q.offer_approvals()
    pend = ap[ap["decision"] == "Pending"] if not ap.empty else ap
    if pend.empty:
        st.info("No offer approvals are waiting.")
    else:
        ui.small_table(pend)
        if is_admin:
            with st.form("decide_offer"):
                pm = {int(r.offer_approval_id): f"Offer #{r.offer_id} - approver {r.approver}" for r in pend.itertuples()}
                xid = st.selectbox("Approval", list(pm), format_func=pm.get)
                dec = st.radio("Decision", ["Approved", "Rejected"], horizontal=True)
                if ui.submit("Record decision"):
                    S.call(S.decide_offer_approval, int(xid), dec, None, None)
                    st.rerun()
        else:
            st.caption("Only an administrator can record approval decisions.")

with t_resp:
    if not can_edit:
        st.info("Your role is read-only.")
    else:
        sent = offers[offers["status"] == "Sent"] if not offers.empty else offers
        if sent.empty:
            st.info("There are no offers waiting for the candidate's reply.")
        else:
            om = {int(r.offer_id): f"Offer #{r.offer_id} - {r.candidate_name} for {r.job_title} ({ui.pkr(r.salary_offered)})" for r in sent.itertuples()}
            oid = int(st.selectbox("Offer", list(om), format_func=om.get, key="resp_offer"))
            resp = st.radio("Candidate response", ["Accepted", "Declined", "Withdrawn"], horizontal=True,
                            captions=["Candidate accepts", "Candidate declines", "Company withdraws the offer"])
            with st.form(f"resp_{oid}"):
                join = st.date_input("Joining date (if accepted)", value=date.today() + timedelta(days=21))
                hr = ui.select_pair("HR employee for onboarding (if accepted)", Q.employees(("HRAdmin", "Recruiter")), f"resp_hr_{oid}")
                reasons = Q.rejection_reasons()
                reason = ui.select_pair("Reason (if declined / withdrawn)", reasons, f"resp_rs_{oid}", allow_none=True, none_label="- none -")
                if ui.submit("Record response"):
                    S.call(S.respond_offer, oid, resp, None, join, hr, reason)
                    st.rerun()

with t_onb:
    if onb.empty:
        st.info("No onboarding records yet. They are created when an offer is accepted.")
    else:
        sf = st.multiselect("Status", ["Pending", "DocumentsSubmitted", "Completed"], key="ob_stat")
        df = onb[onb["status"].isin(sf)] if sf else onb
        ui.show_table(df, "onboarding.csv", key="dl_onb")
        if can_edit:
            with st.form("upd_onb"):
                om = {int(r.onboarding_id): f"#{r.onboarding_id} - {r.candidate_name} ({r.job_title})" for r in onb.itertuples()}
                oid = st.selectbox("Onboarding record", list(om), format_func=om.get)
                c1, c2 = st.columns(2)
                stt = c1.selectbox("Status", ["Pending", "DocumentsSubmitted", "Completed"])
                jd = c2.date_input("Joining date", value=date.today() + timedelta(days=14))
                hr = ui.select_pair("Assigned HR", Q.employees(("HRAdmin", "Recruiter")), "onb_hr")
                if ui.submit("Update onboarding"):
                    S.call(S.update_onboarding, int(oid), stt, jd, hr)
                    st.rerun()
