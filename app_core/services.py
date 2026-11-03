"""
Write operations (create / update / delete) with validation, role checks and transactions.

Rules followed everywhere in this file
* require_role() is called first, so permissions are enforced on the server side, not just in the UI.
* Every statement uses bound parameters.
* Operations that touch several tables run inside one transaction (all-or-nothing).
* Important records are never deleted silently: candidates can only be removed when nothing depends on
  them; everything else is closed, withdrawn or rejected, and the change is logged in the status history.
"""
import re
from datetime import date, datetime

import streamlit as st
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError

from .auth import current_user, require_role
from .db import one, run, transaction
from .ui import notify

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
PHONE_RE = re.compile(r"^\+?[0-9][0-9\-\s]{6,18}[0-9]$")

TRANSITIONS = {
    "Applied": ["Screening", "Rejected", "Withdrawn"],
    "Screening": ["Interviewing", "Rejected", "Withdrawn"],
    "Interviewing": ["Assessment", "Rejected", "Withdrawn"],
    "Assessment": ["BackgroundCheck", "Rejected", "Withdrawn"],
    "BackgroundCheck": ["Rejected", "Withdrawn"],     # 'Offered' is set by the offer-approval workflow
    "Offered": ["Rejected", "Withdrawn"],             # 'Hired' is set when an offer is accepted
}
OPEN_STATUSES = list(TRANSITIONS)
REASON_REQUIRED = ("Rejected", "Withdrawn")


class ServiceError(Exception):
    """A problem the user can fix (bad input, rule violation). Shown as a friendly message."""


def call(fn, *args, **kwargs) -> bool:
    """Run a service function and turn any problem into a friendly message. Returns True on success.
    Shows a spinner while saving and ignores an identical request repeated within 3 seconds (double-click protection)."""
    import time
    sig = (fn.__name__, repr(args), repr(sorted(kwargs.items())))
    last = st.session_state.get("_last_call")
    if last and last[0] == sig and time.time() - last[1] < 3:
        notify("warning", "That action was just submitted. Duplicate submission ignored.")
        return False
    st.session_state["_last_call"] = (sig, time.time())
    try:
        with st.spinner("Saving..."):
            message = fn(*args, **kwargs)
        notify("success", message or "Saved.")
        return True
    except (ServiceError, PermissionError) as exc:
        notify("error", str(exc))
        st.session_state.pop("_last_call", None)        # a failed attempt may be corrected and retried at once
    except IntegrityError as exc:
        notify("error", "The database rejected this change because it would break a rule or relationship. "
                        f"Details: {str(exc.orig)[:160]}")
        st.session_state.pop("_last_call", None)
    except OperationalError as exc:
        notify("error", f"Database connection problem. Please try again. ({str(exc.orig)[:120]})")
        st.session_state.pop("_last_call", None)
    return False


# ---------------------------------------------------------------- small helpers
def _need(cond, message):
    if not cond:
        raise ServiceError(message)


def _text(value, label, maxlen, required=True):
    value = (value or "").strip()
    _need(value or not required, f"{label} is required.")
    _need(len(value) <= maxlen, f"{label} must be at most {maxlen} characters.")
    return value or None


def _actor(performed_by):
    if performed_by:
        return performed_by
    user = current_user()
    return user.get("employee_id") if user else None


def _history(conn, application_id, old, new, employee_id, reason_id):
    run(conn, """INSERT INTO application_status_history
                 (application_id, employee_id, reason_id, old_status, new_status, changed_date)
                 VALUES (:a, :e, :r, :o, :n, NOW())""",
        a=application_id, e=employee_id, r=reason_id, o=old, n=new)


def _set_status(conn, application_id, new_status, employee_id, reason_id=None, internal=False):
    row = one(conn, "SELECT status FROM application WHERE application_id = :a FOR UPDATE", a=application_id)
    _need(row, "Application not found.")
    old = row["status"]
    if old == new_status:
        return old
    allowed = TRANSITIONS.get(old, [])
    if not internal:
        _need(new_status in allowed, f"An application in '{old}' cannot move to '{new_status}'. "
                                     f"Allowed: {', '.join(allowed) or 'none (final status)'}.")
    if new_status in REASON_REQUIRED:
        _need(reason_id, f"Please choose a reason for '{new_status}'.")
    run(conn, "UPDATE application SET status = :s WHERE application_id = :a", s=new_status, a=application_id)
    _history(conn, application_id, old, new_status, employee_id, reason_id if new_status in REASON_REQUIRED else None)
    return old


