#!/bin/bash
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"
export PYTHONPATH=src
export ZCF_NON_INTERACTIVE=1
if command -v xvfb-run >/dev/null 2>&1; then
    xvfb-run -a python3 -m unittest discover -s tests -v
else
    python3 -m unittest discover -s tests -v
fi
