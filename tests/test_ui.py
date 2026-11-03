"""
UI tests: drive the real pages with Streamlit's AppTest (login, header menu, role menus, every important form).
Needs a database with the auth migration applied and users imported (see tests/run_all.sh). Modifies data.
"""
import datetime as dt, os, pathlib, re, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sqlalchemy import text
from streamlit.testing.v1 import AppTest
from app_core import db

APP = str(ROOT / "app.py")
RESULTS = []
def check(name, cond, extra=""):
    RESULTS.append((name, bool(cond)))
    print(("  PASS " if cond else "  FAIL ") + name + (f"  [{extra}]" if (extra and not cond) else ""))

def Q(sql, **p):
    with db.get_engine().connect() as c:
        return c.execute(text(sql), p).fetchall()
def S(sql, **p): r = Q(sql, **p); return r[0][0] if r else None

def find(coll, label=None, key=None, nth=0):
    hits = [w for w in coll if (key is not None and w.key == key) or (label is not None and w.label == label)]
    assert len(hits) > nth, f"widget not found: {label or key} (#{nth}); have {[w.label for w in coll][:12]}"
    return hits[nth]
def submit(at, label, nth=0):
    find(at.button, label=label, nth=nth).click().run()
def stray(at): return [type(e).__name__ for e in at.main if type(e).__name__ == "Help"]
def msgs(at): return [m.value for m in list(at.success) + list(at.error) + list(at.warning)]

def new_app():
    return AppTest.from_file(APP, default_timeout=90).run()
def login(at, who, pw):
    find(at.text_input, "Username or email").set_value(who)
    find(at.text_input, "Password").set_value(pw)
    submit(at, "Sign In")
    return at
def popover(at):
    return [b for b in at.main if getattr(b, "type", "") == "popover"]
PAGES = ["views/dashboard.py", "views/vacancies.py", "views/candidates.py", "views/applications.py", "views/interviews.py",
         "views/hiring.py", "views/reports.py", "views/about.py", "views/profile.py", "views/settings.py", "views/change_password.py"]

# ------------------------------------------------------------ login page
at = new_app()
check("login page: branding, username/email + password fields, Sign In and Forgot password",
      any("Recruitment Management System" in m.value for m in at.markdown) and len(at.text_input) == 2
      and find(at.text_input, "Password").proto.type == 1 and any(b.label == "Sign In" for b in at.button)
      and any(b.label == "Forgot password?" for b in at.button))
submit(at, "Sign In")
check("login validation: empty fields give a clear message", any("Enter your username" in e.value for e in at.error))
login(at, "admin", "wrong-password")
check("login failure message is generic", any(e.value == "Invalid username/email or password." for e in at.error))
at = new_app(); login(at, "admin@test.example", "Admin#2026")
check("login succeeds with email + password and header avatar menu is shown", at.session_state["user"]["role"] == "admin" and len(popover(at)) == 2)

# ------------------------------------------------------------ forgot / reset UI
at = new_app(); submit(at, "Forgot password?")
check("Forgot password view opens (warning when email service is not configured)",
      any("Forgot password" in s.value for s in at.subheader) and any("not set up" in w.value for w in at.warning))
at = new_app(); at.query_params["reset_token"] = "not-a-real-token"; at.run()
check("invalid / expired reset link shows an error and no form", any("invalid, expired" in e.value for e in at.error) and not any(b.label == "Reset password" for b in at.button))

# ------------------------------------------------------------ every page renders, per role
for who, pw, role in [("admin", "Admin#2026", "admin"), ("recruiter", "Recruit#2026", "recruiter"), ("viewer", "Viewer#2026", "viewer")]:
    at = login(new_app(), who, pw)
    bad = []
    for page in PAGES + (["views/user_management.py"] if role == "admin" else []):
        at.switch_page(page).run()
        if at.exception or at.error or stray(at):
            bad.append((page, [e.value[:60] for e in at.exception], [e.value[:60] for e in at.error], stray(at)))
    check(f"all pages render for {role} (no exceptions, errors or stray framework output)", not bad, str(bad)[:300])
