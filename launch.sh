#!/usr/bin/env bash
# Double-click launcher for the Pixel Palette web app.
cd "$(dirname "$0")" || exit 1
exec ./venv/bin/python run_app.py