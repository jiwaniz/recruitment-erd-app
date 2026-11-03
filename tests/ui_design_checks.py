# Design-system and dashboard checks (executed from test_ui.py; uses its helpers and the `adm` admin session).
import pandas as pd
from app_core import analytics as A, queries as QQ

# ---- shell: sidebar brand, grouped navigation, user box, header
adm = login(new_app(), "admin", "Admin#2026")
side = " ".join(m.value for m in adm.sidebar.markdown)
check("sidebar: brand name, grouped navigation and signed-in user with role",
      "Management System" in side and all(g in side for g in ("Overview", "Recruitment", "Hiring", "Insights", "System")) and "Test Admin" in side and "Admin" in side)
check("sidebar: sign out button present", any(b.label == "Sign out" for b in adm.sidebar.button))
head = " ".join(m.value for m in adm.main.markdown)
check("header: breadcrumbs, refresh button with last-updated time", "crumbs" in head and any(b.label.startswith("Refresh") and "Updated" in b.label for b in adm.main.button))

# ---- tables: no database IDs, status badges, paging, CSV, Cancel buttons
adm.switch_page("views/applications.py").run()
tbl = adm.dataframe[0].value if adm.dataframe else None
check("table: IDs hidden, readable headings, status badges, 10 rows per page by default",
      tbl is not None and not any(c.lower().endswith(" id") or c.lower().endswith("_id") for c in tbl.columns)
      and "Candidate name" in tbl.columns and tbl["Status"].str.contains("🟢|🟡|🔴|⚪").all() and len(tbl) == 10, str(None if tbl is None else list(tbl.columns)))
check("table: paging controls and row-action hint are shown for a long list",
      any(w.label == "Rows per page" for w in adm.selectbox) and any("Select a row" in c.value for c in adm.caption))
adm.switch_page("views/candidates.py").run()
check("forms: every form has a Cancel button next to the primary action", sum(b.label == "Cancel" for b in adm.button) >= 4)

# ---- dashboard numbers against SQL ground truth
def kpi_values(at):
    html = " ".join(m.value for m in at.main.markdown)
    return {m.group(1): m.group(2) for m in re.finditer(r"<span>([^<]+)</span><span class='ico'>[^<]*</span></div><div class='val'>([^<]+)</div>", html)}
dash = login(new_app(), "admin", "Admin#2026"); dash.switch_page("views/dashboard.py").run()
kv = kpi_values(dash)
sql_apps, sql_hires = S("SELECT COUNT(*) FROM application"), S("SELECT COUNT(*) FROM application WHERE status='Hired'")
sql_iv = S("SELECT COUNT(*) FROM interview")
acc, ans = S("SELECT COUNT(*) FROM job_offer WHERE status='Accepted'"), S("SELECT COUNT(*) FROM job_offer WHERE status IN ('Accepted','Declined')")
sql_tth = S("""SELECT AVG(DATEDIFF(h.changed_date, a.date_applied)) FROM application a JOIN application_status_history h
               ON h.application_id=a.application_id AND h.new_status='Hired' WHERE a.status='Hired'""")
check("dashboard KPIs (no filter) equal the database counts",
      kv["Total Applications"] == f"{sql_apps:,}" and kv["Total Hires"] == f"{sql_hires:,}" and kv["Total Interviews"] == f"{sql_iv:,}"
      and kv["Total Candidates"] == f"{S('SELECT COUNT(*) FROM candidate'):,}" and kv["Total Vacancies"] == f"{S('SELECT COUNT(*) FROM job'):,}"
      and kv["Pending Requisition Approvals"] == str(S("SELECT COUNT(*) FROM requisition_request WHERE status='PendingApproval'")), str(kv))
check("dashboard offer acceptance and time-to-hire equal the SQL calculation",
      kv["Offer Acceptance"] == f"{acc / ans * 100:.0f}%" and kv["Avg. Time to Hire"] == f"{float(sql_tth):.0f} days", str(kv))
check("no trend is invented for 'All time' (no previous period exists)", "vs previous" not in " ".join(m.value for m in dash.main.markdown))
dname = S("SELECT d.department_name FROM application a JOIN job_posting p ON p.posting_id=a.posting_id JOIN job j ON j.job_id=p.job_id "
          "JOIN department d ON d.department_id=j.department_id GROUP BY d.department_name ORDER BY COUNT(*) DESC LIMIT 1")
