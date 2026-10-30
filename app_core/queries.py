"""Read-only queries (all cached through db.q). Filtering happens in pandas, so no dynamic SQL is built."""
import pandas as pd

from .db import options, q

# ---------------------------------------------------------------- lookup lists for forms
def departments():      return options("SELECT department_id, CONCAT(department_name, ' - ', location) FROM department ORDER BY department_name, location")
def locations():        return options("SELECT location_id, CONCAT(city, ' (', work_mode, ')') FROM location ORDER BY city")
def employment_types(): return options("SELECT employment_type_id, employment_type_name FROM employment_type ORDER BY employment_type_name")
def sources():          return options("SELECT source_id, CONCAT(source_name, ' [', source_type, ']') FROM source ORDER BY source_name")
def skills():           return options("SELECT skill_id, skill_name FROM skill ORDER BY skill_name")
def rejection_reasons(): return options("SELECT reason_id, CONCAT(stage, ': ', description) FROM rejection_reason ORDER BY reason_id")
def assessment_types(): return options("SELECT assessment_type_id, CONCAT(assessment_type_name, ' (pass ', passing_score, ')') FROM assessment_type ORDER BY assessment_type_name")
def employees(roles: tuple = ()):
    sql = ("SELECT e.employee_id, CONCAT(e.employee_name, ' - ', dg.designation_title) FROM employee e "
           "JOIN designation dg ON dg.designation_id = e.designation_id ")
    if roles:
        sql += "WHERE dg.role_category IN (" + ",".join("'%s'" % r for r in roles if r.isalpha()) + ") "
    return options(sql + "ORDER BY e.employee_name")
def candidates_list():  return options("SELECT candidate_id, CONCAT(candidate_name, ' <', candidate_email, '>') FROM candidate ORDER BY candidate_name")


# ---------------------------------------------------------------- core tables
def candidates() -> pd.DataFrame:
    return q("""
        SELECT c.candidate_id, c.candidate_name, c.candidate_email, c.candidate_contact_no,
               (SELECT GROUP_CONCAT(s.skill_name ORDER BY s.skill_name SEPARATOR ', ')
                  FROM candidate_skill cs JOIN skill s ON s.skill_id = cs.skill_id
                 WHERE cs.candidate_id = c.candidate_id) AS skills,
               (SELECT COUNT(*) FROM application a WHERE a.candidate_id = c.candidate_id) AS applications,
               (SELECT MIN(a.date_applied) FROM application a WHERE a.candidate_id = c.candidate_id) AS first_applied
        FROM candidate c ORDER BY c.candidate_id""")


def applications() -> pd.DataFrame:
    return q("""
        SELECT a.application_id, a.candidate_id, c.candidate_name, j.job_id, j.job_title,
               d.department_name, p.posting_id, s.source_name, a.date_applied, a.status
        FROM application a
        JOIN candidate c ON c.candidate_id = a.candidate_id
        JOIN job_posting p ON p.posting_id = a.posting_id
        JOIN job j ON j.job_id = p.job_id
        JOIN department d ON d.department_id = j.department_id
        JOIN source s ON s.source_id = p.source_id
        ORDER BY a.application_id DESC""")


def vacancies() -> pd.DataFrame:
    df = q("""
        SELECT j.job_id, j.requisition_id, j.job_title, d.department_name,
               CONCAT(l.city, ' (', l.work_mode, ')') AS location, et.employment_type_name AS employment_type,
               j.salary_range_min, j.salary_range_max, r.requested_headcount AS headcount,
               r.status AS requisition_status, r.hiring_deadline,
               (SELECT COUNT(*) FROM job_posting p WHERE p.job_id = j.job_id) AS postings,
               (SELECT COUNT(*) FROM job_posting p WHERE p.job_id = j.job_id AND p.status = 'Active') AS active_postings,
               (SELECT COUNT(*) FROM application a JOIN job_posting p ON p.posting_id = a.posting_id
                 WHERE p.job_id = j.job_id) AS applications,
               (SELECT COUNT(*) FROM application a JOIN job_posting p ON p.posting_id = a.posting_id
                 WHERE p.job_id = j.job_id AND a.status = 'Hired') AS hires
        FROM job j
        JOIN requisition_request r ON r.requisition_id = j.requisition_id
        JOIN department d ON d.department_id = j.department_id
        JOIN location l ON l.location_id = j.location_id
        JOIN employment_type et ON et.employment_type_id = j.employment_type_id
        ORDER BY j.job_id DESC""")
    if df.empty:
        df["vacancy_status"] = []
        df["open_positions"] = []
        return df
    df["open_positions"] = (df["headcount"] - df["hires"]).clip(lower=0)

    def status(r):
        if r["requisition_status"] == "Closed":
            return "Closed"
        if r["hires"] >= r["headcount"]:
            return "Filled"
        return "Open" if r["active_postings"] > 0 else "Not advertised"
    df["vacancy_status"] = df.apply(status, axis=1)
    return df


