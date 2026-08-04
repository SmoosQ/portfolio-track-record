"""Generate normalized CSV, charts, and performance summaries from Binance data."""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .binance_client import BinanceReadOnlyClient
from .calculate_performance import PerformanceResult, calculate_performance
from .fetch_account_data import fetch_account_data

LOGGER = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "reports"
PROCESSED_DIR = ROOT / "data" / "processed"
LOCAL_REPORTS_DIR = ROOT / "local_reports"
BLUE = "#2563EB"
BLUE_DARK = "#1E3A8A"
GOLD = "#D4A72C"
INK = "#172033"
GRID = "#DDE3EC"


def main() -> int:
    """Fetch live data and atomically replace all public report artifacts."""

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    LOCAL_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(LOCAL_REPORTS_DIR, 0o700)

    historical_daily = _load_historical_daily()
    historical_private_daily = _load_private_daily()
    with BinanceReadOnlyClient() as client:
        account_data = fetch_account_data(client)
    result = calculate_performance(
        account_data,
        historical_daily,
        historical_private_daily,
    )
    generated_at = datetime.now(UTC).replace(microsecond=0)

    _write_normalized_csv(result)
    _write_charts(result)
    _write_key_metrics(result)
    _write_private_reports(result, generated_at)
    summary = _build_summary(result, generated_at)
    _write_json(REPORTS_DIR / "performance_summary.json", summary)
    _write_markdown(REPORTS_DIR / "performance_summary.md", summary)

    LOGGER.info("Generated normalized performance reports for %d UTC days.", len(result.daily))
    for warning in result.warnings:
        LOGGER.warning(warning)
    return 0


def _write_normalized_csv(result: PerformanceResult) -> None:
    public = result.daily.reset_index()[
        [
            "date",
            "daily_return",
            "normalized_equity",
            "drawdown",
            "daily_realized_pnl_usdc",
            "daily_commission_usdc",
            "daily_funding_fee_usdc",
            "daily_net_pnl_usdc",
            "daily_trade_count",
        ]
    ].copy()
    public["date"] = public["date"].dt.strftime("%Y-%m-%d")
    _atomic_csv(PROCESSED_DIR / "normalized_daily_equity.csv", public)


def _write_charts(result: PerformanceResult) -> None:
    daily = result.daily.copy()
    dates = daily.index.tz_localize(None)
    coverage = f"{daily.index.min():%Y-%m-%d} to {daily.index.max():%Y-%m-%d} · UTC"

    fig, ax = _figure("Normalized USDC Equity Curve", f"Flow-adjusted realized USD-M Futures performance · {coverage}")
    ax.plot(dates, daily["normalized_equity"], color=BLUE, linewidth=2.2)
    ax.axhline(1.0, color=INK, linewidth=1.0, linestyle="--", alpha=0.7)
    ax.set_ylabel("Normalized equity (start = 1.0)")
    _finish_time_axis(fig, ax, REPORTS_DIR / "normalized_equity_curve.png")

    fig, ax = _figure("Cumulative USDC PnL", f"Cumulative realized net performance · {coverage}")
    cumulative_pnl = daily["daily_net_pnl_usdc"].cumsum()
    ax.plot(dates, cumulative_pnl, color=BLUE, linewidth=2.2)
    ax.fill_between(dates, cumulative_pnl, 0, color=BLUE, alpha=0.12, linewidth=0)
    ax.axhline(0, color=INK, linewidth=1.0)
    ax.set_ylabel("Cumulative net PnL (USDC)")
    _finish_time_axis(fig, ax, REPORTS_DIR / "cumulative_pnl_curve.png")

    fig, ax = _figure("USDC Drawdown Curve", f"Decline from prior normalized-equity peak · {coverage}")
    drawdown_pct = daily["drawdown"] * 100
    ax.fill_between(dates, drawdown_pct, 0, color=BLUE, alpha=0.22, linewidth=0)
    ax.plot(dates, drawdown_pct, color=BLUE_DARK, linewidth=1.6)
    ax.axhline(0, color=INK, linewidth=1.0)
    ax.set_ylabel("Drawdown (%)")
    _finish_time_axis(fig, ax, REPORTS_DIR / "drawdown_curve.png")

    fig, ax = _figure("USDC Daily Returns", f"Flow-adjusted daily return · {coverage}")
    return_pct = daily["daily_return"].fillna(0) * 100
    colors = [BLUE if value >= 0 else GOLD for value in return_pct]
    ax.bar(dates, return_pct, color=colors, width=0.85, edgecolor="white", linewidth=0.25)
    ax.axhline(0, color=INK, linewidth=1.0)
    ax.set_ylabel("Daily return (%)")
    ax.margins(y=0.08)
    _finish_time_axis(fig, ax, REPORTS_DIR / "daily_returns.png")

    monthly = (1.0 + daily["daily_return"].fillna(0)).resample("ME").prod() - 1.0
    labels = [timestamp.strftime("%Y-%m") for timestamp in monthly.index]
    values = monthly.to_numpy() * 100
    values[np.abs(values) < 1e-10] = 0.0
    fig, ax = _figure("USDC Monthly Returns", f"Compounded flow-adjusted return by calendar month · {coverage}")
    colors = [BLUE if value >= 0 else GOLD for value in values]
    positions = np.arange(len(labels))
    ax.bar(positions, values, color=colors, edgecolor="white", linewidth=0.5)
    ax.axhline(0, color=INK, linewidth=1.0)
    ax.set_ylabel("Monthly return (%)")
    ax.set_xticks(positions, labels, rotation=45, ha="right")
    ax.ticklabel_format(axis="y", style="plain", useOffset=False)
    if np.allclose(values, 0.0):
        ax.set_ylim(-1.0, 1.0)
    else:
        ax.margins(y=0.1)
    _save_figure(fig, REPORTS_DIR / "monthly_returns.png")


