"""Minimal read-only Binance USD-M Futures REST client."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlencode

import requests

LOGGER = logging.getLogger(__name__)


class BinanceClientError(RuntimeError):
    """Base exception for safe, non-sensitive client failures."""


class MissingCredentialsError(BinanceClientError):
    """Raised when required environment credentials are absent."""


class BinanceAuthenticationError(BinanceClientError):
    """Raised when Binance rejects the supplied API credentials."""


class BinanceRateLimitError(BinanceClientError):
    """Raised when rate limiting persists after retries."""


class BinanceResponseError(BinanceClientError):
    """Raised for malformed or unsuccessful Binance responses."""


@dataclass(frozen=True)
class TimeoutConfig:
    """Requests connect and read timeouts in seconds."""

    connect: float = 5.0
    read: float = 20.0


class BinanceReadOnlyClient:
    """Signed GET-only client for USD-M Futures account and income data."""

    BASE_URL = "https://fapi.binance.com"
    WALLET_BASE_URL = "https://api.binance.com"

    def __init__(
        self,
        *,
        timeout: TimeoutConfig | None = None,
        max_retries: int = 4,
        recv_window_ms: int = 5_000,
        session: requests.Session | None = None,
    ) -> None:
        api_key = os.getenv("BINANCE_API_KEY", "").strip()
        api_secret = os.getenv("BINANCE_API_SECRET", "").strip()
        if not api_key or not api_secret:
            raise MissingCredentialsError(
                "BINANCE_API_KEY and BINANCE_API_SECRET must both be set."
            )
        if not 1 <= recv_window_ms <= 60_000:
            raise ValueError("recv_window_ms must be between 1 and 60000")

        self._api_secret = api_secret.encode("utf-8")
        self._timeout = timeout or TimeoutConfig()
        self._max_retries = max_retries
        self._recv_window_ms = recv_window_ms
        self._session = session or requests.Session()
        self._session.headers.update(
            {"X-MBX-APIKEY": api_key, "User-Agent": "portfolio-track-record/1.0"}
        )
        self._time_offset_ms = 0
        self._time_is_synchronized = False

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> "BinanceReadOnlyClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def futures_account(self) -> dict[str, Any]:
        """Read the current USD-M Futures account snapshot."""

        return self._signed_get("/fapi/v3/account", {})

    def futures_income(self, **params: Any) -> list[dict[str, Any]]:
        """Read paginated USD-M Futures income history."""

        return self._signed_get("/fapi/v1/income", params)

    def futures_account_snapshots(self, **params: Any) -> dict[str, Any]:
        """Read official daily Futures account snapshots from Binance Wallet."""

        query = {"type": "FUTURES", **params}
        return self._signed_get(
            "/sapi/v1/accountSnapshot",
            query,
            base_url=self.WALLET_BASE_URL,
        )

    def futures_user_trades(self, **params: Any) -> list[dict[str, Any]]:
        """Read account trades for one USD-M Futures symbol."""

        return self._signed_get("/fapi/v1/userTrades", params)

    def mark_price_klines(self, **params: Any) -> list[list[Any]]:
        """Read public mark-price klines for one USD-M Futures symbol."""

        return self._public_get("/fapi/v1/markPriceKlines", params)

    def _public_get(self, path: str, params: Mapping[str, Any]) -> Any:
        for attempt in range(self._max_retries + 1):
            try:
                response = self._session.get(
                    f"{self.BASE_URL}{path}",
                    params=dict(params),
                    timeout=(self._timeout.connect, self._timeout.read),
                )
            except requests.RequestException as exc:
                if attempt >= self._max_retries:
                    raise BinanceResponseError(
                        f"Network failure while reading Binance endpoint {path}."
                    ) from exc
                self._backoff(attempt)
                continue
            if response.status_code in (418, 429):
                if attempt >= self._max_retries:
                    raise BinanceRateLimitError(
                        f"Binance rate limit persisted for endpoint {path}."
                    )
                time.sleep(self._retry_after(response, attempt))
                continue
            if response.status_code >= 500 and attempt < self._max_retries:
                self._backoff(attempt)
                continue
            payload = self._safe_json(response, path)
            if not response.ok:
                raise BinanceResponseError(f"Binance endpoint {path} failed.")
            return payload
        raise BinanceResponseError(f"Unexpected retry exhaustion for endpoint {path}.")

    def _sync_server_time(self) -> None:
        started = int(time.time() * 1_000)
        try:
            response = self._session.get(
                f"{self.BASE_URL}/fapi/v1/time",
                timeout=(self._timeout.connect, self._timeout.read),
            )
            if response.status_code == 451:
                raise BinanceResponseError(
                    "Binance denied this network location (HTTP 451)."
                )
            response.raise_for_status()
            server_time = int(response.json()["serverTime"])
        except BinanceResponseError:
            raise
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            raise BinanceResponseError("Unable to synchronize with Binance server time.") from exc
        finished = int(time.time() * 1_000)
        self._time_offset_ms = server_time - ((started + finished) // 2)
        self._time_is_synchronized = True

    def _signed_get(
        self,
        path: str,
        params: Mapping[str, Any],
        *,
        base_url: str | None = None,
    ) -> Any:
        """Perform a signed GET without logging headers, query strings, or signatures."""

        if not self._time_is_synchronized:
            self._sync_server_time()

        for attempt in range(self._max_retries + 1):
            signed_params = dict(params)
            signed_params["recvWindow"] = self._recv_window_ms
            signed_params["timestamp"] = int(time.time() * 1_000) + self._time_offset_ms
            query = urlencode(signed_params, doseq=True)
            signature = hmac.new(
                self._api_secret, query.encode("utf-8"), hashlib.sha256
            ).hexdigest()
            url = f"{base_url or self.BASE_URL}{path}?{query}&signature={signature}"

            try:
                response = self._session.get(
                    url, timeout=(self._timeout.connect, self._timeout.read)
                )
            except requests.RequestException as exc:
                if attempt >= self._max_retries:
                    raise BinanceResponseError(
                        f"Network failure while reading Binance endpoint {path}."
                    ) from exc
                self._backoff(attempt)
                continue

            payload = self._safe_json(response, path)
            error_code = payload.get("code") if isinstance(payload, dict) else None
            if error_code == -1021 and attempt < self._max_retries:
                LOGGER.warning("Binance timestamp drift detected; resynchronizing time.")
                self._sync_server_time()
                continue
            if response.status_code in (418, 429):
                if attempt >= self._max_retries:
                    raise BinanceRateLimitError(
                        f"Binance rate limit persisted for endpoint {path}."
                    )
                LOGGER.warning("Binance rate limit reached; retrying after a delay.")
                time.sleep(self._retry_after(response, attempt))
                continue
            if response.status_code >= 500:
                if attempt >= self._max_retries:
                    raise BinanceResponseError(f"Binance service error for endpoint {path}.")
                self._backoff(attempt)
                continue
            if response.status_code in (401, 403) or error_code in (-2014, -2015):
                raise BinanceAuthenticationError(
                    "Binance rejected the API credentials or read permissions."
                )
            if response.status_code == 451:
                raise BinanceResponseError(
                    "Binance denied this network location (HTTP 451)."
                )
            if not response.ok or (isinstance(error_code, int) and error_code < 0):
                message = payload.get("msg", "Unknown Binance API error") if isinstance(payload, dict) else "Unknown Binance API error"
                safe_message = str(message).replace("\n", " ").replace("\r", " ")[:240]
                raise BinanceResponseError(f"Binance endpoint {path} failed: {safe_message}")
            return payload

        raise BinanceResponseError(f"Unexpected retry exhaustion for endpoint {path}.")

    @staticmethod
    def _safe_json(response: requests.Response, path: str) -> Any:
        try:
            payload = response.json()
        except ValueError as exc:
            raise BinanceResponseError(
                f"Binance returned non-JSON data for endpoint {path}."
            ) from exc
        if not isinstance(payload, (dict, list)):
            raise BinanceResponseError(
                f"Binance returned an unexpected response shape for endpoint {path}."
            )
        return payload

    @staticmethod
    def _backoff(attempt: int) -> None:
        time.sleep(min(2**attempt, 16))

    @staticmethod
    def _retry_after(response: requests.Response, attempt: int) -> float:
        raw = response.headers.get("Retry-After")
        try:
            return min(max(float(raw), 1.0), 60.0) if raw else min(2**attempt, 16)
        except ValueError:
            return min(2**attempt, 16)
