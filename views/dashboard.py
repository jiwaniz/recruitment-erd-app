from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from app_core import analytics as A, db, queries as Q, ui

ui.page_header("Dashboard", "Recruitment analytics command centre. Every figure is calculated from live database records.")
ui.show_flash()

apps_all, hist, evs = Q.dash_applications(), Q.dash_history(), Q.dash_evaluations()
ivs, vac, reqs = Q.interviews(), Q.vacancies(), Q.requisitions()
total_candidates = int(db.scalar("SELECT COUNT(*) AS n FROM candidate") or 0)

if apps_all.empty:
    ui.empty_state("No recruitment data yet", "Add candidates and applications to see analytics here.")
    st.stop()

# ------------------------------------------------------------------ filters
with st.container(border=True):
    st.caption("Filters apply to every figure and chart on this page.")
    c1, c2, c3, c4, c5 = st.columns([1.2, 1.5, 1.6, 1.4, 1.4])
    period = c1.selectbox("Period (by application date)", ["All time", "Last 30 days", "Last 90 days", "Custom range"], key="d_period")
    depts = c2.multiselect("Department", sorted(apps_all["department_name"].unique()), key="d_dept")
    vmap = {int(r.job_id): f"#{r.job_id} {r.job_title}" for r in vac.itertuples()} if not vac.empty else {}
    jobs = c3.multiselect("Vacancy", list(vmap), format_func=vmap.get, key="d_job")
    stats = c4.multiselect("Recruitment status", A.STAGES + ["Rejected", "Withdrawn"], key="d_status")
    srcs = c5.multiselect("Source", sorted(apps_all["source_name"].unique()), key="d_src")
    start = end = None
    unit = "period"
    today = date.today()
    if period == "Last 30 days":
        start, end, unit = today - timedelta(days=29), today, "30 days"
    elif period == "Last 90 days":
        start, end, unit = today - timedelta(days=89), today, "90 days"
    elif period == "Custom range":
        d1, d2 = st.columns(2)
        start = d1.date_input("From", value=apps_all["date_applied"].min().date(), key="d_from")
        end = d2.date_input("To", value=today, key="d_to")
        if start > end:
            st.error("The start date must not be after the end date.")
            st.stop()
f = A.Filters(start, end, depts, jobs, stats, srcs)
apps = A.apply(apps_all, f)
k = A.kpis(apps_all, ivs, vac, reqs, total_candidates, f, unit)
if apps.empty:
    ui.empty_state("No applications match these filters", "Widen the period or clear some filters.")


def card(icon, label, key, fmt="{:,}", help="", sub=""):
    v = k[key]
    t = k["trends"].get(key)
    return dict(icon=icon, label=label, value=fmt.format(v) if v is not None else "n/a", help=help, sub=sub,
                delta=t[0] if t else "", good=t[1] if t else True)


ui.kpi_row([
    card("👥", "Total Candidates", "candidates", help="Candidates with applications that match the filters (all candidates when no filter is set)"),
    card("💼", "Total Vacancies", "vacancies", help="Vacancies matching the department / vacancy filters"),
    card("📄", "Total Applications", "applications", help="Counted by application date"),
    card("🗓️", "Total Interviews", "interviews", help="Interviews of the applications that match the filters"),
    card("✅", "Total Hires", "hires", help="Applications in status Hired"),
    card("🟢", "Open Vacancies", "open_vacancies", help="Vacancies with an Active posting that are not yet filled"),
    card("🤝", "Offer Acceptance", "offer_acceptance", "{:.0f}%", "Accepted / (Accepted + Declined)", "of answered offers"),
    card("⏱️", "Avg. Time to Hire", "time_to_hire", "{:.0f} days", "Application date to hire date", "applied to hired"),
    card("📝", "Pending Requisition Approvals", "pending_requisitions", help="Requisitions waiting for approval"),
    card("📅", "Upcoming Interviews", "upcoming_interviews", help="Interviews in the next 7 days", sub="next 7 days"),
])
if f.active and period in ("Last 30 days", "Last 90 days", "Custom range"):
    st.caption("Trend arrows compare with the previous period of the same length and appear only when that period has data.")

# ------------------------------------------------------------------ analytics
st.divider()
ui.section("Pipeline and status")
l, r = st.columns(2)
with l:
    st.markdown("**Recruitment pipeline** (candidates who reached each stage)")
    pl = A.pipeline(apps, hist)
    if pl["applications"].sum() == 0:
        ui.empty_state("No pipeline data")
    else:
        ui.chart(px.funnel(pl, x="applications", y="stage", color_discrete_sequence=[ui.PRIMARY]), 340)
with r:
    st.markdown("**Application status distribution**")
    dist = apps.groupby("status").size().reset_index(name="applications")
    if dist.empty:
        ui.empty_state("No applications")
    else:
        ui.chart(px.pie(dist, names="status", values="applications", hole=0.55, color="status", color_discrete_map=ui.STATUS_COLORS), 340)

ui.section("Trends and volumes")
l, r = st.columns(2)
with l:
    st.markdown("**Monthly recruitment trends**")
    m = A.monthly(apps, ivs)
    if m.empty:
        ui.empty_state("No monthly data")
    else:
        mm = m.melt("month", var_name="measure", value_name="count")
        ui.chart(px.line(mm, x="month", y="count", color="measure", markers=True), 320)
