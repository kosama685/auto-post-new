#!/usr/bin/env bash
set -euo pipefail
python main.py run-once --limit "${1:-2}"
