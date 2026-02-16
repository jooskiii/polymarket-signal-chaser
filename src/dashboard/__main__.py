"""Terminal dashboard — full overview of the signal-chaser pipeline.

Usage:
    python -m src.dashboard
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.market import MarketStore
from src.signals import SignalStore
from src.matching import MatchEngine
from src.paper_trading import PaperTrader

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
MATCH_LOG = DATA_DIR / "match_log.json"
CONFIDENCE_THRESHOLD = 0.6


def _fmt_duration(td):
    total_seconds = int(td.total_seconds())
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def _load_match_log():
    if not MATCH_LOG.exists():
        return []
    with open(MATCH_LOG, "r") as f:
        data = json.load(f)
    return data.get("matches", [])


def main():
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(name)s %(levelname)s  %(message)s",
        datefmt="%H:%M:%S",
    )

    # ── Load all data from caches ────────────────────────────────────
    market_store = MarketStore()
    market_store.load()

    signal_store = SignalStore()
    signal_store.load()

    matches = _load_match_log()

    signal_store_for_engine = SignalStore()
    engine = MatchEngine(market_store, signal_store_for_engine)
    trader = PaperTrader(market_store, engine)
    trader.load_trades()
    trade_results = trader.check_trades()

    # ── Compute stats ────────────────────────────────────────────────
    now = datetime.now(timezone.utc)
    cutoff_24h = now - timedelta(hours=24)

    # Headlines in last 24h
    recent_headlines = 0
    for h in signal_store.headlines:
        ts = h.get("fetched_at") or h.get("published", "")
        if ts:
            try:
                t = datetime.fromisoformat(ts)
                if t.tzinfo is None:
                    t = t.replace(tzinfo=timezone.utc)
                if t >= cutoff_24h:
                    recent_headlines += 1
            except (ValueError, TypeError):
                pass

    # Match stats
    total_matches = len(matches)
    matches_with_trade = 0
    matches_without_trade = 0
    trade_keys = {(t["market_id"], t["headline"]) for t in trader._trades}

    for m in matches:
        llm = m.get("llm_assessment")
        if not llm or not llm.get("relevant"):
            matches_without_trade += 1
            continue
        if (llm.get("confidence") or 0) < CONFIDENCE_THRESHOLD:
            matches_without_trade += 1
            continue
        market = m.get("market", {})
        mid = market.get("id", market.get("conditionId", ""))
        headline = m.get("headline", {}).get("title", "")
        if (mid, headline) in trade_keys:
            matches_with_trade += 1
        else:
            matches_without_trade += 1

    # Trade performance — all trades (open + closed)
    total_trades = len(trader._trades)
    skipped_count = len(trader._skipped)
    open_results = [r for r in trade_results if r["trade"]["status"] == "open"]
    closed_results = [r for r in trade_results if r["trade"]["status"] == "closed"]

    if trade_results:
        wins = sum(1 for r in trade_results if r["pnl_usd"] > 0)
        losses = sum(1 for r in trade_results if r["pnl_usd"] < 0)
        flat = len(trade_results) - wins - losses
        win_rate = (wins / len(trade_results)) * 100
        avg_return = sum(r["pnl_pct"] for r in trade_results) / len(trade_results)
        total_pnl = sum(r["pnl_usd"] for r in trade_results)
        avg_held_s = sum(r["time_held"].total_seconds() for r in trade_results) / len(trade_results)
        avg_held = timedelta(seconds=avg_held_s)
    else:
        wins = losses = flat = 0
        win_rate = avg_return = total_pnl = 0
        avg_held = timedelta()

    # Exit reason breakdown
    exit_reasons = {}
    for r in closed_results:
        reason = r["trade"].get("exit_reason", "unknown")
        exit_reasons[reason] = exit_reasons.get(reason, 0) + 1

    # ── Print dashboard ──────────────────────────────────────────────
    print()
    print("=" * 60)
    print("  Polymarket Signal Chaser — Dashboard")
    print("=" * 60)

    print()
    print("  Pipeline Overview")
    print("  " + "-" * 40)
    print(f"  Active markets:          {market_store.count}")
    print(f"  Headlines (last 24h):    {recent_headlines}")
    print(f"  Headlines (total):       {signal_store.count}")
    print(f"  Matches found:           {total_matches}")
    print(f"    -> became trades:      {matches_with_trade}")
    print(f"    -> no trade:           {matches_without_trade}")
    print(f"  Paper trades logged:     {total_trades}")
    print(f"  Skipped (low liquidity): {skipped_count}")

    print()
    print("  Paper Trade Performance")
    print("  " + "-" * 40)
    if total_trades > 0:
        print(f"  Open trades:     {len(open_results)}")
        print(f"  Closed trades:   {len(closed_results)}")
        if exit_reasons:
            reason_str = ", ".join(f"{v} {k}" for k, v in sorted(exit_reasons.items()))
            print(f"  Exit reasons:    {reason_str}")
        print(f"  Wins / Losses:   {wins}W / {losses}L / {flat}F")
        print(f"  Win rate:        {win_rate:.1f}%")
        print(f"  Avg return:      {avg_return:+.2f}%")
        print(f"  Total P&L:       ${total_pnl:+.2f}")
        print(f"  Avg time held:   {_fmt_duration(avg_held)}")
    else:
        print("  No trades yet.")

    # ── 5 Most Recent Trades ─────────────────────────────────────────
    print()
    print("=" * 60)
    print("  5 Most Recent Paper Trades")
    print("=" * 60)

    if not trade_results:
        print("\n  No paper trades to display.")
        print("  Run `python -m src.paper_trading.log` to log trades.")
    else:
        sorted_results = sorted(
            trade_results,
            key=lambda r: r["trade"]["timestamp"],
            reverse=True,
        )[:5]

        for i, r in enumerate(sorted_results, 1):
            t = r["trade"]
            is_closed = t["status"] == "closed"

            if is_closed:
                outcome = "WIN" if r["pnl_usd"] > 0 else ("LOSS" if r["pnl_usd"] < 0 else "FLAT")
                label = f"CLOSED — {t.get('exit_reason', '?')} — {outcome}"
            else:
                label = "OPEN"

            print(f"\n  [{i}] {t['trade_id']} — {label}")
            print(f"      Market:    {t['market_title']}")
            print(f"      Headline:  {t['headline']}")
            print(f"      Direction: {t['direction']}")
            print(f"      Entry:     ${t['entry_price']:.4f}")
            if is_closed:
                print(f"      Exit:      ${t.get('exit_price', 0):.4f}")
            else:
                print(f"      Current:   ${r['current_price']:.4f}")
            print(f"      P&L:       ${r['pnl_usd']:+.2f} ({r['pnl_pct']:+.2f}%)")
            print(f"      Held:      {_fmt_duration(r['time_held'])}")
            print(f"      LLM conf:  {t['llm_confidence']}")
            print(f"      Reasoning: {t['llm_reasoning']}")

    print()


if __name__ == "__main__":
    main()
