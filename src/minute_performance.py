"""Build private minute-level USDC performance from trades and mark prices."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .binance_client import BinanceReadOnlyClient
from .fetch_account_data import AccountData

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_DIR = ROOT / "data" / "private"
TRADES_DIR = PRIVATE_DIR / "trades"
MARKS_DIR = PRIVATE_DIR / "mark_prices"
SYMBOL_PATTERN = re.compile(r"^[A-Z0-9_]{2,30}$")
PERFORMANCE_TYPES = {"REALIZED_PNL", "COMMISSION", "FUNDING_FEE"}


@dataclass
class MinutePerformance:
    daily: pd.DataFrame
    warnings: list[str]
    symbol_count: int


def build_minute_performance(
    client: BinanceReadOnlyClient,
    data: AccountData,
) -> MinutePerformance:
    """Fetch private caches and reconstruct snapshot-calibrated minute PnL."""

    symbols = sorted(
        {
            str(row.get("symbol", "")).upper()
            for row in data.futures_income
            if str(row.get("symbol", "")).strip()
        }
    )
    if not symbols or any(not SYMBOL_PATTERN.fullmatch(symbol) for symbol in symbols):
        raise RuntimeError("Unable to identify safe USDC Futures symbols for minute analysis.")

    _prepare_private_directories()
    start = data.inception_utc.replace(second=0, microsecond=0)
    end = data.end_utc.replace(second=0, microsecond=0)
    minute_index = pd.date_range(start, end, freq="min", tz="UTC")
    reconstructed = pd.Series(0.0, index=minute_index)

    for symbol in symbols:
        trades = _update_trade_cache(client, symbol, data.end_utc)
        marks = _update_mark_cache(client, symbol, start, data.end_utc)
        reconstructed = reconstructed.add(
            _symbol_unrealized(trades, marks, minute_index), fill_value=0.0
        )

    calibrated, calibration_error = _calibrate_unrealized(
        reconstructed, data.equity_snapshots
    )
    realized_events, capital_events, balance_events = _income_events(
        data.futures_income, minute_index
    )
    cumulative_realized = realized_events.cumsum()

    frame = pd.DataFrame(index=minute_index)
    frame.index.name = "timestamp_utc"
    frame["cumulative_realized_net_pnl_usdc"] = cumulative_realized
    frame["unrealized_pnl_usdc"] = calibrated
    frame["combined_realized_plus_unrealized_pnl_usdc"] = (
        cumulative_realized + calibrated
    )
    frame["minute_realized_net_pnl_usdc"] = realized_events
    frame["minute_unrealized_pnl_change_usdc"] = calibrated.diff()
    frame["minute_total_pnl_usdc"] = (
        frame["minute_realized_net_pnl_usdc"]
        + frame["minute_unrealized_pnl_change_usdc"]
    )
    frame["capital_adjustment_usdc"] = capital_events

    baseline = _first_official_snapshot(data.equity_snapshots)
    if baseline is None:
        raise RuntimeError("No official USDC equity snapshot is available for minute analysis.")
    baseline_time, baseline_equity = baseline
    baseline_time = max(baseline_time.floor("min"), minute_index[0])
    baseline_position = minute_index.searchsorted(baseline_time)
    frame["estimated_total_equity_usdc"] = np.nan
    if baseline_position < len(frame):
        cumulative_balance = balance_events.cumsum()
        wallet_delta = (
            cumulative_balance.iloc[baseline_position:]
            - cumulative_balance.iloc[baseline_position]
        )
        unrealized_delta = calibrated.iloc[baseline_position:] - calibrated.iloc[baseline_position]
        frame.iloc[baseline_position:, frame.columns.get_loc("estimated_total_equity_usdc")] = (
            baseline_equity + wallet_delta + unrealized_delta
        )

    previous_equity = frame["estimated_total_equity_usdc"].shift(1)
    denominator = previous_equity + capital_events.clip(lower=0)
    frame["minute_total_return"] = np.where(
        denominator > 0,
        frame["minute_total_pnl_usdc"] / denominator,
        np.nan,
    )
    frame.loc[frame["minute_total_return"] <= -1, "minute_total_return"] = np.nan
    frame["normalized_total_equity"] = np.nan
    valid = frame.index >= baseline_time
    frame.loc[valid, "normalized_total_equity"] = (
        1.0 + frame.loc[valid, "minute_total_return"].fillna(0.0)
    ).cumprod()

    warnings = [
        "Minute unrealized PnL is reconstructed from private account trades and one-minute mark prices, then calibrated to official Binance equity snapshots."
    ]
    if calibration_error is not None:
        warnings.append(
            f"Maximum pre-calibration snapshot difference: {calibration_error:.6f} USDC."
        )
    return MinutePerformance(frame, warnings, len(symbols))


def _prepare_private_directories() -> None:
    for path in (PRIVATE_DIR, TRADES_DIR, MARKS_DIR):
        path.mkdir(parents=True, exist_ok=True)
        os.chmod(path, 0o700)


def _update_trade_cache(
    client: BinanceReadOnlyClient,
    symbol: str,
    end: datetime,
) -> list[dict[str, Any]]:
    path = TRADES_DIR / f"{symbol}.json"
    cached = _read_json_list(path)
    six_month_floor = end - timedelta(days=179)
    if cached:
        latest = datetime.fromtimestamp(max(int(row["time"]) for row in cached) / 1_000, UTC)
        start = max(six_month_floor, latest - timedelta(days=1))
    else:
        start = six_month_floor

    fetched: list[dict[str, Any]] = []
    cursor = start
    while cursor < end:
        window_end = min(cursor + timedelta(days=7) - timedelta(milliseconds=1), end)
        page_start = cursor
        while page_start <= window_end:
            batch = client.futures_user_trades(
                symbol=symbol,
                startTime=int(page_start.timestamp() * 1_000),
                endTime=int(window_end.timestamp() * 1_000),
                limit=1000,
            )
            if not isinstance(batch, list):
                raise RuntimeError("Unexpected Binance account trade response shape.")
            fetched.extend(batch)
            if len(batch) < 1000:
                break
            page_start = datetime.fromtimestamp(
                (int(batch[-1]["time"]) + 1) / 1_000, UTC
            )
        cursor = window_end + timedelta(milliseconds=1)

    unique = {
        (str(row.get("symbol")), int(row.get("id", 0))): row
        for row in cached + fetched
        if row.get("id") is not None and row.get("time") is not None
    }
    rows = sorted(unique.values(), key=lambda row: (int(row["time"]), int(row["id"])))
    _write_private_json(path, rows)
    return rows


def _update_mark_cache(
    client: BinanceReadOnlyClient,
    symbol: str,
    inception: datetime,
    end: datetime,
) -> pd.DataFrame:
    path = MARKS_DIR / f"{symbol}.csv"
    cached = pd.read_csv(path) if path.exists() else pd.DataFrame(columns=["timestamp_ms", "close"])
    if not cached.empty:
        start_ms = max(
            int(inception.timestamp() * 1_000),
            int(cached["timestamp_ms"].max()) - 60 * 60 * 1_000,
        )
    else:
        start_ms = int(inception.timestamp() * 1_000)
    end_ms = int(end.timestamp() * 1_000)
    rows: list[dict[str, Any]] = []
    cursor = start_ms
    while cursor <= end_ms:
        batch = client.mark_price_klines(
            symbol=symbol,
            interval="1m",
            startTime=cursor,
            endTime=end_ms,
            limit=1000,
        )
        if not isinstance(batch, list):
            raise RuntimeError("Unexpected Binance mark-price kline response shape.")
        if not batch:
            break
        rows.extend({"timestamp_ms": int(row[0]), "close": float(row[4])} for row in batch)
        next_cursor = int(batch[-1][0]) + 60_000
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        if len(batch) < 1000:
            break

    fresh = pd.DataFrame(rows)
    combined = fresh if cached.empty else pd.concat([cached, fresh], ignore_index=True)
    combined["timestamp_ms"] = pd.to_numeric(combined["timestamp_ms"], errors="coerce")
    combined["close"] = pd.to_numeric(combined["close"], errors="coerce")
    combined = combined.dropna().drop_duplicates("timestamp_ms", keep="last").sort_values("timestamp_ms")
    _write_private_csv(path, combined)
    return combined


def _symbol_unrealized(
    trades: list[dict[str, Any]],
    marks: pd.DataFrame,
    minute_index: pd.DatetimeIndex,
) -> pd.Series:
    mark_series = pd.Series(
        marks["close"].to_numpy(dtype=float),
        index=pd.to_datetime(marks["timestamp_ms"], unit="ms", utc=True),
    ).reindex(minute_index).ffill()
    total = pd.Series(0.0, index=minute_index)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for trade in trades:
        grouped.setdefault(str(trade.get("positionSide", "BOTH")), []).append(trade)

    for position_trades in grouped.values():
        quantity = 0.0
        entry = 0.0
        states: list[tuple[pd.Timestamp, float, float]] = []
        for trade in position_trades:
            price = float(trade["price"])
            delta = float(trade["qty"]) * (1.0 if trade.get("side") == "BUY" else -1.0)
            if abs(quantity) < 1e-15:
                quantity, entry = delta, price
            elif quantity * delta > 0:
                entry = (abs(quantity) * entry + abs(delta) * price) / (abs(quantity) + abs(delta))
                quantity += delta
            elif abs(delta) < abs(quantity):
                quantity += delta
            elif np.isclose(abs(delta), abs(quantity), rtol=0.0, atol=1e-12):
                quantity, entry = 0.0, 0.0
            else:
                quantity += delta
                entry = price
            timestamp = pd.to_datetime(int(trade["time"]), unit="ms", utc=True).floor("min")
            states.append((timestamp, quantity, entry))

        if not states:
            continue
        state = pd.DataFrame(states, columns=["timestamp", "quantity", "entry"]).groupby("timestamp").last()
        state = state.reindex(state.index.union(minute_index)).sort_index().ffill().reindex(minute_index)
        quantity_series = state["quantity"].fillna(0.0)
        entry_series = state["entry"].fillna(0.0)
        total += quantity_series * (mark_series - entry_series)
    return total


def _calibrate_unrealized(
    reconstructed: pd.Series,
    snapshots: list[dict[str, Any]],
) -> tuple[pd.Series, float | None]:
    points: dict[pd.Timestamp, float] = {}
    errors: list[float] = []
    for row in snapshots:
        raw_timestamp = row.get("timestamp_utc") or f"{row['date']}T23:59:00Z"
        timestamp = pd.Timestamp(raw_timestamp).floor("min")
        if timestamp < reconstructed.index[0] or timestamp > reconstructed.index[-1]:
            continue
        location = reconstructed.index.get_indexer([timestamp], method="nearest")[0]
        actual_time = reconstructed.index[location]
        difference = float(row["unrealized_pnl_usdc"]) - float(reconstructed.iloc[location])
        points[actual_time] = difference
        errors.append(abs(difference))
    if not points:
        raise RuntimeError("No Binance snapshot overlaps the minute reconstruction.")
    correction = pd.Series(points).sort_index()
    correction = correction.reindex(correction.index.union(reconstructed.index)).interpolate(
        method="time"
    ).ffill().bfill().reindex(reconstructed.index)
    return reconstructed + correction, max(errors) if errors else None


def _income_events(
    records: list[dict[str, Any]],
    minute_index: pd.DatetimeIndex,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    realized = pd.Series(0.0, index=minute_index)
    capital = pd.Series(0.0, index=minute_index)
    balance = pd.Series(0.0, index=minute_index)
    for row in records:
        try:
            timestamp = pd.to_datetime(int(row["time"]), unit="ms", utc=True).floor("min")
            amount = float(row["income"])
        except (KeyError, TypeError, ValueError):
            continue
        if timestamp not in minute_index:
            continue
        balance.loc[timestamp] += amount
        if row.get("incomeType") in PERFORMANCE_TYPES:
            realized.loc[timestamp] += amount
        else:
            capital.loc[timestamp] += amount
    return realized, capital, balance


def _first_official_snapshot(
    snapshots: list[dict[str, Any]],
) -> tuple[pd.Timestamp, float] | None:
    official = [row for row in snapshots if row.get("source") == "binance_daily_snapshot"]
    if not official:
        return None
    row = min(official, key=lambda item: item["date"])
    timestamp = pd.Timestamp(row.get("timestamp_utc") or f"{row['date']}T23:59:00Z")
    return timestamp, float(row["margin_balance_usdc"])


def _read_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Private cache is unreadable: {path.name}") from exc
    if not isinstance(payload, list):
        raise RuntimeError(f"Private cache has an invalid shape: {path.name}")
    return [row for row in payload if isinstance(row, dict)]


def _write_private_json(path: Path, payload: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _write_private_csv(path: Path, frame: pd.DataFrame) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False)
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
