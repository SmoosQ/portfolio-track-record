"""Tests for the read-only Binance REST client."""

from __future__ import annotations

import os
import unittest
from unittest.mock import Mock, patch

import requests

from src.binance_client import BinanceReadOnlyClient


class BinanceTimeoutRetryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = patch.dict(
            os.environ,
            {"BINANCE_API_KEY": "test-key", "BINANCE_API_SECRET": "test-secret"},
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)

    @patch("src.binance_client.time.sleep")
    def test_time_sync_retries_timeouts_until_success(self, sleep: Mock) -> None:
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"serverTime": 1_700_000_000_000}
        session = Mock()
        session.headers = {}
        session.get.side_effect = [
            requests.ConnectTimeout(),
            requests.ReadTimeout(),
            response,
        ]

        client = BinanceReadOnlyClient(session=session, max_retries=0)
        client._sync_server_time()

        self.assertTrue(client._time_is_synchronized)
        self.assertEqual(session.get.call_count, 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [1, 2])

    @patch("src.binance_client.time.sleep")
    def test_signed_get_retries_more_than_normal_retry_limit(self, sleep: Mock) -> None:
        time_response = Mock()
        time_response.status_code = 200
        time_response.json.return_value = {"serverTime": 1_700_000_000_000}
        account_response = Mock()
        account_response.status_code = 200
        account_response.ok = True
        account_response.json.return_value = {"assets": []}
        session = Mock()
        session.headers = {}
        session.get.side_effect = [
            time_response,
            requests.ConnectTimeout(),
            requests.ConnectTimeout(),
            account_response,
        ]

        client = BinanceReadOnlyClient(session=session, max_retries=0)
        result = client.futures_account()

        self.assertEqual(result, {"assets": []})
        self.assertEqual(session.get.call_count, 4)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [1, 2])


if __name__ == "__main__":
    unittest.main()
