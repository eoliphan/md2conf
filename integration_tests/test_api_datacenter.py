"""
Integration tests for Confluence Data Center API (REST API v1).

Copyright 2022-2025, Levente Hunyadi

:see: https://github.com/hunyadi/md2conf

NOTE: These tests require access to a Confluence Data Center instance.

Required environment variables:
    CONFLUENCE_DOMAIN=your-datacenter.example.com
    CONFLUENCE_PATH=/wiki/
    CONFLUENCE_USER_NAME=your-username
    CONFLUENCE_API_KEY=your-api-key
    CONFLUENCE_SPACE_KEY=TESTSPACE

Optional environment variables (with defaults):
    CONFLUENCE_DEPLOYMENT_TYPE=datacenter  # Default: 'datacenter'
    CONFLUENCE_TEST_ROOT_PAGE_ID=293077930  # Default: '293077930'

All test pages will be created as children of the test root page (default: 293077930).
Override CONFLUENCE_TEST_ROOT_PAGE_ID to use a different parent page, or set to empty
string to create pages at space root level.

The tests verify that all CRUD operations work correctly with the v1 REST API
used by Confluence Data Center and Server editions.
"""

import logging
import os
import unittest
from typing import Optional

from md2conf.api import ConfluenceAPI, ConfluenceSession, ConfluenceVersion
from md2conf.environment import ConfluenceConnectionProperties
from tests.utility import TypedTestCase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(funcName)s [%(lineno)d] - %(message)s",
)


def get_datacenter_connection() -> Optional[ConfluenceConnectionProperties]:
    """
    Get Data Center connection properties from environment variables.

    Defaults:
        - CONFLUENCE_DEPLOYMENT_TYPE: 'datacenter' (can be overridden)
        - CONFLUENCE_TEST_ROOT_PAGE_ID: '293077930' (can be overridden)

    Returns:
        ConfluenceConnectionProperties if all required variables are set, None otherwise
    """
    # Default to datacenter if not explicitly set
    deployment_type = os.getenv("CONFLUENCE_DEPLOYMENT_TYPE", "datacenter")
    if deployment_type.lower() != "datacenter":
        return None

    domain = os.getenv("CONFLUENCE_DOMAIN")
    base_path = os.getenv("CONFLUENCE_PATH", "/wiki/")
    username = os.getenv("CONFLUENCE_USER_NAME")  # Optional - if not set, uses Bearer token
    api_key = os.getenv("CONFLUENCE_API_KEY")
    space_key = os.getenv("CONFLUENCE_SPACE_KEY")

    # Require domain, api_key, and space_key (username is optional for Bearer auth)
    if not all([domain, api_key, space_key]):
        return None

    return ConfluenceConnectionProperties(
        domain=domain, base_path=base_path, user_name=username, api_key=api_key, space_key=space_key, deployment_type="datacenter"
    )


