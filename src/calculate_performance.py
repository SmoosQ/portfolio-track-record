"""Calculate daily USDC PnL, normalized equity, drawdown, and risk ratios."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .fetch_account_data import AccountData

ANNUALIZATION_FACTOR = 365
PERFORMANCE_TYPES = {"REALIZED_PNL", "COMMISSION", "FUNDING_FEE"}
PERSISTED_COLUMNS = [
    "daily_return",
    "daily_realized_pnl_usdc",
    "daily_commission_usdc",
    "daily_funding_fee_usdc",
    "daily_net_pnl_usdc",
    "daily_trade_count",
]


@dataclass
class PerformanceResult:
    """Calculated daily series, metrics, definitions, and coverage warnings."""

    daily: pd.DataFrame
    metrics: dict[str, Any]
    definitions: dict[str, str]
    warnings: list[str]
    api_window_start_utc: str


def calculate_performance(
    data: AccountData, historical_daily: pd.DataFrame | None = None
) -> PerformanceResult:
    """Build an inception-to-date series, preserving verified rows beyond API retention."""

    if not data.futures_account:
        raise ValueError("USD-M Futures account information is required.")
    asset_row = _asset_row(data.futures_account, data.asset)
    current_wallet = _number(asset_row.get("walletBalance"))
    if current_wallet is None or current_wallet <= 0:
        raise ValueError("A positive USDC USD-M Futures wallet balance is required.")

    current = _current_api_window(data, current_wallet)
    daily = _merge_historical_rows(current, historical_daily, data.inception_utc)
    daily["normalized_equity"] = (1.0 + daily["daily_return"].fillna(0.0)).cumprod()
    daily["drawdown"] = daily["normalized_equity"] / daily["normalized_equity"].cummax() - 1.0

    metrics = _metrics(daily)
    warnings = list(data.warnings)
    ignored_types = sorted(
        {
            str(row.get("incomeType"))
            for row in data.futures_income
            if row.get("incomeType") not in PERFORMANCE_TYPES | {"TRANSFER"}
        }
    )
    if ignored_types:
        warnings.append(
            "Non-performance income types were treated as capital adjustments: "
            + ", ".join(ignored_types)
        )
    if metrics["excluded_return_days"]:
        warnings.append(
            f"{metrics['excluded_return_days']} day(s) were excluded from ratios because the reconstructed capital base was invalid."
        )

    return PerformanceResult(
        daily=daily,
        metrics=metrics,
        definitions=metric_definitions(),
        warnings=warnings,
        api_window_start_utc=data.fetch_start_utc.date().isoformat(),
    )


def _current_api_window(data: AccountData, current_wallet: float) -> pd.DataFrame:
    frame = _income_frame(data.futures_income)
    start_date = pd.Timestamp(data.fetch_start_utc).tz_convert("UTC").normalize()
    end_date = pd.Timestamp(data.end_utc).tz_convert("UTC").normalize()
    dates = pd.date_range(start_date, end_date, freq="D", tz="UTC")

    if frame.empty:
        daily = pd.DataFrame(index=dates)
        for column in (
            "daily_realized_pnl_usdc",
            "daily_commission_usdc",
            "daily_funding_fee_usdc",
            "capital_flow",
            "balance_change",
            "daily_trade_count",
        ):
            daily[column] = 0.0
    else:
        daily = frame.groupby("date", observed=True).agg(
            daily_realized_pnl_usdc=("realized_pnl", "sum"),
            daily_commission_usdc=("commission", "sum"),
            daily_funding_fee_usdc=("funding_fee", "sum"),
            capital_flow=("capital_flow", "sum"),
            balance_change=("amount", "sum"),
            daily_trade_count=("trade_id", lambda values: values[values != ""].nunique()),
        ).reindex(dates, fill_value=0.0)

    daily.index.name = "date"
    daily["daily_net_pnl_usdc"] = (
        daily["daily_realized_pnl_usdc"]
        + daily["daily_commission_usdc"]
        + daily["daily_funding_fee_usdc"]
    )

    end_balances = pd.Series(index=daily.index, dtype=float)
    running_balance = current_wallet
    for date in reversed(daily.index):
        end_balances.loc[date] = running_balance
        running_balance -= float(daily.loc[date, "balance_change"])
    start_balances = end_balances - daily["balance_change"]
    denominator = start_balances + daily["capital_flow"].clip(lower=0)
    daily["daily_return"] = np.where(
        denominator > 0,
        daily["daily_net_pnl_usdc"] / denominator,
        np.nan,
    )
    daily.loc[daily["daily_return"] <= -1, "daily_return"] = np.nan
    return daily


def _merge_historical_rows(
    current: pd.DataFrame,
    historical: pd.DataFrame | None,
    inception: Any,
) -> pd.DataFrame:
    columns = PERSISTED_COLUMNS.copy()
    current_public = current[columns].copy()
    if historical is None or historical.empty:
        return current_public

    previous = historical.copy()
    if "date" in previous.columns:
        previous["date"] = pd.to_datetime(previous["date"], utc=True, errors="coerce")
        previous = previous.dropna(subset=["date"]).set_index("date")
    elif not isinstance(previous.index, pd.DatetimeIndex):
        return current_public
    if previous.index.tz is None:
        previous.index = previous.index.tz_localize("UTC")
    else:
        previous.index = previous.index.tz_convert("UTC")

    missing = [column for column in columns if column not in previous.columns]
    if missing:
        return current_public
    inception_date = pd.Timestamp(inception).tz_convert("UTC").normalize()
    preserved = previous.loc[
        (previous.index >= inception_date) & (previous.index < current_public.index.min()),
        columns,
    ]
    combined = pd.concat([preserved, current_public]).sort_index()
    return combined[~combined.index.duplicated(keep="last")]


def _metrics(daily: pd.DataFrame) -> dict[str, Any]:
    valid_returns = daily["daily_return"].dropna()
    chain = (1.0 + daily["daily_return"].fillna(0.0)).cumprod()
    cumulative_return = float(chain.iloc[-1] - 1.0)
    performance_days = daily.loc[daily["daily_net_pnl_usdc"] != 0, "daily_net_pnl_usdc"]
    positive = float(performance_days[performance_days > 0].sum())
    negative = float(performance_days[performance_days < 0].sum())
    annualized_return = _annualized_return(cumulative_return, len(valid_returns))
    max_drawdown = float((chain / chain.cummax() - 1.0).min())
    return {
        "cumulative_return": cumulative_return,
        "latest_daily_return": _optional_float(valid_returns.iloc[-1]) if not valid_returns.empty else None,
        "annualized_return": annualized_return,
        "annualized_volatility": _annualized_volatility(valid_returns),
        "sharpe_ratio": _sharpe(valid_returns),
        "sortino_ratio": _sortino(valid_returns),
        "maximum_drawdown": max_drawdown,
        "calmar_ratio": _safe_divide(annualized_return, abs(max_drawdown)),
        "win_rate": _safe_divide(float((performance_days > 0).sum()), float(len(performance_days))),
        "profit_factor": _safe_divide(positive, abs(negative)),
        "total_realized_pnl_usdc": float(daily["daily_realized_pnl_usdc"].sum()),
        "total_commission_usdc": float(daily["daily_commission_usdc"].sum()),
        "total_funding_fee_usdc": float(daily["daily_funding_fee_usdc"].sum()),
        "total_net_pnl_usdc": float(daily["daily_net_pnl_usdc"].sum()),
        "number_of_trading_days": int((daily["daily_net_pnl_usdc"] != 0).sum()),
        "number_of_trades": int(daily["daily_trade_count"].sum()),
        "valid_return_days": int(len(valid_returns)),
        "excluded_return_days": int(daily["daily_return"].isna().sum()),
        "annualization_factor": ANNUALIZATION_FACTOR,
    }


def metric_definitions() -> dict[str, str]:
    return {
        "performance_scope": "Daily realized USDC USD-M Futures performance from 2026-07-01, using UTC day boundaries.",
        "daily_net_pnl": "USDC realized PnL + USDC commission + USDC funding fee for each UTC day.",
        "daily_return": "Daily net PnL divided by reconstructed starting USDC capital; positive same-day transfers are added to the denominator.",
        "cumulative_return": "Product of (1 + daily return) minus 1.",
        "annualized_return": "Geometric cumulative return annualized with 365 calendar days.",
        "annualized_volatility": "Sample standard deviation of daily returns multiplied by sqrt(365).",
        "sharpe_ratio": "Mean daily return divided by sample daily standard deviation, multiplied by sqrt(365); risk-free rate is 0.",
        "sortino_ratio": "Mean daily return divided by sample downside deviation, multiplied by sqrt(365); target return is 0.",
        "maximum_drawdown": "Largest decline from a prior peak in normalized equity.",
        "calmar_ratio": "Annualized return divided by the absolute maximum drawdown.",
        "win_rate": "Positive daily net-PnL days divided by non-zero daily net-PnL days.",
        "profit_factor": "Sum of positive daily net PnL divided by absolute negative daily net PnL.",
        "annualization_factor": "365 calendar days because crypto markets trade continuously.",
    }


def _income_frame(records: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for record in records:
        income_type = str(record.get("incomeType", "UNKNOWN"))
        amount = _number(record.get("income"))
        timestamp = record.get("time")
        if amount is None or timestamp is None:
            continue
        rows.append(
            {
                "date": pd.to_datetime(int(timestamp), unit="ms", utc=True).normalize(),
                "amount": amount,
                "realized_pnl": amount if income_type == "REALIZED_PNL" else 0.0,
                "commission": amount if income_type == "COMMISSION" else 0.0,
                "funding_fee": amount if income_type == "FUNDING_FEE" else 0.0,
                "capital_flow": amount if income_type == "TRANSFER" else 0.0,
                "trade_id": str(record.get("tradeId", "") or ""),
            }
        )
    return pd.DataFrame(rows)


def _asset_row(account: dict[str, Any], asset: str) -> dict[str, Any]:
    assets = account.get("assets", [])
    for row in assets if isinstance(assets, list) else []:
        if isinstance(row, dict) and row.get("asset") == asset:
            return row
    raise ValueError(f"USD-M Futures account has no {asset} asset row.")


def _annualized_return(cumulative_return: float, periods: int) -> float | None:
    if periods <= 0 or cumulative_return <= -1:
        return None
    return _optional_float((1.0 + cumulative_return) ** (ANNUALIZATION_FACTOR / periods) - 1.0)


def _annualized_volatility(returns: pd.Series) -> float | None:
    if len(returns) < 2:
        return None
    return _optional_float(float(returns.std(ddof=1) * math.sqrt(ANNUALIZATION_FACTOR)))


def _sharpe(returns: pd.Series) -> float | None:
    if len(returns) < 2:
        return None
    return _safe_divide(
        float(returns.mean()) * math.sqrt(ANNUALIZATION_FACTOR),
        float(returns.std(ddof=1)),
    )


def _sortino(returns: pd.Series) -> float | None:
    if returns.empty or not (returns < 0).any():
        return None
    downside = np.minimum(returns.to_numpy(dtype=float), 0.0)
    downside_deviation = float(np.sqrt(np.mean(np.square(downside))))
    return _safe_divide(
        float(returns.mean()) * math.sqrt(ANNUALIZATION_FACTOR),
        downside_deviation,
    )


def _safe_divide(numerator: float | None, denominator: float) -> float | None:
    if numerator is None or not math.isfinite(denominator) or abs(denominator) < 1e-15:
        return None
    return _optional_float(numerator / denominator)


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _optional_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None