def _write_key_metrics(result: PerformanceResult) -> None:
    """Publish high-level metrics without exposing daily unrealized PnL."""

    metrics = result.metrics
    entries = [
        ("Realized cumulative return", _format_metric(metrics.get("cumulative_return"), percent=True)),
        ("Realized maximum drawdown", _format_metric(metrics.get("maximum_drawdown"), percent=True)),
        ("Sharpe · incl. unrealized", _format_metric(metrics.get("sharpe_ratio"))),
        ("Sortino · incl. unrealized", _format_metric(metrics.get("sortino_ratio"))),
        ("Realized net PnL", _format_metric(metrics.get("total_net_pnl_usdc"), suffix=" USDC")),
        ("Realized win rate", _format_metric(metrics.get("win_rate"), percent=True)),
    ]
    fig, axes = plt.subplots(2, 3, figsize=(12, 4.2), dpi=160, facecolor="white")
    for ax, (label, value) in zip(axes.flat, entries):
        ax.axis("off")
        ax.text(0.5, 0.62, value, ha="center", va="center", fontsize=19, fontweight="bold", color=BLUE_DARK)
        ax.text(0.5, 0.28, label, ha="center", va="center", fontsize=9.5, color="#5C667A")
    fig.suptitle("USDC Performance at a Glance", x=0.04, y=0.97, ha="left", fontsize=16, fontweight="bold", color=INK)
    fig.text(0.04, 0.02, "Only Sharpe and Sortino use private total returns including unrealized PnL; no unrealized amounts are published.", fontsize=8.5, color="#5C667A")
    _save_figure(fig, REPORTS_DIR / "key_metrics.png")


