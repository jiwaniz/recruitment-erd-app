import streamlit as st

from app_core import accounts, auth, emailer, services as S, ui

ui.page_header("Account Settings", "Preferences and security")
ui.show_flash()
u = auth.current_user()
LANDING = ["Dashboard", "Recruitment / Vacancies", "Candidates", "Applications", "Interviews", "Hiring", "Reports"]

t_pref, t_sec = st.tabs(["Preferences", "Security"])
with t_pref:
    if not accounts.accounts_enabled() or not u.get("user_id"):
        st.info("Preferences are saved per account and need the one-time database upgrade (see AUTH_SETUP.md).")
    else:
        prefs = u.get("preferences", {})
        with st.form("prefs"):
            land = st.selectbox("Page to open after sign-in", LANDING,
                                index=LANDING.index(prefs.get("landing_page", "Dashboard")) if prefs.get("landing_page", "Dashboard") in LANDING else 0)
            compact = st.checkbox("Compact tables (shorter tables with scrolling)", value=bool(prefs.get("compact_tables")))
            if ui.submit("Save preferences"):
                S.call(accounts.save_preferences, {"landing_page": land, "compact_tables": compact})
                st.rerun()
with t_sec:
    ui.metrics([("Role", u["role"]), ("Last sign-in", f"{u['last_login']:%d %b %Y %H:%M}" if u.get("last_login") else "-"),
                ("Password reset by email", "Configured" if emailer.is_configured() else "Not configured")], cols=3)
    st.page_link("views/change_password.py", label="Change my password", icon=":material/key:")
    st.caption("Passwords are stored only as salted hashes. Five wrong attempts lock the account for 15 minutes. "
               "Role changes and deactivation by an administrator take effect on your next page load.")
    if st.button("Sign out"):
        auth.logout()
