import streamlit as st

from app_core import accounts, auth, queries as Q, services as S, ui

ui.page_header("User Management", "Administrators only: create users, assign roles, activate, deactivate and reset passwords")
ui.show_flash()
if not auth.has_role("admin"):          # server-side guard, independent of the navigation menu
    st.error("Administrator access is required for this page.")
    st.stop()
if not accounts.accounts_enabled():
    st.info("User management needs the one-time database upgrade (see AUTH_SETUP.md).")
    st.stop()

ROLES = list(auth.ROLE_LEVEL)
users = accounts.list_users()
t_list, t_new, t_edit, t_log = st.tabs(["Users", "Create user", "Edit / manage", "Security log"])

with t_list:
    show = users.assign(status=users["is_active"].map({1: "Active", 0: "Inactive", True: "Active", False: "Inactive"}))
    ui.show_table(show[["user_id", "username", "full_name", "email", "role", "status", "last_login", "created_date"]], "users.csv", key="dl_users")

with t_new:
    emps = Q.employees()
    with st.form("new_user"):
        c1, c2 = st.columns(2)
        username = c1.text_input("Username (lowercase)")
        full = c2.text_input("Full name")
        email = c1.text_input("Email")
        role = c2.selectbox("Role", ROLES, index=ROLES.index("viewer"))
        emp = ui.select_pair("Linked employee (optional)", emps, "nu_emp", allow_none=True, none_label="- none -")
        st.caption("A random temporary password is generated and shown once. The user must change it at first sign-in.")
        if ui.submit("Create user"):
            S.call(accounts.create_user, username, email, full, role, emp)
            st.rerun()

with t_edit:
    if users.empty:
        st.info("No users.")
    else:
        um = {int(r.user_id): f"{r.username} - {r.full_name} ({r.role}, {'active' if r.is_active else 'inactive'})" for r in users.itertuples()}
        uid = int(st.selectbox("User", list(um), format_func=um.get, key="mu"))
        r = users[users["user_id"] == uid].iloc[0]
        emps = Q.employees()
        with st.form(f"edit_user_{uid}"):
            full = st.text_input("Full name", value=r["full_name"])
            email = st.text_input("Email", value=r["email"])
            role = st.selectbox("Role", ROLES, index=ROLES.index(r["role"]))
            ids = [None] + [e[0] for e in emps]
            cur = None if r["employee_id"] != r["employee_id"] or r["employee_id"] is None else int(r["employee_id"])
            emp = st.selectbox("Linked employee", ids, index=ids.index(cur) if cur in ids else 0,
                               format_func=lambda v: "- none -" if v is None else dict(emps)[v])
            if ui.submit("Save changes"):
                S.call(accounts.update_user, uid, full, email, role, emp)
                st.rerun()
        c1, c2, c3 = st.columns(3)
        active = bool(r["is_active"])
        if c1.button("Deactivate account" if active else "Activate account", key=f"act_{uid}"):
            S.call(accounts.set_active, uid, not active)
            st.rerun()
        if c2.button("Unlock account", key=f"unl_{uid}"):
            S.call(accounts.unlock_user, uid)
            st.rerun()
        sure = c3.checkbox("Confirm reset", key=f"rs_ok_{uid}")
        if c3.button("Reset password", disabled=not sure, key=f"rs_{uid}"):
            S.call(accounts.admin_reset_password, uid)
            st.rerun()

with t_log:
    st.caption("Recent sign-in and account events (no passwords or tokens are ever recorded).")
    ui.show_table(accounts.recent_events(200), "security_log.csv", key="dl_log")
