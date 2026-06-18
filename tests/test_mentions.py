import tempfile
import unittest
from pathlib import Path

from md2conf.collection import ConfluencePageCollection, ConfluenceUserCollection
from md2conf.converter import ConfluenceDocument
from md2conf.domain import ConfluenceDocumentOptions
from md2conf.metadata import ConfluenceSiteMetadata
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


class TestConfluenceUserCollection(unittest.TestCase):
    def test_add_and_get(self) -> None:
        col: ConfluenceUserCollection = ConfluenceUserCollection()
        col.add("alice@example.com", ("ri:account-id", "557058:abc"))
        result = col.get("alice@example.com")
        self.assertEqual(result, ("ri:account-id", "557058:abc"))

    def test_get_missing_returns_none(self) -> None:
        col: ConfluenceUserCollection = ConfluenceUserCollection()
        self.assertIsNone(col.get("nobody@example.com"))

    def test_contains(self) -> None:
        col: ConfluenceUserCollection = ConfluenceUserCollection()
        col.add("alice@example.com", ("ri:account-id", "557058:abc"))
        self.assertIn("alice@example.com", col)
        self.assertNotIn("bob@example.com", col)


class TestMentionConversion(unittest.TestCase):
    """Tests for the full Markdown-to-CSF pipeline for user mentions."""

    _site_metadata: ConfluenceSiteMetadata = ConfluenceSiteMetadata(
        domain="example.com",
        base_path="/wiki/",
        space_key="SPACE_KEY",
    )

    def _create_doc(self, md_text: str, user_metadata: ConfluenceUserCollection) -> str:
        """Convert md_text to a CSF string using the given user_metadata collection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.md"
            path.write_text(md_text)
            options = ConfluenceDocumentOptions()
            _page_id, doc = ConfluenceDocument.create(
                path,
                options,
                Path(tmpdir),
                self._site_metadata,
                ConfluencePageCollection(),
                user_metadata=user_metadata,
            )
            return doc.xhtml()

    def test_v2_mention_renders_account_id(self) -> None:
        """A mailto link whose email is in user_metadata with ri:account-id renders as a user mention."""
        col = ConfluenceUserCollection()
        col.add("alice@example.com", ("ri:account-id", "557058:abc"))
        csf = self._create_doc(
            "<!-- confluence-page-id: 1 -->\nHello [Alice](mailto:alice@example.com)!",
            col,
        )
        self.assertIn('ri:account-id="557058:abc"', csf)
        self.assertNotIn("mailto:", csf)

    def test_v1_mention_renders_username(self) -> None:
        """A mailto link whose email is in user_metadata with ri:username renders as a user mention."""
        col = ConfluenceUserCollection()
        col.add("bob@example.com", ("ri:username", "bsmith"))
        csf = self._create_doc(
            "<!-- confluence-page-id: 1 -->\n[Bob](mailto:bob@example.com)",
            col,
        )
        self.assertIn('ri:username="bsmith"', csf)
        self.assertNotIn("mailto:", csf)

    def test_unknown_email_falls_back_to_mailto(self) -> None:
        """A mailto link whose email is NOT in user_metadata remains as a plain mailto anchor."""
        col = ConfluenceUserCollection()  # empty — email not registered
        csf = self._create_doc(
            "<!-- confluence-page-id: 1 -->\n[Carol](mailto:carol@example.com)",
            col,
        )
        self.assertIn("mailto:carol@example.com", csf)
        self.assertNotIn("ri:user", csf)

    def test_empty_user_metadata_falls_back_to_mailto(self) -> None:
        """When user_metadata is empty (as when user_mentions is disabled in processor), links fall back to mailto.

        Note: ConfluenceDocumentOptions.user_mentions only gates _synchronize_users in Processor.
        The converter itself always converts based on user_metadata content; passing an empty
        collection simulates the disabled-mentions path through the processor.
        """
        col = ConfluenceUserCollection()  # populated collection…
        col.add("dave@example.com", ("ri:account-id", "123"))
        # …but we pass an empty one to simulate the disabled path
        csf = self._create_doc(
            "<!-- confluence-page-id: 1 -->\n[Dave](mailto:dave@example.com)",
            ConfluenceUserCollection(),
        )
        self.assertIn("mailto:dave@example.com", csf)
        self.assertNotIn("ri:user", csf)
