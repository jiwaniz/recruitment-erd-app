# Database inspection report

**Status: completed before any application code was written.**

This report was produced with `python scripts/inspect_db.py`, a script that only runs
`SELECT`, `SHOW` and `INFORMATION_SCHEMA` queries (it cannot change anything).
It was run against a test copy of `recruitment_erd_db` created from `rms_01_schema.sql` and `rms_02_data.sql`
(the scripts you were given). Run the same script on your own MySQL server to confirm that your live
database matches:

```
python scripts/inspect_db.py > my_inspection.md
```

## Summary of findings

| Question | Finding |
|---|---|
| Does the database exist, is MySQL running? | Yes. 29 base tables, 0 views, all InnoDB. |
| Primary keys | Every table has a primary key; two junction tables (`candidate_skill`, `job_skill`) use composite keys. |
| Foreign keys | 41 enforced constraints; every FK column has the same name as the primary key it references. |
| Indexes / uniques | Primary keys, FK indexes, unique email columns, `UNIQUE(candidate_id, posting_id)` on `application`, `UNIQUE(interview_id, employee_id)` on panel and evaluation, `UNIQUE(offer_id)` on `onboarding`. |
| Sample data | Present in every table (about 4,000 rows). |
| Data-integrity checks | All eight checks in section 5 return 0 violations. |
| User accounts / roles | **None exist in the database.** Authentication is therefore implemented outside the schema (hashed passwords in Streamlit secrets / `.env`). **No schema change was required or made.** |
| Triggers / views / procedures | None. The application writes `application_status_history` itself, inside the same transaction as the status change. If you add a status-logging trigger later, remove that insert from `services.py` to avoid double logging. |

## Schema limitations and how the application handles them (no migration needed)

| Gap in the schema | How it is handled |
|---|---|
| `job` has no status column | Vacancy status is derived: Closed (requisition closed), Filled (hires >= headcount), Open (has an Active posting) or Not advertised. |
| `interview` has no status column | Status is derived: Scheduled (future), Awaiting feedback (past, panel not fully evaluated), Completed (every panel member evaluated). |
| `candidate` has no archive flag | Candidates can only be deleted when nothing depends on them; otherwise the record is kept for history. |
| Foreign keys have no `ON DELETE CASCADE` | Deletes are done explicitly, in order, inside one transaction. |
| No `hired_date` column | Taken from the `Hired` row in `application_status_history`. |

## Mapping of existing tables to application modules

| Module | Tables used |
|---|---|
| Dashboard | candidate, job, job_posting, application, application_status_history, interview, interview_evaluation, job_offer, requisition_request, source, department |
| Recruitment / Vacancies | requisition_request, requisition_approval, job, job_posting, job_skill, skill, department, location, employment_type, source |
| Candidates | candidate, candidate_skill, skill, resume, referral, application |
| Applications | application, application_status_history, screening, assessment, assessment_type, background_check, rejection_reason, job_posting, source |
| Interviews | interview, interview_participant, interview_evaluation, employee |
| Hiring | job_offer, offer_approval, onboarding, application, employee |
| Reports | all of the above (read only) |

---

# Full inspection output: `recruitment_erd_db`

Server version: `10.11.14-MariaDB-0ubuntu0.24.04.1`

## 1. Tables and views (29)

| Name | Type | Engine | Rows (exact) |
|---|---|---|---|
| application | BASE TABLE | InnoDB | 205 |
| application_status_history | BASE TABLE | InnoDB | 674 |
| assessment | BASE TABLE | InnoDB | 40 |
| assessment_type | BASE TABLE | InnoDB | 6 |
| background_check | BASE TABLE | InnoDB | 16 |
| candidate | BASE TABLE | InnoDB | 184 |
| candidate_skill | BASE TABLE | InnoDB | 1171 |
| department | BASE TABLE | InnoDB | 16 |
| designation | BASE TABLE | InnoDB | 45 |
| employee | BASE TABLE | InnoDB | 212 |
| employment_type | BASE TABLE | InnoDB | 4 |
| interview | BASE TABLE | InnoDB | 167 |
| interview_evaluation | BASE TABLE | InnoDB | 341 |
| interview_participant | BASE TABLE | InnoDB | 351 |
| job | BASE TABLE | InnoDB | 12 |
| job_offer | BASE TABLE | InnoDB | 11 |
| job_posting | BASE TABLE | InnoDB | 23 |
| job_skill | BASE TABLE | InnoDB | 63 |
| location | BASE TABLE | InnoDB | 3 |
| offer_approval | BASE TABLE | InnoDB | 22 |
| onboarding | BASE TABLE | InnoDB | 6 |
| referral | BASE TABLE | InnoDB | 18 |
| rejection_reason | BASE TABLE | InnoDB | 13 |
| requisition_approval | BASE TABLE | InnoDB | 34 |
| requisition_request | BASE TABLE | InnoDB | 20 |
| resume | BASE TABLE | InnoDB | 240 |
| screening | BASE TABLE | InnoDB | 204 |
| skill | BASE TABLE | InnoDB | 53 |
| source | BASE TABLE | InnoDB | 8 |

