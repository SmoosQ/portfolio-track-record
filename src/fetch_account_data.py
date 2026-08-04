"""Fetch paginated USDC USD-M Futures data for daily performance analysis."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from .binance_client import BinanceClientError, BinanceReadOnlyClient

TRACKED_ASSET = "USDC"
PERFORMANCE_INCEPTION_UTC = datetime(2026, 7, 1, tzinfo=UTC)
FUTURES_RETENTION_DAYS = 89
ROOT = Path(__file__).resolve().parents[1]
PRIVATE_SNAPSHOT_PATH = ROOT / "data" / "private" / "usdc_equity_snapshots.json"


@dataclass
class AccountData:
    """In-memory USDC data with no account identifiers or credentials."""

    inception_utc: datetime
    fetch_start_utc: datetime
    end_utc: datetime
    asset: str = TRACKED_ASSET
    futures_account: dict[str, Any] | None = None
    futures_income: list[dict[str, Any]] = field(default_factory=list)
    equity_snapshots: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def fetch_account_data(
    client: BinanceReadOnlyClient,
    *,
    inception_utc: datetime = PERFORMANCE_INCEPTION_UTC,
    end_utc: datetime | None = None,
) -> AccountData:
    """Fetch USDC account data in seven-day windows with complete pagination."""

    end = _as_utc(end_utc or datetime.now(UTC))
    inception = _as_utc(inception_utc)
    if inception >= end:
        raise ValueError("Performance inception must be earlier than the report end time.")

    retention_floor = end - timedelta(days=FUTURES_RETENTION_DAYS)
    fetch_start = max(inception, retention_floor)
    data = AccountData(
        inception_utc=inception,
        fetch_start_utc=fetch_start,
        end_utc=end,
    )
    if fetch_start > inception:
        data.warnings.append(
            "Binance API retention no longer covers inception; verified earlier daily rows were preserved from the repository."
        )

    try:
        account = client.futures_account()
        income = _fetch_futures_income(client, fetch_start, end)
        snapshots = _fetch_equity_snapshots(client, inception, end, account)
    except BinanceClientError as exc:
        raise RuntimeError(f"Required USD-M Futures read failed: {exc}") from exc

    assets = account.get("assets", []) if isinstance(account, dict) else []
    if not isinstance(assets, list) or not any(
        row.get("asset") == TRACKED_ASSET for row in assets if isinstance(row, dict)
    ):
        raise RuntimeError("The USD-M Futures account response contains no USDC asset row.")

    data.futures_account = account
    data.futures_income = [
        row for row in income if str(row.get("asset", "")).upper() == TRACKED_ASSET
    ]
    data.equity_snapshots = snapshots
    return data


def _fetch_equity_snapshots(
    client: BinanceReadOnlyClient,
    inception: datetime,
    end: datetime,
    current_account: dict[str, Any],
) -> list[dict[str, Any]]:
    """Merge Binance daily snapshots with private local history and today's account."""

    query_start = max(inception, end - timedelta(days=29, hours=23))
    payload = client.futures_account_snapshots(
        startTime=_to_ms(query_start),
        endTime=_to_ms(end),
        limit=30,
    )
    if payload.get("code") != 200 or not isinstance(payload.get("snapshotVos"), list):
        raise BinanceClientError("Unexpected Futures account snapshot response shape.")

    merged = {row["date"]: row for row in _load_private_snapshots()}
    for snapshot in payload["snapshotVos"]:
        row = _snapshot_row(snapshot)
        if row and row["date"] >= inception.date().isoformat():
            merged[row["date"]] = row

    current_row = _current_account_row(current_account, end)
    merged[current_row["date"]] = current_row
    result = [merged[key] for key in sorted(merged) if key >= inception.date().isoformat()]
    _write_private_snapshots(result)
    return result


def _snapshot_row(snapshot: Any) -> dict[str, Any] | None:
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("data"), dict):
        return None
    asset = _find_asset(snapshot["data"].get("assets"))
    if asset is None:
        return None
    updated = datetime.fromtimestamp(int(snapshot.get("updateTime", 0)) / 1_000, UTC)
    return _equity_row(updated, asset, "binance_daily_snapshot")


def _current_account_row(account: dict[str, Any], end: datetime) -> dict[str, Any]:
    asset = _find_asset(account.get("assets"))
    if asset is None:
        raise BinanceClientError("Current Futures account contains no USDC asset row.")
    return _equity_row(end, asset, "current_account")


def _find_asset(assets: Any) -> dict[str, Any] | None:
    if not isinstance(assets, list):
        return None
    return next(
        (row for row in assets if isinstance(row, dict) and row.get("asset") == TRACKED_ASSET),
        None,
    )


def _equity_row(timestamp: datetime, asset: dict[str, Any], source: str) -> dict[str, Any]:
    try:
        wallet = float(asset["walletBalance"])
        margin = float(asset["marginBalance"])
    except (KeyError, TypeError, ValueError) as exc:
        raise BinanceClientError("USDC account snapshot has invalid balance fields.") from exc
    unrealized = float(asset.get("unrealizedProfit", margin - wallet))
    return {
        "date": timestamp.date().isoformat(),
        "timestamp_utc": timestamp.isoformat().replace("+00:00", "Z"),
        "wallet_balance_usdc": wallet,
        "margin_balance_usdc": margin,
        "unrealized_pnl_usdc": unrealized,
        "source": source,
    }


def _load_private_snapshots() -> list[dict[str, Any]]:
    if not PRIVATE_SNAPSHOT_PATH.exists():
        return []
    try:
        payload = json.loads(PRIVATE_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BinanceClientError("Private equity snapshot history is unreadable.") from exc
    if not isinstance(payload, list):
        raise BinanceClientError("Private equity snapshot history has an invalid shape.")
    return [row for row in payload if isinstance(row, dict) and isinstance(row.get("date"), str)]


def _write_private_snapshots(rows: list[dict[str, Any]]) -> None:
    PRIVATE_SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = PRIVATE_SNAPSHOT_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, PRIVATE_SNAPSHOT_PATH)


def _fetch_futures_income(
    client: BinanceReadOnlyClient, start: datetime, end: datetime
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for window_start, window_end in _time_windows(start, end, timedelta(days=7)):
        page = 1
        while True:
            batch = client.futures_income(
                startTime=_to_ms(window_start),
                endTime=_to_ms(window_end),
                page=page,
                limit=1000,
            )
            if not isinstance(batch, list):
                raise BinanceClientError("Unexpected USD-M Futures income response shape.")
            records.extend(batch)
            if len(batch) < 1000:
                break
            page += 1

    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in records:
        key = (
            row.get("incomeType"),
            row.get("tranId"),
            row.get("tradeId"),
            row.get("time"),
            row.get("asset"),
            row.get("income"),
        )
        unique[key] = row
    return sorted(unique.values(), key=lambda row: int(row.get("time", 0) or 0))


def _time_windows(
    start: datetime, end: datetime, width: timedelta
) -> Iterator[tuple[datetime, datetime]]:
    cursor = start
    one_millisecond = timedelta(milliseconds=1)
    while cursor < end:
        window_end = min(cursor + width - one_millisecond, end)
        yield cursor, window_end
        cursor = window_end + one_millisecond


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _to_ms(value: datetime) -> int:
    return int(value.timestamp() * 1_000)
