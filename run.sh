#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

source venv/bin/activate

SLEEP_SECONDS=$((4 * 60 * 60))

while true; do
    echo "=========================================="
    echo "  Polymarket Signal Chaser — Pipeline Run"
    echo "  $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
    echo "=========================================="
    echo

    python -m src.market.cli
    echo
    python -m src.signals.cli
    echo
    python -m src.paper_trading.log
    echo
    python -m src.paper_trading.check
    echo
    python -m src.dashboard

    NEXT_RUN=$(date -u -d "+4 hours" '+%Y-%m-%d %H:%M:%S UTC' 2>/dev/null \
            || date -u -v+4H '+%Y-%m-%d %H:%M:%S UTC')
    echo
    echo "=========================================="
    echo "  Next run: $NEXT_RUN"
    echo "  Sleeping for 4 hours..."
    echo "=========================================="
    sleep "$SLEEP_SECONDS"
done
