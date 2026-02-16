"""Embedding index for semantic matching between headlines and markets."""

import json
import logging
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer, util

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[2] / "data"
MODEL_NAME = "all-MiniLM-L6-v2"


class EmbeddingIndex:
    """Builds and queries a semantic embedding index over Polymarket markets."""

    def __init__(self, cache_dir=None):
        self.cache_dir = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
        self._embeddings_path = self.cache_dir / "market_embeddings.npy"
        self._index_path = self.cache_dir / "market_index.json"
        self._model = None
        self._embeddings = None
        self._index_map = []  # list of market dicts, position matches embedding row

    def _get_model(self):
        if self._model is None:
            logger.info("Loading sentence-transformers model: %s", MODEL_NAME)
            self._model = SentenceTransformer(MODEL_NAME)
        return self._model

    def _load_cache(self):
        """Load cached embeddings and index from disk. Returns True if cache exists."""
        if self._embeddings_path.exists() and self._index_path.exists():
            logger.info("Loading cached market embeddings from %s", self._embeddings_path)
            self._embeddings = np.load(self._embeddings_path)
            with open(self._index_path, "r") as f:
                self._index_map = json.load(f)
            logger.info("Loaded %d cached market embeddings", len(self._index_map))
            return True
        return False

    def _save_cache(self):
        """Persist embeddings and index map to disk."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        np.save(self._embeddings_path, self._embeddings)
        with open(self._index_path, "w") as f:
            json.dump(self._index_map, f)
        logger.info("Saved %d market embeddings to %s", len(self._index_map), self._embeddings_path)

    @staticmethod
    def _market_id(market):
        return market.get("id", market.get("conditionId", ""))

    def build_market_index(self, markets):
        """Encode market questions and cache to disk.

        Only encodes new markets that aren't already cached, and prunes
        closed markets that are no longer in the incoming list.

        Args:
            markets: List of market dicts with at least a 'question' field.
        """
        has_cache = self._load_cache()

        if has_cache:
            # Build lookup: cached market_id -> row index
            cached_id_to_row = {}
            for i, m in enumerate(self._index_map):
                mid = self._market_id(m)
                if mid:
                    cached_id_to_row[mid] = i

            # Split incoming markets into reusable (cached) and new
            reuse_rows = []
            reuse_markets = []
            new_markets = []

            for m in markets:
                mid = self._market_id(m)
                if mid in cached_id_to_row:
                    reuse_rows.append(cached_id_to_row[mid])
                    reuse_markets.append(m)
                else:
                    new_markets.append(m)

            if not new_markets and len(reuse_rows) == len(cached_id_to_row):
                logger.info("Cache is up to date (%d markets), skipping recomputation", len(markets))
                return

            if not new_markets:
                # Only need to prune closed markets
                self._embeddings = self._embeddings[reuse_rows]
                self._index_map = reuse_markets
                self._save_cache()
                pruned = len(cached_id_to_row) - len(reuse_rows)
                logger.info("Pruned %d closed markets (%d remaining)", pruned, len(reuse_markets))
                return

            # Encode only new markets
            logger.info(
                "Incremental update: encoding %d new markets (reusing %d cached)",
                len(new_markets), len(reuse_rows),
            )
            model = self._get_model()
            new_texts = [
                f"{m.get('question', '')} {m.get('description', '')}".strip()
                for m in new_markets
            ]
            new_embeddings = model.encode(new_texts, show_progress_bar=True, convert_to_numpy=True)

            # Merge: reused cached embeddings + newly encoded
            cached_part = self._embeddings[reuse_rows]
            self._embeddings = np.vstack([cached_part, new_embeddings])
            self._index_map = reuse_markets + new_markets
            self._save_cache()
            return

        # No cache at all — full encode
        model = self._get_model()
        texts = [
            f"{m.get('question', '')} {m.get('description', '')}".strip()
            for m in markets
        ]
        logger.info("Encoding %d market titles/descriptions...", len(texts))
        self._embeddings = model.encode(texts, show_progress_bar=True, convert_to_numpy=True)
        self._index_map = markets
        self._save_cache()

    def find_matches(self, headline_text, threshold=0.65):
        """Find markets semantically similar to a headline.

        Args:
            headline_text: The headline string to match against.
            threshold: Minimum cosine similarity score.

        Returns:
            List of (market_dict, score) tuples sorted by score descending.
        """
        if self._embeddings is None or len(self._index_map) == 0:
            logger.warning("No market embeddings loaded — call build_market_index first")
            return []

        model = self._get_model()
        headline_embedding = model.encode(headline_text, convert_to_numpy=True)

        scores = util.cos_sim(headline_embedding, self._embeddings)[0].numpy()

        matches = []
        for idx in np.where(scores >= threshold)[0]:
            matches.append((self._index_map[idx], float(scores[idx])))

        matches.sort(key=lambda x: x[1], reverse=True)
        return matches
