"""
Publish Markdown files to Confluence wiki.

Copyright 2022-2025, Levente Hunyadi

:see: https://github.com/hunyadi/md2conf
"""

import logging
import shutil
import tempfile
import unittest
from pathlib import Path

from md2conf.skill import generate_skill
from tests.utility import TypedTestCase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(funcName)s [%(lineno)d] - %(message)s",
)


class TestGenerateSkill(TypedTestCase):
    """Tests that generate_skill produces the expected skill directory structure."""

    tmp_dir: str
    out_dir: Path

    def setUp(self) -> None:
        self.tmp_dir = tempfile.mkdtemp()
        self.out_dir = Path(self.tmp_dir)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_dir)

    def test_creates_skill_directory(self) -> None:
        """generate_skill should create an md2conf/ subdirectory."""
        result = generate_skill(self.out_dir)
        self.assertTrue(result.is_dir())
        self.assertEqual(result.name, "md2conf")

    def test_creates_skill_md(self) -> None:
        """generate_skill should create md2conf/SKILL.md."""
        generate_skill(self.out_dir)
        skill_md = self.out_dir / "md2conf" / "SKILL.md"
        self.assertTrue(skill_md.is_file())

    def test_skill_md_has_frontmatter(self) -> None:
        """SKILL.md should contain valid YAML frontmatter with required fields."""
        generate_skill(self.out_dir)
        skill_md = self.out_dir / "md2conf" / "SKILL.md"
        content = skill_md.read_text(encoding="utf-8")

        self.assertIn("name: md2conf", content)
        self.assertIn("description:", content)
        self.assertIn("version:", content)
        self.assertIn("allowed-tools:", content)
        self.assertIn("user-invocable: false", content)

    def test_skill_md_has_body(self) -> None:
        """SKILL.md should contain documentation body content."""
        generate_skill(self.out_dir)
        skill_md = self.out_dir / "md2conf" / "SKILL.md"
        content = skill_md.read_text(encoding="utf-8")

        self.assertIn("# md2conf", content)
        self.assertIn("python3 -m md2conf", content)
        self.assertIn("confluence-page-id", content)
        self.assertIn("CONFLUENCE_DOMAIN", content)

    def test_creates_cli_reference(self) -> None:
        """generate_skill should create md2conf/references/cli-help.md."""
        generate_skill(self.out_dir)
        cli_ref = self.out_dir / "md2conf" / "references" / "cli-help.md"
        self.assertTrue(cli_ref.is_file())

    def test_cli_reference_has_help_text(self) -> None:
        """cli-help.md should contain the actual CLI help output."""
        generate_skill(self.out_dir)
        cli_ref = self.out_dir / "md2conf" / "references" / "cli-help.md"
        content = cli_ref.read_text(encoding="utf-8")

        self.assertIn("# md2conf CLI Reference", content)
        self.assertIn("--local", content)
        self.assertIn("--skill", content)
        self.assertIn("mdpath", content)

    def test_frontmatter_delimiters(self) -> None:
        """SKILL.md frontmatter should be properly delimited with --- markers."""
        generate_skill(self.out_dir)
        skill_md = self.out_dir / "md2conf" / "SKILL.md"
        content = skill_md.read_text(encoding="utf-8")

        self.assertTrue(content.startswith("---\n"))
        # Should have closing --- delimiter
        parts = content.split("---")
        self.assertTrue(len(parts) >= 3)

    def test_idempotent(self) -> None:
        """Running generate_skill twice should produce the same output without errors."""
        generate_skill(self.out_dir)
        generate_skill(self.out_dir)

        skill_md = self.out_dir / "md2conf" / "SKILL.md"
        self.assertTrue(skill_md.is_file())

    def test_returns_skill_dir_path(self) -> None:
        """generate_skill should return the path to the skill directory."""
        result = generate_skill(self.out_dir)
        self.assertEqual(result, self.out_dir / "md2conf")

    def test_version_in_frontmatter(self) -> None:
        """SKILL.md frontmatter should include the package version."""
        from md2conf import __version__

        generate_skill(self.out_dir)
        skill_md = self.out_dir / "md2conf" / "SKILL.md"
        content = skill_md.read_text(encoding="utf-8")

        self.assertIn(__version__, content)


if __name__ == "__main__":
    unittest.main()
