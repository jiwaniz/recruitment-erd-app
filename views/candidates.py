from datetime import date

import streamlit as st

from app_core import auth, queries as Q, services as S, ui

ui.page_header("Candidates", "Search, view and maintain candidate records")
ui.show_flash()
can_edit, is_admin = auth.has_role("recruiter"), auth.has_role("admin")
LEVELS = ["Beginner", "Intermediate", "Advanced", "Expert"]

t_browse, t_profile, t_add, t_edit = st.tabs(["Browse", "Profile", "Add candidate", "Edit / manage"])
cands = Q.candidates()

with t_browse:
    if cands.empty:
        st.info("There are no candidates yet.")
    else:
        c1, c2, c3 = st.columns([3, 3, 2])
        text = c1.text_input("Search name, email or phone", key="c_search")
        all_skills = sorted({s.strip() for v in cands["skills"].dropna() for s in v.split(",")})
        skill_f = c2.multiselect("Has skills (all selected)", all_skills, key="c_skill")
        min_apps = c3.number_input("Minimum applications", min_value=0, value=0, step=1, key="c_minapps")
        df = cands
        if text:
            mask = (df["candidate_name"].str.contains(text, case=False, na=False) |
                    df["candidate_email"].str.contains(text, case=False, na=False) |
                    df["candidate_contact_no"].fillna("").str.contains(text, case=False, na=False))
            df = df[mask]
        for s in skill_f:
            df = df[df["skills"].fillna("").str.contains(s, regex=False)]
        df = df[df["applications"] >= min_apps]
        ui.show_table(df, "candidates.csv", key="dl_cand")

with t_profile:
    if cands.empty:
        st.info("No candidates yet.")
    else:
        cm = {int(r.candidate_id): f"{r.candidate_name} <{r.candidate_email}>" for r in cands.itertuples()}
        cid = st.selectbox("Candidate", list(cm), format_func=cm.get, key="prof_c")
        prof = Q.candidate_profile(int(cid))
        b = prof["base"].iloc[0]
        st.subheader(b["candidate_name"])
        ui.metrics([("Email", b["candidate_email"]), ("Contact", b["candidate_contact_no"] or "-"),
                    ("Applications", len(prof["applications"])), ("Resumes", len(prof["resumes"]))], cols=4)
        a, c = st.columns(2)
        with a:
            st.markdown("**Skills and qualifications**")
            st.dataframe(prof["skills"], hide_index=True, width="stretch") if not prof["skills"].empty else st.caption("No skills recorded.")
            st.markdown("**Resumes**")
            st.dataframe(prof["resumes"], hide_index=True, width="stretch") if not prof["resumes"].empty else st.caption("No resumes recorded.")
        with c:
            st.markdown("**Application history**")
            st.dataframe(prof["applications"], hide_index=True, width="stretch") if not prof["applications"].empty else st.caption("This candidate has not applied yet.")
            st.markdown("**Referrals**")
            st.dataframe(prof["referrals"], hide_index=True, width="stretch") if not prof["referrals"].empty else st.caption("No referrals.")

with t_add:
    if not can_edit:
        st.info("Your role is read-only.")
    else:
        skills = Q.skills()
        with st.form("add_candidate"):
            c1, c2 = st.columns(2)
            name = c1.text_input("Full name *")
            email = c2.text_input("Email *")
            phone = c1.text_input("Contact number", placeholder="0321-1234567")
            resume = c2.text_input("Resume file path (optional)", placeholder="resumes/2026/10/name_cv_v1.pdf")
            chosen = st.multiselect("Skills", [n for _, n in skills])
            level = st.selectbox("Default proficiency for the selected skills", LEVELS, index=1)
            if st.form_submit_button("Add candidate", type="primary"):
                ids = {n: i for i, n in skills}
                S.call(S.create_candidate, name, email, phone, {ids[n]: level for n in chosen}, resume)
                st.rerun()

with t_edit:
    if not can_edit:
        st.info("Your role is read-only.")
    elif cands.empty:
        st.info("No candidates to edit.")
    else:
        cm = {int(r.candidate_id): f"{r.candidate_name} <{r.candidate_email}>" for r in cands.itertuples()}
        cid = int(st.selectbox("Candidate", list(cm), format_func=cm.get, key="edit_c"))
        row = cands[cands["candidate_id"] == cid].iloc[0]
        st.markdown("#### Contact details")
        with st.form(f"edit_cand_{cid}"):
            name = st.text_input("Full name", value=row["candidate_name"])
            email = st.text_input("Email", value=row["candidate_email"])
            phone = st.text_input("Contact number", value=row["candidate_contact_no"] or "")
            if st.form_submit_button("Save details", type="primary"):
                S.call(S.update_candidate, cid, name, email, phone)
                st.rerun()

        st.markdown("#### Skills")
        skills = Q.skills()
        name_to_id = {n: i for i, n in skills}
        cur = Q.candidate_profile(cid)["skills"]
        chosen = st.multiselect("Skills", list(name_to_id), default=list(cur["skill"]), key=f"sk_{cid}")
        cur_level = dict(zip(cur["skill"], cur["level"]))
        levels = {}
        cols = st.columns(3)
        for i, n in enumerate(chosen):
            levels[n] = cols[i % 3].selectbox(n, LEVELS, index=LEVELS.index(cur_level.get(n, "Intermediate")), key=f"lv_{cid}_{n}")
        if st.button("Save skills", key=f"sv_{cid}"):
            S.call(S.set_candidate_skills, cid, {name_to_id[n]: lv for n, lv in levels.items()})
            st.rerun()

        st.markdown("#### Add a resume")
        with st.form(f"resume_{cid}"):
            path = st.text_input("File path")
            d = st.date_input("Upload date", value=date.today())
            prim = st.checkbox("Make this the primary resume", value=True)
            if st.form_submit_button("Add resume"):
                S.call(S.add_resume, cid, path, d, prim)
                st.rerun()

        st.markdown("#### Record a referral")
        with st.form(f"ref_{cid}"):
            emp = ui.select_pair("Referred by (employee)", Q.employees(), f"ref_emp_{cid}")
            d = st.date_input("Referral date", value=date.today(), key=f"ref_d_{cid}")
            if st.form_submit_button("Save referral"):
                S.call(S.add_referral, cid, emp, d)
                st.rerun()

        if is_admin:
            st.markdown("#### Delete candidate")
            st.caption("Only possible when the candidate has no applications or referrals.")
            sure = st.checkbox("I understand this permanently removes the candidate, skills and resumes.", key=f"del_ok_{cid}")
            if st.button("Delete candidate", disabled=not sure, key=f"del_{cid}"):
                S.call(S.delete_candidate, cid)
                st.rerun()
