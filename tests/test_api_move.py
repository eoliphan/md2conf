"""
Tests for page-move resilience in ConfluenceSession.

Copyright 2022-2025, Levente Hunyadi

:see: https://github.com/hunyadi/md2conf
"""

import unittest
from unittest.mock import Mock

import requests

from md2conf.api import ConfluenceSession
from md2conf.environment import ConfluenceConnectionProperties


def _make_session(deployment_type: str) -> ConfluenceSession:
    """Builds a ConfluenceSession without any network calls."""
    session_mock = Mock(spec=requests.Session)
    properties = ConfluenceConnectionProperties(
        domain="example.com",
        base_path="/wiki/",
        user_name="user",
        api_key="key",
        space_key="TEST",
        deployment_type=deployment_type,
    )
    return ConfluenceSession(
        session_mock,
        properties=properties,
        api_url="https://example.com/wiki/",
        domain="example.com",
        base_path="/wiki/",
        space_key="TEST",
    )


def _http_error_response() -> Mock:
    response = Mock(spec=requests.Response)
    response.status_code = 404
    response.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Client Error: Not Found")
    return response


class TestMovePageResilienceV1(unittest.TestCase):
    def test_move_before_sibling_swallows_http_error(self) -> None:
        confluence = _make_session("datacenter")
        confluence.session.put.return_value = _http_error_response()  # type: ignore[attr-defined]

        with self.assertLogs("md2conf.api", level="WARNING") as log_ctx:
            confluence.move_page_before_sibling("111", "222")  # must not raise

        self.assertTrue(any("111" in message and "222" in message for message in log_ctx.output))

    def test_move_after_sibling_swallows_http_error(self) -> None:
        confluence = _make_session("datacenter")
        confluence.session.put.return_value = _http_error_response()  # type: ignore[attr-defined]

        with self.assertLogs("md2conf.api", level="WARNING") as log_ctx:
            confluence.move_page_after_sibling("111", "222")  # must not raise

        self.assertTrue(any("111" in message and "222" in message for message in log_ctx.output))


class TestMovePageResilienceV2(unittest.TestCase):
    def test_move_before_sibling_swallows_http_error(self) -> None:
        confluence = _make_session("cloud")
        confluence.session.put.return_value = _http_error_response()  # type: ignore[attr-defined]

        with self.assertLogs("md2conf.api", level="WARNING") as log_ctx:
            confluence.move_page_before_sibling("111", "222")  # must not raise

        self.assertTrue(any("111" in message and "222" in message for message in log_ctx.output))

    def test_move_after_sibling_swallows_http_error(self) -> None:
        confluence = _make_session("cloud")
        confluence.session.put.return_value = _http_error_response()  # type: ignore[attr-defined]

        with self.assertLogs("md2conf.api", level="WARNING") as log_ctx:
            confluence.move_page_after_sibling("111", "222")  # must not raise

        self.assertTrue(any("111" in message and "222" in message for message in log_ctx.output))


if __name__ == "__main__":
    unittest.main()