at = login(new_app(), "viewer", "Viewer#2026")
try:
    at.switch_page("views/user_management.py").run(); reachable = not at.exception and not any("Administrator access" in e.value for e in at.error) and bool(at.tabs)
except Exception:
    reachable = False
check("viewer cannot open User Management (not in navigation; direct access is refused)", not reachable)

# ------------------------------------------------------------ profile / settings / change password (UI)
at = login(new_app(), "recruiter", "Recruit#2026"); at.switch_page("views/profile.py").run()
check("profile page shows name, username, role, status, created date", {"Full name", "Username", "Role", "Account status", "Created"} <= {m.label for m in at.metric})
find(at.text_input, "Full name").set_value("Test Recruiter UI"); submit(at, "Save profile")
check("profile update through the UI is saved", S("SELECT full_name FROM app_user WHERE username='recruiter'") == "Test Recruiter UI")
at.switch_page("views/settings.py").run(); find(at.checkbox, "Compact tables (shorter tables with scrolling)").set_value(True); submit(at, "Save preferences")
check("account settings (preferences) saved through the UI", '"compact_tables": true' in str(S("SELECT preferences FROM app_user WHERE username='recruiter'")).lower())
at.switch_page("views/change_password.py").run()
find(at.text_input, "Current password").set_value("Recruit#2026"); find(at.text_input, "New password").set_value("Fresh-Passw0rd!9")
find(at.text_input, "Confirm new password").set_value("Fresh-Passw0rd!9"); submit(at, "Change password")
check("change password through the UI works (new password signs in, old one does not)",
      "user" in login(new_app(), "recruiter", "Fresh-Passw0rd!9").session_state
      and "user" not in login(new_app(), "recruiter", "Recruit#2026").session_state)
db.get_engine().dispose()

# ------------------------------------------------------------ admin: user management + forced password change
at = login(new_app(), "admin", "Admin#2026"); at.switch_page("views/user_management.py").run()
find(at.text_input, "Username (lowercase)").set_value("ui.user"); find(at.text_input, "Full name", nth=0).set_value("UI User")
find(at.text_input, "Email", nth=0).set_value("ui.user@test.example"); submit(at, "Create user")
tmp = re.search(r"Temporary password .*?: (\S+)", " ".join(msgs(at)))
check("admin creates a user through the UI and sees the one-time temporary password", S("SELECT COUNT(*) FROM app_user WHERE username='ui.user'") == 1 and bool(tmp))
at2 = login(new_app(), "ui.user", tmp.group(1))
check("first sign-in with a temporary password forces the Change Password page only",
      at2.session_state["user"]["must_change_password"] and any(b.label == "Change password" for b in at2.button))

# ------------------------------------------------------------ functional audit of recruitment forms (as admin)
adm = login(new_app(), "admin", "Admin#2026")

# Candidates: add, edit
adm.switch_page("views/candidates.py").run()
find(adm.text_input, "Full name *").set_value("Ui Candidate"); find(adm.text_input, "Email *").set_value("ui.candidate@test.example")
submit(adm, "Add candidate")
cid = S("SELECT candidate_id FROM candidate WHERE candidate_email='ui.candidate@test.example'")
check("Candidates: add candidate form saves to the database", cid is not None)
adm.switch_page("views/candidates.py").run(); find(adm.selectbox, key="edit_c").set_value(cid).run()
find(adm.text_input, "Full name").set_value("Ui Candidate Edited"); submit(adm, "Save details")
check("Candidates: edit details form updates the record", S("SELECT candidate_name FROM candidate WHERE candidate_id=:c", c=cid) == "Ui Candidate Edited")
adm.switch_page("views/candidates.py").run(); find(adm.selectbox, key="prof_c").set_value(cid).run()
check("Candidates: profile page renders for a candidate without applications", not adm.exception and not stray(adm))

