"""
Containment checks over a Confluence page hierarchy.

Copyright 2022-2025, Levente Hunyadi

:see: https://github.com/hunyadi/md2conf
"""

import logging

from .api import ConfluenceSession

LOGGER = logging.getLogger(__name__)


class AncestryResolver:
    """
    Answers whether a Confluence page lies within a given page sub-tree.

    Ancestor chains are cached for the lifetime of this object. The cache is deliberately *not* held on
    `ConfluenceSession`, which outlives a single publish run; callers create one resolver per run and call
    `invalidate` whenever a page is moved.
    """

    api: ConfluenceSession

    def __init__(self, api: ConfluenceSession) -> None:
        self.api = api
        self._cache: dict[str, list[str]] = {}

    def ancestors(self, page_id: str) -> list[str]:
        """
        Returns the ancestors of a page, outermost first, excluding the page itself.
        """

        chain = self._cache.get(page_id)
        if chain is None:
            chain = self.api.get_ancestor_ids(page_id)
            self._cache[page_id] = chain

            # every prefix of the chain is the ancestry of the page that ends it, so siblings
            # elsewhere in the tree do not trigger a second walk over the same spine
            for index, ancestor_id in enumerate(chain):
                self._cache.setdefault(ancestor_id, chain[:index])

        return chain

    def contains(self, root_id: str, page_id: str) -> bool:
        """
        Whether the page is the given root, or a descendant of it.

        :param root_id: Page ID of the sub-tree root.
        :param page_id: Page ID to test.
        """

        if page_id == root_id:
            return True
        return root_id in self.ancestors(page_id)

    def invalidate(self) -> None:
        """
        Discards all cached chains. Call after any operation that re-parents a page.
        """

        self._cache.clear()
