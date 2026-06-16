"""Tests for the migrate subcommand CLI entry point."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.utility import TypedTestCase


class TestMigrateCLI(TypedTestCase):

    def test_migrate_dry_run_exits_zero(self) -> None:
        """python -m md2conf migrate --dry-run <dir> exits with code 0."""
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "doc.md").write_text(
                "<!-- confluence-page-id: 1 -->\nContent\n", encoding="utf-8"
            )
            with patch.object(sys, "argv", ["md2conf", "migrate", "--dry-run", d]):
                from md2conf.__main__ import main
                try:
                    main()
                except SystemExit as e:
                    self.fail(f"main() raised SystemExit({e.code})")

    def test_migrate_no_args_prints_help(self) -> None:
        """python -m md2conf migrate (no path) exits with code 2 (argparse error)."""
        with patch.object(sys, "argv", ["md2conf", "migrate"]):
            from md2conf.__main__ import main
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
