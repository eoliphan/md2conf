"""
Tests for page lookup ambiguity handling.

Copyright 2022-2025, Levente Hunyadi

:see: https://github.com/hunyadi/md2conf
"""

import unittest
from typing import Any
from unittest.mock import Mock

import requests

from md2conf.environment import PageCollisionError
from tests.utility import make_session


def _json_response(payload: dict[str, Any]) -> Mock:
    response = Mock(spec=requests.Response)
    response.status_code = 200
    response.text = ""
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def _v1_result(page_id: str, title: str) -> dict[str, Any]:
    return {"id": page_id, "title": title, "status": "current"}


def _v2_result(page_id: str, title: str) -> dict[str, Any]:
    return {
        "id": page_id,
        "status": "current",
        "title": title,
        "spaceId": "500",
        "parentId": "600",
        "parentType": "page",
        "position": 1,
        "authorId": "author-1",
        "ownerId": "owner-1",
        "lastOwnerId": None,
        "createdAt": "2025-01-01T00:00:00.000Z",
        "version": {"number": 1, "minorEdit": False, "createdAt": "2025-01-01T00:00:00.000Z", "message": None, "authorId": "author-1"},
    }


class TestPageExistsAmbiguityDataCenter(unittest.TestCase):
    def test_single_match_returns_id(self) -> None:
        session = make_session("datacenter")
        transport: Mock = session.session  # type: ignore[assignment]
        transport.get.return_value = _json_response({"results": [_v1_result("300", "Guide")]})

        self.assertEqual(session.page_exists("Guide", space_key="TEST"), "300")

    def test_no_match_returns_none(self) -> None:
        session = make_session("datacenter")
        transport: Mock = session.session  # type: ignore[assignment]
        transport.get.return_value = _json_response({"results": []})

        self.assertIsNone(session.page_exists("Guide", space_key="TEST"))

    def test_multiple_matches_raise_naming_ids(self) -> None:
        session = make_session("datacenter")
        transport: Mock = session.session  # type: ignore[assignment]
        transport.get.return_value = _json_response({"results": [_v1_result("300", "Guide"), _v1_result("400", "Guide")]})

        with self.assertRaises(PageCollisionError) as context:
            session.page_exists("Guide", space_key="TEST")

        message = str(context.exception)
        self.assertIn("300", message)
        self.assertIn("400", message)

    def test_query_is_scoped_to_a_single_space(self) -> None:
        """Identical titles in different spaces are legitimate, so the query must carry a space filter."""

        session = make_session("datacenter")
        transport: Mock = session.session  # type: ignore[assignment]
        transport.get.return_value = _json_response({"results": [_v1_result("300", "Guide")]})

        session.page_exists("Guide", space_key="TEST")

        self.assertEqual(transport.get.call_args.kwargs["params"]["spaceKey"], "TEST")


class TestPageExistsAmbiguityCloud(unittest.TestCase):
    def test_single_match_returns_id(self) -> None:
        session = make_session("cloud")
        transport: Mock = session.session  # type: ignore[assignment]
        transport.get.return_value = _json_response({"results": [_v2_result("300", "Guide")]})

        self.assertEqual(session.page_exists("Guide", space_id="500"), "300")

    def test_no_match_returns_none(self) -> None:
        session = make_session("cloud")
        transport: Mock = session.session  # type: ignore[assignment]
        transport.get.return_value = _json_response({"results": []})

        self.assertIsNone(session.page_exists("Guide", space_id="500"))

    def test_multiple_matches_raise_naming_ids(self) -> None:
        session = make_session("cloud")
        transport: Mock = session.session  # type: ignore[assignment]
        transport.get.return_value = _json_response({"results": [_v2_result("300", "Guide"), _v2_result("400", "Guide")]})

        with self.assertRaises(PageCollisionError) as context:
            session.page_exists("Guide", space_id="500")

        message = str(context.exception)
        self.assertIn("300", message)
        self.assertIn("400", message)

    def test_query_is_scoped_to_a_single_space(self) -> None:
        """Identical titles in different spaces are legitimate, so the query must carry a space filter."""

        session = make_session("cloud")
        transport: Mock = session.session  # type: ignore[assignment]
        transport.get.return_value = _json_response({"results": [_v2_result("300", "Guide")]})

        session.page_exists("Guide", space_id="500")

        self.assertEqual(transport.get.call_args.kwargs["params"]["space-id"], "500")


if __name__ == "__main__":
    unittest.main()
