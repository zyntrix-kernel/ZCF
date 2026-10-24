#!/bin/bash
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"
export PYTHONPATH=src
export ZCF_NON_INTERACTIVE=1
python3 -m unittest discover -s tests -v