def _write_private_reports(result: PerformanceResult, generated_at: datetime) -> None:
    """Write detailed total-equity artifacts to the ignored local-only directory."""

    daily = result.private_daily.copy()
    public = daily.reset_index().rename(columns={"index": "date"})
    public["date"] = public["date"].dt.strftime("%Y-%m-%d")
    _atomic_private_csv(LOCAL_REPORTS_DIR / "detailed_daily_performance.csv", public)

    dates = daily.index.tz_localize(None)
    fig, ax = _figure("Local Total Equity Curve", "Includes realized and unrealized USDC PnL · private local output")
    ax.plot(dates, daily["normalized_total_equity"], color=BLUE, linewidth=2.2)
    ax.axhline(1.0, color=INK, linewidth=1.0, linestyle="--", alpha=0.7)
    ax.set_ylabel("Normalized total equity")
    _finish_private_time_axis(fig, ax, LOCAL_REPORTS_DIR / "total_equity_curve.png")

    fig, ax = _figure("Local PnL Components", "Realized net PnL and end-of-day unrealized PnL · private local output")
    ax.plot(dates, daily["daily_net_pnl_usdc"].cumsum(), color=BLUE, linewidth=2.0, label="Cumulative realized net PnL")
    ax.plot(dates, daily["end_unrealized_pnl_usdc"], color=GOLD, linewidth=1.8, label="End-of-day unrealized PnL")
    ax.axhline(0, color=INK, linewidth=1.0)
    ax.set_ylabel("PnL (USDC)")
    ax.legend(frameon=False)
    _finish_private_time_axis(fig, ax, LOCAL_REPORTS_DIR / "pnl_components.png")

    valid = daily["daily_total_return"].dropna() * 100
    fig, ax = _figure("Local Daily Total Returns", "Includes realized and unrealized PnL · private local output")
    colors = [BLUE if value >= 0 else GOLD for value in valid]
    ax.bar(valid.index.tz_localize(None), valid, color=colors, width=0.85)
    ax.axhline(0, color=INK, linewidth=1.0)
    ax.set_ylabel("Daily total return (%)")
    _finish_private_time_axis(fig, ax, LOCAL_REPORTS_DIR / "daily_total_returns.png")

    monthly = (1.0 + daily["daily_total_return"].dropna()).resample("ME").prod() - 1.0
    labels = [timestamp.strftime("%Y-%m") for timestamp in monthly.index]
    values = monthly.to_numpy() * 100
    fig, ax = _figure("Local Monthly Total Returns", "Includes realized and unrealized PnL · private local output")
    positions = np.arange(len(labels))
    colors = [BLUE if value >= 0 else GOLD for value in values]
    ax.bar(positions, values, color=colors)
    ax.axhline(0, color=INK, linewidth=1.0)
    ax.set_ylabel("Monthly total return (%)")
    ax.set_xticks(positions, labels, rotation=45, ha="right")
    _save_figure(fig, LOCAL_REPORTS_DIR / "monthly_total_returns.png")
    os.chmod(LOCAL_REPORTS_DIR / "monthly_total_returns.png", 0o600)

    summary = {
        "generated_at_utc": generated_at.isoformat().replace("+00:00", "Z"),
        "privacy": "Local only; contains absolute equity and unrealized PnL.",
        "metrics": _json_safe(result.private_metrics),
        "monthly_total_returns": {
            date.strftime("%Y-%m"): float(value) for date, value in monthly.items()
        },
    }
    _write_private_json(LOCAL_REPORTS_DIR / "detailed_summary.json", summary)


def _figure(title: str, subtitle: str) -> tuple[plt.Figure, plt.Axes]:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "axes.edgecolor": INK,
            "axes.labelcolor": INK,
            "xtick.color": INK,
            "ytick.color": INK,
            "text.color": INK,
        }
    )
    fig, ax = plt.subplots(figsize=(12, 6.4), dpi=160, facecolor="white")
    ax.set_facecolor("white")
    fig.suptitle(title, x=0.09, y=0.97, ha="left", fontsize=17, fontweight="bold", color=INK)
    ax.set_title(subtitle, loc="left", fontsize=10, color="#5C667A", pad=14)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    return fig, ax


def _finish_time_axis(fig: plt.Figure, ax: plt.Axes, path: Path) -> None:
    locator = mdates.AutoDateLocator(minticks=5, maxticks=10)
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    _save_figure(fig, path)


def _finish_private_time_axis(fig: plt.Figure, ax: plt.Axes, path: Path) -> None:
    locator = mdates.AutoDateLocator(minticks=5, maxticks=10)
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    _save_figure(fig, path)
    os.chmod(path, 0o600)