## 2. Columns, keys and defaults

### application

| Column | Type | Null | Key | Default | Extra |
|---|---|---|---|---|---|
| application_id | int(11) | NO | PRI |  | auto_increment |
| candidate_id | int(11) | NO | MUL |  |  |
| posting_id | int(11) | NO | MUL |  |  |
| date_applied | date | NO |  |  |  |
| status | enum('Applied','Screening','Interviewing','Assessment','BackgroundCheck','Offered','Hired','Rejected','Withdrawn') | NO |  | 'Applied' |  |

### application_status_history

| Column | Type | Null | Key | Default | Extra |
|---|---|---|---|---|---|
| log_id | int(11) | NO | PRI |  | auto_increment |
| application_id | int(11) | NO | MUL |  |  |
| employee_id | int(11) | YES | MUL | NULL |  |
| reason_id | int(11) | YES | MUL | NULL |  |
| old_status | varchar(30) | YES |  | NULL |  |
| new_status | varchar(30) | NO |  |  |  |
| changed_date | datetime | NO |  |  |  |

### assessment

| Column | Type | Null | Key | Default | Extra |
|---|---|---|---|---|---|
| assessment_id | int(11) | NO | PRI |  | auto_increment |
| application_id | int(11) | NO | MUL |  |  |
| assessment_type_id | int(11) | NO | MUL |  |  |
| score | int(11) | YES |  | NULL |  |
| remarks | varchar(500) | YES |  | NULL |  |
| assessment_date | date | NO |  |  |  |

### assessment_type

| Column | Type | Null | Key | Default | Extra |
|---|---|---|---|---|---|
| assessment_type_id | int(11) | NO | PRI |  | auto_increment |
| assessment_type_name | varchar(100) | NO |  |  |  |
| provider | varchar(100) | YES |  | NULL |  |
| passing_score | int(11) | YES |  | NULL |  |

### background_check

| Column | Type | Null | Key | Default | Extra |
|---|---|---|---|---|---|
| check_id | int(11) | NO | PRI |  | auto_increment |
| application_id | int(11) | NO | MUL |  |  |
| provider | varchar(100) | YES |  | NULL |  |
| initiated_date | date | YES |  | NULL |  |
| completion_date | date | YES |  | NULL |  |
| status | enum('Pending','InProgress','Completed') | NO |  | 'Pending' |  |
| result | enum('Clear','Flagged','Failed') | YES |  | NULL |  |

### candidate

| Column | Type | Null | Key | Default | Extra |
|---|---|---|---|---|---|
| candidate_id | int(11) | NO | PRI |  | auto_increment |
| candidate_name | varchar(100) | NO |  |  |  |
| candidate_email | varchar(150) | NO | UNI |  |  |
| candidate_contact_no | varchar(20) | YES |  | NULL |  |

### candidate_skill

| Column | Type | Null | Key | Default | Extra |
|---|---|---|---|---|---|
| candidate_id | int(11) | NO | PRI |  |  |
| skill_id | int(11) | NO | PRI |  |  |
| proficiency_level | enum('Beginner','Intermediate','Advanced','Expert') | NO |  | 'Intermediate' |  |

### department

| Column | Type | Null | Key | Default | Extra |
|---|---|---|---|---|---|
| department_id | int(11) | NO | PRI |  | auto_increment |
| department_name | varchar(100) | NO |  |  |  |
| location | varchar(100) | NO |  |  |  |

### designation

