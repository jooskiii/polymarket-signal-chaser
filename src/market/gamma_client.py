import json
import logging

import requests

logger = logging.getLogger(__name__)

GAMMA_BASE_URL = "https://gamma-api.polymarket.com"
DEFAULT_PAGE_SIZE = 100


class GammaClient:
    """Client for the Polymarket Gamma API (read-only market metadata)."""

    def __init__(self, base_url=GAMMA_BASE_URL):
        self.base_url = base_url
        self.session = requests.Session()

    def fetch_markets(self, limit=DEFAULT_PAGE_SIZE, offset=0, **params):
        """Fetch a single page of markets from the Gamma API."""
        url = f"{self.base_url}/markets"
        params.update({"limit": limit, "offset": offset})
        resp = self.session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def fetch_all_active_markets(self):
        """Fetch all active, non-closed markets with automatic pagination."""
        all_markets = []
        offset = 0

        while True:
            page = self.fetch_markets(
                limit=DEFAULT_PAGE_SIZE,
                offset=offset,
                active="true",
                closed="false",
            )
            if not page:
                break

            all_markets.extend(page)
            logger.debug("Fetched %d markets (offset=%d)", len(page), offset)

            if len(page) < DEFAULT_PAGE_SIZE:
                break
            offset += DEFAULT_PAGE_SIZE

        return [_parse_market(m) for m in all_markets]


def _parse_market(raw):
    """Normalise a raw Gamma market dict, parsing stringified JSON fields."""
    market = dict(raw)

    for field in ("outcomes", "outcomePrices", "clobTokenIds"):
        val = market.get(field)
        if isinstance(val, str):
            try:
                market[field] = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                market[field] = []

    # Ensure volumeNum is a float for sorting
    if "volumeNum" in market:
        try:
            market["volumeNum"] = float(market["volumeNum"])
        except (ValueError, TypeError):
            market["volumeNum"] = 0.0

    return market