def requisitions() -> pd.DataFrame:
    return q("""
        SELECT r.requisition_id, d.department_name, e.employee_name AS raised_by, r.job_title,
               r.requested_headcount AS headcount, r.reason, r.status, r.hiring_deadline,
               r.created_date, r.closed_date,
               (SELECT COUNT(*) FROM requisition_approval ra WHERE ra.requisition_id = r.requisition_id
                   AND ra.decision = 'Pending') AS pending_approvals,
               (SELECT COUNT(*) FROM job j WHERE j.requisition_id = r.requisition_id) AS jobs
        FROM requisition_request r
        JOIN department d ON d.department_id = r.department_id
        JOIN employee e ON e.employee_id = r.employee_id
        ORDER BY r.requisition_id DESC""")


def requisition_approvals(requisition_id: int | None = None) -> pd.DataFrame:
    df = q("""
        SELECT ra.approval_id, ra.requisition_id, r.job_title, ra.approval_level, e.employee_name AS approver,
               ra.decision, ra.comments, ra.approval_date
        FROM requisition_approval ra
        JOIN requisition_request r ON r.requisition_id = ra.requisition_id
        JOIN employee e ON e.employee_id = ra.employee_id
        ORDER BY ra.requisition_id DESC, ra.approval_level""")
    return df if requisition_id is None else df[df["requisition_id"] == requisition_id]


def postings() -> pd.DataFrame:
    return q("""
        SELECT p.posting_id, p.job_id, j.job_title, s.source_name, p.publish_date, p.close_date, p.status,
               (SELECT COUNT(*) FROM application a WHERE a.posting_id = p.posting_id) AS applications
        FROM job_posting p JOIN job j ON j.job_id = p.job_id JOIN source s ON s.source_id = p.source_id
        ORDER BY p.posting_id DESC""")


def interviews() -> pd.DataFrame:
    df = q("""
        SELECT i.interview_id, i.application_id, c.candidate_name, j.job_title, i.round_type,
               i.interview_date, i.mode,
               (SELECT GROUP_CONCAT(e.employee_name ORDER BY e.employee_name SEPARATOR ', ')
                  FROM interview_participant ip JOIN employee e ON e.employee_id = ip.employee_id
                 WHERE ip.interview_id = i.interview_id) AS panel,
               (SELECT COUNT(*) FROM interview_participant ip WHERE ip.interview_id = i.interview_id) AS panel_size,
               (SELECT COUNT(*) FROM interview_evaluation ev WHERE ev.interview_id = i.interview_id) AS evaluations,
               (SELECT ROUND(AVG(ev.rating), 2) FROM interview_evaluation ev WHERE ev.interview_id = i.interview_id) AS avg_rating
        FROM interview i
        JOIN application a ON a.application_id = i.application_id
        JOIN candidate c ON c.candidate_id = a.candidate_id
        JOIN job_posting p ON p.posting_id = a.posting_id
        JOIN job j ON j.job_id = p.job_id
        ORDER BY i.interview_date DESC""")
    if df.empty:
        df["status"] = []
        return df
    now = pd.Timestamp.now()
    df["interview_date"] = pd.to_datetime(df["interview_date"])

    def status(r):
        if r["panel_size"] > 0 and r["evaluations"] >= r["panel_size"]:
            return "Completed"
        if r["interview_date"] > now:
            return "Scheduled"
        return "Awaiting feedback"
    df["status"] = df.apply(status, axis=1)
    return df


def evaluations(interview_id: int) -> pd.DataFrame:
    return q("""
        SELECT ev.evaluation_id, e.employee_name AS evaluator, ev.rating, ev.recommendation, ev.comments, ev.submitted_date
        FROM interview_evaluation ev JOIN employee e ON e.employee_id = ev.employee_id
        WHERE ev.interview_id = :i ORDER BY e.employee_name""", i=interview_id)


def panel(interview_id: int) -> pd.DataFrame:
    return q("""SELECT ip.employee_id, e.employee_name FROM interview_participant ip
                JOIN employee e ON e.employee_id = ip.employee_id WHERE ip.interview_id = :i ORDER BY e.employee_name""",
             i=interview_id)


