-- Run this ONCE as your MySQL administrator (root locally, or the admin account of your cloud provider).
-- It creates a limited account for the web application: it can read and change rows,
-- but it cannot drop tables or change the schema.
-- Replace the database name and the password.

CREATE USER 'rms_app'@'%' IDENTIFIED BY 'CHANGE_THIS_PASSWORD';
GRANT SELECT, INSERT, UPDATE, DELETE ON recruitment_erd_db.* TO 'rms_app'@'%';
FLUSH PRIVILEGES;

-- On a cloud database the database is usually called defaultdb, so use:
-- GRANT SELECT, INSERT, UPDATE, DELETE ON defaultdb.* TO 'rms_app'@'%';