dash.multiselect(key="d_dept").set_value([dname]).run()
kv = kpi_values(dash)
sqlc = S("""SELECT COUNT(*) FROM application a JOIN job_posting p ON p.posting_id=a.posting_id JOIN job j ON j.job_id=p.job_id
            JOIN department d ON d.department_id=j.department_id WHERE d.department_name=:n""", n=dname)
sqlh = S("""SELECT COUNT(*) FROM application a JOIN job_posting p ON p.posting_id=a.posting_id JOIN job j ON j.job_id=p.job_id
            JOIN department d ON d.department_id=j.department_id WHERE d.department_name=:n AND a.status='Hired'""", n=dname)
check("department filter changes KPIs to the filtered database counts", kv["Total Applications"] == f"{sqlc:,}" and kv["Total Hires"] == f"{sqlh:,}" and not dash.exception, str(kv))
dash.multiselect(key="d_dept").set_value([]).run()
dash.multiselect(key="d_src").set_value(["Rozee.pk"]).run()
sqls = S("SELECT COUNT(*) FROM application a JOIN job_posting p ON p.posting_id=a.posting_id JOIN source s ON s.source_id=p.source_id WHERE s.source_name='Rozee.pk'")
check("source filter works", kpi_values(dash)["Total Applications"] == f"{sqls:,}")
dash.multiselect(key="d_src").set_value([]).run()
dash.multiselect(key="d_status").set_value(["Hired"]).run()
check("status filter works", kpi_values(dash)["Total Applications"] == f"{sql_hires:,}")
dash.multiselect(key="d_status").set_value([]).run()
dash.multiselect(key="d_dept").set_value([dname]).run(); dash.multiselect(key="d_status").set_value(["Withdrawn"]).run(); dash.multiselect(key="d_src").set_value(["Walk-in Interview Day"]).run()
check("empty filter combinations show an empty state, not an error", not dash.exception and any("No applications match" in m.value for m in dash.main.markdown))

# ---- analytics functions: previous-period trends, pipeline, monthly totals
apps_all, hist, ivs, vac, reqs = QQ.dash_applications(), QQ.dash_history(), QQ.interviews(), QQ.vacancies(), QQ.requisitions()
f = A.Filters(pd.Timestamp("2026-10-01").date(), pd.Timestamp("2026-10-31").date())
k = A.kpis(apps_all, ivs, vac, reqs, 184, f, "31 days")
cur = S("SELECT COUNT(*) FROM application WHERE date_applied BETWEEN '2026-10-01' AND '2026-10-31'")
prev = S("SELECT COUNT(*) FROM application WHERE date_applied BETWEEN '2026-08-31' AND '2026-09-30'")
check("trend compares with the previous period of equal length (and only when it has data)",
      k["applications"] == cur and ("applications" in k["trends"]) == bool(prev) and (not prev or f"{(cur - prev) / prev * 100:+.0f}%" in k["trends"]["applications"][0]),
      f"{cur} {prev} {k['trends']}")
f0 = A.Filters(pd.Timestamp("2025-01-01").date(), pd.Timestamp("2025-01-31").date())
check("no trend when the previous period has no data", A.kpis(apps_all, ivs, vac, reqs, 184, f0)["trends"] == {})
pl = A.pipeline(apps_all, hist).set_index("stage")["applications"]
check("pipeline funnel equals distinct applications that reached each stage",
      all(int(pl[s]) == S("SELECT COUNT(DISTINCT application_id) FROM application_status_history WHERE new_status=:s", s=s) for s in A.STAGES))
check("monthly application totals add up to the number of applications", int(A.monthly(apps_all, ivs)["Applications"].sum()) == sql_apps)
check("source analysis totals equal the number of applications", int(A.by_source(apps_all)["applications"].sum()) == sql_apps)

# ---- row-action targets: the session keys the row-action buttons set must be accepted by the pages' selectboxes
aid = S("SELECT application_id FROM application ORDER BY application_id DESC LIMIT 1")
cid2 = S("SELECT candidate_id FROM candidate ORDER BY candidate_id DESC LIMIT 1")
iid2 = S("SELECT interview_id FROM interview ORDER BY interview_id DESC LIMIT 1")
for page, key, value in [("views/applications.py", "man_app", aid), ("views/candidates.py", "prof_c", cid2), ("views/candidates.py", "edit_c", cid2),
                         ("views/interviews.py", "mi", iid2)]:
    t = login(new_app(), "admin", "Admin#2026"); t.session_state[key] = value; t.switch_page(page).run()
    check(f"row action target {key}: page opens on the chosen record", not t.exception and not t.error and find(t.selectbox, key=key).value == value, str([e.value[:80] for e in t.exception]))
