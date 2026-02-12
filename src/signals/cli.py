"""CLI entry point for the signal ingestion layer.

Usage:
    python -m src.signals.cli            # fetch fresh headlines and print summary
    python -m src.signals.cli --cached   # use local cache only
"""

import argparse
import sys

from .rss import RSSSignalSource
from .store import SignalStore


def main():
    parser = argparse.ArgumentParser(description="Polymarket signal headline fetcher")
    parser.add_argument(
        "--cached",
        action="store_true",
        help="Use locally cached headlines instead of fetching fresh data",
    )
    args = parser.parse_args()

    store = SignalStore(sources=[RSSSignalSource()])

    if args.cached:
        store.load()
        if not store.count:
            print("No cached headlines found. Run without --cached to fetch fresh data.")
            sys.exit(1)
        print(f"\nLoaded {store.count} cached headlines")
    else:
        new_count = store.refresh()
        print(f"\nFetched {new_count} new headlines ({store.count} total)")

    print()
    print("=" * 80)
    print("5 most recent headlines:")
    print("=" * 80)

    for i, h in enumerate(store.get_most_recent(5), 1):
        print(f"\n{i}. [{h['source']}] {h['title']}")
        print(f"   Published: {h['published']}")
        print(f"   {h['url']}")

    print()


if __name__ == "__main__":
    main()
