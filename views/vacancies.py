from datetime import date, timedelta

import plotly.express as px
import streamlit as st

from app_core import auth, queries as Q, services as S, ui

def _open_vac(row):
    st.session_state["v_detail"] = int(row["job_id"])
    ui.notify("success", f"{row['job_title']}: scroll down to 'Vacancy details'.")


def _edit_vac(row):
    st.session_state["edit_job"] = int(row["job_id"])
    ui.notify("success", f"{row['job_title']}: open the 'Edit vacancy' tab.")


ui.page_header("Recruitment / Vacancies", "Requisitions, vacancies (jobs) and job postings")
ui.show_flash()
can_edit, is_admin = auth.has_role("recruiter"), auth.has_role("admin")

t_list, t_add, t_edit, t_post, t_req = st.tabs(["Vacancies", "Add vacancy", "Edit vacancy", "Postings", "Requisitions"])
vac = Q.vacancies()

# ------------------------------------------------------------------ list + details
with t_list:
    if vac.empty:
        st.info("There are no vacancies yet. Create a requisition, get it approved, then add a vacancy.")
    else:
        f1, f2, f3, f4 = st.columns([2, 2, 2, 2])
        text = f1.text_input("Search job title", key="v_search")
        dept = f2.multiselect("Department", sorted(vac["department_name"].unique()), key="v_dept")
        stat = f3.multiselect("Vacancy status", sorted(vac["vacancy_status"].unique()), key="v_stat")
        loc = f4.multiselect("Location", sorted(vac["location"].unique()), key="v_loc")
        df = vac
        if text:
            df = df[df["job_title"].str.contains(text, case=False, na=False)]
        if dept:
            df = df[df["department_name"].isin(dept)]
        if stat:
            df = df[df["vacancy_status"].isin(stat)]
        if loc:
            df = df[df["location"].isin(loc)]
        show = df[["job_id", "job_title", "department_name", "location", "employment_type", "headcount", "hires",
                   "open_positions", "applications", "active_postings", "vacancy_status", "requisition_id"]]
        ui.show_table(show, "vacancies.csv", key="vac", label_col="job_title",
                      actions=[("Show details", _open_vac), ("Edit vacancy", _edit_vac)])
        if not df.empty:
            st.markdown("#### Vacancy details")
            labels = {int(r.job_id): f"#{r.job_id} - {r.job_title} ({r.department_name})" for r in df.itertuples()}
            jid = st.selectbox("Choose a vacancy", list(labels), format_func=labels.get, key="v_detail")
            row = vac[vac["job_id"] == jid].iloc[0]
            ui.metrics([("Headcount", int(row["headcount"])), ("Hired", int(row["hires"])),
                        ("Open positions", int(row["open_positions"])), ("Applications", int(row["applications"])),
                        ("Status", row["vacancy_status"])])
            st.write(f"**Salary range:** {ui.pkr(row['salary_range_min'])} - {ui.pkr(row['salary_range_max'])}  |  "
                     f"**Hiring deadline:** {ui.val(row['hiring_deadline'], '-')}  |  **Requisition:** #{row['requisition_id']} "
                     f"({row['requisition_status']})")
            d1, d2 = st.columns(2)
            with d1:
                st.markdown("**Required / preferred skills**")
                js = Q.job_skills(int(jid))
                if js.empty:
                    st.caption("No skills recorded.")
                else:
                    js["is_mandatory"] = js["is_mandatory"].map({1: "Required", 0: "Preferred", True: "Required", False: "Preferred"})
                    ui.small_table(js)
            with d2:
                st.markdown("**Postings**")
                pp = Q.postings()
                pp = pp[pp["job_id"] == jid]
                ui.small_table(pp.drop(columns=["job_id", "job_title"]))
            apps = Q.applications()
            apps = apps[apps["job_id"] == jid]
            if not apps.empty:
                counts = apps.groupby("status").size().reset_index(name="applications")
                fig = px.bar(counts, x="status", y="applications", color="status", color_discrete_map=ui.STATUS_COLORS)
                fig.update_layout(showlegend=False, height=260, margin=dict(l=0, r=0, t=10, b=0))
                st.plotly_chart(fig, width="stretch")

