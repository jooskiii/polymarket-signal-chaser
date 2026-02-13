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

    def load_cache(self):
        """Load cached embeddings and index from disk. Returns True if cache exists."""
        if self._embeddings_path.exists() and self._index_path.exists():
            logger.info("Loading cached market embeddings from %s", self._embeddings_path)
            self._embeddings = np.load(self._embeddings_path)
            with open(self._index_path, "r") as f:
                self._index_map = json.load(f)
            logger.info("Loaded %d cached market embeddings", len(self._index_map))
            return True
        return False

    def build_market_index(self, markets):
        """Encode all market questions and cache to disk.

        Args:
            markets: List of market dicts with at least a 'question' field.
        """
        if self.load_cache() and len(self._index_map) == len(markets):
            logger.info("Cache is up to date, skipping recomputation")
            return

        model = self._get_model()
        texts = []
        for m in markets:
            question = m.get("question", "")
            description = m.get("description", "")
            texts.append(f"{question} {description}".strip())

        logger.info("Encoding %d market titles/descriptions...", len(texts))
        self._embeddings = model.encode(texts, show_progress_bar=True, convert_to_numpy=True)
        self._index_map = markets

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        np.save(self._embeddings_path, self._embeddings)
        with open(self._index_path, "w") as f:
            json.dump(self._index_map, f)
        logger.info("Saved market embeddings to %s", self._embeddings_path)

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
