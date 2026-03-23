#!/bin/bash
# Refresh gold data every run. Intended for launchd/cron.
set -e

cd "$(dirname "$0")/.."
export TWELVEDATA_API_KEY="3834cbd383484120a7becb985aafa63c"

python scripts/refresh_all.py --symbol gold
