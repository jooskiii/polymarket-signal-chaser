#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

source venv/bin/activate

PIPELINE_INTERVAL=$((20 * 60))        # full pipeline every 20 minutes
CHECK_INTERVAL=$((2 * 60))            # check open trades every 2 minutes

while true; do
    # ── Full pipeline: fetch data, match, log new trades ──────────
    echo "=========================================="
    echo "  Polymarket Signal Chaser — Full Pipeline"
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

    NEXT_PIPELINE=$(date -u -d "+20 minutes" '+%Y-%m-%d %H:%M:%S UTC' 2>/dev/null \
                 || date -u -v+20M '+%Y-%m-%d %H:%M:%S UTC')
    echo
    echo "=========================================="
    echo "  Next full pipeline: $NEXT_PIPELINE"
    echo "  Checking open trades every 2 minutes..."
    echo "=========================================="

    # ── Between pipelines: check trades frequently ────────────────
    ELAPSED=0
    while [ "$ELAPSED" -lt "$PIPELINE_INTERVAL" ]; do
        sleep "$CHECK_INTERVAL"
        ELAPSED=$((ELAPSED + CHECK_INTERVAL))

        echo
        echo "------------------------------------------"
        echo "  Trade check — $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
        echo "------------------------------------------"
        python -m src.paper_trading.check
    done
done
