"""
Create a password hash for the login users.

    python scripts/make_password_hash.py

Copy the printed line into .env (APP_USERS) or .streamlit/secrets.toml ([users.<name>] section).
The password itself is never stored anywhere.
"""
import getpass
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from app_core.auth import hash_password   # noqa: E402

pw1 = getpass.getpass("Choose a password: ")
pw2 = getpass.getpass("Repeat the password: ")
if pw1 != pw2 or len(pw1) < 8:
    sys.exit("Passwords must match and be at least 8 characters long.")
print("\npassword_hash =", hash_password(pw1))
