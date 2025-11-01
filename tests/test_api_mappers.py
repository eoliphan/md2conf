"""
Publish Markdown files to Confluence wiki.

Copyright 2022-2025, Levente Hunyadi

:see: https://github.com/hunyadi/md2conf
"""

import logging
import unittest

from md2conf.api_mappers import (
    map_label_v1_to_domain,
    map_property_v1_to_domain,
    map_space_v1_to_id,
)
from tests.utility import TypedTestCase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(funcName)s [%(lineno)d] - %(message)s",
)


class TestSpaceMappers(TypedTestCase):
    def test_map_space_v1_to_id(self) -> None:
        """Test extracting space ID from v1 response"""
        v1_response = {"id": "789", "key": "TEST", "name": "Test Space"}

        space_id = map_space_v1_to_id(v1_response)

        self.assertEqual(space_id, "789")


class TestLabelMappers(TypedTestCase):
    def test_map_label_v1_to_domain(self) -> None:
        """Test mapping v1 label response"""
        v1_response = {"id": "label123", "name": "test-label", "prefix": "global"}

        label = map_label_v1_to_domain(v1_response)

        self.assertEqual(label.id, "label123")
        self.assertEqual(label.name, "test-label")
        self.assertEqual(label.prefix, "global")

    def test_map_label_v1_default_prefix(self) -> None:
        """Test mapping v1 label with default prefix"""
        v1_response = {"id": "label456", "name": "my-label"}

        label = map_label_v1_to_domain(v1_response)

        self.assertEqual(label.prefix, "global")  # Default


class TestPropertyMappers(TypedTestCase):
    def test_map_property_v1_to_domain(self) -> None:
        """Test mapping v1 content property response"""
        v1_response = {"id": "prop123", "key": "custom-property", "value": {"data": "test value", "count": 42}, "version": {"number": 3}}

        prop = map_property_v1_to_domain(v1_response)

        self.assertEqual(prop.id, "prop123")
        self.assertEqual(prop.key, "custom-property")
        self.assertEqual(prop.value["data"], "test value")  # type: ignore
        self.assertEqual(prop.value["count"], 42)  # type: ignore
        self.assertEqual(prop.version.number, 3)

    def test_map_property_v1_complex_value(self) -> None:
        """Test mapping v1 property with complex nested value"""
        v1_response = {"id": "prop456", "key": "metadata", "value": {"nested": {"deeply": {"value": "test"}}, "array": [1, 2, 3]}, "version": {"number": 1}}

        prop = map_property_v1_to_domain(v1_response)

        self.assertEqual(prop.key, "metadata")
        self.assertIsInstance(prop.value, dict)
        self.assertIn("nested", prop.value)  # type: ignore


if __name__ == "__main__":
    unittest.main()