| Column | Type | Null | Key | Default | Extra |
|---|---|---|---|---|---|
| designation_id | int(11) | NO | PRI |  | auto_increment |
| designation_title | varchar(100) | NO | UNI |  |  |
| role_category | enum('Recruiter','HiringManager','Interviewer','Approver','HRAdmin') | NO |  |  |  |

### employee

| Column | Type | Null | Key | Default | Extra |
|---|---|---|---|---|---|
| employee_id | int(11) | NO | PRI |  | auto_increment |
| employee_name | varchar(100) | NO |  |  |  |
| employee_email | varchar(150) | NO | UNI |  |  |
| designation_id | int(11) | NO | MUL |  |  |
| department_id | int(11) | NO | MUL |  |  |

### employment_type

| Column | Type | Null | Key | Default | Extra |
|---|---|---|---|---|---|
| employment_type_id | int(11) | NO | PRI |  | auto_increment |
| employment_type_name | varchar(50) | NO | UNI |  |  |

### interview

| Column | Type | Null | Key | Default | Extra |
|---|---|---|---|---|---|
| interview_id | int(11) | NO | PRI |  | auto_increment |
| application_id | int(11) | NO | MUL |  |  |
| round_type | enum('HR','Technical','Managerial','Final') | NO |  |  |  |
| interview_date | datetime | NO |  |  |  |
| mode | enum('Onsite','Virtual','Phone') | NO |  | 'Virtual' |  |

### interview_evaluation

| Column | Type | Null | Key | Default | Extra |
|---|---|---|---|---|---|
| evaluation_id | int(11) | NO | PRI |  | auto_increment |
| interview_id | int(11) | NO | MUL |  |  |
| employee_id | int(11) | NO | MUL |  |  |
| rating | int(11) | NO |  |  |  |
| recommendation | enum('StrongHire','Hire','NoHire','StrongNoHire') | NO |  |  |  |
| comments | varchar(500) | YES |  | NULL |  |
| submitted_date | datetime | NO |  |  |  |

### interview_participant

| Column | Type | Null | Key | Default | Extra |
|---|---|---|---|---|---|
| participant_id | int(11) | NO | PRI |  | auto_increment |
| interview_id | int(11) | NO | MUL |  |  |
| employee_id | int(11) | NO | MUL |  |  |

### job

| Column | Type | Null | Key | Default | Extra |
|---|---|---|---|---|---|
| job_id | int(11) | NO | PRI |  | auto_increment |
| requisition_id | int(11) | NO | MUL |  |  |
| department_id | int(11) | NO | MUL |  |  |
| location_id | int(11) | NO | MUL |  |  |
| employment_type_id | int(11) | NO | MUL |  |  |
| job_title | varchar(150) | NO |  |  |  |
| description | text | YES |  | NULL |  |
| salary_range_min | decimal(12,2) | YES |  | NULL |  |
| salary_range_max | decimal(12,2) | YES |  | NULL |  |

### job_offer

| Column | Type | Null | Key | Default | Extra |
|---|---|---|---|---|---|
| offer_id | int(11) | NO | PRI |  | auto_increment |
| application_id | int(11) | NO | MUL |  |  |
| requisition_id | int(11) | NO | MUL |  |  |
| salary_offered | decimal(12,2) | NO |  |  |  |
| start_date | date | YES |  | NULL |  |
| status | enum('Draft','PendingApproval','Sent','Accepted','Declined','Withdrawn') | NO |  | 'Draft' |  |

### job_posting

| Column | Type | Null | Key | Default | Extra |
|---|---|---|---|---|---|
| posting_id | int(11) | NO | PRI |  | auto_increment |
| job_id | int(11) | NO | MUL |  |  |
| source_id | int(11) | NO | MUL |  |  |
| publish_date | date | NO |  |  |  |
| close_date | date | YES |  | NULL |  |
| status | enum('Active','Closed','Expired') | NO |  | 'Active' |  |

### job_skill

| Column | Type | Null | Key | Default | Extra |
|---|---|---|---|---|---|
| job_id | int(11) | NO | PRI |  |  |
| skill_id | int(11) | NO | PRI |  |  |
| is_mandatory | tinyint(1) | NO |  | 1 |  |

### location

| Column | Type | Null | Key | Default | Extra |
|---|---|---|---|---|---|
| location_id | int(11) | NO | PRI |  | auto_increment |
| city | varchar(100) | NO |  |  |  |
| country | varchar(100) | NO |  |  |  |
| work_mode | enum('Onsite','Remote','Hybrid') | NO |  | 'Onsite' |  |