def _save_figure(fig: plt.Figure, path: Path) -> None:
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    temporary = path.with_suffix(path.suffix + ".tmp")
    fig.savefig(temporary, format="png", dpi=160, bbox_inches="tight", metadata={"Software": "portfolio-track-record"})
    plt.close(fig)
    os.replace(temporary, path)


def _build_summary(result: PerformanceResult, generated_at: datetime) -> dict[str, Any]:
    start_date = result.daily.index.min().strftime("%Y-%m-%d")
    end_date = result.daily.index.max().strftime("%Y-%m-%d")
    return {
        "generated_at_utc": generated_at.isoformat().replace("+00:00", "Z"),
        "data_source": "Binance read-only USD-M Futures account and income REST APIs",
        "performance_scope": "Daily USDC USD-M Futures realized performance",
        "tracked_asset": "USDC",
        "api_window_start_utc": result.api_window_start_utc,
        "coverage_start_utc": start_date,
        "coverage_end_utc": end_date,
        "account_values_normalized": True,
        "transfers_excluded_from_pnl": True,
        "credentials_included": False,
        "metrics": _json_safe(result.metrics),
        "definitions": result.definitions,
        "warnings": result.warnings,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _write_markdown(path: Path, summary: dict[str, Any]) -> None:
    metrics = summary["metrics"]
    percentage_metrics = {
        "cumulative_return",
        "latest_daily_return",
        "annualized_return",
        "annualized_volatility",
        "maximum_drawdown",
        "win_rate",
    }
    rows = []
    for key, value in metrics.items():
        if isinstance(value, list):
            formatted = ", ".join(str(item) for item in value) if value else "None"
        elif value is None:
            formatted = "N/A"
        elif key in percentage_metrics:
            formatted = f"{value * 100:.2f}%"
        elif isinstance(value, float):
            formatted = f"{value:.6f}"
        else:
            formatted = str(value)
        rows.append(f"| {key.replace('_', ' ').title()} | {formatted} |")

    warnings = summary["warnings"]
    warning_lines = "\n".join(f"- {warning}" for warning in warnings) or "- None"
    content = f"""# Performance Summary

Generated at: **{summary['generated_at_utc']}**<br>
Coverage: **{summary['coverage_start_utc']} to {summary['coverage_end_utc']} (UTC)**<br>
Scope: **{summary['performance_scope']}**

Absolute account values are not published. USD-M Futures transfers are excluded from trading return.
Sharpe and Sortino use private total daily returns including unrealized PnL; unrealized amounts and daily total returns are not published.

| Metric | Value |
|---|---:|
{chr(10).join(rows)}

## Warnings and coverage notes

{warning_lines}

## Definitions

{chr(10).join(f'- **{key.replace("_", " ").title()}**: {value}' for key, value in summary['definitions'].items())}

This report is for professional evaluation only and is not investment advice.
"""
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def _atomic_csv(path: Path, frame: pd.DataFrame) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False, float_format="%.10f")
    os.replace(temporary, path)


def _load_historical_daily() -> pd.DataFrame | None:
    """Load only the prior normalized public series used to preserve expired API days."""

    path = PROCESSED_DIR / "normalized_daily_equity.csv"
    if not path.exists():
        return None
    try:
        return pd.read_csv(path)
    except (OSError, pd.errors.ParserError) as exc:
        raise RuntimeError("Existing normalized daily history could not be read safely.") from exc


def _load_private_daily() -> pd.DataFrame | None:
    path = LOCAL_REPORTS_DIR / "detailed_daily_performance.csv"
    if not path.exists():
        return None
    try:
        return pd.read_csv(path)
    except (OSError, pd.errors.ParserError) as exc:
        raise RuntimeError("Existing private daily history could not be read safely.") from exc


def _atomic_private_csv(path: Path, frame: pd.DataFrame) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False, float_format="%.10f")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _write_private_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _format_metric(value: Any, *, percent: bool = False, suffix: str = "") -> str:
    if value is None:
        return "N/A"
    number = float(value)
    if percent:
        return f"{number * 100:.2f}%"
    return f"{number:.3f}{suffix}"


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return number if np.isfinite(number) else None
    return value


if __name__ == "__main__":
    raise SystemExit(main())
