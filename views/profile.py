import streamlit as st

from app_core import accounts, auth, emailer, services as S, ui

ui.page_header("My Profile", "Your account details")
ui.show_flash()
u = auth.current_user()
if not accounts.accounts_enabled() or not u.get("user_id"):
    st.info("You are signed in with a configuration-file account, so the profile is read-only. "
            "Self-service accounts need the one-time database upgrade (see AUTH_SETUP.md).")
    ui.metrics([("Name", u["display_name"]), ("Username", u["username"]), ("Role", u["role"])])
    st.stop()

ui.metrics([("Full name", u["display_name"]), ("Username", u["username"]), ("Role", u["role"])], cols=3)
ui.metrics([("Account status", "Active" if u["is_active"] else "Inactive"),
            ("Created", f"{u['created_date']:%d %b %Y}" if u["created_date"] else "-"),
            ("Last sign-in", f"{u['last_login']:%d %b %Y %H:%M}" if u["last_login"] else "-")], cols=3)
st.subheader("Update my details")
st.caption("Your role and permissions can only be changed by an administrator.")
with st.form("profile"):
    name = st.text_input("Full name", value=u["display_name"])
    email = st.text_input("Email (used for password reset)", value=u["email"])
    if ui.submit("Save profile"):
        S.call(accounts.update_profile, name, email)
        st.rerun()
