-- =====================================================================
-- PROPOSED MIGRATION 001: login accounts, password reset and security log
-- STATUS: proposal. Review it, then apply it with scripts/apply_auth_migration.py
-- It ONLY ADDS three new tables. It never drops, alters or deletes anything that exists
-- (CREATE TABLE IF NOT EXISTS), and it touches none of the 29 recruitment tables.
--
-- Why it is needed: today logins live in Streamlit secrets / .env, which cannot store a changed password,
-- an email address for password reset, a reset token, an account status or a creation date.
-- Naming rule kept: every foreign key has the same name as the primary key it references.
-- =====================================================================

CREATE TABLE IF NOT EXISTS app_user (
    user_id               INT AUTO_INCREMENT PRIMARY KEY,
    username              VARCHAR(50)  NOT NULL UNIQUE,
    email                 VARCHAR(150) NOT NULL UNIQUE,
    full_name             VARCHAR(100) NOT NULL,
    password_hash         VARCHAR(255) NOT NULL,                       -- PBKDF2-SHA256, never plain text
    role                  ENUM('viewer','recruiter','admin') NOT NULL DEFAULT 'viewer',
    employee_id           INT NULL,                                    -- optional link to an employee
    is_active             BOOLEAN NOT NULL DEFAULT TRUE,
    must_change_password  BOOLEAN NOT NULL DEFAULT FALSE,
    failed_logins         INT NOT NULL DEFAULT 0,
    locked_until          DATETIME NULL,
    last_login            DATETIME NULL,
    preferences           JSON NULL,
    created_date          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_user_employee FOREIGN KEY (employee_id) REFERENCES employee (employee_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS password_reset_token (
    token_id      INT AUTO_INCREMENT PRIMARY KEY,
    user_id       INT NOT NULL,
    token_hash    CHAR(64) NOT NULL UNIQUE,                            -- SHA-256 of the token; the token itself is never stored
    expires_at    DATETIME NOT NULL,
    used_at       DATETIME NULL,
    created_date  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_reset_user FOREIGN KEY (user_id) REFERENCES app_user (user_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS auth_event (
    event_id    INT AUTO_INCREMENT PRIMARY KEY,
    event_time  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    event_type  VARCHAR(30)  NOT NULL,
    username    VARCHAR(150) NULL,
    user_id     INT NULL,
    detail      VARCHAR(255) NULL,
    INDEX idx_auth_event_lookup (event_type, username, event_time),
    CONSTRAINT fk_event_user FOREIGN KEY (user_id) REFERENCES app_user (user_id)
) ENGINE=InnoDB;
