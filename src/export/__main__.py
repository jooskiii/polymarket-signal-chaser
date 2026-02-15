"""CSV export — writes markets, signals, matches, and trades to data/.

Usage:
    python -m src.export
"""

import csv
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


def _load_match_log():
    if not MATCH_LOG.exists():
        return []
    with open(MATCH_LOG, "r") as f:
        data = json.load(f)
    return data.get("matches", [])


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


def export_markets(market_store, out_dir):
    """Write markets.csv — all monitored markets with current prices."""
    path = out_dir / "markets.csv"
    markets = market_store.markets

    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "market_id", "question", "outcomes", "outcome_prices",
            "volume", "liquidity", "start_date", "end_date",
        ])
        for m in markets:
            outcomes = m.get("outcomes", [])
            prices = m.get("outcomePrices", [])
            outcome_str = " / ".join(str(o) for o in outcomes)
            price_str = " / ".join(str(p) for p in prices)
            writer.writerow([
                m.get("id", m.get("conditionId", "")),
                m.get("question", ""),
                outcome_str,
                price_str,
                m.get("volumeNum", ""),
                m.get("liquidityNum", m.get("liquidity", "")),
                m.get("startDate", m.get("startDateIso", "")),
                m.get("endDate", m.get("endDateIso", "")),
            ])

    print(f"  markets.csv    — {len(markets)} rows")
    return path


def export_signals(signal_store, out_dir):
    """Write signals.csv — all ingested headlines with timestamps and sources."""
    path = out_dir / "signals.csv"
    headlines = signal_store.headlines

    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "title", "url", "source", "published", "fetched_at",
        ])
        for h in headlines:
            writer.writerow([
                h.get("title", ""),
                h.get("url", ""),
                h.get("source", ""),
                h.get("published", ""),
                h.get("fetched_at", ""),
            ])

    print(f"  signals.csv    — {len(headlines)} rows")
    return path


def export_matches(matches, trade_keys, out_dir):
    """Write matches.csv — all matches with embedding score, LLM assessment, trade status."""
    path = out_dir / "matches.csv"

    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "headline", "market_id", "market_question", "embedding_score",
            "llm_relevant", "llm_direction", "llm_confidence", "llm_reasoning",
            "became_trade", "matched_at",
        ])
        for m in matches:
            headline = m.get("headline", {}).get("title", "")
            market = m.get("market", {})
            mid = market.get("id", market.get("conditionId", ""))
            llm = m.get("llm_assessment") or {}

            became_trade = False
            if llm.get("relevant") and (llm.get("confidence") or 0) >= CONFIDENCE_THRESHOLD:
                became_trade = (mid, headline) in trade_keys

            writer.writerow([
                headline,
                mid,
                market.get("question", ""),
                m.get("embedding_score", ""),
                llm.get("relevant", ""),
                llm.get("direction", ""),
                llm.get("confidence", ""),
                llm.get("reasoning", ""),
                became_trade,
                m.get("matched_at", ""),
            ])

    print(f"  matches.csv    — {len(matches)} rows")
    return path


def export_trades(trader, out_dir):
    """Write trades.csv — all paper trades with P&L and outcome."""
    path = out_dir / "trades.csv"
    trade_results = trader.check_trades()

    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "trade_id", "timestamp", "market_id", "market_title", "headline",
            "direction", "entry_price", "current_price", "shares",
            "pnl_usd", "pnl_pct", "time_held",
            "embedding_score", "llm_confidence", "llm_reasoning", "outcome",
        ])
        for r in trade_results:
            t = r["trade"]
            outcome = "WIN" if r["pnl_usd"] > 0 else ("LOSS" if r["pnl_usd"] < 0 else "FLAT")
            writer.writerow([
                t["trade_id"],
                t["timestamp"],
                t["market_id"],
                t["market_title"],
                t["headline"],
                t["direction"],
                t["entry_price"],
                r["current_price"],
                t["shares"],
                r["pnl_usd"],
                f"{r['pnl_pct']:.2f}%",
                _fmt_duration(r["time_held"]),
                t["embedding_score"],
                t["llm_confidence"],
                t["llm_reasoning"],
                outcome,
            ])

    # Also include trades that check_trades skipped (non-open)
    checked_ids = {r["trade"]["trade_id"] for r in trade_results}
    extra = [t for t in trader._trades if t["trade_id"] not in checked_ids]
    if extra:
        with open(path, "a", newline="") as f:
            writer = csv.writer(f)
            for t in extra:
                writer.writerow([
                    t["trade_id"],
                    t["timestamp"],
                    t["market_id"],
                    t["market_title"],
                    t["headline"],
                    t["direction"],
                    t["entry_price"],
                    "",
                    t["shares"],
                    "",
                    "",
                    "",
                    t["embedding_score"],
                    t["llm_confidence"],
                    t["llm_reasoning"],
                    t.get("status", ""),
                ])

    total = len(trade_results) + len(extra)
    print(f"  trades.csv     — {total} rows")
    return path


def main():
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(name)s %(levelname)s  %(message)s",
        datefmt="%H:%M:%S",
    )

    print()
    print("=" * 60)
    print("  Polymarket Signal Chaser — CSV Export")
    print("=" * 60)

    # Load all data
    market_store = MarketStore()
    market_store.load()

    signal_store = SignalStore()
    signal_store.load()

    matches = _load_match_log()

    signal_store_for_engine = SignalStore()
    engine = MatchEngine(market_store, signal_store_for_engine)
    trader = PaperTrader(market_store, engine)
    trader.load_trades()

    trade_keys = {(t["market_id"], t["headline"]) for t in trader._trades}

    # Write CSVs
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\n  Writing to {DATA_DIR}/\n")

    export_markets(market_store, DATA_DIR)
    export_signals(signal_store, DATA_DIR)
    export_matches(matches, trade_keys, DATA_DIR)
    export_trades(trader, DATA_DIR)

    print(f"\n  Done. All CSVs written to {DATA_DIR}/")
    print()


if __name__ == "__main__":
    main()
