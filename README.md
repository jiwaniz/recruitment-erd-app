# Recruitment Management System (Streamlit + MySQL)

A web application for the `recruitment_erd_db` database (29 tables). One code base runs on your computer and,
without changes, on Streamlit Community Cloud with a free cloud MySQL database.

## What you get

| Page | What it does |
|---|---|
| **Dashboard** | KPIs (candidates, vacancies, applications, interviews, hires, offer acceptance, time to hire), pipeline funnel, status charts. Everything is calculated from the database. |
| **Recruitment / Vacancies** | Browse and filter vacancies, add / edit vacancies and their skills, manage postings, raise requisitions, approve them (admin), close them. |
| **Candidates** | Search and filter, full profile (skills, resumes, application history, referrals), add / edit, skills, resumes, referrals, safe delete. |
| **Applications** | Pipeline view, filters, create applications, move through stages with a status history, record screening, assessments and background checks. |
| **Interviews** | Schedule with a panel, reschedule, record feedback per panel member, derived status (Scheduled / Awaiting feedback / Completed). |
| **Hiring** | Selected candidates, create offers, two-step offer approval, accept / decline / withdraw, onboarding. |
| **Reports** | Seven reports (candidates, vacancies, application status, interviews, funnel, hiring, departments) with filters and CSV download. |
| **About** | Connection status, ERD image, table row counts, role description. |

## Project layout

```
app.py                  entry point: login, navigation
views/                  one file per page
app_core/
    config.py           reads .env or Streamlit secrets (same code local and cloud)
    db.py               SQLAlchemy engine + connection pool, cached reads, transactions
    queries.py          read-only SQL
    services.py         all writes: validation, roles, transactions
    auth.py             login, password hashing, roles
    ui.py               theme, metric cards, tables, CSV download
database/               SQL scripts (schema + sample data) for local and cloud
scripts/                inspect_db.py (read only), make_password_hash.py, load_sample_database.py, create_app_user.sql
tests/                  smoke_test.py (all pages, all roles), test_services.py (all write rules)
DB_INSPECTION.md        result of the mandatory database inspection
DEPLOYMENT_GUIDE.md     GitHub + Streamlit Community Cloud + free MySQL, step by step
```

## Run it on your computer (Windows 11)

1. Install Python 3.12 and MySQL. Make sure the database exists (see "Create the database" below).
2. Open a terminal in the project folder (VS Code: Terminal > New Terminal):
   ```
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   copy .env.example .env
   ```
3. Create a limited MySQL account for the app: open `scripts/create_app_user.sql`, change the password, run it as root.
4. Edit `.env`: fill `DB_USER`, `DB_PASSWORD`.
5. Create a login: `python scripts/make_password_hash.py`, then paste the printed hash into the `APP_USERS` line of `.env`.
6. Start the app: `streamlit run app.py` and sign in at http://localhost:8501.

### Create the database
If you have not yet created `recruitment_erd_db`, run `database/01_schema_local.sql` and then `database/02_data_local.sql`
(`mysql -u root -p < database/01_schema_local.sql`). The first script creates a new database and drops an existing one with the
same name, so do not run it over a database you want to keep.

### Create the login users
Roles: `viewer` (read only), `recruiter` (add and edit), `admin` (also approvals, closing, deleting).
Users live in `.env` (`APP_USERS`, one line of JSON) locally or in `[users.*]` sections of Streamlit secrets in the cloud.
There is no public registration. The database has no user table, so no schema change was made.
`employee_id` is optional; when set, that employee is recorded as the person who made status changes.

## Safety rules the code follows
* No table is dropped, truncated or renamed by the application. The app account only needs SELECT, INSERT, UPDATE, DELETE.
* Every query with user input uses bound parameters (SQL injection safe).
* Multi-table operations run in one transaction (for example: interview + panel, offer + approvals, accept offer + onboarding + status history).
* Permissions are checked inside every write function, not only by hiding buttons.
* Candidates, interviews and requisitions with dependent records are never deleted silently; statuses are changed instead and logged.
* Passwords are stored only as salted PBKDF2-SHA256 hashes; five wrong attempts lock the login form for a minute.
* Credentials are read from `.env` / Streamlit secrets; both are excluded by `.gitignore`.

## Tests
```
python tests/smoke_test.py       # opens every page as admin, recruiter and viewer
python tests/test_services.py    # end-to-end write rules  (modifies the database: use a scratch copy!)
```
Both need the same environment variables as the app (`DB_*`, `APP_USERS`).
Both passed against MariaDB 10.11 with MySQL 8 style strict SQL mode (`ONLY_FULL_GROUP_BY`).
They were not run against MySQL 8 itself or against a cloud database, because that was not available while the code was written.

## Design notes and limits
* Reads are cached for 60 seconds and the cache is cleared after every successful write. Filters run in pandas on the cached result,
  which is simple and safe for a database of this size (thousands of rows). For very large data, move the filters into SQL.
* Vacancy status and interview status are derived (the tables have no such columns); see `DB_INSPECTION.md`.
* Free hosting limits (database powering off, app sleeping) are explained in `DEPLOYMENT_GUIDE.md`.
