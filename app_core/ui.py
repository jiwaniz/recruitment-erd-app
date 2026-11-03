"""
Design system: one place for colours, typography, CSS, headers, KPI cards, status badges, tables, forms and charts.
Every page uses these helpers, so the whole application looks and behaves the same.
"""
from datetime import date, datetime

import pandas as pd
import streamlit as st

NAVY, PRIMARY, BLUE = "#172554", "#4F46E5", "#2563EB"
BG, CARD, TEXT, MUTED, BORDER = "#F8FAFC", "#FFFFFF", "#0F172A", "#64748B", "#E2E8F0"
GREEN, AMBER, RED = "#16A34A", "#D97706", "#DC2626"
COLORS = [PRIMARY, BLUE, "#0EA5E9", "#14B8A6", "#8B5CF6", AMBER, "#F97316", "#64748B", GREEN]
STATUS_COLORS = {
    "Applied": "#94A3B8", "Screening": "#0EA5E9", "Interviewing": PRIMARY, "Assessment": "#8B5CF6",
    "BackgroundCheck": "#14B8A6", "Offered": AMBER, "Hired": GREEN, "Rejected": RED, "Withdrawn": "#64748B",
    "Active": GREEN, "Closed": "#64748B", "Expired": "#F97316", "Draft": "#94A3B8", "PendingApproval": AMBER,
    "Approved": GREEN, "Open": GREEN, "Filled": BLUE, "Not advertised": "#94A3B8", "Sent": "#0EA5E9",
    "Accepted": GREEN, "Declined": RED, "Pending": AMBER, "Completed": GREEN, "DocumentsSubmitted": BLUE,
}
_DOT = {**{k: "🟢" for k in ("Hired", "Approved", "Accepted", "Active", "Completed", "Clear", "Shortlisted", "Open", "Filled", "Hire", "StrongHire")},
        **{k: "🟡" for k in ("Applied", "Screening", "Interviewing", "Assessment", "BackgroundCheck", "Offered", "PendingApproval", "Pending",
                             "InProgress", "Scheduled", "OnHold", "Awaiting feedback", "Sent", "Draft", "DocumentsSubmitted")},
        **{k: "🔴" for k in ("Rejected", "Declined", "Failed", "Flagged", "NoHire", "StrongNoHire", "Expired")},
        **{k: "⚪" for k in ("Closed", "Withdrawn", "Not advertised")}}

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"], .stApp {{ font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif; color: {TEXT}; }}
.stApp {{ background: {BG}; }}
.block-container {{ padding-top: 1.2rem; padding-bottom: 3rem; max-width: 1320px; }}
header[data-testid="stHeader"] {{ background: transparent; }}
h1, h2, h3, h4 {{ letter-spacing: -0.01em; color: {TEXT}; font-weight: 600; }}
h3 {{ font-size: 1.1rem; }}
.page-title {{ font-size: 1.65rem; font-weight: 700; margin: .2rem 0 0; color: {TEXT}; }}
.page-sub {{ color: {MUTED}; margin: .15rem 0 1rem; font-size: .95rem; }}
.crumbs {{ color: {MUTED}; font-size: .8rem; padding-top: .55rem; }}
.crumbs b {{ color: {TEXT}; font-weight: 600; }}
.login-title {{ font-size: 1.8rem; font-weight: 700; color: {NAVY}; margin: 2rem 0 .2rem; }}
div[data-testid="stMetric"], .kpi, div[data-testid="stForm"], div[data-testid="stExpander"] {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 12px; }}
div[data-testid="stMetric"] {{ padding: .8rem 1rem; box-shadow: 0 1px 2px rgba(15,23,42,.04); }}
div[data-testid="stMetricLabel"] {{ color: {MUTED}; font-size: .8rem; }}
div[data-testid="stMetricValue"] {{ font-weight: 700; }}
div[data-testid="stForm"] {{ padding: 1.1rem 1.2rem; }}
.kpi {{ padding: .85rem 1rem; box-shadow: 0 1px 2px rgba(15,23,42,.04); min-height: 108px; }}
.kpi .top {{ display: flex; justify-content: space-between; align-items: center; color: {MUTED}; font-size: .8rem; font-weight: 500; }}
.kpi .ico {{ background: #EEF2FF; color: {PRIMARY}; border-radius: 10px; width: 32px; height: 32px; display: inline-flex; align-items: center; justify-content: center; font-size: 1rem; }}
.kpi .val {{ font-size: 1.75rem; font-weight: 700; color: {TEXT}; line-height: 1.25; margin-top: .2rem; }}
.kpi .sub {{ font-size: .76rem; color: {MUTED}; margin-top: .1rem; }}
.kpi .up {{ color: {GREEN}; font-weight: 600; }} .kpi .down {{ color: {RED}; font-weight: 600; }}
.empty {{ border: 1px dashed {BORDER}; border-radius: 12px; padding: 1.6rem; text-align: center; color: {MUTED}; background: {CARD}; }}
.empty b {{ color: {TEXT}; display: block; margin-bottom: .2rem; }}
div[data-baseweb="input"], div[data-baseweb="select"] > div, div[data-baseweb="textarea"] {{ border-radius: 10px !important; }}
.stButton > button, .stDownloadButton > button, div[data-testid="stFormSubmitButton"] > button {{ border-radius: 10px; font-weight: 500; }}
button[kind="primary"] {{ background: {PRIMARY}; border-color: {PRIMARY}; }}
button[kind="primary"]:hover {{ background: #4338CA; border-color: #4338CA; }}
button[data-baseweb="tab"] {{ font-weight: 500; }}
div[data-testid="stDataFrame"] {{ border: 1px solid {BORDER}; border-radius: 12px; overflow: hidden; }}
section[data-testid="stSidebar"] {{ background: {NAVY}; }}
section[data-testid="stSidebar"] * {{ color: #E2E8F0; }}
section[data-testid="stSidebar"] hr {{ border-color: rgba(255,255,255,.12); }}
section[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] {{ border-radius: 10px; padding: .35rem .6rem; }}
section[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"]:hover {{ background: rgba(255,255,255,.08); }}
section[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"][aria-current="page"] {{ background: {PRIMARY}; }}
section[data-testid="stSidebar"] a[aria-current="page"] * {{ color: #FFFFFF; font-weight: 600; }}
section[data-testid="stSidebar"] .stButton > button {{ background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.18); color: #E2E8F0; width: 100%; }}
.brand {{ display: flex; align-items: center; gap: .6rem; padding: .3rem .2rem .6rem; }}
.brand .logo {{ background: {PRIMARY}; border-radius: 10px; width: 36px; height: 36px; display: flex; align-items: center; justify-content: center; font-size: 1.1rem; }}
.brand .name {{ font-weight: 700; font-size: .95rem; line-height: 1.15; color: #fff; }}
.navgroup {{ font-size: .68rem; letter-spacing: .08em; text-transform: uppercase; color: #94A3B8 !important; margin: .9rem 0 .25rem .3rem; }}
.userbox {{ background: rgba(255,255,255,.06); border-radius: 10px; padding: .6rem .7rem; margin-bottom: .5rem; font-size: .82rem; }}
.userbox b {{ color: #fff; display: block; }}
@media (max-width: 640px) {{
  .block-container {{ padding: 1rem .7rem 3rem; }} .page-title {{ font-size: 1.3rem; }} .kpi .val {{ font-size: 1.4rem; }} .crumbs {{ display: none; }}
}}
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def page_header(title: str, subtitle: str = ""):
    st.markdown(f"<div class='page-title'>{title}</div>", unsafe_allow_html=True)
    if subtitle:
        st.markdown(f"<div class='page-sub'>{subtitle}</div>", unsafe_allow_html=True)


def section(title: str, caption: str = ""):
    st.markdown(f"#### {title}")
    if caption:
        st.caption(caption)


def metrics(items: list[tuple], cols: int | None = None):
    """items = [(label, value, help_text_or_None), ...]"""
    cols = cols or len(items)
    for start in range(0, len(items), cols):
        row = st.columns(cols)
        for col, item in zip(row, items[start:start + cols]):
            col.metric(item[0], item[1], help=item[2] if len(item) > 2 else None)


def kpi_row(cards: list[dict]):
    """cards = [{icon, label, value, sub, delta, good(bool), help}] shown 5 per row."""
    for start in range(0, len(cards), 5):
        cols = st.columns(5)
        for col, c in zip(cols, cards[start:start + 5]):
            delta = f"<span class='{'up' if c.get('good', True) else 'down'}'>{c['delta']}</span> " if c.get("delta") else ""
            col.markdown(f"<div class='kpi' title=\"{c.get('help', '')}\"><div class='top'><span>{c['label']}</span>"
                         f"<span class='ico'>{c['icon']}</span></div><div class='val'>{c['value']}</div>"
                         f"<div class='sub'>{delta}{c.get('sub', '')}</div></div>", unsafe_allow_html=True)


def empty_state(title: str, hint: str = ""):
    st.markdown(f"<div class='empty'><b>{title}</b>{hint}</div>", unsafe_allow_html=True)


def last_updated():
    t = st.session_state.get("_data_time")
    return f"Updated {t:%H:%M:%S}" if t else ""


def val(v, default=""):
    """Database NULL becomes NaN in pandas (and NaN is truthy), so `v or default` is wrong. Use this instead."""
    return default if v is None or (isinstance(v, float) and v != v) else v


def pkr(value) -> str:
    try:
        return f"PKR {float(value):,.0f}"
    except (TypeError, ValueError):
        return "-"


def badge(v) -> str:
    return f"{_DOT.get(str(v), '⚪')} {v}"


def _title(col: str) -> str:
    words = col.replace("_", " ").strip()
    return (words[:1].upper() + words[1:]).replace(" no", " no.").replace("Pkr", "PKR")


def prettify(df: pd.DataFrame, hide_ids: bool = True) -> pd.DataFrame:
    """Business-friendly copy of a table: no database IDs, status badges, readable dates and column names."""
    out = df.copy()
    if hide_ids:
        out = out[[c for c in out.columns if not (c == "id" or c.endswith("_id"))]]
    for c in out.columns:
        low = c.lower()
        if low == "status" or low.endswith("_status") or low in ("decision", "result", "recommendation", "outcome"):
            out[c] = out[c].map(lambda v: badge(v) if pd.notna(v) else "")
        elif pd.api.types.is_datetime64_any_dtype(out[c]):
            out[c] = out[c].dt.strftime("%d %b %Y %H:%M").str.replace(" 00:00", "", regex=False)
        elif out[c].map(lambda v: isinstance(v, (date, datetime))).any():
            out[c] = out[c].map(lambda v: v.strftime("%d %b %Y") if pd.notna(v) and hasattr(v, "strftime") else "")
    return out.rename(columns={c: _title(c) for c in out.columns})


def small_table(df: pd.DataFrame, hide_ids: bool = True):
    """Compact table for detail views (no paging). Accepts a DataFrame or a list of dicts."""
    if df is not None and not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    if df is None or df.empty:
        empty_state("Nothing to show yet")
        return
    st.dataframe(prettify(df, hide_ids), hide_index=True, width="stretch")


def show_table(df: pd.DataFrame, filename: str | None = None, height: int | None = None, key: str | None = None,
               page_sizes=(10, 25, 50, 100), actions: list | None = None, label_col: str | None = None):
    """
    Main list table: readable headings, status badges, no IDs, search / sort (built in), paging, CSV download.
    `actions` = [(button label, callback(row_dict))] adds a row-action bar for the selected row. Returns that row or None.
    """
    if df is None or df.empty:
        empty_state("No records match the current selection", "Change the filters or add a new record.")
        return None
    k = key or filename or "tbl"
    total, size, page = len(df), page_sizes[0], 1
    if total > page_sizes[0]:
        c1, c2, c3 = st.columns([1.4, 1.4, 5])
        size = c1.selectbox("Rows per page", page_sizes, key=f"{k}_ps")
        pages = max(1, -(-total // size))
        page = c2.number_input("Page", 1, pages, 1, key=f"{k}_pg")
        c3.markdown(f"<div style='padding-top:1.9rem;color:{MUTED};font-size:.85rem'>{total:,} records, page {page} of {pages}</div>",
                    unsafe_allow_html=True)
    chunk = df.iloc[(page - 1) * size: page * size]
    prefs = (st.session_state.get("user") or {}).get("preferences", {})
    kwargs = dict(hide_index=True, width="stretch", height=height or (320 if prefs.get("compact_tables") else "auto"))
    if actions:
        kwargs.update(on_select="rerun", selection_mode="single-row", key=f"{k}_sel")
    event = st.dataframe(prettify(chunk), **kwargs)
    if total <= size:
        st.caption(f"{total:,} record(s)")
    selected = None
    if actions:
        rows = (getattr(getattr(event, "selection", None), "rows", None) or []) if event is not None else []
        if rows:
            selected = chunk.iloc[rows[0]].to_dict()
            name = selected.get(label_col) if label_col else None
            with st.container(border=True):
                st.caption(f"Row actions{f': {name}' if name else ''}")
                for col, (label, fn) in zip(st.columns(len(actions)), actions):
                    col.button(label, key=f"{k}_act_{label}", on_click=fn, args=(selected,))
        else:
            st.caption("Select a row to see its actions.")
    if filename:
        st.download_button("Download CSV", df.to_csv(index=False).encode("utf-8"), file_name=filename, mime="text/csv", key=f"dl_{k}")
    return selected


def submit(label: str) -> bool:
    """Primary save button plus a Cancel button (use inside st.form). Returns True only for the save button."""
    c1, c2, _ = st.columns([1.3, 1, 4])
    saved = c1.form_submit_button(label, type="primary")
    c2.form_submit_button("Cancel")
    return saved


def notify(kind: str, message: str):
    st.session_state["_flash"] = (kind, message)


def show_flash():
    flash = st.session_state.pop("_flash", None)
    if flash:
        kind, message = flash
        {"success": st.success, "error": st.error, "warning": st.warning}.get(kind, st.info)(message)
        if kind == "success" and "Temporary password" not in message:
            st.toast(message, icon="✅")


def labels(options: list[tuple]) -> dict:
    return {value: label for value, label in options}


def select_pair(label: str, options: list[tuple], key: str, index: int | None = 0, allow_none: bool = False,
                none_label: str = "None"):
    """Selectbox that shows labels but returns the id."""
    ids = [o[0] for o in options]
    names = labels(options)
    if allow_none:
        ids = [None] + ids
        names[None] = none_label
    if not ids:
        st.warning(f"No options available for '{label}'.")
        return None
    return st.selectbox(label, ids, format_func=lambda v: names[v], key=key,
                        index=index if (index is None or index < len(ids)) else 0)


def chart(fig, height: int = 300):
    """Consistent chart look."""
    fig.update_layout(height=height, margin=dict(l=0, r=0, t=10, b=0), font=dict(family="Inter, system-ui", size=12, color=TEXT),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", legend=dict(orientation="h", y=-0.2, title=""),
                      colorway=COLORS)
    fig.update_xaxes(showgrid=False, linecolor=BORDER)
    fig.update_yaxes(gridcolor=BORDER)
    st.plotly_chart(fig, width="stretch")
