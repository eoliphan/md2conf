"""
Publish Markdown files to Confluence wiki.

Copyright 2022-2025, Levente Hunyadi
"""

import logging
import unittest

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

# JSON frontmatter for title; comments supply page_id and space_key (comments after frontmatter so regex works)
id_space_title = """\
---
{ "title": "Markdown parent page" }
---

<!-- confluence-page-id: 1966122 -->
<!-- confluence-space-key: ~hunyadi -->

# Title
"""

# YAML frontmatter for title/tags/page_id; comment supplies generated_by (comment after frontmatter)
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
        with self.assertNoLogs("md2conf.scanner", level="WARNING"):
            Scanner().parse(frontmatter_only)

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
