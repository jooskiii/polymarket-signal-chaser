#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

source venv/bin/activate

echo "=========================================="
echo "  Polymarket Signal Chaser — Single Run"
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
