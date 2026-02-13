"""CLI entry point for the matching engine.

Usage:
    python -m src.matching.cli
"""

import logging
import sys

from src.market import MarketStore
from src.signals import SignalStore
from .engine import MatchEngine


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s  %(message)s",
        datefmt="%H:%M:%S",
    )

    print("=" * 60)
    print("Phase 3 — Matching Engine")
    print("=" * 60)

    # Load cached data
    market_store = MarketStore()
    market_store.load()
    print(f"Loaded {market_store.count} markets from cache")

    signal_store = SignalStore()
    signal_store.load()
    print(f"Loaded {signal_store.count} headlines from cache")

    if market_store.count == 0:
        print("No markets cached. Run `python -m src.market.cli` first.")
        sys.exit(1)
    if signal_store.count == 0:
        print("No headlines cached. Run `python -m src.signals.cli` first.")
        sys.exit(1)

    # Run matching
    engine = MatchEngine(market_store, signal_store)
    results = engine.run()

    # Report
    print()
    print("=" * 60)
    print("Results")
    print("=" * 60)

    headlines_checked = len(signal_store.get_most_recent(20))
    confirmed = [r for r in results if r["llm_assessment"] and r["llm_assessment"].get("relevant")]

    print(f"Headlines checked:    {headlines_checked}")
    print(f"Embedding candidates: {len(results)}")
    print(f"LLM confirmed:       {len(confirmed)}")

    if not results:
        print("\nNo matches found above the similarity threshold.")
        return

    print()
    for i, r in enumerate(results, 1):
        headline = r["headline"]["title"]
        market_q = r["market"]["question"]
        score = r["embedding_score"]
        llm = r["llm_assessment"]

        print(f"--- Match {i} ---")
        print(f"  Headline: {headline}")
        print(f"  Market:   {market_q}")
        print(f"  Cosine:   {score:.4f}")
        if llm:
            print(f"  Relevant: {llm.get('relevant')}")
            print(f"  Direction:{llm.get('direction')}")
            print(f"  Confidence:{llm.get('confidence')}")
            print(f"  Reasoning: {llm.get('reasoning')}")
        else:
            print("  LLM:      (skipped or failed)")
        print()


if __name__ == "__main__":
    main()