# ================================================================= VACANCIES / REQUISITIONS
def create_requisition(department_id, raised_by, job_title, headcount, reason, deadline, submit, approver_ids):
    require_role("recruiter")
    job_title = _text(job_title, "Job title", 150)
    reason = _text(reason, "Reason", 500, required=False)
    _need(headcount and headcount >= 1, "Headcount must be at least 1.")
    _need(raised_by, "Please choose the employee raising the request.")
    _need(not deadline or deadline >= date.today(), "The hiring deadline cannot be in the past.")
    if submit:
        _need(approver_ids, "Choose at least one approver to submit the request.")
        _need(len(set(approver_ids)) == len(approver_ids), "The same approver was selected twice.")
    with transaction() as conn:
        res = run(conn, """INSERT INTO requisition_request (department_id, employee_id, job_title, requested_headcount,
                           reason, status, hiring_deadline, created_date)
                           VALUES (:d, :e, :t, :h, :r, :s, :dl, CURRENT_DATE)""",
                  d=department_id, e=raised_by, t=job_title, h=headcount, r=reason,
                  s="PendingApproval" if submit else "Draft", dl=deadline)
        rid = res.lastrowid
        if submit:
            for level, emp in enumerate(approver_ids, start=1):
                run(conn, """INSERT INTO requisition_approval (requisition_id, employee_id, approval_level, decision)
                             VALUES (:r, :e, :l, 'Pending')""", r=rid, e=emp, l=level)
    return f"Requisition #{rid} created ({'submitted for approval' if submit else 'saved as draft'})."


def decide_requisition_approval(approval_id, decision, comments):
    require_role("admin")
    _need(decision in ("Approved", "Rejected"), "Decision must be Approved or Rejected.")
    with transaction() as conn:
        row = one(conn, "SELECT * FROM requisition_approval WHERE approval_id = :a FOR UPDATE", a=approval_id)
        _need(row, "Approval record not found.")
        _need(row["decision"] == "Pending", "This approval has already been decided.")
        earlier = one(conn, """SELECT COUNT(*) AS n FROM requisition_approval WHERE requisition_id = :r
                               AND approval_level < :l AND decision <> 'Approved'""",
                      r=row["requisition_id"], l=row["approval_level"])
        _need(earlier["n"] == 0, "A lower approval level must be approved first.")
        run(conn, """UPDATE requisition_approval SET decision = :d, comments = :c, approval_date = CURRENT_DATE
                     WHERE approval_id = :a""", d=decision, c=_text(comments, "Comments", 500, False), a=approval_id)
        remaining = one(conn, """SELECT COUNT(*) AS n FROM requisition_approval WHERE requisition_id = :r
                                 AND decision = 'Pending'""", r=row["requisition_id"])["n"]
        new_status = "Rejected" if decision == "Rejected" else ("Approved" if remaining == 0 else "PendingApproval")
        run(conn, "UPDATE requisition_request SET status = :s WHERE requisition_id = :r",
            s=new_status, r=row["requisition_id"])
    return f"Approval recorded. Requisition #{row['requisition_id']} is now '{new_status}'."


def close_requisition(requisition_id):
    require_role("admin")
    with transaction() as conn:
        row = one(conn, "SELECT status FROM requisition_request WHERE requisition_id = :r FOR UPDATE", r=requisition_id)
        _need(row, "Requisition not found.")
        _need(row["status"] == "Approved", "Only an Approved requisition can be closed.")
        run(conn, "UPDATE requisition_request SET status = 'Closed', closed_date = CURRENT_DATE WHERE requisition_id = :r",
            r=requisition_id)
        run(conn, """UPDATE job_posting SET status = 'Closed' WHERE status = 'Active' AND job_id IN
                     (SELECT job_id FROM job WHERE requisition_id = :r)""", r=requisition_id)
    return f"Requisition #{requisition_id} closed and its active postings were closed too."


def _check_salary(low, high):
    _need(low is not None and high is not None, "Enter both the minimum and maximum salary.")
    _need(0 <= low <= high, "Minimum salary must be zero or more and not greater than the maximum.")


