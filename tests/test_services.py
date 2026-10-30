"""
End-to-end test of the write operations (validation, role checks, transactions, status workflow).
WARNING: it modifies the database it runs against. Run it only on a scratch copy.
    python tests/test_services.py
"""
import pathlib
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sqlalchemy import text           # noqa: E402
from app_core import auth, db, services as S   # noqa: E402

USER = {"username": "t", "role": "admin", "display_name": "Tester", "employee_id": 12}
auth.current_user = lambda: USER

eng = db.get_engine()
def val(sql, **p):
    with eng.connect() as c:
        return c.execute(text(sql), p).scalar()

def expect_error(fn, *a, contains=""):
    try:
        fn(*a)
    except (S.ServiceError, PermissionError) as e:
        assert contains.lower() in str(e).lower(), f"unexpected message: {e}"
        return
    raise AssertionError(f"{fn.__name__} should have been rejected ({contains})")

def step(msg):
    print("  ok ", msg)

# ---------------------------------------------------------------- roles
USER["role"] = "viewer"
expect_error(S.create_candidate, "A B", "a@b.co", "", {}, "", contains="recruiter")
USER["role"] = "recruiter"
expect_error(S.delete_candidate, 1, contains="admin")
step("viewer / recruiter are blocked from restricted writes")
USER["role"] = "admin"

# ---------------------------------------------------------------- candidates
n0 = val("SELECT COUNT(*) FROM candidate")
msg = S.create_candidate("Test Person", "test.person@example.com", "0300-1234567", {1: "Advanced", 2: "Beginner"}, "resumes/test.pdf")
cid = val("SELECT candidate_id FROM candidate WHERE candidate_email='test.person@example.com'")
assert val("SELECT COUNT(*) FROM candidate_skill WHERE candidate_id=:c", c=cid) == 2
assert val("SELECT COUNT(*) FROM resume WHERE candidate_id=:c AND is_primary=1", c=cid) == 1
expect_error(S.create_candidate, "Other", "TEST.person@example.com", "", {}, "", contains="already exists")
expect_error(S.create_candidate, "Bad", "not-an-email", "", {}, "", contains="valid email")
expect_error(S.create_candidate, "Bad", "bad@example.com", "abc", {}, "", contains="contact number")
expect_error(S.create_candidate, "", "x@example.com", "", {}, "", contains="required")
assert val("SELECT COUNT(*) FROM candidate") == n0 + 1
step("create candidate (+skills +resume) and validation / duplicate checks")

S.update_candidate(cid, "Test Person Updated", "test.person@example.com", "0321-7654321")
other_email = val("SELECT candidate_email FROM candidate WHERE candidate_id <> :c LIMIT 1", c=cid)
expect_error(S.update_candidate, cid, "X", other_email, "", contains="already uses")
S.set_candidate_skills(cid, {3: "Expert"})
assert val("SELECT COUNT(*) FROM candidate_skill WHERE candidate_id=:c", c=cid) == 1
S.add_resume(cid, "resumes/test_v2.pdf", date.today(), True)
assert val("SELECT COUNT(*) FROM resume WHERE candidate_id=:c AND is_primary=1", c=cid) == 1
step("update candidate, skills, resume (single primary resume kept)")

with_apps = val("SELECT candidate_id FROM application LIMIT 1")
expect_error(S.delete_candidate, with_apps, contains="applications")
step("candidate with applications cannot be deleted")

# ---------------------------------------------------------------- application workflow
posting = eng.connect().execute(text("""SELECT p.posting_id, p.job_id FROM job_posting p JOIN job j ON j.job_id=p.job_id
        JOIN requisition_request r ON r.requisition_id=j.requisition_id
        WHERE p.status='Active' AND r.requested_headcount=1 AND r.status='Approved' ORDER BY p.posting_id LIMIT 1""")).first()
pid, jid = posting
S.create_application(cid, pid, date.today(), None)
aid = val("SELECT application_id FROM application WHERE candidate_id=:c AND posting_id=:p", c=cid, p=pid)
assert val("SELECT COUNT(*) FROM application_status_history WHERE application_id=:a", a=aid) == 1
expect_error(S.create_application, cid, pid, date.today(), None, contains="already applied")
expect_error(S.create_application, cid, pid, date.today() + timedelta(days=3), None, contains="future")
step("application created with first history row; duplicates / future dates rejected")

expect_error(S.change_status, aid, "Hired", None, None, contains="cannot move")
expect_error(S.change_status, aid, "Rejected", None, None, contains="reason")
S.add_screening(aid, 12, "Shortlisted", 80, "Good profile", None)
assert val("SELECT status FROM application WHERE application_id=:a", a=aid) == "Interviewing"
assert val("SELECT COUNT(*) FROM application_status_history WHERE application_id=:a", a=aid) == 3
step("illegal transitions blocked; shortlisting moves the application to Interviewing (3 history rows)")

# ---------------------------------------------------------------- interview + transaction rollback
before = val("SELECT COUNT(*) FROM interview")
try:
    S.schedule_interview(aid, "HR", datetime.now() + timedelta(days=1), "Virtual", [12, 99999])
    raise AssertionError("invalid employee id should fail")
except Exception as e:
    assert "AssertionError" not in type(e).__name__