def offers() -> pd.DataFrame:
    return q("""
        SELECT o.offer_id, o.application_id, c.candidate_name, j.job_title, d.department_name,
               o.salary_offered, j.salary_range_min, j.salary_range_max, o.start_date, o.status,
               (SELECT COUNT(*) FROM offer_approval oa WHERE oa.offer_id = o.offer_id AND oa.decision = 'Pending') AS pending_approvals,
               o.requisition_id
        FROM job_offer o
        JOIN application a ON a.application_id = o.application_id
        JOIN candidate c ON c.candidate_id = a.candidate_id
        JOIN job_posting p ON p.posting_id = a.posting_id
        JOIN job j ON j.job_id = p.job_id
        JOIN department d ON d.department_id = j.department_id
        ORDER BY o.offer_id DESC""")


def offer_approvals(offer_id: int | None = None) -> pd.DataFrame:
    df = q("""SELECT oa.offer_approval_id, oa.offer_id, e.employee_name AS approver, oa.approved_salary, oa.decision, oa.approval_date
              FROM offer_approval oa JOIN employee e ON e.employee_id = oa.employee_id ORDER BY oa.offer_id DESC, oa.offer_approval_id""")
    return df if offer_id is None else df[df["offer_id"] == offer_id]


def onboarding() -> pd.DataFrame:
    return q("""
        SELECT b.onboarding_id, b.offer_id, c.candidate_name, j.job_title, d.department_name,
               e.employee_name AS assigned_hr, b.joining_date, b.status
        FROM onboarding b
        JOIN job_offer o ON o.offer_id = b.offer_id
        JOIN application a ON a.application_id = o.application_id
        JOIN candidate c ON c.candidate_id = a.candidate_id
        JOIN job_posting p ON p.posting_id = a.posting_id
        JOIN job j ON j.job_id = p.job_id
        JOIN department d ON d.department_id = j.department_id
        JOIN employee e ON e.employee_id = b.employee_id
        ORDER BY b.joining_date DESC""")


def status_history(application_id: int) -> pd.DataFrame:
    return q("""
        SELECT h.changed_date, h.old_status, h.new_status, e.employee_name AS changed_by, rr.description AS reason
        FROM application_status_history h
        LEFT JOIN employee e ON e.employee_id = h.employee_id
        LEFT JOIN rejection_reason rr ON rr.reason_id = h.reason_id
        WHERE h.application_id = :a ORDER BY h.log_id""", a=application_id)


def app_screenings(application_id: int) -> pd.DataFrame:
    return q("""SELECT s.screening_date, e.employee_name AS reviewer, s.outcome, s.score, s.notes
                FROM screening s JOIN employee e ON e.employee_id = s.employee_id
                WHERE s.application_id = :a ORDER BY s.screening_id""", a=application_id)


def app_assessments(application_id: int) -> pd.DataFrame:
    return q("""SELECT x.assessment_date, t.assessment_type_name AS assessment, x.score, t.passing_score, x.remarks
                FROM assessment x JOIN assessment_type t ON t.assessment_type_id = x.assessment_type_id
                WHERE x.application_id = :a ORDER BY x.assessment_id""", a=application_id)


def app_background(application_id: int) -> pd.DataFrame:
    return q("""SELECT provider, initiated_date, completion_date, status, result FROM background_check
                WHERE application_id = :a ORDER BY check_id""", a=application_id)


def candidate_profile(candidate_id: int) -> dict:
    base = q("SELECT * FROM candidate WHERE candidate_id = :c", c=candidate_id)
    return {
        "base": base,
        "skills": q("""SELECT s.skill_name AS skill, cs.proficiency_level AS level FROM candidate_skill cs
                       JOIN skill s ON s.skill_id = cs.skill_id WHERE cs.candidate_id = :c ORDER BY s.skill_name""", c=candidate_id),
        "resumes": q("""SELECT resume_id, file_path, upload_date, is_primary FROM resume WHERE candidate_id = :c
                        ORDER BY upload_date DESC""", c=candidate_id),
        "applications": q("""SELECT a.application_id, j.job_title, d.department_name, s.source_name, a.date_applied, a.status
                             FROM application a JOIN job_posting p ON p.posting_id = a.posting_id JOIN job j ON j.job_id = p.job_id
                             JOIN department d ON d.department_id = j.department_id JOIN source s ON s.source_id = p.source_id
                             WHERE a.candidate_id = :c ORDER BY a.date_applied DESC""", c=candidate_id),
        "referrals": q("""SELECT r.referral_date, e.employee_name AS referred_by, r.status FROM referral r
                          JOIN employee e ON e.employee_id = r.employee_id WHERE r.candidate_id = :c""", c=candidate_id),
    }


def job_skills(job_id: int) -> pd.DataFrame:
    return q("""SELECT s.skill_name AS skill, js.is_mandatory FROM job_skill js JOIN skill s ON s.skill_id = js.skill_id
                WHERE js.job_id = :j ORDER BY js.is_mandatory DESC, s.skill_name""", j=job_id)