def create_job(requisition_id, location_id, employment_type_id, title, description, low, high):
    require_role("recruiter")
    title = _text(title, "Job title", 150)
    _check_salary(low, high)
    with transaction() as conn:
        req = one(conn, "SELECT department_id, status FROM requisition_request WHERE requisition_id = :r", r=requisition_id)
        _need(req, "Requisition not found.")
        _need(req["status"] == "Approved", "A vacancy can only be created from an Approved requisition.")
        res = run(conn, """INSERT INTO job (requisition_id, department_id, location_id, employment_type_id, job_title,
                           description, salary_range_min, salary_range_max)
                           VALUES (:r, :d, :l, :e, :t, :ds, :lo, :hi)""",
                  r=requisition_id, d=req["department_id"], l=location_id, e=employment_type_id, t=title,
                  ds=_text(description, "Description", 5000, False), lo=low, hi=high)
    return f"Vacancy #{res.lastrowid} '{title}' created."


def update_job(job_id, location_id, employment_type_id, title, description, low, high):
    require_role("recruiter")
    title = _text(title, "Job title", 150)
    _check_salary(low, high)
    with transaction() as conn:
        n = run(conn, """UPDATE job SET location_id = :l, employment_type_id = :e, job_title = :t, description = :ds,
                         salary_range_min = :lo, salary_range_max = :hi WHERE job_id = :j""",
                l=location_id, e=employment_type_id, t=title, ds=_text(description, "Description", 5000, False),
                lo=low, hi=high, j=job_id).rowcount
    return "Vacancy updated." if n else "No changes were made."


def set_job_skills(job_id, required_ids, optional_ids):
    require_role("recruiter")
    _need(not (set(required_ids) & set(optional_ids)), "A skill cannot be both required and optional.")
    with transaction() as conn:
        run(conn, "DELETE FROM job_skill WHERE job_id = :j", j=job_id)
        for sid in required_ids:
            run(conn, "INSERT INTO job_skill (job_id, skill_id, is_mandatory) VALUES (:j, :s, 1)", j=job_id, s=sid)
        for sid in optional_ids:
            run(conn, "INSERT INTO job_skill (job_id, skill_id, is_mandatory) VALUES (:j, :s, 0)", j=job_id, s=sid)
    return "Required skills saved."


def create_posting(job_id, source_id, publish_date, close_date):
    require_role("recruiter")
    _need(publish_date, "Publish date is required.")
    _need(not close_date or close_date >= publish_date, "The close date cannot be before the publish date.")
    with transaction() as conn:
        req = one(conn, """SELECT r.status FROM job j JOIN requisition_request r ON r.requisition_id = j.requisition_id
                           WHERE j.job_id = :j""", j=job_id)
        _need(req and req["status"] == "Approved", "Postings can only be added to vacancies with an Approved requisition.")
        res = run(conn, """INSERT INTO job_posting (job_id, source_id, publish_date, close_date, status)
                           VALUES (:j, :s, :p, :c, 'Active')""", j=job_id, s=source_id, p=publish_date, c=close_date)
    return f"Posting #{res.lastrowid} published."


def set_posting_status(posting_id, status, close_date):
    require_role("recruiter")
    _need(status in ("Active", "Closed", "Expired"), "Invalid posting status.")
    with transaction() as conn:
        row = one(conn, "SELECT publish_date FROM job_posting WHERE posting_id = :p", p=posting_id)
        _need(row, "Posting not found.")
        _need(not close_date or close_date >= row["publish_date"], "The close date cannot be before the publish date.")
        run(conn, "UPDATE job_posting SET status = :s, close_date = :c WHERE posting_id = :p",
            s=status, c=close_date, p=posting_id)
    return f"Posting #{posting_id} is now '{status}'."


# ================================================================= CANDIDATES
def _validate_candidate(name, email, phone):
    name = _text(name, "Name", 100)
    email = _text(email, "Email", 150).lower()
    _need(EMAIL_RE.match(email), "Enter a valid email address.")
    phone = _text(phone, "Contact number", 20, required=False)
    _need(not phone or PHONE_RE.match(phone), "Enter a valid contact number, for example 0321-1234567.")
    return name, email, phone


