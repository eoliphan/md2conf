"""
Publish Markdown files to Confluence wiki.

Copyright 2022-2025, Levente Hunyadi

:see: https://github.com/hunyadi/md2conf
"""

import logging
from pathlib import Path
from typing import Optional

from .api import ConfluenceContentProperty, ConfluenceLabel, ConfluenceSession, ConfluenceStatus
from .collection import ConfluenceUserCollection
from .converter import ConfluenceDocument, attachment_name, get_volatile_attributes, get_volatile_elements
from .csf import AC_ATTR, elements_from_string
from .domain import ConfluenceDocumentOptions, ConfluencePageID
from .environment import PageError
from .extra import override, path_relative_to
from .kroki import KrokiServer
from .metadata import ConfluencePageMetadata
from .processor import Converter, DocumentNode, Processor, ProcessorFactory
from .xml import is_xml_equal, unwrap_substitute

LOGGER = logging.getLogger(__name__)


class SynchronizingProcessor(Processor):
    """
    Synchronizes a single Markdown page or a directory of Markdown pages with Confluence.
    """

    api: ConfluenceSession

    def __init__(self, api: ConfluenceSession, options: ConfluenceDocumentOptions, root_dir: Path, kroki_server: Optional[KrokiServer] = None) -> None:
        """
        Initializes a new processor instance.

        :param api: Holds information about an open session to a Confluence server.
        :param options: Options that control the generated page content.
        :param root_dir: File system directory that acts as topmost root node.
        :param kroki_server: Optional Kroki server for rendering diagrams.
        """

        super().__init__(options, api.site, root_dir, kroki_server=kroki_server)
        self.api = api

    @override
    def _synchronize_structure(self, root: DocumentNode) -> dict[str, list[str]]:
        """
        Creates the cross-reference index and synchronizes the directory tree structure with the Confluence page hierarchy.

        Creates new Confluence pages as necessary, e.g. if no page is linked in the Markdown document, or no page is found with lookup by page title.

        Updates the original Markdown document to add tags to associate the document with its corresponding Confluence page.

        :returns: Mapping of parent page ID → list of direct child page IDs in Confluence display order.
        """

        root_id = self.options.root_page_id
        if root.page_id is None and root_id is None:
            raise PageError(f"expected: root page ID in options, or explicit page ID in {root.absolute_path}")
        elif root.page_id is not None and root_id is not None:
            if root.page_id != root_id.page_id:
                raise PageError(f"mismatched inferred page ID of {root_id.page_id} and explicit page ID in {root.absolute_path}")

            real_id = root_id
        elif root_id is not None:
            real_id = root_id
        elif root.page_id is not None:
            real_id = ConfluencePageID(root.page_id)
        else:
            raise NotImplementedError("condition not exhaustive")

        parent_to_children: dict[str, list[str]] = {}
        self._synchronize_subtree(root, real_id, parent_to_children)
        return parent_to_children

    def _synchronize_subtree(
        self,
        node: DocumentNode,
        parent_id: ConfluencePageID,
        parent_to_children: dict[str, list[str]],
    ) -> None:
        if node.page_id is not None:
            # verify if page exists
            page = self.api.get_page_properties(node.page_id)

            # check if page needs re-parenting
            if page.parentId is not None and page.parentId != parent_id.page_id:
                LOGGER.info(
                    "Moving page %s from parent %s to %s",
                    node.page_id,
                    page.parentId,
                    parent_id.page_id,
                )
                self.api.move_page(node.page_id, parent_id.page_id)
            else:
                LOGGER.debug(
                    "Page %s already under correct parent %s",
                    node.page_id,
                    parent_id.page_id,
                )

            update = False
        else:
            if node.title is not None:
                # use title extracted from source metadata
                title = node.title
            else:
                # assign an auto-generated title
                digest = self._generate_hash(node.absolute_path)
                title = f"{node.absolute_path.stem} [{digest}]"

            # look up page by (possibly auto-generated) title
            page = self.api.get_or_create_page(title, parent_id.page_id)

            if page.status is ConfluenceStatus.ARCHIVED:
                # user has archived a page with this (auto-generated) title
                raise PageError(f"unable to update archived page with ID {page.id}")

            update = True

        # For v1 API, use space key from session properties (reverse lookup not supported)
        space_key = self.api.site.space_key
        if update:
            self._update_markdown(
                node.absolute_path,
                page_id=page.id,
                space_key=space_key,
            )

        data = ConfluencePageMetadata(
            page_id=page.id,
            space_key=space_key,
            title=page.title,
            synchronized=node.synchronized,
        )
        self.page_metadata.add(node.absolute_path, data)

        # Record the current Confluence child order for this page
        child_ids = self.api.get_child_page_ids(page.id)
        parent_to_children[page.id] = child_ids

        for child_node in node.children():
            self._synchronize_subtree(child_node, ConfluencePageID(page.id), parent_to_children)

    @override
    def _synchronize_order(self, tree: DocumentNode, parent_to_children: dict[str, list[str]]) -> None:
        """Reorders child pages in Confluence to match local directory sort order."""
        self._reorder_node(tree, parent_to_children)

    def _reorder_node(self, node: DocumentNode, parent_to_children: dict[str, list[str]]) -> None:
        metadata = self.page_metadata.get(node.absolute_path)
        if metadata is None:
            return

        parent_id = metadata.page_id

        local_order: list[str] = []
        for child in node.children():
            child_meta = self.page_metadata.get(child.absolute_path)
            if child_meta is not None:
                local_order.append(child_meta.page_id)

        if local_order:
            child_pages = parent_to_children.get(parent_id)
            if child_pages:
                managed_set = set(local_order)
                remote_order = [cid for cid in child_pages if cid in managed_set]

                if remote_order != local_order:
                    from .order import sort_items_in_order

                    sort_items_in_order(
                        remote_order,
                        key=lambda page_id: local_order.index(page_id),
                        insert_before=self.api.move_page_before_sibling,
                        insert_after=self.api.move_page_after_sibling,
                    )

        for child in node.children():
            self._reorder_node(child, parent_to_children)

    @override
    def _synchronize_users(self, users: set[tuple[str, str]]) -> ConfluenceUserCollection:
        collection = ConfluenceUserCollection()
        for email, name in users:
            if email in collection:
                continue
            matches = self.api.get_users(name)
            for user in matches:
                if user.email is not None and user.email.casefold() == email.casefold():
                    collection.add(email, (user.csf_attr, user.csf_value))
                    break
            else:
                LOGGER.warning("User not found in Confluence: %s <%s>", name, email)
        return collection

    @override
    def _update_page(self, page_id: ConfluencePageID, document: ConfluenceDocument, path: Path) -> None:
        """
        Saves a new version of a Confluence document.

        Invokes Confluence REST API to persist the new version.
        """

        base_path = path.parent
        for image_data in document.images:
            self.api.upload_attachment(
                page_id.page_id,
                attachment_name(path_relative_to(image_data.path, base_path)),
                attachment_path=image_data.path,
                comment=image_data.description,
            )

        for name, file_data in document.embedded_files.items():
            self.api.upload_attachment(
                page_id.page_id,
                name,
                raw_data=file_data.data,
                comment=file_data.description,
            )

        content = document.xhtml()
        LOGGER.debug("Generated Confluence Storage Format document:\n%s", content)

        title = None
        if document.title is not None:
            meta = self.page_metadata.get(path)
            if meta is not None and meta.title != document.title:
                conflicting_page_id = self.api.page_exists(document.title, space_id=self.api.space_key_to_id(meta.space_key))
                if conflicting_page_id is None:
                    title = document.title
                else:
                    LOGGER.info(
                        "Document title of %s conflicts with Confluence page title of %s",
                        path,
                        conflicting_page_id,
                    )

        # fetch existing page
        page = self.api.get_page(page_id.page_id)
        if not title:  # empty or `None`
            title = page.title

        # discard comments
        tree = elements_from_string(page.content)
        unwrap_substitute(AC_ATTR("inline-comment-marker"), tree)

        # check if page has any changes
        if page.title != title or not is_xml_equal(
            document.root,
            tree,
            skip_attributes=get_volatile_attributes(),
            skip_elements=get_volatile_elements(),
        ):
            self.api.update_page(page_id.page_id, content, title=title, version=page.version.number + 1)
        else:
            LOGGER.info("Up-to-date page: %s", page_id.page_id)

        if document.labels is not None:
            self.api.update_labels(
                page_id.page_id,
                [ConfluenceLabel(name=label, prefix="global") for label in document.labels],
            )

        if document.properties is not None:
            self.api.update_content_properties_for_page(page_id.page_id, [ConfluenceContentProperty(key, value) for key, value in document.properties.items()])

    def _update_markdown(self, path: Path, *, page_id: str, space_key: str) -> None:
        """
        Writes the Confluence page ID and space key at the beginning of the Markdown file.
        """

        with open(path, "r", encoding="utf-8") as file:
            document = file.read()

        content: list[str] = []

        # check if the file has frontmatter
        index = 0
        if document.startswith("---\n"):
            index = document.find("\n---\n", 4) + 4

            # insert the Confluence keys after the frontmatter
            content.append(document[:index])

        content.append(f"<!-- confluence-page-id: {page_id} -->")
        content.append(f"<!-- confluence-space-key: {space_key} -->")
        content.append(document[index:])

        with open(path, "w", encoding="utf-8") as file:
            file.write("\n".join(content))


class SynchronizingProcessorFactory(ProcessorFactory):
    api: ConfluenceSession

    def __init__(self, api: ConfluenceSession, options: ConfluenceDocumentOptions, kroki_server: Optional[KrokiServer] = None) -> None:
        super().__init__(options, api.site, kroki_server=kroki_server)
        self.api = api

    def create(self, root_dir: Path) -> Processor:
        return SynchronizingProcessor(self.api, self.options, root_dir, kroki_server=self.kroki_server)


class Publisher(Converter):
    """
    The entry point for Markdown to Confluence conversion.

    This is the class instantiated by the command-line application.
    """

    def __init__(self, api: ConfluenceSession, options: ConfluenceDocumentOptions, kroki_server: Optional[KrokiServer] = None) -> None:
        super().__init__(SynchronizingProcessorFactory(api, options, kroki_server=kroki_server))
