import pandas as pd
from typing import Optional
from config import DEFAULT_THRESHOLDS, DEFAULT_GROUP_WEIGHTS, SIGNAL_EMOJI, EARNINGS_CRITICAL_DAYS
from scanner.indicators.registry import get_enabled_indicators

# Trigger indicator module imports so @register decorators run
import scanner.indicators.trend  # noqa: F401
import scanner.indicators.momentum  # noqa: F401
import scanner.indicators.volume  # noqa: F401
import scanner.indicators.volatility  # noqa: F401
import scanner.indicators.candlesticks  # noqa: F401


def compute_score(
    ohlcv: pd.DataFrame,
    toggles: dict = None,
    weights: dict = None,
    thresholds: dict = None,
) -> dict:
    """
    Run all enabled indicators against OHLCV data and return composite result.

    Returns dict with keys: score (0-100), signal, reasoning, indicator_detail.
    """
    weights = weights or DEFAULT_GROUP_WEIGHTS
    thresholds = thresholds or DEFAULT_THRESHOLDS

    group_scores: dict[str, list[float]] = {}
    group_reasoning: dict[str, list[str]] = {}
    indicator_detail: dict[str, dict] = {}

    for entry in get_enabled_indicators(toggles):
        indicator = entry.cls(params=entry.params)
        try:
            ind_score, ind_reasoning = indicator.score(ohlcv)
        except Exception as e:
            ind_score, ind_reasoning = 5.0, f"Error in {entry.cls.__name__}: {e}"

        group = entry.group
        group_scores.setdefault(group, []).append(ind_score)
        group_reasoning.setdefault(group, []).append(ind_reasoning)
        indicator_detail[entry.cls.__name__] = {
            "score": round(ind_score, 2),
            "reasoning": ind_reasoning,
            "group": group,
        }

    composite = 0.0
    for group, scores in group_scores.items():
        group_avg = sum(scores) / len(scores)
        weight = weights.get(group, 0.0)
        composite += group_avg * weight

    final_score = round(composite * 10, 1)
    signal = signal_from_score(final_score, thresholds)

    all_reasoning = []
    for group in ["trend", "momentum", "volume", "volatility", "candlesticks"]:
        if group in group_reasoning:
            all_reasoning.extend(group_reasoning[group])
    reasoning = " ".join(all_reasoning)

    return {
        "score": final_score,
        "signal": signal,
        "reasoning": reasoning,
        "indicator_detail": indicator_detail,
    }


def signal_from_score(score: float, thresholds: dict = None) -> str:
    t = thresholds or DEFAULT_THRESHOLDS
    if score >= t["BUY"]:
        return "BUY"
    if score >= t["WATCH CAREFULLY"]:
        return "WATCH CAREFULLY"
    if score >= t["HOLD"]:
        return "HOLD"
    if score >= t["REDUCE"]:
        return "REDUCE"
    return "EXIT"


def format_signal(
    signal: str,
    earnings_warning: bool,
    sentiment_flag: bool,
    days_to_earnings: Optional[int] = None,
) -> str:
    """Return the display-ready signal string with emoji and event modifier flags."""
    display = signal

    if earnings_warning and days_to_earnings is not None and days_to_earnings <= EARNINGS_CRITICAL_DAYS:
        if signal == "BUY":
            display = "WATCH CAREFULLY"

    emoji = SIGNAL_EMOJI.get(display, "")
    result = f"{emoji} {display}"

    if earnings_warning:
        result += " ⚠️"
    if sentiment_flag:
        result += " 🔻"

    return result