def create_candidate(name, email, phone, skill_levels: dict, resume_path):
    require_role("recruiter")
    name, email, phone = _validate_candidate(name, email, phone)
    with transaction() as conn:
        _need(not one(conn, "SELECT 1 AS x FROM candidate WHERE LOWER(candidate_email) = :e", e=email),
              "A candidate with this email already exists.")
        if phone:
            _need(not one(conn, "SELECT 1 AS x FROM candidate WHERE LOWER(candidate_name) = :n AND candidate_contact_no = :p",
                          n=name.lower(), p=phone), "A candidate with the same name and contact number already exists.")
        cid = run(conn, "INSERT INTO candidate (candidate_name, candidate_email, candidate_contact_no) VALUES (:n, :e, :p)",
                  n=name, e=email, p=phone).lastrowid
        for sid, level in skill_levels.items():
            run(conn, "INSERT INTO candidate_skill (candidate_id, skill_id, proficiency_level) VALUES (:c, :s, :l)",
                c=cid, s=sid, l=level)
        if resume_path and resume_path.strip():
            run(conn, "INSERT INTO resume (candidate_id, file_path, upload_date, is_primary) VALUES (:c, :f, CURRENT_DATE, 1)",
                c=cid, f=_text(resume_path, "Resume path", 255))
    return f"Candidate #{cid} '{name}' added."


def update_candidate(candidate_id, name, email, phone):
    require_role("recruiter")
    name, email, phone = _validate_candidate(name, email, phone)
    with transaction() as conn:
        _need(not one(conn, "SELECT 1 AS x FROM candidate WHERE LOWER(candidate_email) = :e AND candidate_id <> :c",
                      e=email, c=candidate_id), "Another candidate already uses this email.")
        run(conn, """UPDATE candidate SET candidate_name = :n, candidate_email = :e, candidate_contact_no = :p
                     WHERE candidate_id = :c""", n=name, e=email, p=phone, c=candidate_id)
    return "Candidate updated."


def set_candidate_skills(candidate_id, skill_levels: dict):
    require_role("recruiter")
    with transaction() as conn:
        run(conn, "DELETE FROM candidate_skill WHERE candidate_id = :c", c=candidate_id)
        for sid, level in skill_levels.items():
            run(conn, "INSERT INTO candidate_skill (candidate_id, skill_id, proficiency_level) VALUES (:c, :s, :l)",
                c=candidate_id, s=sid, l=level)
    return "Skills saved."


def add_resume(candidate_id, file_path, upload_date, make_primary):
    require_role("recruiter")
    file_path = _text(file_path, "Resume file path", 255)
    with transaction() as conn:
        has = one(conn, "SELECT COUNT(*) AS n FROM resume WHERE candidate_id = :c", c=candidate_id)["n"]
        primary = make_primary or has == 0
        if primary:
            run(conn, "UPDATE resume SET is_primary = 0 WHERE candidate_id = :c", c=candidate_id)
        run(conn, "INSERT INTO resume (candidate_id, file_path, upload_date, is_primary) VALUES (:c, :f, :d, :p)",
            c=candidate_id, f=file_path, d=upload_date or date.today(), p=1 if primary else 0)
    return "Resume added."


def add_referral(candidate_id, employee_id, referral_date):
    require_role("recruiter")
    _need(employee_id, "Choose the referring employee.")
    with transaction() as conn:
        run(conn, "INSERT INTO referral (candidate_id, employee_id, referral_date, status) VALUES (:c, :e, :d, 'Pending')",
            c=candidate_id, e=employee_id, d=referral_date or date.today())
    return "Referral recorded."


def delete_candidate(candidate_id):
    require_role("admin")
    with transaction() as conn:
        deps = one(conn, """SELECT (SELECT COUNT(*) FROM application WHERE candidate_id = :c) AS apps,
                                   (SELECT COUNT(*) FROM referral WHERE candidate_id = :c) AS refs""", c=candidate_id)
        _need(deps["apps"] == 0, "This candidate has applications, so the record must be kept for recruitment history.")
        _need(deps["refs"] == 0, "This candidate has referral records, so the record must be kept.")
        run(conn, "DELETE FROM candidate_skill WHERE candidate_id = :c", c=candidate_id)
        run(conn, "DELETE FROM resume WHERE candidate_id = :c", c=candidate_id)
        run(conn, "DELETE FROM candidate WHERE candidate_id = :c", c=candidate_id)
    return "Candidate deleted."


