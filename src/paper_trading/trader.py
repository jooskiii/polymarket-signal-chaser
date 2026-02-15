"""Paper trading engine — logs simulated trades and evaluates P&L."""

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.market import ClobClient, MarketStore
from src.matching import MatchEngine

logger = logging.getLogger(__name__)

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
TRADES_FILENAME = "paper_trades.json"
POSITION_SIZE_USD = 25.0
CONFIDENCE_THRESHOLD = 0.6


class PaperTrader:
    """Logs and evaluates paper trades based on match engine signals."""

    def __init__(self, market_store, match_engine, data_dir=None):
        self.market_store = market_store
        self.match_engine = match_engine
        self.clob = ClobClient()
        self.data_dir = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
        self.trades_path = self.data_dir / TRADES_FILENAME
        self._trades = []

    # ── Persistence ──────────────────────────────────────────────────

    def load_trades(self):
        """Load existing paper trades from disk."""
        if not self.trades_path.exists():
            self._trades = []
            return self._trades
        with open(self.trades_path, "r") as f:
            data = json.load(f)
        self._trades = data.get("trades", [])
        return self._trades

    def _save_trades(self):
        """Persist paper trades to disk."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "count": len(self._trades),
            "trades": self._trades,
        }
        with open(self.trades_path, "w") as f:
            json.dump(payload, f, indent=2, default=str)

    # ── Log trades ───────────────────────────────────────────────────

    def log_trades(self):
        """Run the match engine and log paper trades for high-confidence signals.

        Returns:
            List of newly created trade dicts.
        """
        self.load_trades()
        results = self.match_engine.run()

        # De-duplicate against existing trades
        existing_keys = {(t["market_id"], t["headline"]) for t in self._trades}

        new_trades = []
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

            if (market_id, headline) in existing_keys:
                continue

            # Entry price from order book
            token_id = self._get_token_id(market, direction)
            entry_price = None
            if token_id:
                entry_price = self._compute_entry_price(token_id)

            # Fallback to cached outcomePrices
            if entry_price is None:
                entry_price = self._get_outcome_price(market, direction)

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

        if new_trades:
            self._save_trades()

        return new_trades

    # ── Check trades ─────────────────────────────────────────────────

    def check_trades(self):
        """Evaluate all open paper trades against current market prices.

        Returns:
            List of dicts with trade details, current price, P&L, and time held.
        """
        self.load_trades()
        self.market_store.load()

        # Build lookup by market ID for fast access
        market_lookup = {}
        for m in self.market_store.markets:
            mid = m.get("id", m.get("conditionId"))
            if mid:
                market_lookup[mid] = m

        results = []
        for trade in self._trades:
            if trade.get("status") != "open":
                continue

            current_price = None

            # Try MarketStore cached prices first
            market = market_lookup.get(trade["market_id"])
            if market:
                current_price = self._get_outcome_price(market, trade["direction"])

            # Fallback to live CLOB midpoint
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
            held = datetime.now(timezone.utc) - trade_time

            results.append({
                "trade": trade,
                "current_price": round(current_price, 4),
                "pnl_usd": round(pnl_usd, 2),
                "pnl_pct": round(pnl_pct, 2),
                "time_held": held,
            })

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
        """Walk the order book asks to compute fill price for a $25 position."""
        try:
            book = self.clob.get_order_book(token_id)
        except Exception as e:
            logger.warning("Failed to fetch order book for %s: %s", token_id, e)
            return None

        asks = book.get("asks", [])
        if not asks:
            return None

        asks = sorted(asks, key=lambda a: float(a["price"]))

        total_cost = 0.0
        total_shares = 0.0
        remaining = POSITION_SIZE_USD

        for ask in asks:
            price = float(ask["price"])
            size = float(ask["size"])
            if price <= 0:
                continue

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
            return None
        return total_cost / total_shares

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