# Applications: new application, screening, status change, manage page
posting = Q("SELECT p.posting_id FROM job_posting p WHERE p.status='Active' ORDER BY p.posting_id LIMIT 1")[0][0]
adm.switch_page("views/applications.py").run()
find(adm.selectbox, "Candidate").set_value(cid); find(adm.selectbox, "Job posting").set_value(posting); submit(adm, "Create application")
aid = S("SELECT application_id FROM application WHERE candidate_id=:c", c=cid)
check("Applications: new application form creates the application and history", aid and S("SELECT COUNT(*) FROM application_status_history WHERE application_id=:a", a=aid) == 1)
adm.switch_page("views/applications.py").run(); find(adm.selectbox, key="man_app").set_value(aid).run()
check("Applications: Manage page renders (no framework output)", not adm.exception and not stray(adm))
find(adm.selectbox, "Outcome").set_value("Shortlisted"); submit(adm, "Save screening")
check("Applications: screening form shortlists and moves the application to Interviewing", S("SELECT status FROM application WHERE application_id=:a", a=aid) == "Interviewing")

# Interviews: schedule, feedback, update
adm.switch_page("views/interviews.py").run()
find(adm.selectbox, "Application").set_value(aid); find(adm.selectbox, "Round").set_value("Technical")
find(adm.date_input, "Date", nth=0).set_value(dt.date.today() + dt.timedelta(days=2))
find(adm.multiselect, "Panel members", nth=0).set_value([12, 13]); submit(adm, "Schedule interview")
iid = S("SELECT interview_id FROM interview WHERE application_id=:a", a=aid)
check("Interviews: schedule form saves the interview and its panel", iid and S("SELECT COUNT(*) FROM interview_participant WHERE interview_id=:i", i=iid) == 2)
adm.switch_page("views/interviews.py").run(); find(adm.selectbox, key="mi").set_value(iid).run()
check("Interviews: Update / feedback section renders (no framework output)", not adm.exception and not stray(adm))
find(adm.selectbox, "Evaluator (panel member)").set_value(12); find(adm.text_area, "Comments").set_value("Strong candidate"); submit(adm, "Save feedback")
check("Interviews: feedback form stores the evaluation", S("SELECT COUNT(*) FROM interview_evaluation WHERE interview_id=:i AND employee_id=12", i=iid) == 1)
adm.switch_page("views/interviews.py").run(); find(adm.selectbox, key="mi").set_value(iid).run()
find(adm.selectbox, "Mode", nth=1).set_value("Phone"); submit(adm, "Save changes")
check("Interviews: update form changes the mode", S("SELECT mode FROM interview WHERE interview_id=:i", i=iid) == "Phone")

# Manage application: status change form
sid = S("SELECT application_id FROM application WHERE status='Screening' ORDER BY application_id LIMIT 1")
adm.switch_page("views/applications.py").run(); find(adm.selectbox, key="man_app").set_value(sid).run()
find(adm.selectbox, "New status").set_value("Interviewing"); submit(adm, "Update status")
check("Applications: status change form updates status and writes history", S("SELECT status FROM application WHERE application_id=:a", a=sid) == "Interviewing"
      and S("SELECT new_status FROM application_status_history WHERE application_id=:a ORDER BY log_id DESC LIMIT 1", a=sid) == "Interviewing")

# Hiring: offer -> approvals -> response
bg = Q("""SELECT a.application_id, j.salary_range_min FROM application a JOIN job_posting p ON p.posting_id=a.posting_id JOIN job j ON j.job_id=p.job_id
          WHERE a.status='BackgroundCheck' AND NOT EXISTS (SELECT 1 FROM background_check b WHERE b.application_id=a.application_id AND b.result IN ('Flagged','Failed'))
          ORDER BY a.application_id LIMIT 1""")[0]
