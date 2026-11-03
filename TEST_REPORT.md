# Test report: bug fixes, authentication and functional audit

Tested on: MariaDB 10.11 (MySQL-compatible, strict `ONLY_FULL_GROUP_BY` mode), Python 3.12, Streamlit 1.66.1, using Streamlit's AppTest
(drives the real pages and forms) and direct service-layer tests. **Not tested:** real MySQL 8 (the author could not install it), a real browser
(visual appearance), a real email provider, Streamlit Community Cloud. Where a requirement depends on those, the status says so.

Suites: `tests/test_rendering.py` (static scan), `tests/test_auth.py` (46 checks), `tests/test_services.py` (all recruitment write rules),
`tests/test_ui.py` (37 checks), `tests/smoke_test.py` (all pages, all roles). Latest run: **all passed**.

| # | Acceptance criterion | Status | Evidence / limits |
|---|---|---|---|
| 1 | All pages render without internal code or object representations | **Passed** | Root cause found and fixed (8 bare conditional statements). Static scan + every page opened as admin, recruiter, viewer with no stray `st.help` output. Visual check in a real browser not done. |
| 2 | Existing recruitment modules and workflows remain functional | **Passed** | 37 UI checks drive each form (candidates, applications, screening, status change, interviews, feedback, offers, approvals, onboarding, requisitions, vacancies, postings, 7 reports) and `test_services.py` covers the rules. One real bug found and fixed (NULL shown as "nan"). Not run on MySQL 8. |
| 3 | Login, logout and role-based restrictions work | **Passed** | Login by username or email, generic errors, lockout, forced password change, role-specific navigation. Show/hide password is Streamlit's built-in eye button (not visually verified). |
| 4 | Profile and account settings work | **Passed** | Profile view/update, preferences (landing page, compact tables) saved and applied. Role cannot be changed by the user. |
| 5 | Change Password works securely | **Passed** | Current password verified, policy, confirmation, same-password rejection, salted hash, old password stops working. |
| 6 | Forgot / Reset Password with a configured email service | **Passed with a test SMTP server; real provider Not verified** | Token hashed, 30-minute expiry, single use, new request cancels old, unknown email indistinguishable, rate limit, SMTP failure handled. You must add real SMTP credentials (AUTH_SETUP.md). |
| 7 | Administrator user management works | **Passed** | Create, edit, assign existing roles, activate / deactivate, unlock, temporary-password reset, security log, last-admin protection. |
| 8 | Existing database records remain intact | **Passed** | Migration only adds 3 tables; row counts of all 29 existing tables identical before and after; re-running it is harmless; imported users keep role and hash. |
| 9 | Backend permissions prevent unauthorised access | **Passed** | Every admin function refuses recruiter and viewer; page-level guard; deactivated or demoted users lose access at the next page load. Note: this is a Streamlit app, so the "backend" is the service layer. There is no separate REST API. |
| 10 | Local execution and Streamlit Community Cloud remain compatible | **Local: Passed. Cloud: Not verified** | Both login modes tested (old configuration-file mode still works until the migration is applied). Cloud needs: migration run once against the cloud database, `[email]` and `app_base_url` secrets. |

## Not implemented / limits
* Administrator password reset issues a temporary password shown once; it does not email the user.
* Resume file **upload** (requested earlier) is not implemented. It needs a storage decision (see below).
* No multi-factor authentication or single sign-on.

## Outstanding issues
1. **Migration awaits your approval** and must be applied (local and cloud) before the new account features work.
2. Real SMTP credentials are required for Forgot Password.
3. Retest on MySQL 8 and on Streamlit Cloud. The earlier `information_schema` bug showed MariaDB and MySQL 8 can differ.
4. Resume upload: choose between storing files in the database (`LONGBLOB` column, a schema change), an object store, or keeping a path/link field.


---

# Part 2: Enterprise UI redesign (design system, shell, dashboard, tables, forms)

