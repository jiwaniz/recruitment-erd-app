"""
Configuration loader.

Order of precedence (first one found wins):
  1. Streamlit secrets  (.streamlit/secrets.toml locally, "Secrets" box on Streamlit Community Cloud)
  2. Environment variables / a local .env file

The same code therefore runs on your laptop and in the cloud. No credential is ever
written in the source code.
"""
import json
import os

import streamlit as st
from dotenv import load_dotenv

load_dotenv(override=False)   # reads a local .env file if one exists (never committed to GitHub)


def _secrets_section(name: str) -> dict:
    try:
        if name in st.secrets:
            return dict(st.secrets[name])
    except Exception:          # no secrets file at all (normal when using .env)
        pass
    return {}


def _db_secrets() -> tuple[dict, str]:
    """Find the database settings in Streamlit secrets. Accepts [mysql] (preferred) and also the [connections.<name>] layout
    used by Streamlit's own SQL connections, with the key names host/port/name|database/user|username/password or a single url."""
    try:
        if "mysql" in st.secrets:
            return dict(st.secrets["mysql"]), "mysql"
        if "connections" in st.secrets:
            conns = st.secrets["connections"]
            if "mysql" in conns:
                return dict(conns["mysql"]), "connections.mysql"
            for name in conns:
                v = conns[name]
                if hasattr(v, "get") and (v.get("host") or v.get("url")):
                    return dict(v), f"connections.{name}"
            if conns.get("host") or conns.get("url"):
                return dict(conns), "connections"
    except Exception:
        pass
    return {}, ""


def get_db_config() -> dict:
    s, _ = _db_secrets()
    if s.get("url"):                                       # mysql+pymysql://user:password@host:port/database
        try:
            from sqlalchemy.engine import make_url
            u = make_url(str(s["url"]))
            s = {**s, "host": u.host, "port": u.port, "name": u.database, "user": u.username, "password": u.password}
        except Exception:
            pass
    s = {**s, "name": s.get("name") or s.get("database"), "user": s.get("user") or s.get("username")}

    def pick(skey, ekey, default=None):
        val = s.get(skey)
        if val in (None, ""):
            val = os.getenv(ekey, default)
        return val

    ssl_flag = str(pick("ssl", "DB_SSL", "false")).strip().lower() in ("1", "true", "yes", "on")
    return {
        "host": pick("host", "DB_HOST", "localhost"),
        "port": int(pick("port", "DB_PORT", 3306)),
        "name": pick("name", "DB_NAME", "recruitment_erd_db"),
        "user": pick("user", "DB_USER"),
        "password": pick("password", "DB_PASSWORD", ""),
        "ssl": ssl_flag,
        "ssl_ca": pick("ssl_ca", "DB_SSL_CA"),   # PEM text (cloud) or path to ca.pem (local)
    }


def get_users_config() -> dict:
    """Return {username: {password_hash, role, display_name, employee_id}}."""
    users = {}
    try:
        if "users" in st.secrets:
            for uname, info in st.secrets["users"].items():
                users[str(uname).lower()] = dict(info)
    except Exception:
        pass
    raw = os.getenv("APP_USERS")
    if raw and not users:
        try:
            for uname, info in json.loads(raw).items():
                users[str(uname).lower()] = dict(info)
        except json.JSONDecodeError:
            pass
    return users


def _flat(section: str) -> dict:
    try:
        return dict(st.secrets[section]) if section in st.secrets else {}
    except Exception:
        return {}


def get_email_config() -> dict:
    s = _flat("email")
    pick = lambda k, e, d=None: (s.get(k) if s.get(k) not in (None, "") else os.getenv(e, d))
    return {"host": pick("host", "EMAIL_HOST"), "port": int(pick("port", "EMAIL_PORT", 587)),
            "username": pick("username", "EMAIL_USERNAME"), "password": pick("password", "EMAIL_PASSWORD"),
            "from_address": pick("from_address", "EMAIL_FROM"),
            "security": str(pick("security", "EMAIL_SECURITY", "starttls")).lower()}   # starttls | ssl | none


def get_base_url() -> str:
    try:
        if "app_base_url" in st.secrets:
            return str(st.secrets["app_base_url"]).rstrip("/")
    except Exception:
        pass
    return os.getenv("APP_BASE_URL", "http://localhost:8501").rstrip("/")


def diagnostics() -> list[tuple[str, str]]:
    """What the app can see, for the 'cannot reach the database' page. Never includes passwords or the certificate text."""
    cfg = get_db_config()
    sec, where = _db_secrets()
    try:
        sections = ", ".join(str(k) for k in st.secrets.keys()) or "(none)"
    except Exception:
        sections = "(none found - the Secrets box is empty, not saved, or not valid TOML)"
    ca = cfg["ssl_ca"]
    return [("Secret sections found", sections),
            ("Database settings read from", where or "NOT FOUND (expected a [mysql] section)"),
            ("Keys in that section (names only)", ", ".join(sorted(map(str, sec))) or "-"),
            ("host", str(cfg["host"])), ("port", str(cfg["port"])), ("database name", str(cfg["name"])),
            ("user", cfg["user"] or "(not set)"),
            ("password", f"set ({len(cfg['password'])} characters)" if cfg["password"] else "NOT SET"),
            ("TLS certificate", f"set ({str(ca).count(chr(10)) + 1} lines)" if ca else "not set"),
            ("login users configured", str(len(get_users_config())))]
