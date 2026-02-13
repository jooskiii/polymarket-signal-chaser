"""MatchEngine — orchestrates embedding similarity + LLM assessment pipeline."""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import dotenv_values

from .embeddings import EmbeddingIndex
from .llm import assess_match

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[2] / "data"


class MatchEngine:
    """Two-stage matching: embedding cosine similarity then LLM validation."""

    def __init__(self, market_store, signal_store, similarity_threshold=0.65):
        self.market_store = market_store
        self.signal_store = signal_store
        self.similarity_threshold = similarity_threshold
        self._embedding_index = EmbeddingIndex()
        self._api_key = self._load_api_key()
        self._match_log_path = DEFAULT_CACHE_DIR / "match_log.json"

    def _load_api_key(self):
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            env_path = Path(__file__).resolve().parents[2] / ".env"
            vals = dotenv_values(env_path)
            key = vals.get("ANTHROPIC_API_KEY")
        if not key:
            logger.warning("ANTHROPIC_API_KEY not found — LLM assessment will be skipped")
        return key

    def run(self, headlines=None):
        """Run the full matching pipeline.

        Args:
            headlines: Optional list of headline dicts. Defaults to 20 most recent.

        Returns:
            List of match result dicts.
        """
        # Stage 0: load data
        markets = self.market_store.markets
        if not markets:
            self.market_store.load()
            markets = self.market_store.markets

        if headlines is None:
            if not self.signal_store.headlines:
                self.signal_store.load()
            headlines = self.signal_store.get_most_recent(20)

        logger.info("Running match engine: %d headlines against %d markets", len(headlines), len(markets))

        # Stage 1: build / load embedding index
        self._embedding_index.build_market_index(markets)

        results = []
        total_candidates = 0

        for headline in headlines:
            title = headline.get("title", "")
            candidates = self._embedding_index.find_matches(title, threshold=self.similarity_threshold)
            total_candidates += len(candidates)

            for market, score in candidates:
                market_question = market.get("question", "?")
                outcomes = market.get("outcomes", [])
                prices = market.get("outcomePrices", [])
                market_state = ", ".join(
                    f"{o}={p}" for o, p in zip(outcomes, prices)
                ) or "N/A"

                logger.info(
                    "MATCH CHAIN | headline=%r | embedding_score=%.4f | market=%r | prices=[%s]",
                    title, score, market_question, market_state,
                )

                result = {
                    "headline": headline,
                    "market": market,
                    "embedding_score": round(score, 4),
                    "llm_assessment": None,
                    "matched_at": datetime.now(timezone.utc).isoformat(),
                }

                # Stage 2: LLM assessment
                if self._api_key:
                    assessment = assess_match(headline, market, self._api_key)
                    result["llm_assessment"] = assessment
                    logger.info(
                        "MATCH CHAIN | headline=%r | market=%r | llm_response=%s",
                        title, market_question, assessment,
                    )

                results.append(result)

        logger.info(
            "Matching complete: %d headlines, %d candidates, %d results",
            len(headlines), total_candidates, len(results),
        )

        self._save_log(results)
        return results

    def _save_log(self, results):
        """Persist match results to disk."""
        log_data = {
            "run_at": datetime.now(timezone.utc).isoformat(),
            "count": len(results),
            "matches": results,
        }
        self._match_log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._match_log_path, "w") as f:
            json.dump(log_data, f, indent=2, default=str)
        logger.info("Saved match log to %s", self._match_log_path)
