# Polymarket Signal Chaser

Automated bot that monitors Polymarket prediction markets, ingests news headlines via RSS, matches them to markets using embedding similarity + LLM assessment, and executes simulated paper trades.

## Architecture

```
src/
  market/          MarketStore, GammaClient (metadata), ClobClient (order books/prices)
  signals/         SignalStore, RSS feed ingestion
  matching/        EmbeddingIndex (all-MiniLM-L6-v2), LLM assessment (Claude Haiku), MatchEngine
  paper_trading/   PaperTrader (VWAP entry, exit logic), log.py, check.py
  dashboard/       Terminal summary dashboard
  export/          CSV export (markets, signals, matches, trades)
```

## Key Parameters (src/paper_trading/trader.py)

- Position size: $25 per trade
- Confidence threshold: 0.6 (LLM must rate >= 0.6 to trigger trade)
- Embedding similarity threshold: 0.65 (src/matching/engine.py)
- VWAP entry: walks order book asks within 5% of midpoint
- Take profit: +3% (after 15 min hold minimum)
- Stop loss: -5%
- Max hold time: 2 hours

## Data Files (data/)

- `markets.json` — cached market data from Gamma API
- `headlines.json` — cached RSS headlines
- `market_embeddings.npy` / `market_ids.json` — incremental embedding cache
- `match_log.json` — all embedding+LLM match results
- `paper_trades.json` — all trades (open + closed) and skipped trades
- `llm_debug.log` — raw LLM responses for debugging

## Running the Bot

```bash
# Start continuous bot (5-min pipeline, 1-min trade checks)
nohup bash run.sh > run.log 2>&1 &

# Single pipeline run
bash run_once.sh

# Individual steps
python -m src.market.cli          # fetch markets
python -m src.signals.cli         # fetch headlines
python -m src.paper_trading.log   # run matching + log trades
python -m src.paper_trading.check # check P&L + close trades
python -m src.dashboard           # terminal dashboard
python -m src.export              # write CSVs to data/

# Monitor
tail -f run.log                   # follow live output
tail -100 run.log                 # last 100 lines
```

## Pipeline Flow

1. Fetch 28k+ active markets from Polymarket Gamma API
2. Scrape RSS feeds for latest headlines
3. Encode headlines + markets with sentence-transformers, cosine similarity filter (>= 0.65)
4. LLM assessment via Claude Haiku on embedding matches — returns relevance, direction, confidence
5. Log paper trades for high-confidence signals (>= 0.6), entry via VWAP from CLOB order book
6. Check open trades every minute: stop loss (-5%), take profit (+3% after 15min), time expiry (2hr)

## run.sh Loop Structure

- Full pipeline (fetch markets, headlines, match, log trades): every 5 minutes
- Trade check (price lookup + exit conditions): every 1 minute between pipelines

## Environment

- Python venv at `./venv/`
- Requires `.env` with `ANTHROPIC_API_KEY`
- No Polymarket API key needed (public endpoints)

## Trade History

As of 2026-02-16, 3 trades logged (all closed):
- 8a16fa55: Eva Victor Best Director — LOSS (-$14.51, stop_loss)
- 0b1626f7: Sorry Baby Best Screenplay — WIN (+$0.05, time_expired)
- a9d8e573: Nancy Guthrie kidnapper — LOSS (-$0.72, time_expired)
- Total P&L: -$15.18

## Recent Changes

- Fixed trades.csv export to read all trades from paper_trades.json
- Incremental embedding index (only encodes new markets, reuses cached)
- Robust LLM JSON parsing (markdown fence stripping, regex fallback)
- VWAP entry pricing with liquidity check
- Trade exit logic (take profit, stop loss, time expiry)
