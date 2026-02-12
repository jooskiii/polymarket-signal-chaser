"""CLI entry point for the market data layer.

Usage:
    python -m src.market.cli            # fetch fresh data and print summary
    python -m src.market.cli --cached   # use local cache only
"""

import argparse
import sys

from .store import MarketStore


def _format_volume(vol):
    if vol >= 1_000_000:
        return f"${vol / 1_000_000:,.1f}M"
    if vol >= 1_000:
        return f"${vol / 1_000:,.1f}K"
    return f"${vol:,.0f}"


def _format_prices(outcomes, prices):
    if not outcomes or not prices:
        return "n/a"
    parts = []
    for outcome, price in zip(outcomes, prices):
        try:
            pct = float(price) * 100
            parts.append(f"{outcome}: {pct:.0f}¢")
        except (ValueError, TypeError):
            parts.append(f"{outcome}: ?")
    return " / ".join(parts)


def main():
    parser = argparse.ArgumentParser(description="Polymarket active markets summary")
    parser.add_argument(
        "--cached",
        action="store_true",
        help="Use locally cached data instead of fetching fresh data",
    )
    args = parser.parse_args()

    store = MarketStore()

    if args.cached:
        markets = store.load()
        if not markets:
            print("No cached data found. Run without --cached to fetch fresh data.")
            sys.exit(1)
    else:
        markets = store.refresh()

    print(f"\nThere are {store.count} active markets\n")
    print("=" * 80)
    print("Top 10 by volume:")
    print("=" * 80)

    for i, m in enumerate(store.get_top_by_volume(10), 1):
        question = m.get("question", m.get("title", "Untitled"))
        volume = m.get("volumeNum", 0)
        category = m.get("category", "—")
        outcomes = m.get("outcomes", [])
        prices = m.get("outcomePrices", [])

        print(f"\n{i:>2}. {question}")
        print(f"    Category: {category}")
        print(f"    Volume:   {_format_volume(volume)}")
        print(f"    Prices:   {_format_prices(outcomes, prices)}")

    print()


if __name__ == "__main__":
    main()
