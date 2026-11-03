#!/bin/bash
# Rebuild a scratch database, apply the auth migration, import users and run every test. Linux/macOS test helper.
set -e
python tests/test_rendering.py
python tests/test_auth.py
python tests/test_services.py
python tests/test_ui.py
