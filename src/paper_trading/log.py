"""CLI entry point for logging paper trades.

Usage:
    python -m src.paper_trading.log
"""

import logging
import sys

from src.market import MarketStore
from src.signals import SignalStore
from src.matching import MatchEngine
from .trader import PaperTrader


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s  %(message)s",
        datefmt="%H:%M:%S",
    )

    print("=" * 60)
    print("Phase 4 — Paper Trading: Log Trades")
    print("=" * 60)

    # Load cached data
    market_store = MarketStore()
    market_store.load()
    print(f"Loaded {market_store.count} markets from cache")

    signal_store = SignalStore()
    signal_store.load()
    print(f"Loaded {signal_store.count} headlines from cache")

    if market_store.count == 0:
        print("No markets cached. Run `python -m src.market.cli` first.")
        sys.exit(1)
    if signal_store.count == 0:
        print("No headlines cached. Run `python -m src.signals.cli` first.")
        sys.exit(1)

    # Run matching + paper trading
    engine = MatchEngine(market_store, signal_store)
    trader = PaperTrader(market_store, engine)

    print("\nRunning matching engine and logging trades...")
    new_trades, new_skipped = trader.log_trades()

    # Report
    print()
    print("=" * 60)
    print("Paper Trade Results")
    print("=" * 60)

    if not new_trades and not new_skipped:
        print("No new trades logged (no high-confidence signals or all duplicates).")
        total = len(trader._trades)
        if total:
            print(f"({total} existing trade(s) in the log)")
        return

    print(f"New trades logged: {len(new_trades)}")
    print(f"Skipped (insufficient liquidity): {len(new_skipped)}")
    print(f"Total trades in log: {len(trader._trades)}")
    print()

    for i, trade in enumerate(new_trades, 1):
        print(f"--- Trade {i} [{trade['trade_id']}] ---")
        print(f"  Market:     {trade['market_title']}")
        print(f"  Headline:   {trade['headline']}")
        print(f"  Direction:  {trade['direction']}")
        print(f"  Entry:      ${trade['entry_price']:.4f} (VWAP)")
        print(f"  Shares:     {trade['shares']:.2f}")
        print(f"  Size:       ${trade['position_size_usd']:.2f}")
        print(f"  Embedding:  {trade['embedding_score']:.4f}")
        print(f"  LLM conf:   {trade['llm_confidence']}")
        print(f"  Reasoning:  {trade['llm_reasoning']}")
        print()

    for i, skip in enumerate(new_skipped, 1):
        print(f"--- Skipped {i} ---")
        print(f"  Market:     {skip['market_title']}")
        print(f"  Headline:   {skip['headline']}")
        print(f"  Reason:     {skip['reason']}")
        print()


if __name__ == "__main__":
    main()
