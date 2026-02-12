import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from .base import SignalSource

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[2] / "data"
CACHE_FILENAME = "headlines.json"


class SignalStore:
    """Collects headlines from multiple SignalSources, deduplicates by URL,
    and persists them to a local JSON file."""

    def __init__(self, sources=None, cache_dir=None):
        self.sources = list(sources or [])
        self.cache_dir = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
        self.cache_path = self.cache_dir / CACHE_FILENAME
        self._headlines = {}  # url -> headline dict

    def add_source(self, source):
        if not isinstance(source, SignalSource):
            raise TypeError(f"Expected SignalSource, got {type(source).__name__}")
        self.sources.append(source)

    # ── Public API ──────────────────────────────────────────────────

    def refresh(self):
        """Fetch from all sources, deduplicate, merge with cache, and save.

        Returns the number of *new* headlines added this refresh.
        """
        self.load()
        before = len(self._headlines)

        for source in self.sources:
            for h in source.fetch():
                url = h.get("url")
                if not url or url in self._headlines:
                    continue
                h["fetched_at"] = datetime.now(timezone.utc).isoformat()
                self._headlines[url] = h

        new_count = len(self._headlines) - before
        self._save()
        logger.info("Added %d new headlines (%d total)", new_count, len(self._headlines))
        return new_count

    def load(self):
        """Load previously cached headlines from disk."""
        if not self.cache_path.exists():
            return
        with open(self.cache_path, "r") as f:
            data = json.load(f)
        for h in data.get("headlines", []):
            url = h.get("url")
            if url:
                self._headlines[url] = h

    @property
    def count(self):
        return len(self._headlines)

    @property
    def headlines(self):
        return list(self._headlines.values())

    def get_most_recent(self, n=5):
        """Return the N most recently published headlines."""
        return sorted(
            self._headlines.values(),
            key=lambda h: h.get("published", ""),
            reverse=True,
        )[:n]

    # ── Internal ────────────────────────────────────────────────────

    def _save(self):
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "count": len(self._headlines),
            "headlines": list(self._headlines.values()),
        }
        with open(self.cache_path, "w") as f:
            json.dump(payload, f, indent=2, default=str)