adm.switch_page("views/hiring.py").run()
find(adm.selectbox, "Application").set_value(bg[0]); find(adm.number_input, "Offered salary (PKR per month)").set_value(float(bg[1]) + 2500)
find(adm.multiselect, "Approvers").set_value([12]); submit(adm, "Create offer and request approval")
oid = S("SELECT offer_id FROM job_offer WHERE application_id=:a", a=bg[0])
check("Hiring: create offer form saves the offer and its approval request", oid and S("SELECT status FROM job_offer WHERE offer_id=:o", o=oid) == "PendingApproval")
adm.switch_page("views/hiring.py").run()
xid = S("SELECT offer_approval_id FROM offer_approval WHERE offer_id=:o", o=oid)
find(adm.selectbox, "Approval").set_value(xid); submit(adm, "Record decision")
check("Hiring: approval decision moves the offer to Sent and the application to Offered",
      S("SELECT status FROM job_offer WHERE offer_id=:o", o=oid) == "Sent" and S("SELECT status FROM application WHERE application_id=:a", a=bg[0]) == "Offered")
adm.switch_page("views/hiring.py").run(); find(adm.selectbox, key="resp_offer").set_value(oid).run()
find(adm.radio, "Candidate response").set_value("Declined").run(); submit(adm, "Record response")
check("Hiring: offer response form (declined) updates offer and application", S("SELECT status FROM job_offer WHERE offer_id=:o", o=oid) == "Declined"
      and S("SELECT status FROM application WHERE application_id=:a", a=bg[0]) == "Withdrawn")
sent = S("SELECT offer_id FROM job_offer WHERE status='Sent' AND requisition_id IN (SELECT requisition_id FROM requisition_request WHERE requested_headcount > 1) LIMIT 1")
adm.switch_page("views/hiring.py").run(); find(adm.selectbox, key="resp_offer").set_value(sent).run()
find(adm.radio, "Candidate response").set_value("Accepted").run(); submit(adm, "Record response")
check("Hiring: accepting an offer hires the candidate and creates onboarding", S("SELECT COUNT(*) FROM onboarding WHERE offer_id=:o", o=sent) == 1)
adm.switch_page("views/hiring.py").run()
check("Hiring: onboarding tab and overview render", not adm.exception and not stray(adm))

# Vacancies: requisition -> approvals -> vacancy -> posting
adm.switch_page("views/vacancies.py").run()
find(adm.text_input, "Job title", nth=2).set_value("UI Test Role"); find(adm.selectbox, "Level 1 approver").set_value(12)
submit(adm, "Save requisition")
rid = S("SELECT requisition_id FROM requisition_request WHERE job_title='UI Test Role'")
check("Vacancies: raise requisition form saves and submits for approval", rid and S("SELECT status FROM requisition_request WHERE requisition_id=:r", r=rid) == "PendingApproval")
adm.switch_page("views/vacancies.py").run()
find(adm.selectbox, "Approval").set_value(S("SELECT approval_id FROM requisition_approval WHERE requisition_id=:r", r=rid)); submit(adm, "Record decision")
check("Vacancies: requisition approval decision approves the requisition", S("SELECT status FROM requisition_request WHERE requisition_id=:r", r=rid) == "Approved")
adm.switch_page("views/vacancies.py").run(); find(adm.selectbox, "Approved requisition").set_value(rid); submit(adm, "Create vacancy")
jid = S("SELECT job_id FROM job WHERE requisition_id=:r", r=rid)
check("Vacancies: add vacancy form creates the job from the approved requisition", jid is not None)
adm.switch_page("views/vacancies.py").run()
find(adm.selectbox, "Vacancy", nth=1).set_value(jid); submit(adm, "Publish posting")
check("Vacancies: publish posting form creates the posting", S("SELECT COUNT(*) FROM job_posting WHERE job_id=:j", j=jid) == 1)

# Reports: every report renders
adm.switch_page("views/reports.py").run(); bad = []
for name in ["Candidate report", "Vacancy report", "Application status report", "Interview report", "Recruitment funnel", "Hiring report", "Department summary"]:
    find(adm.selectbox, "Choose a report").set_value(name).run()
    if adm.exception or stray(adm): bad.append(name)
check("Reports: all seven reports render without errors", not bad, str(bad))

exec(open(ROOT / "tests" / "ui_design_checks.py", encoding="utf8").read())
failed = [n for n, ok in RESULTS if not ok]
print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} UI checks passed")
if failed: print("FAILED:", failed); sys.exit(1)