### offer_approval

| Column | Type | Null | Key | Default | Extra |
|---|---|---|---|---|---|
| offer_approval_id | int(11) | NO | PRI |  | auto_increment |
| offer_id | int(11) | NO | MUL |  |  |
| employee_id | int(11) | NO | MUL |  |  |
| approved_salary | decimal(12,2) | YES |  | NULL |  |
| decision | enum('Pending','Approved','Rejected') | NO |  | 'Pending' |  |
| approval_date | date | YES |  | NULL |  |

### onboarding

| Column | Type | Null | Key | Default | Extra |
|---|---|---|---|---|---|
| onboarding_id | int(11) | NO | PRI |  | auto_increment |
| offer_id | int(11) | NO | UNI |  |  |
| employee_id | int(11) | NO | MUL |  |  |
| joining_date | date | YES |  | NULL |  |
| status | enum('Pending','DocumentsSubmitted','Completed') | NO |  | 'Pending' |  |

### referral

| Column | Type | Null | Key | Default | Extra |
|---|---|---|---|---|---|
| referral_id | int(11) | NO | PRI |  | auto_increment |
| candidate_id | int(11) | NO | MUL |  |  |
| employee_id | int(11) | NO | MUL |  |  |
| referral_date | date | NO |  |  |  |
| status | enum('Pending','Hired','NotHired') | NO |  | 'Pending' |  |

### rejection_reason

| Column | Type | Null | Key | Default | Extra |
|---|---|---|---|---|---|
| reason_id | int(11) | NO | PRI |  | auto_increment |
| category | varchar(100) | NO |  |  |  |
| description | varchar(255) | YES |  | NULL |  |
| stage | varchar(50) | YES |  | NULL |  |

### requisition_approval

| Column | Type | Null | Key | Default | Extra |
|---|---|---|---|---|---|
| approval_id | int(11) | NO | PRI |  | auto_increment |
| requisition_id | int(11) | NO | MUL |  |  |
| employee_id | int(11) | NO | MUL |  |  |
| approval_level | int(11) | NO |  | 1 |  |
| decision | enum('Pending','Approved','Rejected') | NO |  | 'Pending' |  |
| comments | varchar(500) | YES |  | NULL |  |
| approval_date | date | YES |  | NULL |  |

### requisition_request

| Column | Type | Null | Key | Default | Extra |
|---|---|---|---|---|---|
| requisition_id | int(11) | NO | PRI |  | auto_increment |
| department_id | int(11) | NO | MUL |  |  |
| employee_id | int(11) | NO | MUL |  |  |
| job_title | varchar(150) | NO |  |  |  |
| requested_headcount | int(11) | NO |  | 1 |  |
| reason | varchar(500) | YES |  | NULL |  |
| status | enum('Draft','PendingApproval','Approved','Rejected','Closed') | NO |  | 'Draft' |  |
| hiring_deadline | date | YES |  | NULL |  |
| created_date | date | NO |  | curdate() |  |
| closed_date | date | YES |  | NULL |  |

### resume

| Column | Type | Null | Key | Default | Extra |
|---|---|---|---|---|---|
| resume_id | int(11) | NO | PRI |  | auto_increment |
| candidate_id | int(11) | NO | MUL |  |  |
| file_path | varchar(255) | NO |  |  |  |
| upload_date | date | NO |  |  |  |
| is_primary | tinyint(1) | NO |  | 0 |  |

### screening

| Column | Type | Null | Key | Default | Extra |
|---|---|---|---|---|---|
| screening_id | int(11) | NO | PRI |  | auto_increment |
| application_id | int(11) | NO | MUL |  |  |
| employee_id | int(11) | NO | MUL |  |  |
| reason_id | int(11) | YES | MUL | NULL |  |
| outcome | enum('Shortlisted','Rejected','OnHold') | NO |  |  |  |
| score | int(11) | YES |  | NULL |  |
| notes | varchar(500) | YES |  | NULL |  |
| screening_date | date | NO |  |  |  |

### skill

| Column | Type | Null | Key | Default | Extra |
|---|---|---|---|---|---|
| skill_id | int(11) | NO | PRI |  | auto_increment |
| skill_name | varchar(100) | NO | UNI |  |  |

### source

