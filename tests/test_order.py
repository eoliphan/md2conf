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
