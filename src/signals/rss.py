import logging
import time
from datetime import datetime, timezone

import feedparser

from .base import SignalSource

logger = logging.getLogger(__name__)

# Feed list carried over from polymarket_default_detector.py
DEFAULT_FEEDS = {
    "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "Billboard": "https://www.billboard.com/feed/",
    "Box Office Mojo": "https://www.boxofficemojo.com/feed/",
    "Variety": "https://variety.com/feed/",
    "ESPN": "https://www.espn.com/espn/rss/news",
    "Bleacher Report": "https://bleacherreport.com/articles/feed",
    "Hollywood Reporter": "https://www.hollywoodreporter.com/feed/",
    "TMZ": "https://www.tmz.com/rss.xml",
    "Reuters Breaking": "https://www.reuters.com/rssfeed/breakingviews",
}


class RSSSignalSource(SignalSource):
    """Fetches headlines from a set of RSS feeds."""

    def __init__(self, feeds=None, delay=0.5):
        self.feeds = feeds or dict(DEFAULT_FEEDS)
        self.delay = delay

    def fetch(self):
        """Fetch all feeds and return a flat list of headline dicts."""
        headlines = []
        for source_name, url in self.feeds.items():
            logger.debug("Fetching %s", source_name)
            headlines.extend(self._parse_feed(url, source_name))
            if self.delay:
                time.sleep(self.delay)
        return headlines

    # ── internals (lifted from polymarket_default_detector.py) ──────

    def _parse_feed(self, url, source_name):
        try:
            feed = feedparser.parse(url)
            articles = []
            for entry in feed.entries:
                articles.append(
                    {
                        "title": entry.get("title", ""),
                        "url": entry.get("link", ""),
                        "published": self._parse_timestamp(entry),
                        "summary": entry.get("summary", ""),
                        "source": source_name,
                    }
                )
            return articles
        except Exception as e:
            logger.warning("Error parsing %s: %s", source_name, e)
            return []

    @staticmethod
    def _parse_timestamp(entry):
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).isoformat()
        return datetime.now(timezone.utc).isoformat()
