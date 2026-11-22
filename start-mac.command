#!/bin/bash
set -e
cd "$(dirname "$0")"
echo "Narrative OS — local web-first research"
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
python -m pip install -r requirements.txt
python run.py