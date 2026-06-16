# Frontmatter Priority & Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Flip metadata priority so YAML frontmatter beats HTML comment metadata, emit a deprecation warning when comment metadata is detected during sync, and add a `python -m md2conf migrate` subcommand that rewrites `.md` files to use frontmatter.

**Architecture:** Three independent changes layered on top of each other: (1) `scanner.py` gets a `parse()` method, extracted regex constants, flipped priority, and deprecation warning; (2) new `migrator.py` handles file rewriting; (3) `__main__.py` dispatches the `migrate` subcommand. All new behavior is test-driven.

**Tech Stack:** Python 3.9+, standard library (`re`, `logging`, `argparse`, `pathlib`), PyYAML (already a dependency), `unittest` for tests.

---

## Pre-flight

Before starting, verify the virtual environment is active and note the pre-existing test failures:

```bash
source .venv/bin/activate
python -m unittest discover -s tests 2>&1 | tail -5
```

Expected: 3 failures in `test_scanner.py` (pre-existing — Task 0 fixes them). Mermaid tests pass.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `md2conf/scanner.py` | Modify | Add `parse()`, extract regex constants, flip priority, add LOGGER + warning |
| `md2conf/migrator.py` | Create | Migration logic: scan files, backup, rewrite comments → frontmatter |
| `md2conf/__main__.py` | Modify | Dispatch `migrate` subcommand |
| `tests/test_scanner.py` | Modify | Rewrite to use inline strings; add priority + warning tests |
| `tests/test_migrator.py` | Create | Full coverage of migration edge cases |

---

## Task 0: Repair Pre-existing Scanner Test Failures

**Files:**
- Modify: `md2conf/scanner.py`
- Modify: `tests/test_scanner.py`

