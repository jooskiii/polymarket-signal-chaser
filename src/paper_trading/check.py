"""CLI entry point for checking paper trade P&L.

Usage:
    python -m src.paper_trading.check
"""

import logging
import sys
from datetime import timedelta

from src.market import MarketStore
from src.signals import SignalStore
from src.matching import MatchEngine
from .trader import PaperTrader


def _fmt_duration(td):
    """Format a timedelta into a human-readable string."""
    total_seconds = int(td.total_seconds())
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s  %(message)s",
        datefmt="%H:%M:%S",
    )

    print("=" * 60)
    print("Phase 4 — Paper Trading: Check P&L")
    print("=" * 60)

    market_store = MarketStore()
    market_store.load()

    signal_store = SignalStore()
    engine = MatchEngine(market_store, signal_store)
    trader = PaperTrader(market_store, engine)
    results = trader.check_trades()

    if not results:
        print("\nNo paper trades found.")
        print("Run `python -m src.paper_trading.log` first to log trades.")
        sys.exit(0)

    open_results = [r for r in results if r["trade"]["status"] == "open"]
    closed_results = [r for r in results if r["trade"]["status"] == "closed"]

    # Aggregate stats over all trades
    total_trades = len(results)
    wins = sum(1 for r in results if r["pnl_usd"] > 0)
    losses = sum(1 for r in results if r["pnl_usd"] < 0)
    flat = total_trades - wins - losses
    win_rate = (wins / total_trades) * 100 if total_trades > 0 else 0
    avg_return = sum(r["pnl_pct"] for r in results) / total_trades if total_trades > 0 else 0
    total_pnl = sum(r["pnl_usd"] for r in results)
    avg_held = sum(r["time_held"].total_seconds() for r in results) / total_trades if total_trades > 0 else 0
    avg_held_td = timedelta(seconds=avg_held)

    # Summary
    print()
    print(f"  Total trades:   {total_trades} ({len(open_results)} open, {len(closed_results)} closed)")
    print(f"  Wins / Losses:  {wins}W / {losses}L / {flat}F")
    print(f"  Win rate:       {win_rate:.1f}%")
    print(f"  Avg return:     {avg_return:+.2f}%")
    print(f"  Total P&L:      ${total_pnl:+.2f}")
    print(f"  Avg time held:  {_fmt_duration(avg_held_td)}")

    if closed_results:
        reasons = {}
        for r in closed_results:
            reason = r["trade"].get("exit_reason", "unknown")
            reasons[reason] = reasons.get(reason, 0) + 1
        reason_str = ", ".join(f"{v} {k}" for k, v in sorted(reasons.items()))
        print(f"  Exit reasons:   {reason_str}")
    print()

    # Open trades
    if open_results:
        print("=" * 60)
        print("Open Trades")
        print("=" * 60)
        for i, r in enumerate(open_results, 1):
            t = r["trade"]
            status = "WIN" if r["pnl_usd"] > 0 else ("LOSS" if r["pnl_usd"] < 0 else "FLAT")
            print(f"\n--- Trade {i} [{t['trade_id']}] {status} ---")
            print(f"  Market:     {t['market_title']}")
            print(f"  Headline:   {t['headline']}")
            print(f"  Direction:  {t['direction']}")
            print(f"  Entry:      ${t['entry_price']:.4f}")
            print(f"  Current:    ${r['current_price']:.4f}")
            print(f"  Shares:     {t['shares']:.2f}")
            print(f"  P&L:        ${r['pnl_usd']:+.2f} ({r['pnl_pct']:+.2f}%)")
            print(f"  Held:       {_fmt_duration(r['time_held'])}")
            print(f"  LLM conf:   {t['llm_confidence']}")
            print(f"  Reasoning:  {t['llm_reasoning']}")

    # Closed trades
    if closed_results:
        print()
        print("=" * 60)
        print("Closed Trades")
        print("=" * 60)
        for i, r in enumerate(closed_results, 1):
            t = r["trade"]
            outcome = "WIN" if r["pnl_usd"] > 0 else ("LOSS" if r["pnl_usd"] < 0 else "FLAT")
            print(f"\n--- Trade {i} [{t['trade_id']}] {outcome} — {t.get('exit_reason', '?')} ---")
            print(f"  Market:     {t['market_title']}")
            print(f"  Headline:   {t['headline']}")
            print(f"  Direction:  {t['direction']}")
            print(f"  Entry:      ${t['entry_price']:.4f}")
            print(f"  Exit:       ${t.get('exit_price', 0):.4f}")
            print(f"  Shares:     {t['shares']:.2f}")
            print(f"  P&L:        ${r['pnl_usd']:+.2f} ({r['pnl_pct']:+.2f}%)")
            print(f"  Held:       {_fmt_duration(r['time_held'])}")
            print(f"  Exit reason:{t.get('exit_reason', '?')}")


if __name__ == "__main__":
    main()