| Column | Type | Null | Key | Default | Extra |
|---|---|---|---|---|---|
| source_id | int(11) | NO | PRI |  | auto_increment |
| source_name | varchar(100) | NO |  |  |  |
| source_type | enum('JobBoard','Referral','Agency','WalkIn','SocialMedia','CampusDrive') | NO |  |  |  |

## 3. Foreign keys

| Child table | Column | Parent table | Parent column | Constraint |
|---|---|---|---|---|
| application | candidate_id | candidate | candidate_id | fk_application_candidate |
| application | posting_id | job_posting | posting_id | fk_application_posting |
| application_status_history | application_id | application | application_id | fk_history_application |
| application_status_history | employee_id | employee | employee_id | fk_history_employee |
| application_status_history | reason_id | rejection_reason | reason_id | fk_history_reason |
| assessment | application_id | application | application_id | fk_assessment_application |
| assessment | assessment_type_id | assessment_type | assessment_type_id | fk_assessment_type |
| background_check | application_id | application | application_id | fk_check_application |
| candidate_skill | candidate_id | candidate | candidate_id | fk_cand_skill_candidate |
| candidate_skill | skill_id | skill | skill_id | fk_cand_skill_skill |
| employee | department_id | department | department_id | fk_employee_department |
| employee | designation_id | designation | designation_id | fk_employee_designation |
| interview | application_id | application | application_id | fk_interview_application |
| interview_evaluation | employee_id | employee | employee_id | fk_evaluation_employee |
| interview_evaluation | interview_id | interview | interview_id | fk_evaluation_interview |
| interview_participant | employee_id | employee | employee_id | fk_participant_employee |
| interview_participant | interview_id | interview | interview_id | fk_participant_interview |
| job | department_id | department | department_id | fk_job_department |
| job | employment_type_id | employment_type | employment_type_id | fk_job_employment_type |
| job | location_id | location | location_id | fk_job_location |
| job | requisition_id | requisition_request | requisition_id | fk_job_request |
| job_offer | application_id | application | application_id | fk_offer_application |
| job_offer | requisition_id | requisition_request | requisition_id | fk_offer_request |
| job_posting | job_id | job | job_id | fk_posting_job |
| job_posting | source_id | source | source_id | fk_posting_source |
| job_skill | job_id | job | job_id | fk_job_skill_job |
| job_skill | skill_id | skill | skill_id | fk_job_skill_skill |
| offer_approval | employee_id | employee | employee_id | fk_offer_approval_employee |
| offer_approval | offer_id | job_offer | offer_id | fk_offer_approval_offer |
| onboarding | employee_id | employee | employee_id | fk_onboarding_employee |
| onboarding | offer_id | job_offer | offer_id | fk_onboarding_offer |
| referral | candidate_id | candidate | candidate_id | fk_referral_candidate |
| referral | employee_id | employee | employee_id | fk_referral_employee |
| requisition_approval | employee_id | employee | employee_id | fk_approval_employee |
| requisition_approval | requisition_id | requisition_request | requisition_id | fk_approval_request |
| requisition_request | department_id | department | department_id | fk_request_department |
| requisition_request | employee_id | employee | employee_id | fk_request_employee |
| resume | candidate_id | candidate | candidate_id | fk_resume_candidate |
| screening | application_id | application | application_id | fk_screening_application |
| screening | employee_id | employee | employee_id | fk_screening_employee |
| screening | reason_id | rejection_reason | reason_id | fk_screening_reason |

Total foreign keys: **41**

## 4. Indexes and unique constraints

