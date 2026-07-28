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
from md2conf.api import ConfluenceSession, ConfluenceStatus
from md2conf.domain import ConfluenceDocumentOptions, ConfluencePageID
from md2conf.environment import PageCollisionError, PageError
from md2conf.metadata import ConfluenceSiteMetadata
from md2conf.processor import DocumentNode
from md2conf.publisher import SynchronizingProcessor


def _properties(page_id: str, title: str, parent_id: Optional[str], *, space_id: str = "SPACE-1") -> Mock:
    properties = Mock()
    properties.id = page_id
    properties.title = title
    properties.parentId = parent_id
    properties.spaceId = space_id
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

    def test_ancestry_api_errors_propagate_rather_than_permitting_adoption(self) -> None:
        """A transient API failure must abort the publish, never silently disable the guard."""

        processor, api = _processor(self.CHAINS)
        processor.ancestry = AncestryResolver(api)
        api.get_ancestor_ids.side_effect = RuntimeError("Confluence unavailable")

        with self.assertRaises(RuntimeError):
            processor._assert_owned("900", "Foreign Page", "200", Path("/docs/a.md"))


class TestGuardStopsWritesEndToEnd(unittest.TestCase):
    CHAINS = {"100": [], "200": ["100"], "800": [], "900": ["800"]}

    def test_explicit_foreign_id_writes_nothing(self) -> None:
        processor, api = _processor(self.CHAINS)
        processor.ancestry = AncestryResolver(api)
        api.get_page_properties.side_effect = lambda page_id: _properties(page_id, "Foreign Page", "800")

        node = DocumentNode(
            absolute_path=Path("/docs/source-inventory.md"),
            page_id="900",
            space_key=None,
            title=None,
            synchronized=True,
            users=set(),
        )

        with self.assertRaises(PageCollisionError):
            processor._synchronize_subtree(node, ConfluencePageID("200"), "200", {}, is_root=False)

        api.move_page.assert_not_called()
        api.create_page.assert_not_called()
        api.update_page.assert_not_called()
        api.move_page_before_sibling.assert_not_called()
        api.move_page_after_sibling.assert_not_called()

    def test_title_match_on_foreign_page_writes_nothing(self) -> None:
        """A same-titled page owned by another effort must be refused before it is adopted."""

        processor, api = _processor(self.CHAINS)
        processor.ancestry = AncestryResolver(api)
        api.get_page_properties.side_effect = lambda page_id: _properties(page_id, "Overview", "800")
        api.page_exists.return_value = "900"

        node = DocumentNode(
            absolute_path=Path("/docs/overview.md"),
            page_id=None,
            space_key=None,
            title="Overview",
            synchronized=True,
        )

        with self.assertRaises(PageCollisionError):
            processor._synchronize_subtree(node, ConfluencePageID("200"), "200", {}, is_root=False)

        # the guard must fire before the page is fetched for adoption
        api.get_page.assert_not_called()
        api.move_page.assert_not_called()
        api.create_page.assert_not_called()

    def test_title_lookup_is_scoped_to_the_parent_space(self) -> None:
        """Dropping the parent-properties lookup would let the title match a page in another space."""

        processor, api = _processor(self.CHAINS)
        processor.ancestry = AncestryResolver(api)
        processor._update_markdown = Mock()  # type: ignore[method-assign]
        api.get_page_properties.side_effect = lambda page_id: _properties(page_id, f"Page {page_id}", "100", space_id="SPACE-1")
        api.page_exists.return_value = None
        api.create_page.return_value = _properties("400", "Overview", "200", space_id="SPACE-1")
        api.get_child_page_ids.return_value = []

        node = DocumentNode(
            absolute_path=Path("/docs/overview.md"),
            page_id=None,
            space_key=None,
            title="Overview",
            synchronized=True,
        )

        processor._synchronize_subtree(node, ConfluencePageID("200"), "200", {}, is_root=False)

        api.page_exists.assert_called_once_with("Overview", space_id="SPACE-1")

    def test_archived_page_still_raises_after_the_inlining(self) -> None:
        """The archived-page check must survive the removal of `get_or_create_page`."""

        processor, api = _processor({"100": [], "200": ["100"], "300": ["100", "200"]})
        processor.ancestry = AncestryResolver(api)
        api.get_page_properties.side_effect = lambda page_id: _properties(page_id, "Child", "200")
        api.page_exists.return_value = "300"  # in-tree, so the containment guard passes
        archived = _properties("300", "Child", "200")
        archived.status = ConfluenceStatus.ARCHIVED
        api.get_page.return_value = archived

        node = DocumentNode(
            absolute_path=Path("/docs/a.md"),
            page_id=None,
            space_key=None,
            title="Child",
            synchronized=True,
        )

        with self.assertRaises(PageError) as context:
            processor._synchronize_subtree(node, ConfluencePageID("200"), "200", {}, is_root=False)

        self.assertNotIsInstance(context.exception, PageCollisionError)
        self.assertIn("archived", str(context.exception))


