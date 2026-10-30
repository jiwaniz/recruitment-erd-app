-- =====================================================================
-- RECRUITMENT MANAGEMENT SYSTEM - MySQL 8.0 schema (29 tables)
-- Run this file first, then rms_02_data.sql
-- Naming rule: a foreign key column has exactly the same name as the
-- primary key column it references (employee_id stays employee_id).
-- (cloud copy: no CREATE DATABASE / USE, tables go into the database you connect to)
-- NOTE: the local file creates a NEW database, recruitment_erd_db, so it will not
-- touch an existing recruitment_db. Change the name in the two lines below
-- (and in rms_02_data.sql) if you prefer another name.
-- =====================================================================



-- ---------------------------------------------------------------------
-- 1. Reference (lookup) tables
-- ---------------------------------------------------------------------
CREATE TABLE department (
    department_id    INT AUTO_INCREMENT PRIMARY KEY,
    department_name  VARCHAR(100) NOT NULL,
    location         VARCHAR(100) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE designation (
    designation_id     INT AUTO_INCREMENT PRIMARY KEY,
    designation_title  VARCHAR(100) NOT NULL UNIQUE,
    role_category      ENUM('Recruiter','HiringManager','Interviewer','Approver','HRAdmin') NOT NULL
) ENGINE=InnoDB;

CREATE TABLE employment_type (
    employment_type_id    INT AUTO_INCREMENT PRIMARY KEY,
    employment_type_name  VARCHAR(50) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE location (
    location_id  INT AUTO_INCREMENT PRIMARY KEY,
    city         VARCHAR(100) NOT NULL,
    country      VARCHAR(100) NOT NULL,
    work_mode    ENUM('Onsite','Remote','Hybrid') NOT NULL DEFAULT 'Onsite'
) ENGINE=InnoDB;

CREATE TABLE source (
    source_id    INT AUTO_INCREMENT PRIMARY KEY,
    source_name  VARCHAR(100) NOT NULL,
    source_type  ENUM('JobBoard','Referral','Agency','WalkIn','SocialMedia','CampusDrive') NOT NULL
) ENGINE=InnoDB;

CREATE TABLE skill (
    skill_id    INT AUTO_INCREMENT PRIMARY KEY,
    skill_name  VARCHAR(100) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE rejection_reason (
    reason_id    INT AUTO_INCREMENT PRIMARY KEY,
    category     VARCHAR(100) NOT NULL,
    description  VARCHAR(255),
    stage        VARCHAR(50)
) ENGINE=InnoDB;

CREATE TABLE assessment_type (
    assessment_type_id    INT AUTO_INCREMENT PRIMARY KEY,
    assessment_type_name  VARCHAR(100) NOT NULL,
    provider              VARCHAR(100),
    passing_score         INT
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 2. Employees
-- ---------------------------------------------------------------------
CREATE TABLE employee (
    employee_id     INT AUTO_INCREMENT PRIMARY KEY,
    employee_name   VARCHAR(100) NOT NULL,
    employee_email  VARCHAR(150) NOT NULL UNIQUE,
    designation_id  INT NOT NULL,
    department_id   INT NOT NULL,
    CONSTRAINT fk_employee_designation FOREIGN KEY (designation_id) REFERENCES designation (designation_id),
    CONSTRAINT fk_employee_department  FOREIGN KEY (department_id)  REFERENCES department (department_id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 3. Requisition and approval
-- ---------------------------------------------------------------------
CREATE TABLE requisition_request (
    requisition_id       INT AUTO_INCREMENT PRIMARY KEY,
    department_id        INT NOT NULL,
    employee_id          INT NOT NULL,                  -- employee who raised the request
    job_title            VARCHAR(150) NOT NULL,
    requested_headcount  INT NOT NULL DEFAULT 1,
    reason               VARCHAR(500),
    status               ENUM('Draft','PendingApproval','Approved','Rejected','Closed') NOT NULL DEFAULT 'Draft',
    hiring_deadline      DATE,
    created_date         DATE NOT NULL DEFAULT (CURRENT_DATE),
    closed_date          DATE,
    CONSTRAINT chk_headcount CHECK (requested_headcount > 0),
    CONSTRAINT fk_request_department FOREIGN KEY (department_id) REFERENCES department (department_id),
    CONSTRAINT fk_request_employee   FOREIGN KEY (employee_id)   REFERENCES employee (employee_id)
) ENGINE=InnoDB;

CREATE TABLE requisition_approval (
    approval_id     INT AUTO_INCREMENT PRIMARY KEY,
    requisition_id  INT NOT NULL,
    employee_id     INT NOT NULL,                       -- approver
    approval_level  INT NOT NULL DEFAULT 1,
    decision        ENUM('Pending','Approved','Rejected') NOT NULL DEFAULT 'Pending',
    comments        VARCHAR(500),
    approval_date   DATE,
    CONSTRAINT fk_approval_request  FOREIGN KEY (requisition_id) REFERENCES requisition_request (requisition_id),
    CONSTRAINT fk_approval_employee FOREIGN KEY (employee_id)    REFERENCES employee (employee_id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 4. Job, posting and skills
-- ---------------------------------------------------------------------
CREATE TABLE job (
    job_id              INT AUTO_INCREMENT PRIMARY KEY,
    requisition_id      INT NOT NULL,
    department_id       INT NOT NULL,
    location_id         INT NOT NULL,
    employment_type_id  INT NOT NULL,
    job_title           VARCHAR(150) NOT NULL,
    description         TEXT,
    salary_range_min    DECIMAL(12,2),
    salary_range_max    DECIMAL(12,2),
    CONSTRAINT chk_salary_range CHECK (salary_range_max >= salary_range_min),
    CONSTRAINT fk_job_request         FOREIGN KEY (requisition_id)     REFERENCES requisition_request (requisition_id),
    CONSTRAINT fk_job_department      FOREIGN KEY (department_id)      REFERENCES department (department_id),
    CONSTRAINT fk_job_location        FOREIGN KEY (location_id)        REFERENCES location (location_id),
    CONSTRAINT fk_job_employment_type FOREIGN KEY (employment_type_id) REFERENCES employment_type (employment_type_id)
) ENGINE=InnoDB;

CREATE TABLE job_posting (
    posting_id    INT AUTO_INCREMENT PRIMARY KEY,
    job_id        INT NOT NULL,
    source_id     INT NOT NULL,
    publish_date  DATE NOT NULL,
    close_date    DATE,
    status        ENUM('Active','Closed','Expired') NOT NULL DEFAULT 'Active',
    CONSTRAINT fk_posting_job    FOREIGN KEY (job_id)    REFERENCES job (job_id),
    CONSTRAINT fk_posting_source FOREIGN KEY (source_id) REFERENCES source (source_id)
) ENGINE=InnoDB;

CREATE TABLE job_skill (
    job_id        INT NOT NULL,
    skill_id      INT NOT NULL,
    is_mandatory  BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (job_id, skill_id),
    CONSTRAINT fk_job_skill_job   FOREIGN KEY (job_id)   REFERENCES job (job_id),
    CONSTRAINT fk_job_skill_skill FOREIGN KEY (skill_id) REFERENCES skill (skill_id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 5. Candidates
-- ---------------------------------------------------------------------
CREATE TABLE candidate (
    candidate_id          INT AUTO_INCREMENT PRIMARY KEY,
    candidate_name        VARCHAR(100) NOT NULL,
    candidate_email       VARCHAR(150) NOT NULL UNIQUE,
    candidate_contact_no  VARCHAR(20)
) ENGINE=InnoDB;

CREATE TABLE resume (
    resume_id     INT AUTO_INCREMENT PRIMARY KEY,
    candidate_id  INT NOT NULL,
    file_path     VARCHAR(255) NOT NULL,
    upload_date   DATE NOT NULL,
    is_primary    BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT fk_resume_candidate FOREIGN KEY (candidate_id) REFERENCES candidate (candidate_id)
) ENGINE=InnoDB;

CREATE TABLE candidate_skill (
    candidate_id       INT NOT NULL,
    skill_id           INT NOT NULL,
    proficiency_level  ENUM('Beginner','Intermediate','Advanced','Expert') NOT NULL DEFAULT 'Intermediate',
    PRIMARY KEY (candidate_id, skill_id),
    CONSTRAINT fk_cand_skill_candidate FOREIGN KEY (candidate_id) REFERENCES candidate (candidate_id),
    CONSTRAINT fk_cand_skill_skill     FOREIGN KEY (skill_id)     REFERENCES skill (skill_id)
) ENGINE=InnoDB;

CREATE TABLE referral (
    referral_id    INT AUTO_INCREMENT PRIMARY KEY,
    candidate_id   INT NOT NULL,
    employee_id    INT NOT NULL,                        -- employee who referred
    referral_date  DATE NOT NULL,
    status         ENUM('Pending','Hired','NotHired') NOT NULL DEFAULT 'Pending',
    CONSTRAINT fk_referral_candidate FOREIGN KEY (candidate_id) REFERENCES candidate (candidate_id),
    CONSTRAINT fk_referral_employee  FOREIGN KEY (employee_id)  REFERENCES employee (employee_id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 6. Application pipeline
-- ---------------------------------------------------------------------
CREATE TABLE application (
    application_id  INT AUTO_INCREMENT PRIMARY KEY,
    candidate_id    INT NOT NULL,
    posting_id      INT NOT NULL,
    date_applied    DATE NOT NULL,
    status          ENUM('Applied','Screening','Interviewing','Assessment','BackgroundCheck',
                         'Offered','Hired','Rejected','Withdrawn') NOT NULL DEFAULT 'Applied',
    UNIQUE (candidate_id, posting_id),
    CONSTRAINT fk_application_candidate FOREIGN KEY (candidate_id) REFERENCES candidate (candidate_id),
    CONSTRAINT fk_application_posting   FOREIGN KEY (posting_id)   REFERENCES job_posting (posting_id)
) ENGINE=InnoDB;

CREATE TABLE application_status_history (
    log_id          INT AUTO_INCREMENT PRIMARY KEY,
    application_id  INT NOT NULL,
    employee_id     INT,                                -- NULL = changed by the system
    reason_id       INT,
    old_status      VARCHAR(30),
    new_status      VARCHAR(30) NOT NULL,
    changed_date    DATETIME NOT NULL,
    CONSTRAINT fk_history_application FOREIGN KEY (application_id) REFERENCES application (application_id),
    CONSTRAINT fk_history_employee    FOREIGN KEY (employee_id)     REFERENCES employee (employee_id),
    CONSTRAINT fk_history_reason      FOREIGN KEY (reason_id)       REFERENCES rejection_reason (reason_id)
) ENGINE=InnoDB;

CREATE TABLE screening (
    screening_id    INT AUTO_INCREMENT PRIMARY KEY,
    application_id  INT NOT NULL,
    employee_id     INT NOT NULL,                       -- reviewer
    reason_id       INT,
    outcome         ENUM('Shortlisted','Rejected','OnHold') NOT NULL,
    score           INT,
    notes           VARCHAR(500),
    screening_date  DATE NOT NULL,
    CONSTRAINT fk_screening_application FOREIGN KEY (application_id) REFERENCES application (application_id),
    CONSTRAINT fk_screening_employee    FOREIGN KEY (employee_id)    REFERENCES employee (employee_id),
    CONSTRAINT fk_screening_reason      FOREIGN KEY (reason_id)      REFERENCES rejection_reason (reason_id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 7. Interview (panel) and evaluation
-- ---------------------------------------------------------------------
CREATE TABLE interview (
    interview_id    INT AUTO_INCREMENT PRIMARY KEY,
    application_id  INT NOT NULL,
    round_type      ENUM('HR','Technical','Managerial','Final') NOT NULL,
    interview_date  DATETIME NOT NULL,
    mode            ENUM('Onsite','Virtual','Phone') NOT NULL DEFAULT 'Virtual',
    CONSTRAINT fk_interview_application FOREIGN KEY (application_id) REFERENCES application (application_id)
) ENGINE=InnoDB;

CREATE TABLE interview_participant (
    participant_id  INT AUTO_INCREMENT PRIMARY KEY,
    interview_id    INT NOT NULL,
    employee_id     INT NOT NULL,                       -- panel member
    UNIQUE (interview_id, employee_id),
    CONSTRAINT fk_participant_interview FOREIGN KEY (interview_id) REFERENCES interview (interview_id),
    CONSTRAINT fk_participant_employee  FOREIGN KEY (employee_id)  REFERENCES employee (employee_id)
) ENGINE=InnoDB;

CREATE TABLE interview_evaluation (
    evaluation_id   INT AUTO_INCREMENT PRIMARY KEY,
    interview_id    INT NOT NULL,
    employee_id     INT NOT NULL,                       -- evaluator
    rating          INT NOT NULL,
    recommendation  ENUM('StrongHire','Hire','NoHire','StrongNoHire') NOT NULL,
    comments        VARCHAR(500),
    submitted_date  DATETIME NOT NULL,
    UNIQUE (interview_id, employee_id),
    CONSTRAINT chk_rating CHECK (rating BETWEEN 1 AND 5),
    CONSTRAINT fk_evaluation_interview FOREIGN KEY (interview_id) REFERENCES interview (interview_id),
    CONSTRAINT fk_evaluation_employee  FOREIGN KEY (employee_id)  REFERENCES employee (employee_id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 8. Assessment and background check
-- ---------------------------------------------------------------------
CREATE TABLE assessment (
    assessment_id       INT AUTO_INCREMENT PRIMARY KEY,
    application_id      INT NOT NULL,
    assessment_type_id  INT NOT NULL,
    score               INT,
    remarks             VARCHAR(500),
    assessment_date     DATE NOT NULL,
    CONSTRAINT fk_assessment_application FOREIGN KEY (application_id)    REFERENCES application (application_id),
    CONSTRAINT fk_assessment_type        FOREIGN KEY (assessment_type_id) REFERENCES assessment_type (assessment_type_id)
) ENGINE=InnoDB;

CREATE TABLE background_check (
    check_id         INT AUTO_INCREMENT PRIMARY KEY,
    application_id   INT NOT NULL,
    provider         VARCHAR(100),
    initiated_date   DATE,
    completion_date  DATE,
    status           ENUM('Pending','InProgress','Completed') NOT NULL DEFAULT 'Pending',
    result           ENUM('Clear','Flagged','Failed'),
    CONSTRAINT fk_check_application FOREIGN KEY (application_id) REFERENCES application (application_id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 9. Offer and onboarding
-- ---------------------------------------------------------------------
CREATE TABLE job_offer (
    offer_id        INT AUTO_INCREMENT PRIMARY KEY,
    application_id  INT NOT NULL,
    requisition_id  INT NOT NULL,
    salary_offered  DECIMAL(12,2) NOT NULL,
    start_date      DATE,
    status          ENUM('Draft','PendingApproval','Sent','Accepted','Declined','Withdrawn') NOT NULL DEFAULT 'Draft',
    CONSTRAINT fk_offer_application FOREIGN KEY (application_id) REFERENCES application (application_id),
    CONSTRAINT fk_offer_request     FOREIGN KEY (requisition_id) REFERENCES requisition_request (requisition_id)
) ENGINE=InnoDB;

CREATE TABLE offer_approval (
    offer_approval_id  INT AUTO_INCREMENT PRIMARY KEY,
    offer_id           INT NOT NULL,
    employee_id        INT NOT NULL,                    -- approver
    approved_salary    DECIMAL(12,2),
    decision           ENUM('Pending','Approved','Rejected') NOT NULL DEFAULT 'Pending',
    approval_date      DATE,
    CONSTRAINT fk_offer_approval_offer    FOREIGN KEY (offer_id)    REFERENCES job_offer (offer_id),
    CONSTRAINT fk_offer_approval_employee FOREIGN KEY (employee_id) REFERENCES employee (employee_id)
) ENGINE=InnoDB;

CREATE TABLE onboarding (
    onboarding_id  INT AUTO_INCREMENT PRIMARY KEY,
    offer_id       INT NOT NULL UNIQUE,
    employee_id    INT NOT NULL,                        -- HR employee assigned
    joining_date   DATE,
    status         ENUM('Pending','DocumentsSubmitted','Completed') NOT NULL DEFAULT 'Pending',
    CONSTRAINT fk_onboarding_offer    FOREIGN KEY (offer_id)    REFERENCES job_offer (offer_id),
    CONSTRAINT fk_onboarding_employee FOREIGN KEY (employee_id) REFERENCES employee (employee_id)
) ENGINE=InnoDB;
