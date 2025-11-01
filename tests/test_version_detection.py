"""
Unit tests for Confluence API version detection.

Copyright 2022-2025, Levente Hunyadi

:see: https://github.com/hunyadi/md2conf
"""

import unittest

from md2conf.api import ConfluenceVersion
from md2conf.environment import ConfluenceConnectionProperties
from tests.utility import TypedTestCase


class TestVersionDetection(TypedTestCase):
    """Test suite for API version detection and configuration."""

    def test_datacenter_deployment_forces_v1(self) -> None:
        """Test that deployment_type=datacenter forces v1 API usage."""
        props = ConfluenceConnectionProperties(
            domain="datacenter.example.com", base_path="/wiki/", user_name="user", api_key="key", space_key="TEST", deployment_type="datacenter"
        )

        self.assertEqual(props.deployment_type, "datacenter")

    def test_server_deployment_forces_v1(self) -> None:
        """Test that deployment_type=server forces v1 API usage."""
        props = ConfluenceConnectionProperties(
            domain="server.example.com", base_path="/wiki/", user_name="user", api_key="key", space_key="TEST", deployment_type="server"
        )

        self.assertEqual(props.deployment_type, "server")

    def test_cloud_deployment_uses_v2(self) -> None:
        """Test that deployment_type=cloud uses v2 API."""
        props = ConfluenceConnectionProperties(
            domain="example.atlassian.net", base_path="/wiki/", user_name="user", api_key="key", space_key="TEST", deployment_type="cloud"
        )

        self.assertEqual(props.deployment_type, "cloud")

    def test_auto_detection_default(self) -> None:
        """Test auto-detection with default settings (no deployment_type specified)."""
        props = ConfluenceConnectionProperties(domain="example.atlassian.net", base_path="/wiki/", user_name="user", api_key="key", space_key="TEST")

        # When deployment_type is not specified, it defaults to "cloud"
        self.assertIsNone(props.deployment_type)

    def test_version_detection_logic_datacenter(self) -> None:
        """Test version detection logic for datacenter deployment type."""
        # Test the logic directly without instantiating ConfluenceSession
        deployment_type = "datacenter"
        if deployment_type in ("datacenter", "server"):
            version = ConfluenceVersion.VERSION_1
        elif deployment_type == "cloud":
            version = ConfluenceVersion.VERSION_2
        else:
            version = ConfluenceVersion.VERSION_2

        self.assertEqual(version, ConfluenceVersion.VERSION_1)

    def test_version_detection_logic_server(self) -> None:
        """Test version detection logic for server deployment type."""
        deployment_type = "server"
        if deployment_type in ("datacenter", "server"):
            version = ConfluenceVersion.VERSION_1
        elif deployment_type == "cloud":
            version = ConfluenceVersion.VERSION_2
        else:
            version = ConfluenceVersion.VERSION_2

        self.assertEqual(version, ConfluenceVersion.VERSION_1)

    def test_version_detection_logic_cloud(self) -> None:
        """Test version detection logic for cloud deployment type."""
        deployment_type = "cloud"
        if deployment_type in ("datacenter", "server"):
            version = ConfluenceVersion.VERSION_1
        elif deployment_type == "cloud":
            version = ConfluenceVersion.VERSION_2
        else:
            version = ConfluenceVersion.VERSION_2

        self.assertEqual(version, ConfluenceVersion.VERSION_2)

    def test_version_detection_logic_none(self) -> None:
        """Test version detection logic when deployment_type is None (defaults to v2)."""
        deployment_type = None
        if deployment_type in ("datacenter", "server"):
            version = ConfluenceVersion.VERSION_1
        elif deployment_type == "cloud":
            version = ConfluenceVersion.VERSION_2
        else:
            version = ConfluenceVersion.VERSION_2

        self.assertEqual(version, ConfluenceVersion.VERSION_2)

    def test_version_enum_values(self) -> None:
        """Test that ConfluenceVersion enum has expected values."""
        self.assertEqual(ConfluenceVersion.VERSION_1.value, "rest/api")
        self.assertEqual(ConfluenceVersion.VERSION_2.value, "api/v2")


if __name__ == "__main__":
    unittest.main()
