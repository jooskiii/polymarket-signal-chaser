"""Paper trading engine — logs simulated trades and evaluates P&L."""

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.market import ClobClient, MarketStore
from src.matching import MatchEngine

logger = logging.getLogger(__name__)

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
TRADES_FILENAME = "paper_trades.json"
POSITION_SIZE_USD = 25.0
CONFIDENCE_THRESHOLD = 0.6
LIQUIDITY_SPREAD_LIMIT = 0.05   # only fill asks within 5% of midpoint
TAKE_PROFIT_PCT = 3.0           # close at +3%
STOP_LOSS_PCT = 5.0             # close at -5%
MIN_HOLD_FOR_TP = timedelta(minutes=15)
MAX_HOLD_TIME = timedelta(hours=2)


class PaperTrader:
    """Logs and evaluates paper trades based on match engine signals."""

    def __init__(self, market_store, match_engine, data_dir=None):
        self.market_store = market_store
        self.match_engine = match_engine
        self.clob = ClobClient()
        self.data_dir = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
        self.trades_path = self.data_dir / TRADES_FILENAME
        self._trades = []
        self._skipped = []

    # ── Persistence ──────────────────────────────────────────────────

    def load_trades(self):
        """Load existing paper trades from disk."""
        if not self.trades_path.exists():
            self._trades = []
            self._skipped = []
            return self._trades
        with open(self.trades_path, "r") as f:
            data = json.load(f)
        self._trades = data.get("trades", [])
        self._skipped = data.get("skipped_trades", [])
        return self._trades

    def _save_trades(self):
        """Persist paper trades and skipped entries to disk."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "count": len(self._trades),
            "trades": self._trades,
            "skipped_count": len(self._skipped),
            "skipped_trades": self._skipped,
        }
        with open(self.trades_path, "w") as f:
            json.dump(payload, f, indent=2, default=str)

    # ── Log trades ───────────────────────────────────────────────────

    def log_trades(self):
        """Run the match engine and log paper trades for high-confidence signals.

        Returns:
            (new_trades, new_skipped) — lists of newly created and skipped entries.
        """
        self.load_trades()
        results = self.match_engine.run()

        existing_keys = {(t["market_id"], t["headline"]) for t in self._trades}
        skipped_keys = {(s["market_id"], s["headline"]) for s in self._skipped}

        new_trades = []
        new_skipped = []
        for result in results:
            llm = result.get("llm_assessment")
            if not llm or not llm.get("relevant"):
                continue
            if (llm.get("confidence") or 0) < CONFIDENCE_THRESHOLD:
                continue

            market = result["market"]
            headline = result["headline"]["title"]
            direction = llm["direction"]
            market_id = market.get("id", market.get("conditionId", "unknown"))

            if (market_id, headline) in existing_keys or (market_id, headline) in skipped_keys:
                continue

            # Entry price via VWAP from order book
            token_id = self._get_token_id(market, direction)
            entry_price, skip_reason = self._compute_entry_price(token_id)

            # Fallback to cached outcomePrices (only if order book was unavailable,
            # NOT if liquidity was insufficient — that's a real skip)
            if entry_price is None and skip_reason != "insufficient_liquidity":
                fallback = self._get_outcome_price(market, direction)
                if fallback and fallback > 0:
                    entry_price = fallback
                    skip_reason = None

            if skip_reason == "insufficient_liquidity":
                skip_entry = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "market_id": market_id,
                    "market_title": market.get("question", ""),
                    "headline": headline,
                    "direction": direction,
                    "reason": "insufficient_liquidity",
                    "embedding_score": result["embedding_score"],
                    "llm_confidence": llm["confidence"],
                }
                new_skipped.append(skip_entry)
                self._skipped.append(skip_entry)
                skipped_keys.add((market_id, headline))
                logger.info("Skipped — insufficient liquidity: %s", market.get("question", ""))
                continue

            if entry_price is None or entry_price <= 0:
                logger.warning("Could not determine entry price for market %s — skipping", market_id)
                continue

            trade = {
                "trade_id": str(uuid.uuid4())[:8],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "market_id": market_id,
                "market_title": market.get("question", ""),
                "headline": headline,
                "direction": direction,
                "entry_price": round(entry_price, 4),
                "position_size_usd": POSITION_SIZE_USD,
                "shares": round(POSITION_SIZE_USD / entry_price, 4),
                "embedding_score": result["embedding_score"],
                "llm_confidence": llm["confidence"],
                "llm_reasoning": llm.get("reasoning", ""),
                "token_id": token_id,
                "status": "open",
            }

            new_trades.append(trade)
            self._trades.append(trade)
            existing_keys.add((market_id, headline))

        if new_trades or new_skipped:
            self._save_trades()

        return new_trades, new_skipped

    # ── Check trades ─────────────────────────────────────────────────

    def check_trades(self):
        """Evaluate all paper trades. Closes open trades that hit exit conditions.

        Returns:
            List of dicts with trade details, current price, P&L, and time held
            for ALL trades (open and closed).
        """
        self.load_trades()
        self.market_store.load()

        market_lookup = {}
        for m in self.market_store.markets:
            mid = m.get("id", m.get("conditionId"))
            if mid:
                market_lookup[mid] = m

        results = []
        changed = False
        now = datetime.now(timezone.utc)

        for trade in self._trades:
            # Already closed — return stored exit data
            if trade.get("status") == "closed":
                results.append({
                    "trade": trade,
                    "current_price": trade.get("exit_price", trade["entry_price"]),
                    "pnl_usd": trade.get("final_pnl_usd", 0),
                    "pnl_pct": trade.get("final_pnl_pct", 0),
                    "time_held": timedelta(seconds=trade.get("hold_duration_seconds", 0)),
                })
                continue

            # Open trade — fetch current price
            current_price = None
            market = market_lookup.get(trade["market_id"])
            if market:
                current_price = self._get_outcome_price(market, trade["direction"])
            if current_price is None and trade.get("token_id"):
                try:
                    mid_data = self.clob.get_midpoint(trade["token_id"])
                    current_price = float(mid_data.get("mid", 0))
                except Exception:
                    pass
            if current_price is None or current_price <= 0:
                current_price = trade["entry_price"]  # can't price — assume flat

            entry = trade["entry_price"]
            shares = trade["shares"]
            pnl_usd = (current_price - entry) * shares
            pnl_pct = ((current_price - entry) / entry) * 100 if entry > 0 else 0

            trade_time = datetime.fromisoformat(trade["timestamp"])
            held = now - trade_time

            # ── Exit conditions (checked in priority order) ──────
            exit_reason = None
            if pnl_pct <= -STOP_LOSS_PCT:
                exit_reason = "stop_loss"
            elif pnl_pct >= TAKE_PROFIT_PCT and held >= MIN_HOLD_FOR_TP:
                exit_reason = "take_profit"
            elif held >= MAX_HOLD_TIME:
                exit_reason = "time_expired"

            if exit_reason:
                trade["status"] = "closed"
                trade["exit_price"] = round(current_price, 4)
                trade["exit_timestamp"] = now.isoformat()
                trade["exit_reason"] = exit_reason
                trade["final_pnl_usd"] = round(pnl_usd, 2)
                trade["final_pnl_pct"] = round(pnl_pct, 2)
                trade["hold_duration_seconds"] = int(held.total_seconds())
                changed = True
                logger.info(
                    "Closed trade %s — %s (P&L: $%.2f / %.2f%%)",
                    trade["trade_id"], exit_reason, pnl_usd, pnl_pct,
                )

            results.append({
                "trade": trade,
                "current_price": round(current_price, 4),
                "pnl_usd": round(pnl_usd, 2),
                "pnl_pct": round(pnl_pct, 2),
                "time_held": held,
            })

        if changed:
            self._save_trades()

        return results

    # ── Internal helpers ─────────────────────────────────────────────

    def _get_token_id(self, market, direction):
        """Get the CLOB token ID for the given direction (YES/NO)."""
        outcomes = market.get("outcomes", [])
        token_ids = market.get("clobTokenIds", [])
        for i, outcome in enumerate(outcomes):
            if str(outcome).upper() == direction.upper() and i < len(token_ids):
                return token_ids[i]
        return None

    def _compute_entry_price(self, token_id):
        """Compute VWAP for a $25 order, only filling asks within 5% of midpoint.

        Returns:
            (vwap, None) on success, or (None, reason_string) on failure.
        """
        if not token_id:
            return None, "no_token_id"

        try:
            book = self.clob.get_order_book(token_id)
        except Exception as e:
            logger.warning("Failed to fetch order book for %s: %s", token_id, e)
            return None, "order_book_error"

        asks = book.get("asks", [])
        if not asks:
            return None, "no_asks"

        # Determine midpoint for liquidity band
        try:
            mid_data = self.clob.get_midpoint(token_id)
            midpoint = float(mid_data.get("mid", 0))
        except Exception:
            midpoint = 0

        if midpoint <= 0:
            bids = book.get("bids", [])
            if bids and asks:
                best_ask = min(float(a["price"]) for a in asks)
                best_bid = max(float(b["price"]) for b in bids)
                midpoint = (best_ask + best_bid) / 2
            elif asks:
                midpoint = float(min(asks, key=lambda a: float(a["price"]))["price"])
            else:
                return None, "no_midpoint"

        max_price = midpoint * (1 + LIQUIDITY_SPREAD_LIMIT)
        asks = sorted(asks, key=lambda a: float(a["price"]))

        total_cost = 0.0
        total_shares = 0.0
        remaining = POSITION_SIZE_USD

        for ask in asks:
            price = float(ask["price"])
            size = float(ask["size"])
            if price <= 0:
                continue
            if price > max_price:
                break  # outside 5% band

            cost_at_level = price * size
            if cost_at_level <= remaining:
                total_cost += cost_at_level
                total_shares += size
                remaining -= cost_at_level
            else:
                shares_at_level = remaining / price
                total_cost += remaining
                total_shares += shares_at_level
                remaining = 0
                break

        if total_shares == 0:
            return None, "insufficient_liquidity"

        if remaining > 0:
            # Could not fill the full $25 within the liquidity band
            return None, "insufficient_liquidity"

        return total_cost / total_shares, None

    def _get_outcome_price(self, market, direction):
        """Get the price for a direction from the market's outcomePrices."""
        outcomes = market.get("outcomes", [])
        prices = market.get("outcomePrices", [])
        for outcome, price in zip(outcomes, prices):
            if str(outcome).upper() == direction.upper():
                try:
                    return float(price)
                except (ValueError, TypeError):
                    return None
        return None
