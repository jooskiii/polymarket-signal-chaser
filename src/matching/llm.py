"""Claude Haiku assessment for headline–market match candidates."""

import json
import logging
import re
from pathlib import Path

import anthropic

logger = logging.getLogger(__name__)

DEBUG_LOG_PATH = Path(__file__).resolve().parents[2] / "data" / "llm_debug.log"

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


def _parse_json_response(text):
    """Extract JSON from an LLM response, handling markdown fences and whitespace."""
    # Already a dict (shouldn't happen, but handle it)
    if isinstance(text, dict):
        return text

    # Strip markdown code fences: ```json ... ``` or ``` ... ```
    stripped = re.sub(r"^```(?:json)?\s*\n?", "", text, flags=re.IGNORECASE)
    stripped = re.sub(r"\n?```\s*$", "", stripped)
    stripped = stripped.strip()

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    # Last resort: find the first { ... } block
    match = re.search(r"\{.*\}", stripped, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    logger.warning("Could not parse LLM response as JSON: %s", text[:200])
    return None


def _log_debug(headline, market_question, raw_response):
    """Append raw LLM response to a debug log file."""
    try:
        DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(DEBUG_LOG_PATH, "a") as f:
            f.write(f"headline: {headline}\n")
            f.write(f"market:   {market_question}\n")
            f.write(f"response: {raw_response}\n")
            f.write("-" * 60 + "\n")
    except OSError:
        pass


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
        _log_debug(headline["title"], market.get("question", ""), text)
        result = _parse_json_response(text)
        return result
    except anthropic.APIError as e:
        logger.warning("LLM assessment failed: %s", e)
        return None
    except Exception as e:
        logger.warning("Unexpected error in LLM assessment: %s", e)
        return None
