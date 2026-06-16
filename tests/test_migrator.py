"""Tests for md2conf.migrator."""

import tempfile
import unittest
from pathlib import Path

from md2conf.migrator import migrate, migrate_file
from tests.utility import TypedTestCase


class TestMigrateFile(TypedTestCase):

    def _write(self, dir: str, name: str, content: str) -> Path:
        path = Path(dir) / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_no_comment_metadata_returns_false(self) -> None:
        """File with no HTML comment metadata is untouched."""
        with tempfile.TemporaryDirectory() as d:
            path = self._write(d, "clean.md", "---\npage_id: '123'\n---\n\nContent\n")
            result = migrate_file(path, dry_run=False, backup=False)
            self.assertFalse(result)
            self.assertEqual(path.read_text(encoding="utf-8"), "---\npage_id: '123'\n---\n\nContent\n")

    def test_comment_only_creates_frontmatter(self) -> None:
        """File with only comment metadata gets a new frontmatter block."""
        content = "<!-- confluence-page-id: 42 -->\n\n# Title\n\nContent\n"
        with tempfile.TemporaryDirectory() as d:
            path = self._write(d, "doc.md", content)
            result = migrate_file(path, dry_run=False, backup=False)
            self.assertTrue(result)
            new_content = path.read_text(encoding="utf-8")
            self.assertTrue(new_content.startswith("---\n"))
            self.assertIn("page_id:", new_content)
            self.assertIn("42", new_content)
            self.assertNotIn("<!-- confluence-page-id:", new_content)

    def test_comment_and_frontmatter_merges(self) -> None:
        """Comment key not in frontmatter is merged into the frontmatter block."""
        content = "---\ntitle: My Page\n---\n\n<!-- confluence-page-id: 99 -->\n\nContent\n"
        with tempfile.TemporaryDirectory() as d:
            path = self._write(d, "doc.md", content)
            result = migrate_file(path, dry_run=False, backup=False)
            self.assertTrue(result)
            new_content = path.read_text(encoding="utf-8")
            self.assertIn("title: My Page", new_content)
            self.assertIn("page_id:", new_content)
            self.assertIn("99", new_content)
            self.assertNotIn("<!-- confluence-page-id:", new_content)

    def test_comment_does_not_overwrite_frontmatter_key(self) -> None:
        """When frontmatter already has the key, comment value is discarded."""
        content = "---\npage_id: '100'\n---\n\n<!-- confluence-page-id: 999 -->\n\nContent\n"
        with tempfile.TemporaryDirectory() as d:
            path = self._write(d, "doc.md", content)
            result = migrate_file(path, dry_run=False, backup=False)
            self.assertTrue(result)
            new_content = path.read_text(encoding="utf-8")
            self.assertIn("'100'", new_content)
            self.assertNotIn("999", new_content)
            self.assertNotIn("<!-- confluence-page-id:", new_content)

    def test_dry_run_makes_no_changes(self) -> None:
        """dry_run=True returns True but does not write the file."""
        content = "<!-- confluence-page-id: 5 -->\n\nContent\n"
        with tempfile.TemporaryDirectory() as d:
            path = self._write(d, "doc.md", content)
            result = migrate_file(path, dry_run=True, backup=False)
            self.assertTrue(result)
            self.assertEqual(path.read_text(encoding="utf-8"), content)

    def test_backup_created_by_default(self) -> None:
        """backup=True writes a .md.bak file with original content."""
        content = "<!-- confluence-page-id: 7 -->\n\nContent\n"
        with tempfile.TemporaryDirectory() as d:
            path = self._write(d, "doc.md", content)
            migrate_file(path, dry_run=False, backup=True)
            backup = path.with_suffix(".md.bak")
            self.assertTrue(backup.exists())
            self.assertEqual(backup.read_text(encoding="utf-8"), content)

    def test_no_backup_flag_skips_backup(self) -> None:
        """backup=False skips creating the .md.bak file."""
        content = "<!-- confluence-page-id: 8 -->\n\nContent\n"
        with tempfile.TemporaryDirectory() as d:
            path = self._write(d, "doc.md", content)
            migrate_file(path, dry_run=False, backup=False)
            self.assertFalse(path.with_suffix(".md.bak").exists())

    def test_multiple_comment_fields(self) -> None:
        """All three comment fields (page_id, space_key, generated_by) are migrated."""
        content = (
            "<!-- confluence-page-id: 11 -->\n"
            "<!-- confluence-space-key: MYSPACE -->\n"
            "<!-- generated-by: md2conf tool -->\n\n"
            "Content\n"
        )
        with tempfile.TemporaryDirectory() as d:
            path = self._write(d, "doc.md", content)
            migrate_file(path, dry_run=False, backup=False)
            new_content = path.read_text(encoding="utf-8")
            self.assertIn("page_id:", new_content)
            self.assertIn("space_key:", new_content)
            self.assertIn("generated_by:", new_content)
            self.assertNotIn("<!--", new_content)


class TestMigrateDirectory(TypedTestCase):

    def test_migrate_counts(self) -> None:
        """migrate() returns correct (migrated, clean, errors) counts."""
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a.md").write_text("<!-- confluence-page-id: 1 -->\nContent\n", encoding="utf-8")
            (Path(d) / "b.md").write_text("---\npage_id: '2'\n---\nContent\n", encoding="utf-8")

            migrated, clean, errors = migrate(Path(d), dry_run=False, backup=False)
            self.assertEqual(migrated, 1)
            self.assertEqual(clean, 1)
            self.assertEqual(errors, 0)

    def test_migrate_dry_run_no_writes(self) -> None:
        """migrate() with dry_run=True changes no files."""
        content = "<!-- confluence-page-id: 3 -->\nContent\n"
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "doc.md"
            path.write_text(content, encoding="utf-8")
            migrate(Path(d), dry_run=True, backup=False)
            self.assertEqual(path.read_text(encoding="utf-8"), content)


if __name__ == "__main__":
    unittest.main()