@unittest.skipUnless(
    get_datacenter_connection() is not None, "Data Center integration tests require connection environment variables (CONFLUENCE_DOMAIN, etc.)"
)
class TestDataCenterAPI(TypedTestCase):
    """Test suite for Confluence Data Center REST API v1 operations."""

    api: ConfluenceAPI
    session: ConfluenceSession
    space_key: str
    space_id: str
    test_root_page_id: Optional[str]

    @classmethod
    def setUpClass(cls) -> None:
        """Initialize the Confluence session for all tests."""
        props = get_datacenter_connection()
        assert props is not None, "Data Center connection properties not available"

        cls.api = ConfluenceAPI(props)
        cls.session = cls.api.__enter__()  # Open the session
        cls.space_key = props.space_key

        # Get space ID from space key
        cls.space_id = cls.session.space_key_to_id(cls.space_key)

        # Get test root page ID with default value
        cls.test_root_page_id = os.getenv("CONFLUENCE_TEST_ROOT_PAGE_ID", "293077930")

        # Verify we're actually using v1 API
        assert cls.session.api_version == ConfluenceVersion.VERSION_1, f"Expected VERSION_1 but got {cls.session.api_version}"

        logging.info(f"Data Center tests initialized with space: {cls.space_key} (ID: {cls.space_id}), test root page: {cls.test_root_page_id}")

    @classmethod
    def tearDownClass(cls) -> None:
        """Close the Confluence session after all tests."""
        if hasattr(cls, 'api'):
            cls.api.__exit__(None, None, None)

    def test_version_detection(self) -> None:
        """Verify that deployment_type=datacenter forces v1 API usage."""
        self.assertEqual(self.session.api_version, ConfluenceVersion.VERSION_1)

    def test_space_operations(self) -> None:
        """Test space lookup operations with v1 API."""
        # Test space_key_to_id
        space_id = self.session.space_key_to_id(self.space_key)
        self.assertIsNotNone(space_id)
        self.assertIsInstance(space_id, str)

        # Test space_id_to_key
        retrieved_key = self.session.space_id_to_key(space_id)
        self.assertEqual(retrieved_key, self.space_key)

    def test_page_creation_and_deletion(self) -> None:
        """Test creating and deleting a page using v1 API."""
        # Create a test page under test root page
        created_page = self.session.create_page(
            parent_id=self.test_root_page_id,
            title="Data Center API Test Page",
            new_content="<p>This is a test page created by the Data Center integration tests.</p>",
        )
        self.assertIsNotNone(created_page)
        self.assertEqual(created_page.title, "Data Center API Test Page")

        # Clean up - delete the page
        page_id = created_page.id
        self.session.delete_page(page_id)

    def test_page_update(self) -> None:
        """Test updating a page using v1 API."""
        # Create a test page under test root page
        created_page = self.session.create_page(
            parent_id=self.test_root_page_id,
            title="Data Center Update Test",
            new_content="<p>Original content</p>",
        )

        try:
            # Update the page
            self.session.update_page(
                page_id=created_page.id,
                content="<p>Updated content</p>",
                title="Data Center Update Test - Updated",
                version=created_page.version.number,
            )

            # Verify update
            updated_page = self.session.get_page_properties(created_page.id)
            self.assertEqual(updated_page.title, "Data Center Update Test - Updated")
        finally:
            # Clean up
            self.session.delete_page(created_page.id)

    def test_attachment_operations(self) -> None:
        """Test attachment upload and retrieval using v1 API."""
        import tempfile
        from pathlib import Path

        # Create a test page under test root page
        created_page = self.session.create_page(
            parent_id=self.test_root_page_id,
            title="Data Center Attachment Test",
            new_content="<p>Page for testing attachments</p>",
        )

        try:
            # Create a temporary file to upload
            with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as temp_file:
                temp_file.write("Test attachment content")
                temp_path = Path(temp_file.name)

            try:
                # Upload attachment
                attachment = self.session.upload_attachment(created_page.id, temp_path)
                self.assertIsNotNone(attachment)
                self.assertEqual(attachment.title, temp_path.name)

                # Retrieve attachment by name
                retrieved = self.session.get_attachment_by_name(created_page.id, temp_path.name)
                self.assertIsNotNone(retrieved)
                self.assertEqual(retrieved.id, attachment.id)
            finally:
                # Clean up temp file
                temp_path.unlink()
        finally:
            # Clean up page
            self.session.delete_page(created_page.id)

    def test_label_operations(self) -> None:
        """Test adding, retrieving, and removing labels using v1 API."""
        from md2conf.api import ConfluenceLabel

        # Create a test page under test root page
        created_page = self.session.create_page(
            parent_id=self.test_root_page_id,
            title="Data Center Label Test",
            new_content="<p>Page for testing labels</p>",
        )

        try:
            # Add labels
            label1 = ConfluenceLabel(name="datacenter-test", prefix="global")
            label2 = ConfluenceLabel(name="integration-test", prefix="global")

            added_label1 = self.session.add_label_to_page(created_page.id, label1)
            added_label2 = self.session.add_label_to_page(created_page.id, label2)

            self.assertEqual(added_label1.name, "datacenter-test")
            self.assertEqual(added_label2.name, "integration-test")

            # Retrieve labels
            labels = self.session.get_labels(created_page.id)
            label_names = [label.name for label in labels]
            self.assertIn("datacenter-test", label_names)
            self.assertIn("integration-test", label_names)

            # Remove a label
            self.session.remove_label_from_page(created_page.id, added_label1.id)

            # Verify removal
            updated_labels = self.session.get_labels(created_page.id)
            updated_label_names = [label.name for label in updated_labels]
            self.assertNotIn("datacenter-test", updated_label_names)
            self.assertIn("integration-test", updated_label_names)
        finally:
            # Clean up
            self.session.delete_page(created_page.id)

    def test_content_property_operations(self) -> None:
        """Test content property CRUD operations using v1 API."""
        from md2conf.api import ConfluenceContentProperty

        # Create a test page under test root page
        created_page = self.session.create_page(
            parent_id=self.test_root_page_id,
            title="Data Center Property Test",
            new_content="<p>Page for testing content properties</p>",
        )

        try:
            # Add property
            prop = ConfluenceContentProperty(key="test-property", value={"data": "test value", "number": 42})
            added_prop = self.session.add_content_property_to_page(created_page.id, prop)
            self.assertEqual(added_prop.key, "test-property")
            self.assertEqual(added_prop.value["data"], "test value")  # type: ignore

            # Get properties
            properties = self.session.get_content_properties_for_page(created_page.id)
            prop_keys = [p.key for p in properties]
            self.assertIn("test-property", prop_keys)

            # Update property
            updated_prop = self.session.update_content_property_for_page(created_page.id, added_prop.id, {"data": "updated value", "number": 100})
            self.assertEqual(updated_prop.value["data"], "updated value")  # type: ignore
            self.assertEqual(updated_prop.value["number"], 100)  # type: ignore

            # Remove property
            self.session.remove_content_property_from_page(created_page.id, added_prop.id)

            # Verify removal
            updated_properties = self.session.get_content_properties_for_page(created_page.id)
            updated_prop_keys = [p.key for p in updated_properties]
            self.assertNotIn("test-property", updated_prop_keys)
        finally:
            # Clean up
            self.session.delete_page(created_page.id)


if __name__ == "__main__":
    unittest.main()
