"""
Database layer: one shared SQLAlchemy engine (connection pool), cached reads, safe transactions.

* Every query that contains a user-supplied value uses bound parameters (never string formatting),
  which protects the application against SQL injection.
* Reads are cached for a short time with st.cache_data; every successful write clears the cache so
  the dashboard and tables refresh immediately.
"""
import ssl
import tempfile
from contextlib import contextmanager
from decimal import Decimal

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

from .config import get_db_config


def db_name() -> str:
    return get_db_config()["name"]


def _ca_file(value: str) -> str:
    """Accept either a path to a CA file or the PEM text itself (handy for Streamlit secrets)."""
    if "BEGIN CERTIFICATE" in value:
        f = tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False)
        f.write(value)
        f.close()
        return f.name
    return value


@st.cache_resource(show_spinner=False)
def get_engine():
    cfg = get_db_config()
    if not cfg["user"]:
        raise RuntimeError("Database user is not configured. Check your .env file or Streamlit secrets.")
    url = URL.create("mysql+pymysql", username=cfg["user"], password=cfg["password"],
                     host=cfg["host"], port=cfg["port"], database=cfg["name"],
                     query={"charset": "utf8mb4"})
    connect_args = {"connect_timeout": 10}
    if cfg["ssl_ca"]:
        connect_args["ssl"] = {"ca": _ca_file(cfg["ssl_ca"])}
    elif cfg["ssl"]:
        connect_args["ssl"] = ssl.create_default_context()
    return create_engine(url, pool_size=5, max_overflow=5, pool_pre_ping=True,
                         pool_recycle=1800, connect_args=connect_args, future=True)


def check_connection() -> tuple[bool, str]:
    """Used by the login page and the About page to show a friendly message if the DB is down."""
    try:
        with get_engine().connect() as conn:
            version = conn.execute(text("SELECT VERSION()")).scalar()
        return True, f"Connected to {db_name()} (server {version})"
    except Exception as exc:                                  # noqa: BLE001
        return False, f"{type(exc).__name__}: {str(exc)[:300]}"


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.columns:
        if df[col].map(lambda x: isinstance(x, Decimal)).any():
            df[col] = df[col].astype(float)
    return df


@st.cache_data(ttl=60, show_spinner=False)
def read(sql: str, params: tuple = ()) -> pd.DataFrame:
    """Cached SELECT. params is a tuple of (name, value) pairs so it can be hashed."""
    with get_engine().connect() as conn:
        result = conn.execute(text(sql), dict(params))
        df = pd.DataFrame(result.fetchall(), columns=list(result.keys()))
    return _clean(df)


def q(sql: str, **params) -> pd.DataFrame:
    return read(sql, tuple(sorted(params.items())))


def scalar(sql: str, **params):
    df = q(sql, **params)
    return None if df.empty else df.iloc[0, 0]


def options(sql: str) -> list[tuple]:
    """Return [(id, label), ...] for select boxes."""
    df = q(sql)
    return [(r[0], r[1]) for r in df.itertuples(index=False)]


def clear_cache():
    st.cache_data.clear()


@contextmanager
def transaction():
    """All statements inside the `with` block succeed together or are rolled back together."""
    with get_engine().begin() as conn:
        yield conn
    clear_cache()


def one(conn, sql: str, **params):
    return conn.execute(text(sql), params).mappings().first()


def run(conn, sql: str, **params):
    return conn.execute(text(sql), params)