# ------------------------------------------------------------------ add vacancy
with t_add:
    if not can_edit:
        st.info("Your role is read-only.")
    else:
        reqs = Q.requisitions()
        approved = reqs[reqs["status"] == "Approved"]
        if approved.empty:
            st.warning("No Approved requisitions are available. Approve a requisition first (Requisitions tab).")
        else:
            with st.form("add_vacancy"):
                rmap = {int(r.requisition_id): f"#{r.requisition_id} - {r.job_title} ({r.department_name}, headcount {r.headcount})"
                        for r in approved.itertuples()}
                rid = st.selectbox("Approved requisition", list(rmap), format_func=rmap.get)
                title = st.text_input("Job title", value="")
                c1, c2 = st.columns(2)
                loc = ui.select_pair("Location", Q.locations(), "add_loc")
                et = ui.select_pair("Employment type", Q.employment_types(), "add_et")
                low = c1.number_input("Minimum salary (PKR)", min_value=0, step=5000, value=60000)
                high = c2.number_input("Maximum salary (PKR)", min_value=0, step=5000, value=90000)
                desc = st.text_area("Description")
                if ui.submit("Create vacancy"):
                    default_title = approved[approved["requisition_id"] == rid].iloc[0]["job_title"]
                    S.call(S.create_job, rid, loc, et, title or default_title, desc, low, high)
                    st.rerun()

# ------------------------------------------------------------------ edit vacancy
with t_edit:
    if not can_edit:
        st.info("Your role is read-only.")
    elif vac.empty:
        st.info("No vacancies to edit.")
    else:
        emap = {int(r.job_id): f"#{r.job_id} - {r.job_title}" for r in vac.itertuples()}
        jid = st.selectbox("Vacancy", list(emap), format_func=emap.get, key="edit_job")
        from app_core import db
        j = db.q("SELECT * FROM job WHERE job_id = :j", j=int(jid)).iloc[0]
        with st.form(f"edit_vacancy_{jid}"):
            title = st.text_input("Job title", value=j["job_title"])
            locs, ets = Q.locations(), Q.employment_types()
            loc = st.selectbox("Location", [x[0] for x in locs], format_func=dict(locs).get,
                               index=[x[0] for x in locs].index(int(j["location_id"])))
            et = st.selectbox("Employment type", [x[0] for x in ets], format_func=dict(ets).get,
                              index=[x[0] for x in ets].index(int(j["employment_type_id"])))
            c1, c2 = st.columns(2)
            low = c1.number_input("Minimum salary (PKR)", min_value=0, step=5000, value=int(ui.val(j["salary_range_min"], 0)))
            high = c2.number_input("Maximum salary (PKR)", min_value=0, step=5000, value=int(ui.val(j["salary_range_max"], 0)))
            desc = st.text_area("Description", value=ui.val(j["description"]))
            if ui.submit("Save changes"):
                S.call(S.update_job, int(jid), loc, et, title, desc, low, high)
                st.rerun()
        st.markdown("#### Skills for this vacancy")
        skills = Q.skills()
        cur = Q.job_skills(int(jid))
        name_to_id = {n: i for i, n in skills}
        req_now = [n for n, m in zip(cur["skill"], cur["is_mandatory"]) if m]
        opt_now = [n for n, m in zip(cur["skill"], cur["is_mandatory"]) if not m]
        req = st.multiselect("Required skills", list(name_to_id), default=req_now, key=f"rq_{jid}")
        opt = st.multiselect("Preferred skills", [n for n in name_to_id if n not in req], default=[n for n in opt_now if n not in req], key=f"op_{jid}")
        if st.button("Save skills", key=f"sv_sk_{jid}"):
            S.call(S.set_job_skills, int(jid), [name_to_id[n] for n in req], [name_to_id[n] for n in opt])
            st.rerun()

