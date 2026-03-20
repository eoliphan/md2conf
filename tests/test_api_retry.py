"""
Tests for retry logic in the API module.

Copyright 2022-2025, Levente Hunyadi

:see: https://github.com/hunyadi/md2conf
"""

import unittest
from unittest.mock import MagicMock, patch

import requests

from md2conf.api import _retry_request


class TestRetryLogic(unittest.TestCase):
    """Tests for the _retry_request helper function."""

    def _make_response(self, status_code: int) -> requests.Response:
        """Create a mock response with the given status code."""
        response = requests.Response()
        response.status_code = status_code
        return response

    @patch("md2conf.api.time.sleep", return_value=None)
    def test_retry_on_429(self, mock_sleep: MagicMock) -> None:
        """Should retry on HTTP 429 (rate limit) and succeed on subsequent attempt."""
        func = MagicMock(
            side_effect=[
                self._make_response(429),
                self._make_response(200),
            ]
        )
        response = _retry_request(func, "http://example.com")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(func.call_count, 2)
        mock_sleep.assert_called_once()

    @patch("md2conf.api.time.sleep", return_value=None)
    def test_retry_on_500(self, mock_sleep: MagicMock) -> None:
        """Should retry on HTTP 500 (server error) and succeed on subsequent attempt."""
        func = MagicMock(
            side_effect=[
                self._make_response(500),
                self._make_response(200),
            ]
        )
        response = _retry_request(func, "http://example.com")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(func.call_count, 2)
        mock_sleep.assert_called_once()

    @patch("md2conf.api.time.sleep", return_value=None)
    def test_retry_on_503(self, mock_sleep: MagicMock) -> None:
        """Should retry on HTTP 503 (service unavailable)."""
        func = MagicMock(
            side_effect=[
                self._make_response(503),
                self._make_response(200),
            ]
        )
        response = _retry_request(func, "http://example.com")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(func.call_count, 2)

    def test_no_retry_on_200(self) -> None:
        """Should not retry on successful response."""
        func = MagicMock(return_value=self._make_response(200))
        response = _retry_request(func, "http://example.com")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(func.call_count, 1)

    def test_no_retry_on_400(self) -> None:
        """Should not retry on client errors (4xx) other than 429."""
        func = MagicMock(return_value=self._make_response(400))
        response = _retry_request(func, "http://example.com")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(func.call_count, 1)

    def test_no_retry_on_404(self) -> None:
        """Should not retry on 404 Not Found."""
        func = MagicMock(return_value=self._make_response(404))
        response = _retry_request(func, "http://example.com")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(func.call_count, 1)

    @patch("md2conf.api.time.sleep", return_value=None)
    def test_max_retries_exceeded(self, mock_sleep: MagicMock) -> None:
        """After max retries, should return last response."""
        func = MagicMock(return_value=self._make_response(500))
        response = _retry_request(func, "http://example.com", max_retries=3)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(func.call_count, 4)  # 1 initial + 3 retries
        self.assertEqual(mock_sleep.call_count, 3)

    @patch("md2conf.api.time.sleep", return_value=None)
    def test_multiple_retries_before_success(self, mock_sleep: MagicMock) -> None:
        """Should retry multiple times before succeeding."""
        func = MagicMock(
            side_effect=[
                self._make_response(500),
                self._make_response(429),
                self._make_response(200),
            ]
        )
        response = _retry_request(func, "http://example.com", max_retries=3)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(func.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)

    @patch("md2conf.api.time.sleep", return_value=None)
    @patch("md2conf.api.random.uniform", return_value=0.5)
    def test_exponential_backoff_delays(self, mock_uniform: MagicMock, mock_sleep: MagicMock) -> None:
        """Should use exponential backoff with jitter for delay calculation."""
        func = MagicMock(return_value=self._make_response(500))
        _retry_request(func, "http://example.com", max_retries=3, base_delay=1.0)

        # Expected delays: 1.0 * 2^0 + 0.5 = 1.5, 1.0 * 2^1 + 0.5 = 2.5, 1.0 * 2^2 + 0.5 = 4.5
        delays = [call.args[0] for call in mock_sleep.call_args_list]
        self.assertAlmostEqual(delays[0], 1.5)
        self.assertAlmostEqual(delays[1], 2.5)
        self.assertAlmostEqual(delays[2], 4.5)

    @patch("md2conf.api.time.sleep", return_value=None)
    def test_passes_kwargs_to_func(self, mock_sleep: MagicMock) -> None:
        """Should pass through all args and kwargs to the underlying function."""
        func = MagicMock(return_value=self._make_response(200))
        _retry_request(func, "http://example.com", headers={"Accept": "application/json"}, verify=True)
        func.assert_called_once_with("http://example.com", headers={"Accept": "application/json"}, verify=True)


if __name__ == "__main__":
    unittest.main()
