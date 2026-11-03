# Accounts, passwords and email: setup

## What changed
* Pages fixed (Candidate Profile, Manage Application, Update Interview, Interview Feedback): the cause was code such as
  `st.dataframe(x) if rows else st.caption(...)` written as a bare statement; Streamlit then *displayed the returned object*
  (a DeltaGenerator and its documentation). All 8 occurrences are now normal `if / else` blocks and `tests/test_rendering.py`
  fails if the pattern ever returns. Also fixed: a database NULL showed as the text "nan" in edit forms (blocked saving a candidate without a phone number).
* New: login page (branding, show/hide password, Forgot password), header menu (My Profile, Account Settings, Change Password,
  User Management for admins, Sign Out), password change, email-based reset, admin user management, security log.

## Until you approve the migration
Nothing changes for you. The app keeps using the users in `.env` / secrets; the new account pages explain that they need the upgrade.

## Proposed migration (needs your approval)
`database/migrations/001_auth_tables.sql` **adds three tables** and touches nothing else (`CREATE TABLE IF NOT EXISTS`, no DROP / ALTER / DELETE):

| New table | Purpose |
|---|---|
| `app_user` | Accounts: username, email, name, password hash, role (viewer / recruiter / admin), active flag, lock state, last login, preferences, created date. Optional link to `employee`. |
| `password_reset_token` | Hashed single-use reset tokens with expiry. |
| `auth_event` | Security log (sign-ins, lockouts, resets) that also powers rate limiting. No passwords or tokens. |

Why it cannot be done without new tables: a changed password, a reset token, an account status and an email address have nowhere to be stored today.
Your existing roles are preserved: `import_users.py` copies each current user with the same role and the same password hash (no password is re-typed or re-hashed).

### Apply it (after you approve)
1. Back up first (MySQL Workbench: Server > Data Export).
2. Local: run with an account that may create tables (root), in the project folder:
   ```
   $env:DB_USER="root"; $env:DB_PASSWORD="your-root-password"
   python scripts/apply_auth_migration.py
   ```
   It prints that all 29 existing tables have identical row counts. For the cloud database run the same with the `avnadmin` settings (as for `load_sample_database.py`).
   Close that PowerShell window afterwards so the admin password is not kept.
3. Import the current logins and give each an email address (needed for password reset):
   ```
   python scripts/import_users.py --email admin=you@example.com --email supervisor=boss@example.com
   ```
   Use the normal app account (`rms_app`) settings for this step. The app account already has the rights it needs on the new tables.
4. Restart the app. Sign in with your **existing** password. After that, users, passwords and roles are managed in the app and the `[users.*]` / `APP_USERS` entries are no longer used for sign-in (keep them as a fallback until you are sure).

## Email for "Forgot password"
The app sends a link through any SMTP service; it needs `[email]` secrets (cloud) or `EMAIL_*` variables (local) plus the public URL of the app (`app_base_url` / `APP_BASE_URL`).
Examples: a Gmail or Outlook account with an **app password** (host `smtp.gmail.com`, port 587, security `starttls`), or a transactional provider such as Brevo or SendGrid.
Without it, the Forgot password screen says so and an administrator can issue a temporary password in User Management.
Reset links expire after 30 minutes, work once, and a new request cancels the previous link. At most 3 reset emails per address per hour.

## Rules enforced on the server side
* Password: at least 10 characters, at least 3 of lowercase / uppercase / digit / symbol, not a common password, must not contain the username or email name.
* Five wrong passwords lock the account for 15 minutes (stored in the database).
* Messages never reveal whether an email or username exists.
* A new administrator-created account (or an admin reset) must change its temporary password at first sign-in.
* An administrator cannot demote or deactivate themselves, and the last active administrator cannot be removed.
* Role, deactivation and password changes take effect on the user's next page load (the session is re-checked against the database each time).
* Every administrator action is checked by the service layer, so a hidden menu item is never the only protection.