# ------------------------------------------------------------------ postings
with t_post:
    posts = Q.postings()
    f1, f2 = st.columns(2)
    pst = f1.multiselect("Status", ["Active", "Closed", "Expired"], key="p_stat")
    ptxt = f2.text_input("Search job or source", key="p_txt")
    pdf = posts
    if pst:
        pdf = pdf[pdf["status"].isin(pst)]
    if ptxt:
        pdf = pdf[pdf["job_title"].str.contains(ptxt, case=False) | pdf["source_name"].str.contains(ptxt, case=False)]
    ui.show_table(pdf, "postings.csv", key="dl_post")
    if can_edit and not vac.empty:
        st.markdown("#### Publish a new posting")
        open_jobs = vac[vac["requisition_status"] == "Approved"]
        if open_jobs.empty:
            st.info("No vacancy with an Approved requisition is available.")
        else:
            with st.form("add_posting"):
                jm = {int(r.job_id): f"#{r.job_id} - {r.job_title}" for r in open_jobs.itertuples()}
                jid = st.selectbox("Vacancy", list(jm), format_func=jm.get)
                src = ui.select_pair("Source / channel", Q.sources(), "post_src")
                c1, c2 = st.columns(2)
                pub = c1.date_input("Publish date", value=date.today())
                close = c2.date_input("Close date", value=date.today() + timedelta(days=30))
                if ui.submit("Publish posting"):
                    S.call(S.create_posting, int(jid), src, pub, close)
                    st.rerun()
        st.markdown("#### Change a posting's status")
        if not posts.empty:
            with st.form("posting_status"):
                pm = {int(r.posting_id): f"#{r.posting_id} - {r.job_title} on {r.source_name} ({r.status})" for r in posts.itertuples()}
                pid = st.selectbox("Posting", list(pm), format_func=pm.get)
                new = st.selectbox("New status", ["Active", "Closed", "Expired"])
                close = st.date_input("Close date", value=date.today())
                if ui.submit("Update posting"):
                    S.call(S.set_posting_status, int(pid), new, close)
                    st.rerun()

# ------------------------------------------------------------------ requisitions
with t_req:
    reqs = Q.requisitions()
    sf = st.multiselect("Status", ["Draft", "PendingApproval", "Approved", "Rejected", "Closed"], key="r_stat")
    rdf = reqs[reqs["status"].isin(sf)] if sf else reqs
    ui.show_table(rdf, "requisitions.csv", key="dl_req")
    if can_edit:
        st.markdown("#### Raise a requisition")
        approvers = Q.employees(("HRAdmin", "Approver", "HiringManager"))
        with st.form("new_req"):
            c1, c2 = st.columns(2)
            dept = ui.select_pair("Department", Q.departments(), "rq_dept")
            raiser = ui.select_pair("Raised by", Q.employees(("HiringManager", "HRAdmin", "Approver")), "rq_by")
            title = c1.text_input("Job title")
            heads = c2.number_input("Headcount", min_value=1, value=1, step=1)
            deadline = c1.date_input("Hiring deadline", value=date.today() + timedelta(days=45))
            reason = st.text_area("Reason / justification")
            submit = st.checkbox("Submit for approval now (otherwise save as draft)", value=True)
            a1 = ui.select_pair("Level 1 approver", approvers, "rq_a1")
            a2 = ui.select_pair("Level 2 approver (optional)", approvers, "rq_a2", allow_none=True, none_label="- none -")
            if ui.submit("Save requisition"):
                chosen = [a for a in (a1, a2) if a]
                S.call(S.create_requisition, dept, raiser, title, int(heads), reason, deadline, submit, chosen)
                st.rerun()
    if is_admin:
        st.markdown("#### Approvals waiting for a decision")
        ap = Q.requisition_approvals()
        pend = ap[ap["decision"] == "Pending"]
        if pend.empty:
            st.info("No requisition approvals are pending.")
        else:
            ui.small_table(pend)
            with st.form("decide_req"):
                am = {int(r.approval_id): f"Approval #{r.approval_id} - requisition #{r.requisition_id} {r.job_title} (level {r.approval_level}, {r.approver})" for r in pend.itertuples()}
                aid = st.selectbox("Approval", list(am), format_func=am.get)
                dec = st.radio("Decision", ["Approved", "Rejected"], horizontal=True)
                com = st.text_input("Comments")
                if ui.submit("Record decision"):
                    S.call(S.decide_requisition_approval, int(aid), dec, com)
                    st.rerun()
        st.markdown("#### Close a filled requisition")
        appr = reqs[reqs["status"] == "Approved"]
        if not appr.empty:
            cm = {int(r.requisition_id): f"#{r.requisition_id} - {r.job_title}" for r in appr.itertuples()}
            cid = st.selectbox("Approved requisition", list(cm), format_func=cm.get, key="close_req")
            sure = st.checkbox("I confirm this requisition should be closed (its active postings will be closed)", key="close_ok")
            if st.button("Close requisition", disabled=not sure):
                S.call(S.close_requisition, int(cid))
                st.rerun()