# ================================================================= APPLICATIONS
def create_application(candidate_id, posting_id, date_applied, performed_by):
    require_role("recruiter")
    _need(candidate_id and posting_id, "Choose a candidate and a posting.")
    _need(date_applied and date_applied <= date.today(), "The application date cannot be in the future.")
    with transaction() as conn:
        post = one(conn, "SELECT job_id, status, publish_date, close_date FROM job_posting WHERE posting_id = :p", p=posting_id)
        _need(post, "Posting not found.")
        _need(post["status"] == "Active", "Applications can only be added to Active postings.")
        _need(date_applied >= post["publish_date"], "The application date is before the posting was published.")
        _need(not post["close_date"] or date_applied <= post["close_date"], "The posting had already closed on that date.")
        same_job = one(conn, """SELECT COUNT(*) AS n FROM application a JOIN job_posting p ON p.posting_id = a.posting_id
                                WHERE a.candidate_id = :c AND p.job_id = :j""", c=candidate_id, j=post["job_id"])["n"]
        _need(same_job == 0, "This candidate has already applied for this vacancy (possibly through another posting).")
        aid = run(conn, "INSERT INTO application (candidate_id, posting_id, date_applied, status) VALUES (:c, :p, :d, 'Applied')",
                  c=candidate_id, p=posting_id, d=date_applied).lastrowid
        _history(conn, aid, None, "Applied", _actor(performed_by), None)
    return f"Application #{aid} created."


def change_status(application_id, new_status, performed_by, reason_id):
    require_role("recruiter")
    with transaction() as conn:
        old = _set_status(conn, application_id, new_status, _actor(performed_by), reason_id)
    return f"Application #{application_id}: {old} -> {new_status}."


def add_screening(application_id, reviewer_id, outcome, score, notes, reason_id):
    require_role("recruiter")
    _need(outcome in ("Shortlisted", "Rejected", "OnHold"), "Choose an outcome.")
    _need(reviewer_id, "Choose the reviewer.")
    _need(score is None or 0 <= score <= 100, "Score must be between 0 and 100.")
    if outcome == "Rejected":
        _need(reason_id, "Choose a rejection reason.")
    with transaction() as conn:
        row = one(conn, "SELECT status FROM application WHERE application_id = :a FOR UPDATE", a=application_id)
        _need(row, "Application not found.")
        _need(row["status"] in ("Applied", "Screening"), f"Screening can only be recorded for Applied/Screening applications (this one is '{row['status']}').")
        run(conn, """INSERT INTO screening (application_id, employee_id, reason_id, outcome, score, notes, screening_date)
                     VALUES (:a, :e, :r, :o, :s, :n, CURRENT_DATE)""",
            a=application_id, e=reviewer_id, r=reason_id if outcome == "Rejected" else None, o=outcome, s=score,
            n=_text(notes, "Notes", 500, False))
        if row["status"] == "Applied":
            _set_status(conn, application_id, "Screening", reviewer_id)
        if outcome == "Shortlisted":
            _set_status(conn, application_id, "Interviewing", reviewer_id)
        elif outcome == "Rejected":
            _set_status(conn, application_id, "Rejected", reviewer_id, reason_id)
    return f"Screening recorded ({outcome})."


def add_assessment(application_id, type_id, score, remarks, assessment_date):
    require_role("recruiter")
    _need(score is not None and 0 <= score <= 100, "Score must be between 0 and 100.")
    _need(assessment_date and assessment_date <= date.today(), "The assessment date cannot be in the future.")
    with transaction() as conn:
        row = one(conn, "SELECT status FROM application WHERE application_id = :a", a=application_id)
        _need(row and row["status"] in ("Interviewing", "Assessment"),
              "Assessments can be recorded once the application is in Interviewing or Assessment.")
        run(conn, """INSERT INTO assessment (application_id, assessment_type_id, score, remarks, assessment_date)
                     VALUES (:a, :t, :s, :r, :d)""", a=application_id, t=type_id, s=score,
            r=_text(remarks, "Remarks", 500, False), d=assessment_date)
        passing = one(conn, "SELECT passing_score FROM assessment_type WHERE assessment_type_id = :t", t=type_id)["passing_score"]
    verdict = "passed" if passing is not None and score >= passing else "below the passing score"
    return f"Assessment recorded ({score}, {verdict})."