with r:
    st.markdown("**Applications by department**")
    d = apps.groupby("department_name").size().reset_index(name="applications").sort_values("applications")
    if d.empty:
        ui.empty_state("No applications")
    else:
        ui.chart(px.bar(d, x="applications", y="department_name", orientation="h", color_discrete_sequence=[ui.BLUE]), 320)

l, r = st.columns(2)
with l:
    st.markdown("**Vacancies by status**")
    vv = vac
    if depts:
        vv = vv[vv["department_name"].isin(depts)]
    if jobs:
        vv = vv[vv["job_id"].isin(jobs)]
    vs = vv.groupby("vacancy_status").size().reset_index(name="vacancies") if not vv.empty else vv
    if vs.empty:
        ui.empty_state("No vacancies")
    else:
        ui.chart(px.bar(vs, x="vacancy_status", y="vacancies", color="vacancy_status", color_discrete_map=ui.STATUS_COLORS), 300)
with r:
    st.markdown("**Recruitment source analysis**")
    bs = A.by_source(apps)
    if bs.empty:
        ui.empty_state("No source data")
    else:
        fig = px.bar(bs.melt("source_name", ["applications", "hires"], "measure", "count"), x="source_name", y="count",
                     color="measure", barmode="group", color_discrete_sequence=[ui.PRIMARY, ui.GREEN])
        ui.chart(fig, 300)
        st.caption("Conversion (hires / applications): " + ", ".join(f"{r_.source_name} {r_.conversion_pct:.0f}%" for r_ in bs.itertuples()))

l, r, r2 = st.columns(3)
with l:
    st.markdown("**Interview outcomes**")
    e = evs[evs["application_id"].isin(apps["application_id"])]
    if e.empty:
        ui.empty_state("No interview feedback yet")
    else:
        order = ["StrongHire", "Hire", "NoHire", "StrongNoHire"]
        o = e.groupby("recommendation").size().reindex(order, fill_value=0).reset_index(name="evaluations")
        ui.chart(px.bar(o, x="recommendation", y="evaluations", color="recommendation",
                        color_discrete_map={"StrongHire": ui.GREEN, "Hire": "#65A30D", "NoHire": ui.AMBER, "StrongNoHire": ui.RED}), 300)
with r:
    st.markdown("**Offer-to-hire conversion**")
    of = A.offer_funnel(apps)
    if of["count"].iloc[0] == 0:
        ui.empty_state("No offers yet")
    else:
        ui.chart(px.funnel(of, x="count", y="step", color_discrete_sequence=[ui.COLORS[3]]), 300)
with r2:
    st.markdown("**Time-to-hire analysis**")
    h = apps[(apps["status"] == "Hired") & apps["hired_on"].notna()]
    if h.empty:
        ui.empty_state("No hires in this selection")
    else:
        days = (h["hired_on"].dt.normalize() - h["date_applied"]).dt.days.rename("days to hire")
        ui.chart(px.histogram(days, x="days to hire", nbins=8, color_discrete_sequence=[ui.COLORS[4]]), 300)

# ------------------------------------------------------------------ operational sections
st.divider()
ui.section("What needs attention")
l, r = st.columns(2)
with l:
    st.markdown("**Upcoming interviews**")
    up = A.interviews_for(ivs, apps)
    up = up[up["interview_date"] >= pd.Timestamp.now()].sort_values("interview_date").head(8)
    if not up.empty:
        ui.small_table(up[["candidate_name", "job_title", "round_type", "interview_date", "mode"]])
    else:
        ui.empty_state("No upcoming interviews")
with r:
    st.markdown("**Recent applications**")
    ra = apps.sort_values("date_applied", ascending=False).head(8)
    if not ra.empty:
        ui.small_table(ra[["candidate_name", "job_title", "department_name", "date_applied", "status"]])
    else:
        ui.empty_state("No applications")
l, r = st.columns(2)
with l:
    st.markdown("**Pending offers**")
    of_df = Q.offers()
    po = of_df[of_df["status"].isin(["PendingApproval", "Sent"]) & of_df["application_id"].isin(apps["application_id"])]
    if not po.empty:
        ui.small_table(po[["candidate_name", "job_title", "salary_offered", "status"]])
    else:
        ui.empty_state("No pending offers")
with r:
    st.markdown("**Requisitions requiring attention**")
    rq = reqs
    if depts:
        rq = rq[rq["department_name"].isin(depts)]
    rq = rq[(rq["status"] == "PendingApproval") | ((rq["status"] == "Approved") & (pd.to_datetime(rq["hiring_deadline"]) < pd.Timestamp.now()))]
    if not rq.empty:
        ui.small_table(rq[["job_title", "department_name", "headcount", "status", "hiring_deadline"]])
    else:
        ui.empty_state("Nothing needs attention")
st.markdown("**Recent recruitment activities** (latest status changes across all applications)")
ra2 = Q.recent_activity(10)
if not ra2.empty:
    ui.small_table(ra2)
else:
    ui.empty_state("No activity yet")