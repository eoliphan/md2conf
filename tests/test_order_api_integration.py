"""
Integration-level test proving that ``sort_items_in_order`` (md2conf/order.py) composes
correctly with the real ``ConfluenceSession.move_page_before_sibling`` /
``move_page_after_sibling`` (md2conf/api.py) resilience behavior.

Unlike tests/test_order.py (uses plain mock/lambda callbacks) and
tests/test_api_move.py (calls move_page_before_sibling/move_page_after_sibling directly,
one call at a time), this test wires a real ConfluenceSession, whose HTTP layer is mocked
to fail on exactly one move, directly into sort_items_in_order as the insert_before /
insert_after callables. It proves that when one move raises internally (HTTPError from a
404 response), the whole sort still completes without raising, and moves for OTHER items
scheduled after the failing one are still attempted.

Copyright 2022-2025, Levente Hunyadi

:see: https://github.com/hunyadi/md2conf
"""

import unittest
from unittest.mock import Mock

import requests

from md2conf.api import ConfluenceSession
from md2conf.environment import ConfluenceConnectionProperties
from md2conf.order import sort_items_in_order


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


def _success_response() -> Mock:
    response = Mock(spec=requests.Response)
    response.status_code = 200
    response.raise_for_status = Mock()
    return response


class TestSortItemsInOrderWithRealSession(unittest.TestCase):
    """
    Fixture: remote_order = ["pageD", "pageB", "pageA", "pageC"], target order =
    ["pageA", "pageB", "pageC", "pageD"]. This requires exactly two moves: a
    move_page_before_sibling("pageB", "pageC") call followed by a
    move_page_after_sibling("pageD", "pageC") call. The first call issued against
    session.put is made to fail with an HTTPError (404); the rest succeed. This proves
    the failure of the first move does not abort the sort: the second move is still
    attempted.
    """

    def _run_with_first_call_failing(self, deployment_type: str) -> ConfluenceSession:
        confluence = _make_session(deployment_type)

        call_count = {"n": 0}

        def put_side_effect(*args: object, **kwargs: object) -> Mock:
            call_count["n"] += 1
            if call_count["n"] == 1:
                return _http_error_response()
            return _success_response()

        confluence.session.put.side_effect = put_side_effect  # type: ignore[attr-defined]

        remote_order = ["pageD", "pageB", "pageA", "pageC"]
        local_order = ["pageA", "pageB", "pageC", "pageD"]

        # Must not raise, even though the first move's HTTP call fails.
        sort_items_in_order(
            remote_order,
            key=lambda x: local_order.index(x),
            insert_before=confluence.move_page_before_sibling,
            insert_after=confluence.move_page_after_sibling,
        )

        return confluence

    def test_datacenter_v1_later_move_still_attempted_after_earlier_failure(self) -> None:
        confluence = self._run_with_first_call_failing("datacenter")

        # More than one PUT call proves the sort continued past the failed move and
        # attempted the subsequent move for the other item, instead of aborting.
        self.assertGreater(confluence.session.put.call_count, 1)  # type: ignore[attr-defined]
        # The failing call is not retried into extra PUTs (it raises HTTPError immediately),
        # so a second PUT call can only be the pageD/pageC move -- confirm it explicitly.
        urls_called = [call.args[0] for call in confluence.session.put.call_args_list]  # type: ignore[attr-defined]
        self.assertTrue(any("pageD" in url for url in urls_called))

    def test_cloud_v2_later_move_still_attempted_after_earlier_failure(self) -> None:
        confluence = self._run_with_first_call_failing("cloud")

        self.assertGreater(confluence.session.put.call_count, 1)  # type: ignore[attr-defined]
        urls_called = [call.args[0] for call in confluence.session.put.call_args_list]  # type: ignore[attr-defined]
        self.assertTrue(any("pageD" in url for url in urls_called))


if __name__ == "__main__":
    unittest.main()
