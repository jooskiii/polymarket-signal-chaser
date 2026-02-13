"""Claude Haiku assessment for headline–market match candidates."""

import json
import logging

import anthropic

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = (
    "You are an analyst evaluating whether a news headline is relevant to a "
    "prediction market. Respond in raw JSON only, no markdown, no backticks, "
    "no explanation."
)

USER_PROMPT_TEMPLATE = (
    "Given this headline: {headline}\n"
    "and this Polymarket market: {market_title} — {market_description}\n"
    "Current YES/NO prices: YES={yes_price}, NO={no_price}\n"
    "\n"
    "Is this headline relevant to this market? If yes, which direction does it "
    "push (YES or NO), and rate your confidence 0-1.\n"
    "\n"
    "Respond in raw JSON only, no markdown, no backticks, no explanation:\n"
    '{{"relevant": bool, "direction": "YES/NO/null", "confidence": float, "reasoning": "string"}}'
)


def _extract_prices(market):
    """Extract YES/NO prices from market data."""
    outcomes = market.get("outcomes", [])
    prices = market.get("outcomePrices", [])
    yes_price, no_price = "N/A", "N/A"
    for outcome, price in zip(outcomes, prices):
        if str(outcome).upper() == "YES":
            yes_price = price
        elif str(outcome).upper() == "NO":
            no_price = price
    return yes_price, no_price


def assess_match(headline, market, api_key):
    """Ask Claude Haiku whether a headline is relevant to a market.

    Args:
        headline: Headline dict with 'title' field.
        market: Market dict with 'question', 'outcomes', 'outcomePrices' fields.
        api_key: Anthropic API key string.

    Returns:
        Parsed dict with {relevant, direction, confidence, reasoning}, or None on failure.
    """
    yes_price, no_price = _extract_prices(market)
    prompt = USER_PROMPT_TEMPLATE.format(
        headline=headline["title"],
        market_title=market.get("question", ""),
        market_description=market.get("description", ""),
        yes_price=yes_price,
        no_price=no_price,
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=MODEL,
            max_tokens=256,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        result = json.loads(text)
        return result
    except (anthropic.APIError, json.JSONDecodeError) as e:
        logger.warning("LLM assessment failed: %s", e)
        return None
    except Exception as e:
        logger.warning("Unexpected error in LLM assessment: %s", e)
        return None
