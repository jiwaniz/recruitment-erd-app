"""
Dashboard analytics: pure pandas functions (no Streamlit), so every number can be tested against SQL.

Counting rule (stated in the dashboard help texts): applications are counted by APPLICATION DATE; interviews, hires and offers
belong to the applications that match the filters. Trends compare the selected period with the previous period of the same
length and are shown only when the previous period contains data.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

STAGES = ["Applied", "Screening", "Interviewing", "Assessment", "BackgroundCheck", "Offered", "Hired"]


@dataclass
class Filters:
    start: date | None = None
    end: date | None = None
    departments: list = field(default_factory=list)
    jobs: list = field(default_factory=list)          # job_id values
    statuses: list = field(default_factory=list)
    sources: list = field(default_factory=list)

    @property
    def active(self) -> bool:
        return bool(self.start or self.end or self.departments or self.jobs or self.statuses or self.sources)


def apply(apps: pd.DataFrame, f: Filters, ignore_dates: bool = False) -> pd.DataFrame:
    df = apps
    if not ignore_dates:
        if f.start:
            df = df[df["date_applied"] >= pd.Timestamp(f.start)]
        if f.end:
            df = df[df["date_applied"] <= pd.Timestamp(f.end)]
    if f.departments:
        df = df[df["department_name"].isin(f.departments)]
    if f.jobs:
        df = df[df["job_id"].isin(f.jobs)]
    if f.statuses:
        df = df[df["status"].isin(f.statuses)]
    if f.sources:
        df = df[df["source_name"].isin(f.sources)]
    return df


def previous_period(f: Filters) -> Filters | None:
    if not (f.start and f.end):
        return None
    days = (f.end - f.start).days + 1
    return Filters(f.start - timedelta(days=days), f.start - timedelta(days=1), f.departments, f.jobs, f.statuses, f.sources)


def interviews_for(ivs: pd.DataFrame, apps: pd.DataFrame) -> pd.DataFrame:
    return ivs[ivs["application_id"].isin(apps["application_id"])] if not ivs.empty else ivs


def _counts(apps, ivs):
    return {"applications": len(apps), "interviews": len(interviews_for(ivs, apps)), "hires": int((apps["status"] == "Hired").sum())}


def trend(cur: int, prev: int | None, unit: str) -> tuple[str, bool] | None:
    if not prev:
        return None
    pct = (cur - prev) / prev * 100
    return (f"{'+' if pct >= 0 else ''}{pct:.0f}% vs previous {unit}", pct >= 0)


def kpis(apps_all, ivs, vac, reqs, total_candidates: int, f: Filters, unit: str = "period") -> dict:
    apps = apply(apps_all, f)
    out = {}
    out["candidates"] = apps["candidate_id"].nunique() if f.active else total_candidates
    v = vac
    if f.departments:
        v = v[v["department_name"].isin(f.departments)]
    if f.jobs:
        v = v[v["job_id"].isin(f.jobs)]
    out["vacancies"] = len(v)
    out["open_vacancies"] = int((v["vacancy_status"] == "Open").sum()) if not v.empty else 0
    out["applications"] = len(apps)
    my_iv = interviews_for(ivs, apps)
    out["interviews"] = len(my_iv)
    out["hires"] = int((apps["status"] == "Hired").sum())
    acc = int((apps["offer_status"] == "Accepted").sum())
    ans = int(apps["offer_status"].isin(["Accepted", "Declined"]).sum())
    out["offer_acceptance"] = acc / ans * 100 if ans else None
    hired = apps[(apps["status"] == "Hired") & apps["hired_on"].notna()]
    out["time_to_hire"] = float((hired["hired_on"].dt.normalize() - hired["date_applied"]).dt.days.mean()) if len(hired) else None
    r = reqs
    if f.departments:
        r = r[r["department_name"].isin(f.departments)]
    out["pending_requisitions"] = int((r["status"] == "PendingApproval").sum()) if not r.empty else 0
    now = pd.Timestamp.now()
    out["upcoming_interviews"] = int(((my_iv["interview_date"] >= now) & (my_iv["interview_date"] < now + pd.Timedelta(days=7))).sum()) if len(my_iv) else 0
    out["trends"] = {}
    prev = previous_period(f)
    if prev is not None:
        pa = apply(apps_all, prev)
        pc = _counts(pa, ivs)
        for k in ("applications", "interviews", "hires"):
            t = trend(out[k], pc[k], unit)
            if t:
                out["trends"][k] = t
    return out


def pipeline(apps: pd.DataFrame, hist: pd.DataFrame) -> pd.DataFrame:
    reached = hist[hist["application_id"].isin(apps["application_id"])].groupby("new_status").size()
    return pd.DataFrame({"stage": STAGES, "applications": [int(reached.get(s, 0)) for s in STAGES]})


def monthly(apps: pd.DataFrame, ivs: pd.DataFrame) -> pd.DataFrame:
    a = apps.assign(month=apps["date_applied"].dt.to_period("M").dt.to_timestamp()).groupby("month").size().rename("Applications")
    h = apps[apps["hired_on"].notna()]
    h = h.assign(month=h["hired_on"].dt.to_period("M").dt.to_timestamp()).groupby("month").size().rename("Hires")
    i = interviews_for(ivs, apps)
    i = i.assign(month=pd.to_datetime(i["interview_date"]).dt.to_period("M").dt.to_timestamp()).groupby("month").size().rename("Interviews") if len(i) else pd.Series(dtype=int, name="Interviews")
    return pd.concat([a, i, h], axis=1).fillna(0).astype(int).reset_index().rename(columns={"index": "month"}) if len(a) else pd.DataFrame()


def by_source(apps: pd.DataFrame) -> pd.DataFrame:
    g = apps.groupby("source_name").agg(applications=("application_id", "count"), hires=("status", lambda s: int((s == "Hired").sum())))
    g["conversion_pct"] = (g["hires"] / g["applications"] * 100).round(1)
    return g.reset_index().sort_values("applications", ascending=False)


def offer_funnel(apps: pd.DataFrame) -> pd.DataFrame:
    made = int(apps["offer_status"].notna().sum())
    acc = int((apps["offer_status"] == "Accepted").sum())
    hired = int(((apps["status"] == "Hired") & (apps["offer_status"] == "Accepted")).sum())
    return pd.DataFrame({"step": ["Offers made", "Offers accepted", "Hired"], "count": [made, acc, hired]})
