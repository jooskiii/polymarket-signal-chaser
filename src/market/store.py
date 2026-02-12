import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from .gamma_client import GammaClient

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[2] / "data"
CACHE_FILENAME = "markets.json"


class MarketStore:
    """Local JSON cache of active Polymarket markets."""

    def __init__(self, cache_dir=None, gamma_client=None):
        self.cache_dir = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
        self.cache_path = self.cache_dir / CACHE_FILENAME
        self.gamma = gamma_client or GammaClient()
        self._markets = []

    # ── Public API ──────────────────────────────────────────────────

    def refresh(self):
        """Fetch all active markets from Gamma and write to the local cache."""
        logger.info("Fetching active markets from Gamma API...")
        self._markets = self.gamma.fetch_all_active_markets()
        self._save()
        logger.info("Cached %d markets to %s", len(self._markets), self.cache_path)
        return self._markets

    def load(self):
        """Load markets from the local JSON cache file."""
        if not self.cache_path.exists():
            logger.warning("No cache file at %s — call refresh() first", self.cache_path)
            return []
        with open(self.cache_path, "r") as f:
            data = json.load(f)
        self._markets = data.get("markets", [])
        logger.info(
            "Loaded %d markets from cache (updated %s)",
            len(self._markets),
            data.get("updated_at", "unknown"),
        )
        return self._markets

    @property
    def markets(self):
        return list(self._markets)

    @property
    def count(self):
        return len(self._markets)

    def get_top_by_volume(self, n=10):
        """Return the top N markets sorted by volume descending."""
        return sorted(
            self._markets,
            key=lambda m: m.get("volumeNum", 0),
            reverse=True,
        )[:n]

    # ── Internal ────────────────────────────────────────────────────

    def _save(self):
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "count": len(self._markets),
            "markets": self._markets,
        }
        with open(self.cache_path, "w") as f:
            json.dump(payload, f, indent=2, default=str)
