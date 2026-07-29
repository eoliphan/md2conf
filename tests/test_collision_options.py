"""
Tests for collision-guard option plumbing.

Copyright 2022-2025, Levente Hunyadi

:see: https://github.com/hunyadi/md2conf
"""

import unittest

from md2conf.domain import ConfluenceDocumentOptions
from md2conf.environment import PageCollisionError, PageError


class TestCollisionOptions(unittest.TestCase):
    def test_collision_error_is_a_page_error(self) -> None:
        self.assertTrue(issubclass(PageCollisionError, PageError))

    def test_allow_adopt_defaults_to_empty(self) -> None:
        self.assertEqual(ConfluenceDocumentOptions().allow_adopt, frozenset())

    def test_allow_adopt_accepts_page_ids(self) -> None:
        options = ConfluenceDocumentOptions(allow_adopt=frozenset({"123", "456"}))
        self.assertIn("123", options.allow_adopt)
        self.assertNotIn("789", options.allow_adopt)


if __name__ == "__main__":
    unittest.main()
