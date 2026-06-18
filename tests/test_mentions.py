import unittest
from md2conf.text import user_references


class TestUserReferences(unittest.TestCase):
    def test_extracts_single_user(self) -> None:
        text = "Please review with [John Smith](mailto:jsmith@example.com) before merging."
        result = user_references(text)
        self.assertEqual(result, {("jsmith@example.com", "John Smith")})

    def test_extracts_multiple_users(self) -> None:
        text = "[Alice](mailto:alice@example.com) and [Bob](mailto:bob@example.com)"
        result = user_references(text)
        self.assertEqual(result, {("alice@example.com", "Alice"), ("bob@example.com", "Bob")})

    def test_no_mentions(self) -> None:
        self.assertEqual(user_references("no mentions here"), set())

    def test_ignores_bare_mailto(self) -> None:
        self.assertEqual(user_references("send to mailto:alice@example.com directly"), set())

    def test_ignores_non_mailto_links(self) -> None:
        self.assertEqual(user_references("[Alice](https://example.com)"), set())

    def test_deduplicates(self) -> None:
        text = "[Alice](mailto:alice@example.com) and [Alice](mailto:alice@example.com)"
        self.assertEqual(len(user_references(text)), 1)