Latest full run (MariaDB 10.11, strict mode): `test_ui.py` 59/59, `test_auth.py` 46/46, `test_services.py` all rules, `smoke_test.py` all pages and roles
(also in the older configuration-file login mode), `test_rendering.py` clean. **No authentication, role, permission or database-structure change was made.**

| Requirement | Status | Evidence / limits |
|---|---|---|
| Design system (palette, Inter font, 10-12 px radius, subtle shadows, reusable components) | **Implemented; visual appearance Not verified** | One module (`app_core/ui.py`) holds colours, CSS, headers, KPI cards, badges, tables, form buttons, charts. Pages use it. No browser was available, so colours, spacing and fonts were not seen on screen. I confirmed that every CSS hook I rely on exists in Streamlit's bundle (and removed one that did not). |
| Sidebar: logo/name, grouped icons, active item, user + role + sign out, collapsible | **Passed (structure); look Not verified** | Brand, five groups, signed-in name/role/email and Sign out checked in tests. Collapse uses Streamlit's built-in control. The user box sits under the menu (Streamlit cannot pin it to the very bottom). |
| Header: title, description, breadcrumbs, actions, notifications, profile | **Passed (structure)** | Every page has the same title/description block; shell adds breadcrumbs, Refresh with last-updated time, notification bell (counts from live data, role-aware) and the profile menu. |
| Dashboard KPIs (10), trends only when reliable | **Passed** | All 10 KPIs compared with direct SQL; trends compare with the previous period of equal length and appear only when it has data (tested with and without data; none for "All time"). Nothing is estimated. |
| Dashboard filters (date, department, vacancy, status, source) | **Passed** | Each filter, and an empty combination, checked against SQL counts; every KPI and chart uses the same filtered data. |
| Analytics (pipeline, status, monthly trend, department, vacancy status, source, interview outcomes, offer-to-hire, time-to-hire) and operational sections | **Passed (data); charts Not visually verified** | Pipeline, monthly and source figures equal SQL; all nine charts and five sections render without error and show empty states when there is no data. |
| Tables: headings, badges, hidden IDs, search, sort, paging, empty states, CSV | **Passed** | Tested: no ID columns, readable headings, coloured status badges, 10 rows per page with paging controls. Search and sort are Streamlit's built-in table tools. |
| Row-level action menus | **Partly verified** | Select a row to get action buttons (candidates, applications, interviews, vacancies, offers). Streamlit's test tool cannot click a table row, so I tested the pages accept the record each action selects, not the click itself. Actions point you to the right tab; Streamlit cannot switch tabs by code. |
| Forms: grouped, required markers, inline errors, Save/Update/Cancel, duplicate-submit protection | **Mostly implemented** | Forms are card-styled with a Cancel button; double submissions within 3 seconds are ignored; the server still rejects true duplicates. Messages appear at the top of the page (not beside the field) because Streamlit forms validate on submit. Required fields marked `*` only on the add-candidate form. |
| Loading, notifications, tooltips, friendly errors, refresh, last updated | **Passed** | Saving spinner, success/error banners, KPI tooltips, Refresh button, last-updated stamp. Unexpected errors show a plain message; technical details only for administrators. |
| Responsiveness | **Not verified** | CSS rules for narrow screens exist and Streamlit stacks columns on phones, but no device or browser was available to confirm. |
| Authentication, roles, backend authorisation preserved | **Passed** | All earlier auth/RBAC tests still pass unchanged. |

## Defects found and fixed during this work
* The first redesign build crashed the About page (a list passed to the new table helper). The friendly error handler caught it and my test failed on it; fixed.
* A test expected one header menu; there are now two (notifications, profile).

## Known limits (unchanged unless stated)
* Not run on MySQL 8, a real browser, or Streamlit Community Cloud.
* Resume file upload is still not implemented (needs your storage decision).
* Row-action clicks and all visual styling need a manual check in your browser.
