"""
Tests for Kroki diagram rendering integration.

Copyright 2022-2025, Levente Hunyadi

:see: https://github.com/hunyadi/md2conf
"""

import unittest

from md2conf.kroki import KROKI_DIAGRAM_TYPES, KROKI_FILE_EXTENSIONS


class TestKrokiRegistries(unittest.TestCase):
    def test_diagram_types_not_empty(self) -> None:
        self.assertGreater(len(KROKI_DIAGRAM_TYPES), 20)

    def test_file_extensions_not_empty(self) -> None:
        self.assertGreater(len(KROKI_FILE_EXTENSIONS), 5)

    def test_all_file_extension_types_in_diagram_types(self) -> None:
        """Every file extension must map to a known Kroki diagram type."""
        for ext, diagram_type in KROKI_FILE_EXTENSIONS.items():
            with self.subTest(ext=ext):
                self.assertIn(diagram_type, KROKI_DIAGRAM_TYPES.values())

    def test_file_extensions_start_with_dot(self) -> None:
        for ext in KROKI_FILE_EXTENSIONS:
            with self.subTest(ext=ext):
                self.assertTrue(ext.startswith("."), f"Extension {ext} must start with '.'")

    def test_known_types_present(self) -> None:
        """Verify key diagram types are registered."""
        for name in ["plantuml", "d2", "graphviz", "ditaa", "erd", "structurizr"]:
            with self.subTest(name=name):
                self.assertIn(name, KROKI_DIAGRAM_TYPES)

    def test_dot_is_alias_for_graphviz(self) -> None:
        self.assertEqual(KROKI_DIAGRAM_TYPES["dot"], "graphviz")


if __name__ == "__main__":
    unittest.main()