class TestDescendantBoundary(unittest.TestCase):
    """
    100 (anchor / -r)
     ├── 200 (managed root: the root document's page)
     └── 150 (a sibling sub-tree owned by another effort)
    """

    CHAINS = {"100": [], "200": ["100"], "150": ["100"]}

    def test_descendants_are_bounded_by_the_resolved_root_not_the_anchor(self) -> None:
        processor, api = _processor(self.CHAINS)
        processor.ancestry = AncestryResolver(api)
        api.get_page_properties.side_effect = lambda page_id: _properties(page_id, f"Page {page_id}", "100")
        api.get_child_page_ids.return_value = []

        root = DocumentNode(absolute_path=Path("/docs/index.md"), page_id="200", space_key=None, title=None, synchronized=True)
        root.add_child(DocumentNode(absolute_path=Path("/docs/a.md"), page_id="150", space_key=None, title=None, synchronized=True))

        # page 150 is inside the -r anchor (100) but outside the resolved root (200), so it must be refused
        with self.assertRaises(PageCollisionError) as context:
            processor._synchronize_subtree(root, ConfluencePageID("100"), "100", {}, is_root=True)

        self.assertIn("150", str(context.exception))
        self.assertIn("(200)", str(context.exception))


class TestReparentGuards(unittest.TestCase):
    """
    100 (anchor / -r)
     └── 200
          └── 300
    """

    CHAINS = {"100": [], "200": ["100"], "300": ["100", "200"]}

    def _node(self, path: str) -> Mock:
        node = Mock()
        node.absolute_path = Path(path)
        return node

    def test_root_node_equal_to_its_parent_is_not_moved(self) -> None:
        processor, api = _processor(self.CHAINS)
        processor.ancestry = AncestryResolver(api)

        processor._reparent_if_needed(self._node("/docs/index.md"), _properties("200", "Root", "100"), ConfluencePageID("200"), is_root=True)

        api.move_page.assert_not_called()

    def test_non_root_node_equal_to_its_parent_raises(self) -> None:
        processor, api = _processor(self.CHAINS)
        processor.ancestry = AncestryResolver(api)

        with self.assertRaises(PageCollisionError):
            processor._reparent_if_needed(self._node("/docs/a.md"), _properties("200", "Child", "100"), ConfluencePageID("200"), is_root=False)

        api.move_page.assert_not_called()

    def test_moving_a_page_under_its_own_descendant_raises(self) -> None:
        processor, api = _processor(self.CHAINS)
        processor.ancestry = AncestryResolver(api)

        with self.assertRaises(PageCollisionError):
            processor._reparent_if_needed(self._node("/docs/a.md"), _properties("200", "Parent", "100"), ConfluencePageID("300"), is_root=False)

        api.move_page.assert_not_called()

    def test_legitimate_move_invalidates_the_ancestor_cache(self) -> None:
        processor, api = _processor(self.CHAINS)
        processor.ancestry = AncestryResolver(api)
        processor.ancestry.contains("100", "300")
        calls_before = api.get_ancestor_ids.call_count

        processor._reparent_if_needed(self._node("/docs/a.md"), _properties("300", "Child", "200"), ConfluencePageID("100"), is_root=False)

        api.move_page.assert_called_once_with("300", "100")
        processor.ancestry.contains("100", "300")
        self.assertGreater(api.get_ancestor_ids.call_count, calls_before)

    def test_page_already_under_its_intended_parent_is_not_moved(self) -> None:
        """Without the early return, every unchanged page would incur a redundant move and cache flush."""

        processor, api = _processor(self.CHAINS)
        processor.ancestry = AncestryResolver(api)

        processor._reparent_if_needed(self._node("/docs/a.md"), _properties("300", "Child", "200"), ConfluencePageID("200"), is_root=False)

        api.move_page.assert_not_called()

    def test_page_with_unknown_parent_is_still_moved_into_the_tree(self) -> None:
        """A page adopted via `--allow-adopt` may report no parent, and must still be moved."""

        processor, api = _processor(self.CHAINS)
        processor.ancestry = AncestryResolver(api)

        processor._reparent_if_needed(self._node("/docs/a.md"), _properties("300", "Child", None), ConfluencePageID("100"), is_root=False)

        api.move_page.assert_called_once_with("300", "100")


