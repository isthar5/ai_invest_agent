#!/bin/bash
set -euo pipefail
export PYTHONPATH="$(pwd)"
STREAMLIT_BROWSER_GATHER_USAGE_STATS=false streamlit run app/scripts/streamlit_app.py
