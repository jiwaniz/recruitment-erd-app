"""
Recruitment Management System - Streamlit entry point.
Run locally:   streamlit run app.py        (the same file is the "Main file path" on Streamlit Community Cloud)
"""
from datetime import datetime

import streamlit as st

st.set_page_config(page_title="Recruitment Management System", page_icon="🧑‍💼", layout="wide",
                   initial_sidebar_state="expanded")

from app_core import auth, db, queries as Q, ui   # noqa: E402
from app_core.config import diagnostics   # noqa: E402

ui.inject_css()


@st.cache_data(ttl=30, show_spinner=False)
def _db_status():
    return db.check_connection()


ok, message = _db_status()
if not ok:
    st.error("The application cannot reach its database right now.")
    st.info("Please check that MySQL is running and that the credentials in `.env` (local) or Streamlit Secrets (cloud) are correct. "
            "Free cloud databases such as Aiven may need to be powered on again after inactivity.")
    with st.expander("Connection settings this app can see (no passwords shown)", expanded=True):
        st.table([{"Setting": a, "Value": b} for a, b in diagnostics()])
    with st.expander("Technical details"):
        st.code(message)
    if st.button("Try again"):
        st.cache_data.clear()
        st.rerun()
    st.stop()

if not auth.login_page():
    ui.show_flash()
    st.stop()
auth.refresh_session()
user = auth.current_user()
st.session_state.setdefault("_data_time", datetime.now())

# (file, title, icon, url_path, sidebar group)
MODULES = [("views/dashboard.py", "Dashboard", ":material/dashboard:", "", "Overview"),
           ("views/vacancies.py", "Recruitment / Vacancies", ":material/work:", "vacancies", "Recruitment"),
           ("views/candidates.py", "Candidates", ":material/groups:", "candidates", "Recruitment"),
           ("views/applications.py", "Applications", ":material/description:", "applications", "Recruitment"),
           ("views/interviews.py", "Interviews", ":material/event:", "interviews", "Recruitment"),
           ("views/hiring.py", "Hiring", ":material/handshake:", "hiring", "Hiring"),
           ("views/reports.py", "Reports", ":material/bar_chart:", "reports", "Insights"),
           ("views/about.py", "About", ":material/info:", "about", "System")]
landing = (user.get("preferences") or {}).get("landing_page", "Dashboard")
if landing not in [m[1] for m in MODULES]:
    landing = "Dashboard"
module_pages = {t: st.Page(f, title=t, icon=i, url_path=u or None, default=(t == landing)) for f, t, i, u, g in MODULES}
group_of = {t: g for f, t, i, u, g in MODULES}
account_pages = [st.Page("views/profile.py", title="My Profile", icon=":material/person:", url_path="profile"),
                 st.Page("views/settings.py", title="Account Settings", icon=":material/settings:", url_path="settings"),
                 st.Page("views/change_password.py", title="Change Password", icon=":material/key:", url_path="change-password")]
if auth.has_role("admin"):
    account_pages.append(st.Page("views/user_management.py", title="User Management", icon=":material/admin_panel_settings:",
                                 url_path="user-management"))
for p in account_pages:
    group_of[p.title] = "Account"

forced = bool(user.get("must_change_password"))
if forced:                                              # forced change: nothing else is reachable
    navigation = st.navigation([account_pages[2]], position="hidden")
else:
    navigation = st.navigation(list(module_pages.values()) + account_pages, position="hidden")   # only pages this role may open

# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.markdown("<div class='brand'><div class='logo'>🧑‍💼</div><div class='name'>Recruitment<br>Management System</div></div>",
                unsafe_allow_html=True)
    if not forced:
        shown = None
        for f, t, i, u, g in MODULES:
            if g != shown:
                st.markdown(f"<div class='navgroup'>{g}</div>", unsafe_allow_html=True)
                shown = g
            st.page_link(module_pages[t])
    st.divider()
    st.markdown(f"<div class='userbox'><b>{user['display_name']}</b>{user['role'].capitalize()}"
                f"<br>{user.get('email') or user['username']}</div>", unsafe_allow_html=True)
    if st.button("Sign out", icon=":material/logout:", key="side_signout"):
        auth.logout()

# ------------------------------------------------------------------ header: breadcrumbs, refresh, notifications, profile
crumb, upd, bell, prof = st.columns([5, 2.2, 1.1, 2])
crumb.markdown(f"<div class='crumbs'>Recruitment Management System &nbsp;/&nbsp; {group_of.get(navigation.title, '')} &nbsp;/&nbsp; "
               f"<b>{navigation.title}</b></div>", unsafe_allow_html=True)
with upd:
    if st.button(f"Refresh  ·  {ui.last_updated()}", icon=":material/refresh:", key="hdr_refresh", help="Reload data from the database"):
        db.clear_cache()
        st.rerun()

if not forced:
    n = Q.notifications()
    admin = auth.has_role("admin")
    items = []
    if admin and n["req_approvals"]:
        items.append((f"{n['req_approvals']} requisition approval(s) pending", module_pages["Recruitment / Vacancies"]))
    if admin and n["offer_approvals"]:
        items.append((f"{n['offer_approvals']} offer approval(s) pending", module_pages["Hiring"]))
    if n["offers_waiting"]:
        items.append((f"{n['offers_waiting']} offer(s) waiting for the candidate's reply", module_pages["Hiring"]))
    if n["interviews_soon"]:
        items.append((f"{n['interviews_soon']} interview(s) in the next 7 days", module_pages["Interviews"]))
    if n["feedback_due"]:
        items.append((f"{n['feedback_due']} interview(s) awaiting feedback", module_pages["Interviews"]))
    with bell.popover(str(len(items)) if items else "", icon=":material/notifications:", help="Notifications"):
        if not items:
            st.caption("You're all caught up.")
        for text_, page in items:
            st.page_link(page, label=text_)

with prof.popover(user["display_name"], icon=":material/account_circle:", width="stretch"):
    st.caption(f"{user['role'].capitalize()} | {user.get('email') or user['username']}")
    for page in account_pages:
        if not forced or page.title == "Change Password":
            st.page_link(page)
    if st.button("Sign Out", icon=":material/logout:", width="stretch", key="hdr_signout"):
        auth.logout()

# ------------------------------------------------------------------ page content, with friendly error handling
try:
    navigation.run()
except Exception as exc:                                   # noqa: BLE001
    if type(exc).__module__.startswith("streamlit"):       # Streamlit's own control flow (st.rerun, st.stop, ...)
        raise
    st.error("Something went wrong while loading this page. Your data is safe. Try Refresh; if it keeps happening, tell an administrator.")
    if auth.has_role("admin"):
        with st.expander("Technical details (administrators only)"):
            st.code(f"{type(exc).__name__}: {str(exc)[:300]}")