def add_background_check(application_id, provider, initiated, completion, status, result):
    require_role("recruiter")
    _need(status in ("Pending", "InProgress", "Completed"), "Invalid status.")
    _need(status != "Completed" or (completion and result), "A completed check needs a completion date and a result.")
    _need(not (initiated and completion) or completion >= initiated, "Completion cannot be before initiation.")
    with transaction() as conn:
        row = one(conn, "SELECT status FROM application WHERE application_id = :a", a=application_id)
        _need(row and row["status"] in ("Assessment", "BackgroundCheck"),
              "Background checks can be recorded for applications in Assessment or BackgroundCheck.")
        run(conn, """INSERT INTO background_check (application_id, provider, initiated_date, completion_date, status, result)
                     VALUES (:a, :p, :i, :c, :s, :r)""", a=application_id, p=_text(provider, "Provider", 100, False),
            i=initiated, c=completion, s=status, r=result if status == "Completed" else None)
    return "Background check recorded."


# ================================================================= INTERVIEWS
def _interview_app_check(conn, application_id):
    row = one(conn, "SELECT status FROM application WHERE application_id = :a", a=application_id)
    _need(row, "Application not found.")
    _need(row["status"] == "Interviewing", f"Interviews can only be scheduled for applications in 'Interviewing' (this one is '{row['status']}').")


def schedule_interview(application_id, round_type, when: datetime, mode, panel_ids):
    require_role("recruiter")
    _need(round_type in ("HR", "Technical", "Managerial", "Final"), "Choose the interview round.")
    _need(mode in ("Onsite", "Virtual", "Phone"), "Choose the interview mode.")
    _need(panel_ids, "Choose at least one panel member.")
    _need(len(set(panel_ids)) == len(panel_ids), "A panel member was selected twice.")
    with transaction() as conn:
        _interview_app_check(conn, application_id)
        dup = one(conn, "SELECT COUNT(*) AS n FROM interview WHERE application_id = :a AND round_type = :r",
                  a=application_id, r=round_type)["n"]
        _need(dup == 0, f"A '{round_type}' interview already exists for this application. Edit it instead.")
        iid = run(conn, "INSERT INTO interview (application_id, round_type, interview_date, mode) VALUES (:a, :r, :d, :m)",
                  a=application_id, r=round_type, d=when, m=mode).lastrowid
        for emp in panel_ids:
            run(conn, "INSERT INTO interview_participant (interview_id, employee_id) VALUES (:i, :e)", i=iid, e=emp)
    return f"Interview #{iid} scheduled."


def update_interview(interview_id, when, mode, panel_ids):
    require_role("recruiter")
    _need(panel_ids, "The panel cannot be empty.")
    with transaction() as conn:
        _need(one(conn, "SELECT 1 AS x FROM interview WHERE interview_id = :i", i=interview_id), "Interview not found.")
        evaluated = {r["employee_id"] for r in conn.execute(
            text("SELECT employee_id FROM interview_evaluation WHERE interview_id = :i"),
            {"i": interview_id}).mappings()}
        _need(evaluated <= set(panel_ids), "A panel member who already submitted feedback cannot be removed.")
        run(conn, "UPDATE interview SET interview_date = :d, mode = :m WHERE interview_id = :i", d=when, m=mode, i=interview_id)
        run(conn, "DELETE FROM interview_participant WHERE interview_id = :i", i=interview_id)
        for emp in panel_ids:
            run(conn, "INSERT INTO interview_participant (interview_id, employee_id) VALUES (:i, :e)", i=interview_id, e=emp)
    return "Interview updated."


