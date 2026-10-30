"""Shared look and feel: CSS, page headers, metric cards, tables with CSV export, notifications."""
import pandas as pd
import streamlit as st

PRIMARY = "#4F46E5"
COLORS = ["#4F46E5", "#0EA5E9", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6", "#14B8A6", "#F97316", "#64748B"]
STATUS_COLORS = {
    "Applied": "#94A3B8", "Screening": "#0EA5E9", "Interviewing": "#4F46E5", "Assessment": "#8B5CF6",
    "BackgroundCheck": "#14B8A6", "Offered": "#F59E0B", "Hired": "#10B981", "Rejected": "#EF4444",
    "Withdrawn": "#64748B",
    "Active": "#10B981", "Closed": "#64748B", "Expired": "#F97316",
    "Draft": "#94A3B8", "PendingApproval": "#F59E0B", "Approved": "#10B981",
}

CSS = f"""
<style>
.block-container {{ padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1280px; }}
h1, h2, h3 {{ letter-spacing: -0.01em; }}
.page-title {{ font-size: 1.9rem; font-weight: 700; color: #111827; margin-bottom: 0; }}
.page-sub {{ color: #6B7280; margin-top: 0.1rem; margin-bottom: 1.1rem; }}
.login-title {{ font-size: 2rem; font-weight: 700; color: {PRIMARY}; margin-top: 2rem; }}
div[data-testid="stMetric"] {{
    background: #FFFFFF; border: 1px solid #E5E7EB; border-left: 4px solid {PRIMARY};
    border-radius: 10px; padding: 0.8rem 1rem; box-shadow: 0 1px 2px rgba(0,0,0,0.04);
}}
div[data-testid="stMetricLabel"] {{ color: #6B7280; }}
section[data-testid="stSidebar"] {{ border-right: 1px solid #E5E7EB; }}
.badge {{ display:inline-block; padding: 2px 10px; border-radius: 999px; font-size: 0.78rem; color: white; }}
@media (max-width: 640px) {{
    .block-container {{ padding-left: 0.8rem; padding-right: 0.8rem; }}
    .page-title {{ font-size: 1.4rem; }}
}}
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def page_header(title: str, subtitle: str = ""):
    st.markdown(f"<div class='page-title'>{title}</div>", unsafe_allow_html=True)
    if subtitle:
        st.markdown(f"<div class='page-sub'>{subtitle}</div>", unsafe_allow_html=True)


def metrics(items: list[tuple], cols: int | None = None):
    """items = [(label, value, help_text_or_None), ...]"""
    cols = cols or len(items)
    for start in range(0, len(items), cols):
        row = st.columns(cols)
        for col, item in zip(row, items[start:start + cols]):
            label, value = item[0], item[1]
            help_text = item[2] if len(item) > 2 else None
            col.metric(label, value, help=help_text)


def show_table(df: pd.DataFrame, filename: str | None = None, height: int | None = None, key: str | None = None):
    """Searchable/sortable table (Streamlit's built-in search) with an optional CSV download."""
    if df is None or df.empty:
        st.info("No records match the current selection.")
        return
    st.dataframe(df, width="stretch", hide_index=True, height=height or "auto")
    st.caption(f"{len(df):,} record(s)")
    if filename:
        st.download_button("Download CSV", df.to_csv(index=False).encode("utf-8"), file_name=filename,
                           mime="text/csv", key=key or f"dl_{filename}")


def pkr(value) -> str:
    try:
        return f"PKR {float(value):,.0f}"
    except (TypeError, ValueError):
        return "-"


def notify(kind: str, message: str):
    """Show a message now and keep it for the next run (forms rerun the page after saving)."""
    st.session_state["_flash"] = (kind, message)


def show_flash():
    flash = st.session_state.pop("_flash", None)
    if flash:
        kind, message = flash
        {"success": st.success, "error": st.error, "warning": st.warning}.get(kind, st.info)(message)
        if kind == "success":
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