assert val("SELECT COUNT(*) FROM interview") == before, "interview must be rolled back with the failed participant"
step("failed multi-table write is rolled back completely (no orphan interview)")
S.schedule_interview(aid, "HR", datetime.now() - timedelta(hours=2), "Virtual", [12, 13])
iid = val("SELECT MAX(interview_id) FROM interview")
expect_error(S.schedule_interview, aid, "HR", datetime.now(), "Virtual", [12], contains="already exists")
expect_error(S.record_evaluation, iid, 14, 4, "Hire", "", contains="panel")
S.record_evaluation(iid, 12, 4, "Hire", "Good")
S.record_evaluation(iid, 12, 5, "StrongHire", "Great")
assert val("SELECT rating FROM interview_evaluation WHERE interview_id=:i AND employee_id=12", i=iid) == 5
expect_error(S.update_interview, iid, datetime.now(), "Phone", [13], contains="already submitted")
expect_error(S.delete_interview, iid, contains="feedback")
step("interview scheduled; feedback upsert; panel/delete protections")

# ---------------------------------------------------------------- assessment -> background -> offer -> hired
S.change_status(aid, "Assessment", None, None)
S.add_assessment(aid, 1, 85, "Strong", date.today())
S.change_status(aid, "BackgroundCheck", None, None)
S.add_background_check(aid, "Verifex", date.today() - timedelta(days=3), date.today(), "Completed", "Clear")
lo, hi = val("SELECT salary_range_min FROM job WHERE job_id=:j", j=jid), val("SELECT salary_range_max FROM job WHERE job_id=:j", j=jid)
expect_error(S.create_offer, aid, float(hi) + 50000, date.today() + timedelta(days=20), [12], None, contains="above")
expect_error(S.create_offer, aid, float(lo) - 1000, date.today() + timedelta(days=20), [12], None, contains="below")
S.create_offer(aid, float(lo) + 5000, date.today() + timedelta(days=20), [12, 181], None)
oid = val("SELECT offer_id FROM job_offer WHERE application_id=:a", a=aid)
assert val("SELECT status FROM job_offer WHERE offer_id=:o", o=oid) == "PendingApproval"
expect_error(S.create_offer, aid, float(lo) + 5000, date.today() + timedelta(days=20), [12], None, contains="active offer")
ids = [r[0] for r in eng.connect().execute(text("SELECT offer_approval_id FROM offer_approval WHERE offer_id=:o ORDER BY 1"), {"o": oid})]
S.decide_offer_approval(ids[0], "Approved", None, None)
assert val("SELECT status FROM job_offer WHERE offer_id=:o", o=oid) == "PendingApproval"
S.decide_offer_approval(ids[1], "Approved", None, None)
assert val("SELECT status FROM job_offer WHERE offer_id=:o", o=oid) == "Sent"
assert val("SELECT status FROM application WHERE application_id=:a", a=aid) == "Offered"
expect_error(S.decide_offer_approval, ids[1], "Approved", None, None, contains="already")
step("offer: salary range rules, two-step approval, application moves to Offered")

S.respond_offer(oid, "Accepted", None, date.today() + timedelta(days=21), 12, None)
assert val("SELECT status FROM application WHERE application_id=:a", a=aid) == "Hired"
assert val("SELECT COUNT(*) FROM onboarding WHERE offer_id=:o", o=oid) == 1
last = val("SELECT new_status FROM application_status_history WHERE application_id=:a ORDER BY log_id DESC LIMIT 1", a=aid)
assert last == "Hired"
step("offer accepted -> Hired + onboarding record + history (headcount rule applied)")
S.update_onboarding(val("SELECT onboarding_id FROM onboarding WHERE offer_id=:o", o=oid), "DocumentsSubmitted", date.today() + timedelta(days=21), 12)

# ---------------------------------------------------------------- requisition -> approval -> vacancy -> posting -> close
S.create_requisition(4, 12, "QA Engineer (test)", 2, "Test reason", date.today() + timedelta(days=30), True, [12, 181])
rid = val("SELECT MAX(requisition_id) FROM requisition_request")
a1, a2 = [r[0] for r in eng.connect().execute(text("SELECT approval_id FROM requisition_approval WHERE requisition_id=:r ORDER BY approval_level"), {"r": rid})]
expect_error(S.decide_requisition_approval, a2, "Approved", "", contains="lower approval level")
S.decide_requisition_approval(a1, "Approved", "ok")
S.decide_requisition_approval(a2, "Approved", "ok")
assert val("SELECT status FROM requisition_request WHERE requisition_id=:r", r=rid) == "Approved"
S.create_job(rid, 2, 1, "QA Engineer (test)", "desc", 70000, 90000)
expect_error(S.create_job, rid, 2, 1, "x", "", 90000, 70000, contains="Minimum salary")
j2 = val("SELECT MAX(job_id) FROM job")
S.create_posting(j2, 1, date.today(), date.today() + timedelta(days=20))
expect_error(S.create_posting, j2, 1, date.today(), date.today() - timedelta(days=1), contains="close date")
S.set_job_skills(j2, [1, 2], [3])
S.close_requisition(rid)
assert val("SELECT COUNT(*) FROM job_posting WHERE job_id=:j AND status='Active'", j=j2) == 0
rej = S.create_requisition(4, 12, "Draft role", 1, "", None, False, [])
step("requisition -> sequential approvals -> vacancy -> posting -> close (postings closed too)")

# ---------------------------------------------------------------- delete a fresh candidate
S.create_candidate("Delete Me", "delete.me@example.com", "", {}, "")
did = val("SELECT candidate_id FROM candidate WHERE candidate_email='delete.me@example.com'")
S.delete_candidate(did)
assert val("SELECT COUNT(*) FROM candidate WHERE candidate_id=:c", c=did) == 0
step("candidate without dependencies can be deleted by an admin")
print("ALL SERVICE TESTS PASSED")