The existing `test_scanner.py` reads from sample files that are missing the expected `page_id` / `generated_by` values. Upstream rewrote these tests to use inline strings. We do the same, keeping our flat `document.page_id` API (not the upstream's `document.properties.page_id`).

- [ ] **Step 1: Add `Scanner.parse()` to `scanner.py`**

Extract the body of `Scanner.read()` into a new `parse(text: str)` method. `read()` calls `parse()`.

In `md2conf/scanner.py`, replace the `Scanner` class (lines 166-219) with:

```python
import logging

LOGGER = logging.getLogger(__name__)


class Scanner:
    def read(self, absolute_path: Path) -> "ScannedDocument":
        """Extracts essential properties from a Markdown document."""
        return self.parse(absolute_path.read_text(encoding="utf-8"))

    def parse(self, text: str) -> "ScannedDocument":
        """Extracts essential properties from a Markdown document string."""

        # extract Confluence page ID
        page_id, text = extract_value(r"<!--\s+confluence[-_]page[-_]id:\s*(\d+)\s+-->", text)

        # extract Confluence space key
        space_key, text = extract_value(r"<!--\s+confluence[-_]space[-_]key:\s*(\S+)\s+-->", text)

        # extract 'generated-by' tag text
        generated_by, text = extract_value(r"<!--\s+generated[-_]by:\s*(.*)\s+-->", text)

        title: Optional[str] = None
        tags: Optional[list[str]] = None
        synchronized: Optional[bool] = None
        properties: Optional[dict[str, JsonType]] = None
        alignment: Optional[Literal["center", "left", "right"]] = None
        skill: Optional[SkillProperties] = None

        # extract front-matter
        data, text = extract_frontmatter_properties(text)
        if data is not None:
            skill = _extract_skill_properties(data)
            p = _json_to_object(DocumentProperties, data)
            page_id = page_id or p.confluence_page_id or p.page_id
            space_key = space_key or p.confluence_space_key or p.space_key
            generated_by = generated_by or p.generated_by
            title = p.title
            tags = p.tags
            synchronized = p.synchronized
            properties = p.properties
            alignment = p.alignment

        return ScannedDocument(
            page_id=page_id,
            space_key=space_key,
            generated_by=generated_by,
            title=title,
            tags=tags,
            synchronized=synchronized,
            properties=properties,
            alignment=alignment,
            skill=skill,
            text=text,
        )
```

Note: `LOGGER` is added here; we will use it in Task 1. The priority logic (`page_id = page_id or ...`) is unchanged in this task — Task 1 flips it.

- [ ] **Step 2: Rewrite `tests/test_scanner.py` to use inline strings**

Replace the entire file with:

```python
"""
Publish Markdown files to Confluence wiki.

Copyright 2022-2025, Levente Hunyadi
"""

import logging
import unittest

from cattrs.gen import make_dict_unstructure_fn  # noqa: F401 – verify cattrs present
from strong_typing.exception import JsonTypeError

from md2conf.extra import override
from md2conf.scanner import MermaidScanner, Scanner
from tests.utility import TypedTestCase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(funcName)s [%(lineno)d] - %(message)s",
)

# A document whose only metadata is an HTML comment page-id tag
id_only = """\
<!-- confluence-page-id: 1234 -->

# Title

Text
"""

# JSON frontmatter for title; comments supply page_id and space_key
id_space_title = """\
---
{ "title": "Markdown parent page" }
---

<!-- confluence-page-id: 1966122 -->
<!-- confluence-space-key: ~hunyadi -->

# Title
"""

# YAML frontmatter for title/tags; comment supplies generated_by; page_id in frontmatter
yaml_with_comment = """\
---
page_id: "20250001"
title: "Markdown example document"
tags:
  - markdown
  - confluence
  - md
  - wiki
---

<!-- generated-by: This page has been generated with md2conf. -->

Content
"""

mermaid_frontmatter = """\
---
title: Tiny flow diagram
config:
  scale: 1
---
flowchart LR
    A[Component A] --> B[Component B]
    B --> C[Component C]
"""

mermaid_no_frontmatter = """\
flowchart LR
    A[Component A] --> B[Component B]
    B --> C[Component C]
"""

mermaid_malformed_frontmatter = """\
---
title: Tiny flow diagram
config:
  scale: 1.2.5
---
flowchart LR
    A[Component A] --> B[Component B]
    B --> C[Component C]
"""


class TestScanner(TypedTestCase):
    @override
    def setUp(self) -> None:
        self.maxDiff = 1024

    def test_tag(self) -> None:
        document = Scanner().parse(id_only)
        self.assertEqual(document.page_id, "1234")
        self.assertIsNone(document.space_key)
        self.assertIsNone(document.title)

    def test_json_frontmatter(self) -> None:
        document = Scanner().parse(id_space_title)
        self.assertEqual(document.page_id, "1966122")
        self.assertEqual(document.space_key, "~hunyadi")
        self.assertEqual(document.title, "Markdown parent page")

    def test_yaml_frontmatter(self) -> None:
        document = Scanner().parse(yaml_with_comment)
        self.assertEqual(document.page_id, "20250001")
        self.assertIsNone(document.space_key)
        self.assertEqual(document.generated_by, "This page has been generated with md2conf.")
        self.assertEqual(document.title, "Markdown example document")
        self.assertEqual(document.tags, ["markdown", "confluence", "md", "wiki"])

    def test_mermaid_frontmatter(self) -> None:
        properties = MermaidScanner().read(mermaid_frontmatter)
        if properties.config is None:
            self.fail()
        self.assertEqual(properties.config.scale, 1)

    def test_mermaid_no_frontmatter(self) -> None:
        properties = MermaidScanner().read(mermaid_no_frontmatter)
        self.assertIsNone(properties.config)

    def test_mermaid_malformed_frontmatter(self) -> None:
        with self.assertRaises(JsonTypeError):
            MermaidScanner().read(mermaid_malformed_frontmatter)


if __name__ == "__main__":
    unittest.main()
```

Note: `id_space_title` has comments AFTER the frontmatter block so the frontmatter regex (`\A---`) still matches. `yaml_with_comment` supplies `page_id` in frontmatter and `generated_by` via comment.

- [ ] **Step 3: Run the tests and verify all 6 pass**

```bash
python -m unittest tests.test_scanner -v
```

Expected output:
```
test_json_frontmatter ... ok
test_mermaid_frontmatter ... ok
test_mermaid_malformed_frontmatter ... ok
test_mermaid_no_frontmatter ... ok
test_tag ... ok
test_yaml_frontmatter ... ok
----------------------------------------------------------------------
Ran 6 tests in 0.XXs

OK
```

If `test_json_frontmatter` fails on `"Markdown parent page"` — check that `id_space_title` has the comment lines AFTER the closing `---` of the frontmatter block.

- [ ] **Step 4: Commit**

```bash
git add md2conf/scanner.py tests/test_scanner.py
git commit -m "refactor(scanner): extract parse() method; fix test_scanner to use inline strings"
```

---

## Task 1: Flip Priority + Deprecation Warning (TDD)

**Files:**
- Modify: `md2conf/scanner.py`
- Modify: `tests/test_scanner.py`

- [ ] **Step 1: Write failing tests for priority flip and deprecation warning**

Add these test methods to `TestScanner` in `tests/test_scanner.py`:

```python
# At top of file, add this constant near the other inline strings:

# Both frontmatter and comment provide page_id — frontmatter should win after the flip
both_page_id = """\
---
page_id: "frontmatter-id"
---

<!-- confluence-page-id: 9999 -->

Content
"""

# Comment provides page_id; no frontmatter equivalent — comment is fallback, still used
comment_fallback = """\
<!-- confluence-page-id: 5555 -->

Content
"""
```

```python
# Add these methods to TestScanner:

def test_frontmatter_wins_over_comment(self) -> None:
    """After priority flip, frontmatter page_id overrides HTML comment page_id."""
    document = Scanner().parse(both_page_id)
    self.assertEqual(document.page_id, "frontmatter-id")

def test_comment_fallback_still_works(self) -> None:
    """When frontmatter has no page_id, the HTML comment value is used as fallback."""
    document = Scanner().parse(comment_fallback)
    self.assertEqual(document.page_id, "5555")

def test_deprecation_warning_emitted_for_comment_metadata(self) -> None:
    """Scanning a file with HTML comment metadata emits a WARNING."""
    with self.assertLogs("md2conf.scanner", level="WARNING") as cm:
        Scanner().parse(comment_fallback)
    self.assertTrue(any("migrate" in msg for msg in cm.output))

def test_no_warning_for_frontmatter_only(self) -> None:
    """Scanning a file with only frontmatter emits no deprecation warning."""
    frontmatter_only = "---\npage_id: '123'\n---\n\nContent\n"
    # assertNoLogs requires Python 3.10+; use assertRaises(AssertionError) as a proxy
    with self.assertRaises(AssertionError):
        with self.assertLogs("md2conf.scanner", level="WARNING"):
            Scanner().parse(frontmatter_only)
```

- [ ] **Step 2: Run to confirm new tests fail**

```bash
python -m unittest tests.test_scanner.TestScanner.test_frontmatter_wins_over_comment \
    tests.test_scanner.TestScanner.test_deprecation_warning_emitted_for_comment_metadata -v
```

Expected: both FAIL. `test_frontmatter_wins_over_comment` fails because comments still win. `test_deprecation_warning_emitted_for_comment_metadata` fails because no warning is emitted.

- [ ] **Step 3: Extract regex patterns as constants and flip priority in `scanner.py`**

At the top of `Scanner.parse()` (or as module-level constants before the `Scanner` class), add:

```python
_PAGE_ID_RE = r"<!--\s+confluence[-_]page[-_]id:\s*(\d+)\s+-->"
_SPACE_KEY_RE = r"<!--\s+confluence[-_]space[-_]key:\s*(\S+)\s+-->"
_GENERATED_BY_RE = r"<!--\s+generated[-_]by:\s*(.*)\s+-->"
```

Update `Scanner.parse()`:

```python
def parse(self, text: str) -> "ScannedDocument":
    # extract Confluence page ID from HTML comment
    page_id, text = extract_value(_PAGE_ID_RE, text)

    # extract Confluence space key from HTML comment
    space_key, text = extract_value(_SPACE_KEY_RE, text)

    # extract 'generated-by' from HTML comment
    generated_by, text = extract_value(_GENERATED_BY_RE, text)

    # track whether any comment-based metadata was found (for deprecation warning)
    has_comment_metadata = page_id is not None or space_key is not None or generated_by is not None

    title: Optional[str] = None
    tags: Optional[list[str]] = None
    synchronized: Optional[bool] = None
    properties: Optional[dict[str, JsonType]] = None
    alignment: Optional[Literal["center", "left", "right"]] = None
    skill: Optional[SkillProperties] = None

    # extract front-matter; frontmatter values take priority over HTML comment values
    data, text = extract_frontmatter_properties(text)
    if data is not None:
        skill = _extract_skill_properties(data)
        p = _json_to_object(DocumentProperties, data)
        page_id = p.page_id or p.confluence_page_id or page_id        # frontmatter wins
        space_key = p.space_key or p.confluence_space_key or space_key  # frontmatter wins
        generated_by = p.generated_by or generated_by                   # frontmatter wins
        title = p.title
        tags = p.tags
        synchronized = p.synchronized
        properties = p.properties
        alignment = p.alignment

    if has_comment_metadata:
        LOGGER.warning(
            "Document uses HTML comment metadata (<!-- confluence-page-id: ... -->). "
            "Run `python -m md2conf migrate <path>` to convert to YAML frontmatter."
        )

    return ScannedDocument(
        page_id=page_id,
        space_key=space_key,
        generated_by=generated_by,
        title=title,
        tags=tags,
        synchronized=synchronized,
        properties=properties,
        alignment=alignment,
        skill=skill,
        text=text,
    )
```

- [ ] **Step 4: Run all scanner tests**

```bash
python -m unittest tests.test_scanner -v
```

Expected: all 10 tests pass (6 from Task 0 + 4 new ones).

If `test_no_warning_for_frontmatter_only` fails: it uses `assertRaises(AssertionError)` as a proxy for `assertNoLogs`. If Python ≥ 3.10 is confirmed, replace with `self.assertNoLogs("md2conf.scanner", level="WARNING")` directly.

- [ ] **Step 5: Run full test suite to check for regressions**

```bash
python -m unittest discover -s tests 2>&1 | tail -5
```

Expected: all tests pass (no regressions).

- [ ] **Step 6: Commit**

```bash
git add md2conf/scanner.py tests/test_scanner.py
git commit -m "feat(scanner): frontmatter wins over HTML comments; emit deprecation warning"
```

---

## Task 2: Create `migrator.py` (TDD)

**Files:**
- Create: `md2conf/migrator.py`
- Create: `tests/test_migrator.py`

- [ ] **Step 1: Write `tests/test_migrator.py` with failing tests**

```python
"""Tests for md2conf.migrator."""

import tempfile
import unittest
from pathlib import Path

from md2conf.migrator import migrate_file, migrate
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
        """backup=True (default) writes a .md.bak file with original content."""
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
            # one file with comment metadata
            (Path(d) / "a.md").write_text("<!-- confluence-page-id: 1 -->\nContent\n", encoding="utf-8")
            # one already-clean file
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
```

- [ ] **Step 2: Run to verify tests fail**

```bash
python -m unittest tests.test_migrator -v 2>&1 | tail -5
```

Expected: all tests fail with `ModuleNotFoundError: No module named 'md2conf.migrator'`.

- [ ] **Step 3: Create `md2conf/migrator.py`**

```python
"""
Publish Markdown files to Confluence wiki.

Copyright 2022-2025, Levente Hunyadi

:see: https://github.com/hunyadi/md2conf
"""

import logging
from pathlib import Path
from typing import Any

import yaml

from .scanner import (
    _GENERATED_BY_RE,
    _PAGE_ID_RE,
    _SPACE_KEY_RE,
    extract_frontmatter_block,
    extract_value,
)

LOGGER = logging.getLogger(__name__)


def migrate_file(path: Path, dry_run: bool = False, backup: bool = True) -> bool:
    """
    Migrates HTML comment-based metadata in a single Markdown file to YAML frontmatter.

    :returns: True if the file was (or in dry_run mode, would be) modified.
    """
    text = path.read_text(encoding="utf-8")

    # extract comment values, stripping each comment from the text
    page_id, text_clean = extract_value(_PAGE_ID_RE, text)
    space_key, text_clean = extract_value(_SPACE_KEY_RE, text_clean)
    generated_by, text_clean = extract_value(_GENERATED_BY_RE, text_clean)

    if page_id is None and space_key is None and generated_by is None:
        return False  # nothing to migrate

    # build dict of comment-sourced fields
    comment_fields: dict[str, str] = {}
    if page_id is not None:
        comment_fields["page_id"] = page_id
    if space_key is not None:
        comment_fields["space_key"] = space_key
    if generated_by is not None:
        comment_fields["generated_by"] = generated_by

    # strip leading blank lines that may result from comment removal at the file top
    text_trimmed = text_clean.lstrip("\n")

    # parse any existing frontmatter from the comment-stripped text
    frontmatter_block, body = extract_frontmatter_block(text_trimmed)

    if frontmatter_block is not None:
        existing: dict[str, Any] = yaml.safe_load(frontmatter_block) or {}
        # existing frontmatter values win; comment values fill in only missing keys
        merged: dict[str, Any] = {**comment_fields, **existing}
        new_fm = yaml.dump(merged, default_flow_style=False, allow_unicode=True).rstrip()
        new_text = f"---\n{new_fm}\n---\n{body}"
    else:
        new_fm = yaml.dump(comment_fields, default_flow_style=False, allow_unicode=True).rstrip()
        new_text = f"---\n{new_fm}\n---\n{text_trimmed}"

    if dry_run:
        LOGGER.info("Would migrate: %s (fields: %s)", path, list(comment_fields.keys()))
        return True

    if backup:
        path.with_suffix(path.suffix + ".bak").write_text(text, encoding="utf-8")

    path.write_text(new_text, encoding="utf-8")
    LOGGER.info("Migrated: %s", path)
    return True


def migrate(path: Path, dry_run: bool = False, backup: bool = True) -> tuple[int, int, int]:
    """
    Scans path (file or directory) for Markdown files with HTML comment metadata
    and migrates them to YAML frontmatter.

    :returns: Tuple of (migrated, clean, errors) counts.
    """
    files = [path] if path.is_file() else sorted(path.rglob("*.md"))

    migrated = 0
    clean = 0
    errors = 0

    for file in files:
        try:
            changed = migrate_file(file, dry_run=dry_run, backup=backup)
            if changed:
                migrated += 1
            else:
                clean += 1
        except Exception as e:
            LOGGER.error("Error migrating %s: %s", file, e)
            errors += 1

    return migrated, clean, errors
```

- [ ] **Step 4: Export the regex constants from scanner.py**

The migrator imports `_PAGE_ID_RE`, `_SPACE_KEY_RE`, `_GENERATED_BY_RE` from scanner. Make sure these are module-level string constants in `scanner.py` (added in Task 1):

```python
_PAGE_ID_RE = r"<!--\s+confluence[-_]page[-_]id:\s*(\d+)\s+-->"
_SPACE_KEY_RE = r"<!--\s+confluence[-_]space[-_]key:\s*(\S+)\s+-->"
_GENERATED_BY_RE = r"<!--\s+generated[-_]by:\s*(.*)\s+-->"
```

Confirm `extract_frontmatter_block` and `extract_value` are not prefixed with `_` (they are module-level public functions in the current `scanner.py`).

- [ ] **Step 5: Run migrator tests**

```bash
python -m unittest tests.test_migrator -v
```

Expected: all 10 tests pass.

- [ ] **Step 6: Run full test suite**

```bash
python -m unittest discover -s tests 2>&1 | tail -5
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add md2conf/migrator.py tests/test_migrator.py
git commit -m "feat(migrator): add migrate_file() and migrate() for comment→frontmatter migration"
```

---

## Task 3: Add `migrate` Subcommand to `__main__.py`

**Files:**
- Modify: `md2conf/__main__.py`

- [ ] **Step 1: Write a failing CLI test**

Create `tests/test_migrate_cli.py`:

```python
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
                # main() should complete without raising SystemExit
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
```

- [ ] **Step 2: Run to verify tests fail**

```bash
python -m unittest tests.test_migrate_cli -v 2>&1 | tail -5
```

Expected: tests fail. `test_migrate_dry_run_exits_zero` either completes (treating `migrate` as `mdpath` in the existing sync flow and failing for other reasons) or exits non-zero.

- [ ] **Step 3: Add migrate dispatch to `__main__.py`**

At the top of `md2conf/__main__.py`, add `import sys` if not already present (it is already imported).

Add a `run_migrate()` function and update `main()`. Insert before the existing `def main() -> None:`:

```python
def run_migrate(argv: list[str]) -> None:
    """Entry point for the migrate subcommand."""
    parser = argparse.ArgumentParser(
        prog="md2conf migrate",
        description="Migrate HTML comment metadata to YAML frontmatter.",
    )
    parser.add_argument("mdpath", help="Path to Markdown file or directory to migrate.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Show what would change without writing any files.",
    )
    parser.add_argument(
        "--no-backup",
        dest="backup",
        action="store_false",
        default=True,
        help="Skip creating .md.bak backup files.",
    )
    args = parser.parse_args(argv)

    from .migrator import migrate

    path = Path(args.mdpath)
    migrated, clean, errors = migrate(path, dry_run=args.dry_run, backup=args.backup)
    verb = "Would migrate" if args.dry_run else "Migrated"
    print(f"\nScanned {migrated + clean + errors} file(s).")
    print(f"  {verb}:      {migrated}")
    print(f"  Already clean: {clean}")
    if errors:
        print(f"  Errors:        {errors}")
```

At the top of `main()`, add the subcommand dispatch (before `parser = get_parser()`):

```python
def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "migrate":
        run_migrate(sys.argv[2:])
        return

    parser = get_parser()
    # ... rest of existing main() unchanged ...
```

- [ ] **Step 4: Run CLI tests**

```bash
python -m unittest tests.test_migrate_cli -v
```

Expected: both tests pass.

- [ ] **Step 5: Run full test suite**

```bash
python -m unittest discover -s tests 2>&1 | tail -5
```

Expected: all tests pass.

- [ ] **Step 6: Smoke-test the CLI manually**

```bash
# dry run on the sample directory
python -m md2conf migrate --dry-run sample/

# check help
python -m md2conf migrate --help
```

Expected: dry run prints file counts, no files modified. Help text shows `--dry-run` and `--no-backup` options.

- [ ] **Step 7: Commit**

```bash
git add md2conf/__main__.py tests/test_migrate_cli.py
git commit -m "feat(cli): add 'migrate' subcommand for comment→frontmatter migration"
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] Priority flip (frontmatter wins) — Task 1 Step 3
- [x] Deprecation warning during sync — Task 1 Step 3
- [x] Warning only when comment metadata actually present — Task 1 (`has_comment_metadata` flag)
- [x] `migrate` subcommand — Task 3
- [x] `--dry-run` — Task 2 (migrator) + Task 3 (CLI)
- [x] `--no-backup` — Task 2 (migrator) + Task 3 (CLI)
- [x] Backup `.md.bak` by default — Task 2 Step 3
- [x] Merge into existing frontmatter (don't overwrite) — Task 2 Step 3
- [x] Create new frontmatter if none exists — Task 2 Step 3
- [x] All three comment fields migrated — Task 2 tests
- [x] Dry run reports count without writing — Task 2 + Task 3

**No placeholders:** verified — all steps contain complete code.

**Type consistency:**
- `migrate_file(path, dry_run, backup) -> bool` — used consistently in Tasks 2 and 3
- `migrate(path, dry_run, backup) -> tuple[int, int, int]` — used consistently in Tasks 2 and 3
- `_PAGE_ID_RE`, `_SPACE_KEY_RE`, `_GENERATED_BY_RE` — defined in Task 1, imported in Task 2
- `extract_value`, `extract_frontmatter_block` — already public in `scanner.py`, imported in Task 2
