import streamlit as st

from app_core import accounts, auth, services as S, ui

ui.page_header("Change Password", "Choose a new password for your account")
ui.show_flash()
u = auth.current_user()
if not accounts.accounts_enabled() or not u.get("user_id"):
    st.info("This account is defined in a configuration file, so its password cannot be changed here. "
            "Self-service accounts need the one-time database upgrade (see AUTH_SETUP.md).")
    st.stop()
if u.get("must_change_password"):
    st.warning("You must choose a new password before you can use the application.")
st.caption("At least 10 characters, with at least 3 of: lowercase, uppercase, digit, symbol. "
           "It must not contain your username or email name.")
with st.form("chpw"):
    cur = st.text_input("Current password", type="password")
    new = st.text_input("New password", type="password")
    conf = st.text_input("Confirm new password", type="password")
    if ui.submit("Change password"):
        S.call(accounts.change_password, cur, new, conf)
        st.rerun()
