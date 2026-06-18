"""
Publish Markdown files to Confluence wiki.

Copyright 2022-2025, Levente Hunyadi

:see: https://github.com/hunyadi/md2conf
"""

import bisect
import logging
from collections.abc import Callable
from typing import Any, Optional, TypeVar

LOGGER = logging.getLogger(__name__)

T = TypeVar("T")


def _longest_increasing_subsequence(sequence: list[int]) -> list[int]:
    """
    Returns indices into `sequence` that form its longest increasing subsequence.

    Uses patience sorting (O(n log n)).
    """
    if not sequence:
        return []

    tails: list[int] = []
    predecessor: list[int] = [-1] * len(sequence)
    index_of_tail: list[int] = []

    for i, val in enumerate(sequence):
        pos = bisect.bisect_left(tails, val)
        if pos == len(tails):
            tails.append(val)
            index_of_tail.append(i)
        else:
            tails[pos] = val
            index_of_tail[pos] = i

        if pos > 0:
            predecessor[i] = index_of_tail[pos - 1]

    lis_indices: list[int] = []
    idx = index_of_tail[-1]
    while idx != -1:
        lis_indices.append(idx)
        idx = predecessor[idx]

    lis_indices.reverse()
    return lis_indices


def sort_items_in_order(
    items: list[T],
    *,
    key: Callable[[T], Any],
    insert_before: Callable[[T, T], None],
    insert_after: Callable[[T, T], None],
) -> None:
    """
    Reorders ``items`` to match the ordering defined by ``key``, using the minimum
    number of insert operations.

    Items in the Longest Increasing Subsequence (LIS) of the current permutation
    (relative to the target order) are left in place. All other items are moved
    by calling ``insert_before`` or ``insert_after``.

    The list ``items`` is modified in-place to reflect each move as it is made,
    so that ``insert_before`` / ``insert_after`` always see the current state.

    :param items: List of items to reorder, modified in-place.
    :param key: Function that returns the target position for each item (lower = earlier).
    :param insert_before: Callable ``(item, ref)`` — move ``item`` to just before ``ref``.
    :param insert_after: Callable ``(item, ref)`` — move ``item`` to just after ``ref``.
    """
    if len(items) <= 1:
        return

    target_ranks = [key(item) for item in items]
    lis_index_set = set(_longest_increasing_subsequence(target_ranks))

    # Track settled items by identity (LIS items are settled from the start)
    settled_ids: set[int] = {id(items[i]) for i in lis_index_set}

    # Items to move, sorted by target rank so we place them in order
    to_move = [items[i] for i in range(len(items)) if i not in lis_index_set]
    to_move.sort(key=key)

    for item in to_move:
        item_rank = key(item)

        # Find successor and predecessor among already-settled items only
        successor: Optional[T] = None
        predecessor: Optional[T] = None
        for x in items:
            if id(x) in settled_ids:
                if key(x) > item_rank:
                    successor = x
                    break
                predecessor = x

        if successor is not None:
            insert_before(item, successor)
            items.remove(item)
            items.insert(items.index(successor), item)
        else:
            # No settled item comes after; insert after the last settled predecessor
            assert predecessor is not None, "No settled predecessor or successor found"
            insert_after(item, predecessor)
            items.remove(item)
            items.insert(items.index(predecessor) + 1, item)

        # Mark this item as settled for subsequent moves
        settled_ids.add(id(item))
