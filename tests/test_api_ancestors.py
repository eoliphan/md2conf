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
        transport: Mock = session.session  # type: ignore[assignment]
        transport.get.return_value = _json_response(_v1_page("300", "Child", ["100", "200"]))

        properties = session.get_page_properties("300")

        self.assertIn("ancestors", _requested_url(transport))
        self.assertEqual(properties.parentId, "200")

    def test_get_page_v1_requests_ancestors(self) -> None:
        session = make_session("datacenter")
        transport: Mock = session.session  # type: ignore[assignment]
        transport.get.return_value = _json_response(_v1_page("300", "Child", ["100", "200"]))

        page = session.get_page("300")

        self.assertIn("ancestors", _requested_url(transport))
        self.assertEqual(page.parentId, "200")


class TestGetAncestorIds(unittest.TestCase):
    def test_v1_returns_full_chain_root_first(self) -> None:
        session = make_session("datacenter")
        transport: Mock = session.session  # type: ignore[assignment]
        transport.get.return_value = _json_response(_v1_page("300", "Child", ["100", "200"]))

        self.assertEqual(session.get_ancestor_ids("300"), ["100", "200"])

    def test_v1_root_page_has_no_ancestors(self) -> None:
        session = make_session("datacenter")
        transport: Mock = session.session  # type: ignore[assignment]
        transport.get.return_value = _json_response(_v1_page("100", "Root", []))

        self.assertEqual(session.get_ancestor_ids("100"), [])

    def test_v2_walks_parent_chain_root_first(self) -> None:
        session = make_session("cloud")
        chain: dict[str, Optional[str]] = {"300": "200", "200": "100", "100": None}

        def fake_properties(page_id: str) -> Mock:
            properties = Mock()
            properties.id = page_id
            properties.parentId = chain[page_id]
            return properties

        with unittest.mock.patch.object(session, "get_page_properties", side_effect=fake_properties):
            self.assertEqual(session.get_ancestor_ids("300"), ["100", "200"])

    def test_v2_depth_limit_raises_rather_than_truncating(self) -> None:
        from md2conf.environment import ConfluenceError

        session = make_session("cloud")

        def cyclic_properties(page_id: str) -> Mock:
            properties = Mock()
            properties.id = page_id
            properties.parentId = "999" if page_id == "888" else "888"
            return properties

        with unittest.mock.patch.object(session, "get_page_properties", side_effect=cyclic_properties):
            with self.assertRaises(ConfluenceError):
                session.get_ancestor_ids("777")


if __name__ == "__main__":
    unittest.main()
