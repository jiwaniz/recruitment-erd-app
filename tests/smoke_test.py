"""
Smoke test: opens every page as each role and fails on any exception.
Run from the project folder (MySQL must be running and .env or env vars must point at it):
    python tests/smoke_test.py
"""
import pathlib
import sys
from streamlit.testing.v1 import AppTest

APP = str(pathlib.Path(__file__).resolve().parents[1] / "app.py")

PAGES = ["views/dashboard.py", "views/vacancies.py", "views/candidates.py", "views/applications.py",
         "views/interviews.py", "views/hiring.py", "views/reports.py", "views/about.py"]


def run_as(role, username, password):
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception, at.exception
    at.text_input[0].set_value(username)
    at.text_input[1].set_value(password)
    at.button[0].click().run()
    assert not at.exception, at.exception
    assert at.session_state["user"]["role"] == role, "login failed"
    for page in PAGES:
        at.switch_page(page).run()
        assert not at.exception, f"{role} / {page}: {[e.value for e in at.exception]}"
        assert not at.error, f"{role} / {page}: {[e.value for e in at.error]}"
        print(f"  ok  {role:9s} {page}")
    return at


if __name__ == "__main__":
    bad = AppTest.from_file(APP, default_timeout=60).run()
    bad.text_input[0].set_value("admin")
    bad.text_input[1].set_value("wrong-password")
    bad.button[0].click().run()
    assert "user" not in bad.session_state and bad.error, "a wrong password must be rejected"
    print("  ok  wrong password rejected")
    run_as("admin", "admin", sys.argv[1] if len(sys.argv) > 1 else "Admin#2026")
    run_as("recruiter", "recruiter", "Recruit#2026")
    run_as("viewer", "viewer", "Viewer#2026")
    print("ALL PAGES OK")
