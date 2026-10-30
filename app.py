"""
Recruitment Management System - Streamlit entry point.

Run locally:   streamlit run app.py
The same file is the "Main file path" when you deploy on Streamlit Community Cloud.
"""
import streamlit as st

st.set_page_config(page_title="Recruitment Management System", page_icon="🧑‍💼", layout="wide",
                   initial_sidebar_state="expanded")

from app_core import auth, db, ui   # noqa: E402  (must come after set_page_config)

ui.inject_css()


@st.cache_data(ttl=30, show_spinner=False)
def _db_status():
    return db.check_connection()


if not auth.login_form():
    st.stop()

ok, message = _db_status()
if not ok:
    st.error("The application cannot reach the MySQL database.")
    st.code(message)
    st.info("Check that MySQL is running and that the credentials in `.env` (local) or Streamlit Secrets (cloud) "
            "are correct. Free cloud databases such as Aiven may need to be powered on again after inactivity.")
    if st.button("Try again"):
        st.cache_data.clear()
        st.rerun()
    st.stop()

pages = [
    st.Page("views/dashboard.py", title="Dashboard", icon=":material/dashboard:", default=True),
    st.Page("views/vacancies.py", title="Recruitment / Vacancies", icon=":material/work:", url_path="vacancies"),
    st.Page("views/candidates.py", title="Candidates", icon=":material/groups:", url_path="candidates"),
    st.Page("views/applications.py", title="Applications", icon=":material/description:", url_path="applications"),
    st.Page("views/interviews.py", title="Interviews", icon=":material/event:", url_path="interviews"),
    st.Page("views/hiring.py", title="Hiring", icon=":material/handshake:", url_path="hiring"),
    st.Page("views/reports.py", title="Reports", icon=":material/bar_chart:", url_path="reports"),
    st.Page("views/about.py", title="About", icon=":material/info:", url_path="about"),
]
navigation = st.navigation(pages)

user = auth.current_user()
with st.sidebar:
    st.markdown(f"**{user['display_name']}**  \nRole: `{user['role']}`")
    if st.button("Refresh data", width="stretch"):
        db.clear_cache()
        st.rerun()
    if st.button("Sign out", width="stretch"):
        auth.logout()

navigation.run()