| Table | Index | Unique | Columns |
|---|---|---|---|
| application | candidate_id | yes | candidate_id,posting_id |
| application | fk_application_posting | no | posting_id |
| application | PRIMARY | yes | application_id |
| application_status_history | fk_history_application | no | application_id |
| application_status_history | fk_history_employee | no | employee_id |
| application_status_history | fk_history_reason | no | reason_id |
| application_status_history | PRIMARY | yes | log_id |
| assessment | fk_assessment_application | no | application_id |
| assessment | fk_assessment_type | no | assessment_type_id |
| assessment | PRIMARY | yes | assessment_id |
| assessment_type | PRIMARY | yes | assessment_type_id |
| background_check | fk_check_application | no | application_id |
| background_check | PRIMARY | yes | check_id |
| candidate | candidate_email | yes | candidate_email |
| candidate | PRIMARY | yes | candidate_id |
| candidate_skill | fk_cand_skill_skill | no | skill_id |
| candidate_skill | PRIMARY | yes | candidate_id,skill_id |
| department | PRIMARY | yes | department_id |
| designation | designation_title | yes | designation_title |
| designation | PRIMARY | yes | designation_id |
| employee | employee_email | yes | employee_email |
| employee | fk_employee_department | no | department_id |
| employee | fk_employee_designation | no | designation_id |
| employee | PRIMARY | yes | employee_id |
| employment_type | employment_type_name | yes | employment_type_name |
| employment_type | PRIMARY | yes | employment_type_id |
| interview | fk_interview_application | no | application_id |
| interview | PRIMARY | yes | interview_id |
| interview_evaluation | fk_evaluation_employee | no | employee_id |
| interview_evaluation | interview_id | yes | interview_id,employee_id |
| interview_evaluation | PRIMARY | yes | evaluation_id |
| interview_participant | fk_participant_employee | no | employee_id |
| interview_participant | interview_id | yes | interview_id,employee_id |
| interview_participant | PRIMARY | yes | participant_id |
| job | fk_job_department | no | department_id |
| job | fk_job_employment_type | no | employment_type_id |
| job | fk_job_location | no | location_id |
| job | fk_job_request | no | requisition_id |
| job | PRIMARY | yes | job_id |
| job_offer | fk_offer_application | no | application_id |
| job_offer | fk_offer_request | no | requisition_id |
| job_offer | PRIMARY | yes | offer_id |
| job_posting | fk_posting_job | no | job_id |
| job_posting | fk_posting_source | no | source_id |
| job_posting | PRIMARY | yes | posting_id |
| job_skill | fk_job_skill_skill | no | skill_id |
| job_skill | PRIMARY | yes | job_id,skill_id |
| location | PRIMARY | yes | location_id |
| offer_approval | fk_offer_approval_employee | no | employee_id |
| offer_approval | fk_offer_approval_offer | no | offer_id |
| offer_approval | PRIMARY | yes | offer_approval_id |
| onboarding | fk_onboarding_employee | no | employee_id |
| onboarding | offer_id | yes | offer_id |
| onboarding | PRIMARY | yes | onboarding_id |
| referral | fk_referral_candidate | no | candidate_id |
| referral | fk_referral_employee | no | employee_id |
| referral | PRIMARY | yes | referral_id |
| rejection_reason | PRIMARY | yes | reason_id |
| requisition_approval | fk_approval_employee | no | employee_id |
| requisition_approval | fk_approval_request | no | requisition_id |
| requisition_approval | PRIMARY | yes | approval_id |
| requisition_request | fk_request_department | no | department_id |
| requisition_request | fk_request_employee | no | employee_id |
| requisition_request | PRIMARY | yes | requisition_id |
| resume | fk_resume_candidate | no | candidate_id |
| resume | PRIMARY | yes | resume_id |
| screening | fk_screening_application | no | application_id |
| screening | fk_screening_employee | no | employee_id |
| screening | fk_screening_reason | no | reason_id |
| screening | PRIMARY | yes | screening_id |
| skill | PRIMARY | yes | skill_id |
| skill | skill_name | yes | skill_name |
| source | PRIMARY | yes | source_id |

## 5. Data-integrity checks (every value should be 0)

| Check | Violations |
|---|---|
| Applications whose status disagrees with the last status-history row | 0 |
| Applications with no status-history rows | 0 |
| Hired applications without an accepted offer | 0 |
| Accepted offers without an onboarding record | 0 |
| Interview evaluations by someone not on the panel | 0 |
| Candidates without exactly one primary resume | 0 |
| Jobs whose requisition is not Approved/Closed | 0 |
| Job offers above the job's maximum salary | 0 |

## 6. Status distributions

- **application.status**: Rejected (117), Screening (34), Assessment (29), Hired (6), Withdrawn (5), Interviewing (5), Offered (5), BackgroundCheck (3), Applied (1)
- **requisition_request.status**: Approved (10), PendingApproval (4), Closed (2), Draft (2), Rejected (2)
- **job_posting.status**: Expired (15), Active (5), Closed (3)
- **job_offer.status**: Accepted (6), Sent (5)
- **onboarding.status**: DocumentsSubmitted (4), Pending (2)