def record_evaluation(interview_id, employee_id, rating, recommendation, comments):
    require_role("recruiter")
    _need(rating in (1, 2, 3, 4, 5), "Rating must be 1 to 5.")
    _need(recommendation in ("StrongHire", "Hire", "NoHire", "StrongNoHire"), "Choose a recommendation.")
    with transaction() as conn:
        _need(one(conn, "SELECT 1 AS x FROM interview_participant WHERE interview_id = :i AND employee_id = :e",
                  i=interview_id, e=employee_id), "Only members of the interview panel can submit feedback.")
        existing = one(conn, "SELECT evaluation_id FROM interview_evaluation WHERE interview_id = :i AND employee_id = :e",
                       i=interview_id, e=employee_id)
        comments = _text(comments, "Comments", 500, False)
        if existing:
            run(conn, """UPDATE interview_evaluation SET rating = :r, recommendation = :c, comments = :m, submitted_date = NOW()
                         WHERE evaluation_id = :v""", r=rating, c=recommendation, m=comments, v=existing["evaluation_id"])
            return "Feedback updated."
        run(conn, """INSERT INTO interview_evaluation (interview_id, employee_id, rating, recommendation, comments, submitted_date)
                     VALUES (:i, :e, :r, :c, :m, NOW())""", i=interview_id, e=employee_id, r=rating, c=recommendation, m=comments)
    return "Feedback saved."


def delete_interview(interview_id):
    require_role("admin")
    with transaction() as conn:
        n = one(conn, "SELECT COUNT(*) AS n FROM interview_evaluation WHERE interview_id = :i", i=interview_id)["n"]
        _need(n == 0, "This interview already has feedback, so it must be kept.")
        run(conn, "DELETE FROM interview_participant WHERE interview_id = :i", i=interview_id)
        run(conn, "DELETE FROM interview WHERE interview_id = :i", i=interview_id)
    return "Interview deleted."


# ================================================================= HIRING
def create_offer(application_id, salary, start_date, approver_ids, performed_by):
    require_role("recruiter")
    _need(salary and salary > 0, "Enter the offered salary.")
    _need(approver_ids and len(set(approver_ids)) == len(approver_ids), "Choose at least one approver (no duplicates).")
    _need(start_date and start_date >= date.today(), "The start date cannot be in the past.")
    with transaction() as conn:
        app = one(conn, """SELECT a.status, j.salary_range_min AS lo, j.salary_range_max AS hi, r.requisition_id
                           FROM application a JOIN job_posting p ON p.posting_id = a.posting_id
                           JOIN job j ON j.job_id = p.job_id
                           JOIN requisition_request r ON r.requisition_id = j.requisition_id
                           WHERE a.application_id = :a FOR UPDATE""", a=application_id)
        _need(app, "Application not found.")
        _need(app["status"] == "BackgroundCheck", f"Offers can be prepared for applications in 'BackgroundCheck' (this one is '{app['status']}').")
        bad = one(conn, "SELECT COUNT(*) AS n FROM background_check WHERE application_id = :a AND result IN ('Flagged','Failed')", a=application_id)["n"]
        _need(bad == 0, "The background check was Flagged/Failed, so an offer cannot be made.")
        _need(app["lo"] is None or salary >= app["lo"], f"The salary is below the vacancy range (minimum {app['lo']:,.0f}).")
        _need(app["hi"] is None or salary <= app["hi"], f"The salary is above the vacancy range (maximum {app['hi']:,.0f}).")
        live = one(conn, """SELECT COUNT(*) AS n FROM job_offer WHERE application_id = :a
                            AND status IN ('Draft','PendingApproval','Sent','Accepted')""", a=application_id)["n"]
        _need(live == 0, "This application already has an active offer.")
        oid = run(conn, """INSERT INTO job_offer (application_id, requisition_id, salary_offered, start_date, status)
                           VALUES (:a, :r, :s, :d, 'PendingApproval')""",
                  a=application_id, r=app["requisition_id"], s=salary, d=start_date).lastrowid
        for emp in approver_ids:
            run(conn, "INSERT INTO offer_approval (offer_id, employee_id, decision) VALUES (:o, :e, 'Pending')", o=oid, e=emp)
    return f"Offer #{oid} created and sent for approval."


