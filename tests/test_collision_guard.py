"""
Tests for the cross-effort page collision guard.

Copyright 2022-2025, Levente Hunyadi

:see: https://github.com/hunyadi/md2conf
"""

import unittest
from pathlib import Path
from typing import Optional
from unittest.mock import Mock

from md2conf.ancestry import AncestryResolver
from md2conf.api import ConfluenceSession
from md2conf.domain import ConfluenceDocumentOptions
from md2conf.environment import PageCollisionError
from md2conf.metadata import ConfluenceSiteMetadata
from md2conf.publisher import SynchronizingProcessor


def _properties(page_id: str, title: str, parent_id: Optional[str]) -> Mock:
    properties = Mock()
    properties.id = page_id
    properties.title = title
    properties.parentId = parent_id
    properties.status = "current"
    return properties


def _processor(chains: dict[str, list[str]], *, allow_adopt: frozenset[str] = frozenset()) -> tuple[SynchronizingProcessor, Mock]:
    """Builds a real SynchronizingProcessor over a mocked ConfluenceSession."""

    api = Mock(spec=ConfluenceSession)
    api.site = ConfluenceSiteMetadata(domain="example.com", base_path="/wiki/", space_key="TEST")
    api.get_ancestor_ids.side_effect = lambda page_id: chains[page_id]

    processor = SynchronizingProcessor(api, ConfluenceDocumentOptions(allow_adopt=allow_adopt), Path("/docs"))
    return processor, api


class TestContainmentGuard(unittest.TestCase):
    """
    100 (anchor / -r)
     └── 200 (managed root: the root document's page)
          └── 300 (a child document's page)

    800 (unrelated tree)
     └── 900 (a foreign effort's page)
    """

    CHAINS = {"100": [], "200": ["100"], "300": ["100", "200"], "800": [], "900": ["800"], "901": ["800"]}

    def test_adopting_a_page_outside_the_managed_root_raises(self) -> None:
        processor, _ = _processor(self.CHAINS)
        processor.ancestry = AncestryResolver(processor.api)

        with self.assertRaises(PageCollisionError) as context:
            processor._assert_owned("900", "Foreign Page", "200", Path("/docs/source-inventory.md"))

        message = str(context.exception)
        self.assertIn("900", message)
        self.assertIn("Foreign Page", message)
        self.assertIn("--allow-adopt 900", message)

    def test_adopting_a_page_inside_the_managed_root_is_allowed(self) -> None:
        processor, _ = _processor(self.CHAINS)
        processor.ancestry = AncestryResolver(processor.api)

        processor._assert_owned("300", "Child", "200", Path("/docs/a.md"))  # must not raise

    def test_managed_root_itself_is_adoptable(self) -> None:
        processor, _ = _processor(self.CHAINS)
        processor.ancestry = AncestryResolver(processor.api)

        processor._assert_owned("200", "Root", "200", Path("/docs/index.md"))  # must not raise

    def test_allow_adopt_authorizes_exactly_one_page(self) -> None:
        processor, _ = _processor(self.CHAINS, allow_adopt=frozenset({"900"}))
        processor.ancestry = AncestryResolver(processor.api)

        processor._assert_owned("900", "Foreign Page", "200", Path("/docs/a.md"))  # authorized

        with self.assertRaises(PageCollisionError):
            processor._assert_owned("901", "Another Foreign Page", "200", Path("/docs/b.md"))


if __name__ == "__main__":
    unittest.main()