class TestTitleBranchReparentsEndToEnd(unittest.TestCase):
    """
    100 (anchor / -r)
     └── 200 (managed root)
          └── 300
               └── 400 (title match, sitting under the wrong parent)
    """

    CHAINS = {"100": [], "200": ["100"], "300": ["100", "200"], "400": ["100", "200", "300"]}

    def test_title_match_under_wrong_parent_is_moved(self) -> None:
        """`_synchronize_subtree` must re-parent a page adopted by title match."""

        processor, api = _processor(self.CHAINS)
        processor.ancestry = AncestryResolver(api)
        processor._update_markdown = Mock()  # type: ignore[method-assign]
        api.get_page_properties.side_effect = lambda page_id: _properties(page_id, f"Page {page_id}", "300" if page_id == "400" else "100")
        api.page_exists.return_value = "400"
        api.get_page.return_value = _properties("400", "Child", "300")
        api.get_child_page_ids.return_value = []

        node = DocumentNode(
            absolute_path=Path("/docs/child.md"),
            page_id=None,
            space_key=None,
            title="Child",
            synchronized=True,
        )

        processor._synchronize_subtree(node, ConfluencePageID("200"), "200", {}, is_root=False)

        api.move_page.assert_called_once_with("400", "200")

        # the ancestor cache must have been discarded, so a post-move question re-queries the API
        calls_after_move = api.get_ancestor_ids.call_count
        processor.ancestry.contains("200", "400")
        self.assertGreater(api.get_ancestor_ids.call_count, calls_after_move)


class TestIsRootThreadedToTheGuard(unittest.TestCase):
    """
    The `is_root` flag must reach `_reparent_if_needed` from `_synchronize_subtree`'s explicit-ID branch
    with the caller's value. Passing a hardcoded flag either way breaks a live production scenario.
    """

    CHAINS = {"100": [], "200": ["100"], "300": ["100", "200"]}

    def _api(self, chains: dict[str, list[str]]) -> tuple[SynchronizingProcessor, Mock]:
        processor, api = _processor(chains)
        processor.ancestry = AncestryResolver(api)
        processor._update_markdown = Mock()  # type: ignore[method-assign]
        api.get_child_page_ids.return_value = []
        return processor, api

    def test_root_document_with_an_explicit_page_id_is_not_moved_under_itself(self) -> None:
        """The live Cloud scenario: root Markdown carries an explicit page ID equal to the resolved root."""

        processor, api = self._api(self.CHAINS)
        api.get_page_properties.side_effect = lambda page_id: _properties(page_id, "Root", "100")

        node = DocumentNode(
            absolute_path=Path("/docs/index.md"),
            page_id="200",
            space_key=None,
            title=None,
            synchronized=True,
        )

        processor._synchronize_subtree(node, ConfluencePageID("200"), "200", {}, is_root=True)

        api.move_page.assert_not_called()

    def test_child_document_mapping_to_its_parents_page_raises(self) -> None:
        """A hardcoded `is_root=True` would silently let a child overwrite its parent's page."""

        processor, api = self._api(self.CHAINS)
        api.get_page_properties.side_effect = lambda page_id: _properties(page_id, f"Page {page_id}", "100")

        node = DocumentNode(
            absolute_path=Path("/docs/a.md"),
            page_id="200",
            space_key=None,
            title=None,
            synchronized=True,
        )

        with self.assertRaises(PageCollisionError):
            processor._synchronize_subtree(node, ConfluencePageID("200"), "200", {}, is_root=False)

        api.move_page.assert_not_called()


if __name__ == "__main__":
    unittest.main()
