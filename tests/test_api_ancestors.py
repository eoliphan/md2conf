"""
Tests for ancestor retrieval and v1 ancestor expansion.

Copyright 2022-2025, Levente Hunyadi

:see: https://github.com/hunyadi/md2conf
"""

import unittest
import unittest.mock
from typing import Any, Optional
from unittest.mock import Mock

import requests

from tests.utility import make_session


def _json_response(payload: dict[str, Any]) -> Mock:
    response = Mock(spec=requests.Response)
    response.status_code = 200
    response.text = ""
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def _v1_page(page_id: str, title: str, ancestors: list[str]) -> dict[str, Any]:
    return {
        "id": page_id,
        "title": title,
        "status": "current",
        "space": {"id": "1", "key": "TEST"},
        "version": {"number": 1},
        "history": {"createdBy": {"accountId": "user"}},
        "createdDate": "2026-01-01T00:00:00.000Z",
        "ancestors": [{"id": a} for a in ancestors],
        "body": {"storage": {"value": "", "representation": "storage"}},
    }


def _requested_url(transport: Mock) -> str:
    """Returns the URL of the most recent GET, which is where _get encodes its query."""

    return str(transport.get.call_args.args[0])


class TestV1AncestorExpansion(unittest.TestCase):
    def test_get_page_properties_v1_requests_ancestors(self) -> None:
        session = make_session("datacenter")
        transport: Mock = session.session
        transport.get.return_value = _json_response(_v1_page("300", "Child", ["100", "200"]))

        properties = session.get_page_properties("300")

        self.assertIn("ancestors", _requested_url(transport))
        self.assertEqual(properties.parentId, "200")

    def test_get_page_v1_requests_ancestors(self) -> None:
        session = make_session("datacenter")
        transport: Mock = session.session
        transport.get.return_value = _json_response(_v1_page("300", "Child", ["100", "200"]))

        page = session.get_page("300")

        self.assertIn("ancestors", _requested_url(transport))
        self.assertEqual(page.parentId, "200")


if __name__ == "__main__":
    unittest.main()
