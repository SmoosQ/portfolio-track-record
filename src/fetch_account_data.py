"""Fetch paginated USDC USD-M Futures data for daily performance analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Iterator

from .binance_client import BinanceClientError, BinanceReadOnlyClient

TRACKED_ASSET = "USDC"
PERFORMANCE_INCEPTION_UTC = datetime(2026, 7, 1, tzinfo=UTC)
FUTURES_RETENTION_DAYS = 89


@dataclass
class AccountData:
    """In-memory USDC data with no account identifiers or credentials."""

    inception_utc: datetime
    fetch_start_utc: datetime
    end_utc: datetime
    asset: str = TRACKED_ASSET
    futures_account: dict[str, Any] | None = None
    futures_income: list[dict[str, Any]] = field(default_factory=list)
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
    return data


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
