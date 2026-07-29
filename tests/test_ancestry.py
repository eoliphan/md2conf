"""
Tests for page-tree containment checks.

Copyright 2022-2025, Levente Hunyadi

:see: https://github.com/hunyadi/md2conf
"""

import unittest
from unittest.mock import Mock

from md2conf.ancestry import AncestryResolver
from md2conf.api import ConfluenceSession


def _resolver(chains: dict[str, list[str]]) -> "tuple[AncestryResolver, Mock]":
    api = Mock(spec=ConfluenceSession)
    api.get_ancestor_ids.side_effect = lambda page_id: chains[page_id]
    return AncestryResolver(api), api


class TestAncestryResolver(unittest.TestCase):
    def test_page_is_contained_in_itself(self) -> None:
        resolver, api = _resolver({"100": []})
        self.assertTrue(resolver.contains("100", "100"))
        api.get_ancestor_ids.assert_not_called()

    def test_descendant_is_contained(self) -> None:
        resolver, _ = _resolver({"300": ["100", "200"]})
        self.assertTrue(resolver.contains("100", "300"))
        self.assertTrue(resolver.contains("200", "300"))

    def test_unrelated_page_is_not_contained(self) -> None:
        resolver, _ = _resolver({"300": ["100", "200"]})
        self.assertFalse(resolver.contains("999", "300"))

    def test_chain_is_cached(self) -> None:
        resolver, api = _resolver({"300": ["100", "200"]})
        resolver.contains("100", "300")
        resolver.contains("200", "300")
        self.assertEqual(api.get_ancestor_ids.call_count, 1)

    def test_walk_populates_intermediate_chains(self) -> None:
        """A resolved chain also answers for each page along it, so siblings do not re-walk."""

        resolver, api = _resolver({"300": ["100", "200"]})
        resolver.ancestors("300")
        self.assertEqual(resolver.ancestors("200"), ["100"])
        self.assertEqual(resolver.ancestors("100"), [])
        self.assertEqual(api.get_ancestor_ids.call_count, 1)

    def test_invalidate_forces_refetch(self) -> None:
        resolver, api = _resolver({"300": ["100", "200"]})
        resolver.contains("100", "300")
        resolver.invalidate()
        resolver.contains("100", "300")
        self.assertEqual(api.get_ancestor_ids.call_count, 2)


if __name__ == "__main__":
    unittest.main()