def decide_offer_approval(offer_approval_id, decision, approved_salary, performed_by):
    require_role("admin")
    _need(decision in ("Approved", "Rejected"), "Decision must be Approved or Rejected.")
    with transaction() as conn:
        row = one(conn, """SELECT oa.offer_id, oa.decision, o.salary_offered, o.application_id, o.status
                           FROM offer_approval oa JOIN job_offer o ON o.offer_id = oa.offer_id
                           WHERE oa.offer_approval_id = :x FOR UPDATE""", x=offer_approval_id)
        _need(row, "Approval record not found.")
        _need(row["decision"] == "Pending", "This approval has already been decided.")
        _need(row["status"] == "PendingApproval", "The offer is no longer waiting for approval.")
        run(conn, "UPDATE offer_approval SET decision = :d, approved_salary = :s, approval_date = CURRENT_DATE WHERE offer_approval_id = :x",
            d=decision, s=(approved_salary or row["salary_offered"]) if decision == "Approved" else None, x=offer_approval_id)
        left = one(conn, "SELECT COUNT(*) AS n FROM offer_approval WHERE offer_id = :o AND decision = 'Pending'", o=row["offer_id"])["n"]
        if decision == "Rejected":
            run(conn, "UPDATE job_offer SET status = 'Withdrawn' WHERE offer_id = :o", o=row["offer_id"])
            return f"Offer #{row['offer_id']} was rejected and withdrawn."
        if left == 0:
            run(conn, "UPDATE job_offer SET status = 'Sent' WHERE offer_id = :o", o=row["offer_id"])
            _set_status(conn, row["application_id"], "Offered", _actor(performed_by), internal=True)
            return f"All approvals complete. Offer #{row['offer_id']} is now 'Sent' and the application is 'Offered'."
    return "Approval recorded. Waiting for the remaining approvers."


def respond_offer(offer_id, response, performed_by, joining_date, hr_employee_id, reason_id):
    require_role("recruiter")
    _need(response in ("Accepted", "Declined", "Withdrawn"), "Choose a response.")
    with transaction() as conn:
        o = one(conn, "SELECT offer_id, application_id, requisition_id, status FROM job_offer WHERE offer_id = :o FOR UPDATE", o=offer_id)
        _need(o, "Offer not found.")
        _need(o["status"] == "Sent", f"Only a 'Sent' offer can receive a response (this one is '{o['status']}').")
        actor = _actor(performed_by)
        if response == "Accepted":
            _need(joining_date and joining_date >= date.today(), "Enter a joining date that is today or later.")
            _need(hr_employee_id, "Choose the HR employee who will handle onboarding.")
            filled = one(conn, """SELECT COUNT(*) AS n FROM application a JOIN job_posting p ON p.posting_id = a.posting_id
                                  JOIN job j ON j.job_id = p.job_id WHERE j.requisition_id = :r AND a.status = 'Hired'""",
                         r=o["requisition_id"])["n"]
            need = one(conn, "SELECT requested_headcount AS h FROM requisition_request WHERE requisition_id = :r", r=o["requisition_id"])["h"]
            _need(filled < need, f"The requisition's headcount ({need}) is already filled.")
            run(conn, "UPDATE job_offer SET status = 'Accepted', start_date = :d WHERE offer_id = :o", d=joining_date, o=offer_id)
            run(conn, "INSERT INTO onboarding (offer_id, employee_id, joining_date, status) VALUES (:o, :e, :d, 'Pending')",
                o=offer_id, e=hr_employee_id, d=joining_date)
            _set_status(conn, o["application_id"], "Hired", actor, internal=True)
            return "Offer accepted. The candidate is Hired and an onboarding record was created."
        if response == "Declined":
            run(conn, "UPDATE job_offer SET status = 'Declined' WHERE offer_id = :o", o=offer_id)
            _set_status(conn, o["application_id"], "Withdrawn", actor, reason_id or 12)
            return "Offer declined by the candidate; the application is Withdrawn."
        _need(reason_id, "Choose a reason for withdrawing the offer.")
        run(conn, "UPDATE job_offer SET status = 'Withdrawn' WHERE offer_id = :o", o=offer_id)
        _set_status(conn, o["application_id"], "Rejected", actor, reason_id)
        return "Offer withdrawn; the application is Rejected."


def update_onboarding(onboarding_id, status, joining_date, hr_employee_id):
    require_role("recruiter")
    _need(status in ("Pending", "DocumentsSubmitted", "Completed"), "Invalid status.")
    _need(hr_employee_id, "Choose the assigned HR employee.")
    with transaction() as conn:
        run(conn, "UPDATE onboarding SET status = :s, joining_date = :d, employee_id = :e WHERE onboarding_id = :o",
            s=status, d=joining_date, e=hr_employee_id, o=onboarding_id)
    return "Onboarding updated."
