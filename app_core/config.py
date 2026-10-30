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


def get_db_config() -> dict:
    s = _secrets_section("mysql")

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
