import unittest

from md2conf.order import sort_items_in_order


class TestSortItemsInOrder(unittest.TestCase):
    def _run(self, items: list[str], target: list[str]) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
        """Returns (before_calls, after_calls) recorded by mock callbacks."""
        before_calls: list[tuple[str, str]] = []
        after_calls: list[tuple[str, str]] = []

        def insert_before(item: str, ref: str) -> None:
            before_calls.append((item, ref))
            idx = items.index(item)
            items.pop(idx)
            new_ref_idx = items.index(ref)
            items.insert(new_ref_idx, item)

        def insert_after(item: str, ref: str) -> None:
            after_calls.append((item, ref))
            idx = items.index(item)
            items.pop(idx)
            new_ref_idx = items.index(ref)
            items.insert(new_ref_idx + 1, item)

        sort_items_in_order(
            items,
            key=lambda x: target.index(x),
            insert_before=insert_before,
            insert_after=insert_after,
        )
        return before_calls, after_calls

    def test_already_sorted_zero_moves(self) -> None:
        items = ["a", "b", "c"]
        before, after = self._run(items, ["a", "b", "c"])
        self.assertEqual(before, [])
        self.assertEqual(after, [])

    def test_fully_reversed_n_minus_1_moves(self) -> None:
        items = ["c", "b", "a"]
        target = ["a", "b", "c"]
        before, after = self._run(items, target)
        total_moves = len(before) + len(after)
        # LIS of ["c","b","a"] in ["a","b","c"] order = length 1 → 2 moves
        self.assertEqual(total_moves, 2)
        self.assertEqual(items, target)

    def test_one_item_out_of_place(self) -> None:
        items = ["a", "c", "b"]
        target = ["a", "b", "c"]
        before, after = self._run(items, target)
        total_moves = len(before) + len(after)
        self.assertEqual(total_moves, 1)
        self.assertEqual(items, target)

    def test_single_item_zero_moves(self) -> None:
        items = ["a"]
        before, after = self._run(items, ["a"])
        self.assertEqual(before, [])
        self.assertEqual(after, [])

    def test_empty_list_zero_moves(self) -> None:
        items: list[str] = []
        before, after = self._run(items, [])
        self.assertEqual(before, [])
        self.assertEqual(after, [])

    def test_result_matches_target_order(self) -> None:
        items = ["d", "b", "a", "c"]
        target = ["a", "b", "c", "d"]
        self._run(items, target)
        self.assertEqual(items, target)


class TestSortItemsInOrderBehavior(unittest.TestCase):
    def test_foreign_pages_not_moved(self) -> None:
        """
        Pages not in the local managed set should be ignored during sort.
        This is a behavioral test of how sort_items_in_order is called
        with pre-filtered input (foreign pages removed before calling).
        """
        remote_order = ["pageA", "pageB", "pageC"]  # foreign already filtered
        local_order = ["pageA", "pageB", "pageC"]

        before_calls: list[tuple[str, str]] = []
        after_calls: list[tuple[str, str]] = []

        sort_items_in_order(
            remote_order,
            key=lambda x: local_order.index(x),
            insert_before=lambda a, b: before_calls.append((a, b)),
            insert_after=lambda a, b: after_calls.append((a, b)),
        )

        self.assertEqual(before_calls, [])
        self.assertEqual(after_calls, [])

    def test_two_items_swapped(self) -> None:
        remote_order = ["pageB", "pageA"]
        local_order = ["pageA", "pageB"]

        before_calls: list[tuple[str, str]] = []
        after_calls: list[tuple[str, str]] = []

        sort_items_in_order(
            remote_order,
            key=lambda x: local_order.index(x),
            insert_before=lambda a, b: before_calls.append((a, b)),
            insert_after=lambda a, b: after_calls.append((a, b)),
        )

        total_moves = len(before_calls) + len(after_calls)
        self.assertEqual(total_moves, 1)

    def test_empty_remote_order_no_calls(self) -> None:
        local_order = ["pageA", "pageB"]
        before_calls: list[tuple[str, str]] = []
        after_calls: list[tuple[str, str]] = []

        sort_items_in_order(
            [],
            key=lambda x: local_order.index(x),
            insert_before=lambda a, b: before_calls.append((a, b)),
            insert_after=lambda a, b: after_calls.append((a, b)),
        )

        self.assertEqual(before_calls, [])
        self.assertEqual(after_calls, [])

    def test_insert_callback_failure_propagates(self) -> None:
        """
        sort_items_in_order does not catch exceptions from insert_before/insert_after.
        Resilience to a failed move is the caller's responsibility (see api.py
        move_page_before_sibling / move_page_after_sibling), not this function's.
        """
        remote_order = ["pageB", "pageA"]
        local_order = ["pageA", "pageB"]

        def _raise(item: str, ref: str) -> None:
            raise RuntimeError("simulated move failure")

        with self.assertRaises(RuntimeError):
            sort_items_in_order(
                remote_order,
                key=lambda x: local_order.index(x),
                insert_before=_raise,
                insert_after=_raise,
            )
