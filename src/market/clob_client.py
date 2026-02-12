import logging

import requests

logger = logging.getLogger(__name__)

CLOB_BASE_URL = "https://clob.polymarket.com"


class ClobClient:
    """Client for the Polymarket CLOB API (read-only pricing & order books)."""

    def __init__(self, base_url=CLOB_BASE_URL):
        self.base_url = base_url
        self.session = requests.Session()

    # ── Single-token endpoints ──────────────────────────────────────

    def get_order_book(self, token_id):
        """Fetch the full order book for a token."""
        resp = self.session.get(
            f"{self.base_url}/book",
            params={"token_id": token_id},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def get_price(self, token_id, side="BUY"):
        """Fetch the best price for a token on the given side (BUY/SELL)."""
        resp = self.session.get(
            f"{self.base_url}/price",
            params={"token_id": token_id, "side": side},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def get_midpoint(self, token_id):
        """Fetch the midpoint price for a token."""
        resp = self.session.get(
            f"{self.base_url}/midpoint",
            params={"token_id": token_id},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def get_spread(self, token_id):
        """Fetch the bid-ask spread for a token."""
        resp = self.session.get(
            f"{self.base_url}/spread",
            params={"token_id": token_id},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def get_last_trade_price(self, token_id):
        """Fetch the last traded price for a token."""
        resp = self.session.get(
            f"{self.base_url}/last-trade-price",
            params={"token_id": token_id},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    # ── Batch endpoints ─────────────────────────────────────────────

    def get_midpoints(self, token_ids):
        """Batch-fetch midpoint prices for multiple tokens."""
        resp = self.session.post(
            f"{self.base_url}/midpoints",
            json=[{"token_id": tid} for tid in token_ids],
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def get_order_books(self, token_ids):
        """Batch-fetch order books for multiple tokens."""
        resp = self.session.post(
            f"{self.base_url}/books",
            json=[{"token_id": tid} for tid in token_ids],
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
