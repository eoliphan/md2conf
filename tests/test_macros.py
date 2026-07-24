"""
Publish Markdown files to Confluence wiki.

Copyright 2022-2025, Levente Hunyadi

:see: https://github.com/hunyadi/md2conf
"""

import html as htmlmod
import logging
import re
import tempfile
import unittest
import unittest.mock
from pathlib import Path
from typing import Optional

from md2conf import macros
from md2conf.macros import (
    MacroContext,
    MacroExpander,
    expand_embed_html,
    expand_macros,
)
from tests.utility import TypedTestCase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(funcName)s [%(lineno)d] - %(message)s",
)


def unescape_srcdoc(escaped: str) -> str:
    "Reverses `_escape_srcdoc` the way a browser resolves a `srcdoc` attribute (numeric refs included)."

    return htmlmod.unescape(escaped)


def extract_srcdoc(result: str) -> str:
    "Recovers the original document text from the `srcdoc` attribute of an expansion result."

    # the escaped content contains no raw double quote, so the first `"` closes the attribute
    match = re.search(r'<iframe srcdoc="(.*?)"\s+style=', result, re.DOTALL)
    if match is None:
        raise AssertionError(f"no iframe srcdoc found in: {result[:200]}")
    return unescape_srcdoc(match.group(1))


class TestEmbedHtmlMacro(TypedTestCase):
    "Tests for the `embed_html` macro expander."

    base_dir: Path
    root_dir: Path

    def setUp(self) -> None:
        self.maxDiff = None
        self._tmp = tempfile.TemporaryDirectory()
        self.root_dir = Path(self._tmp.name).resolve()
        self.base_dir = self.root_dir
        self.addCleanup(self._tmp.cleanup)

    def write(self, name: str, content: bytes) -> Path:
        path = self.base_dir / name
        path.write_bytes(content)
        return path

    def context(self) -> MacroContext:
        return MacroContext(base_dir=self.base_dir, root_dir=self.root_dir)

    def expand(self, params: str, context: Optional[MacroContext] = None) -> str:
        return expand_embed_html(params, context if context is not None else self.context())

    # -- structure -----------------------------------------------------------

    def test_produces_csf_wrapped_html_macro_with_iframe_srcdoc(self) -> None:
        self.write("page.html", b"<html><body>hi</body></html>")
        result = self.expand("page.html")

        self.assertStartsWith(result, "<!-- csf: ")
        self.assertTrue(result.endswith(" -->"))
        self.assertIn('<ac:structured-macro ac:name="html">', result)
        self.assertIn("<ac:plain-text-body><![CDATA[", result)
        self.assertIn('<iframe srcdoc="', result)

    def test_uses_no_script_and_no_base64(self) -> None:
        "An inline script trips Confluence's storage sanitizer and never executes via innerHTML."

        self.write("page.html", b"<html><body>hi</body></html>")
        result = self.expand("page.html")

        self.assertNotIn("<script", result)
        self.assertNotIn("atob", result)
        self.assertNotIn("base64", result)
        self.assertNotIn("TextDecoder", result)

    def test_srcdoc_round_trips_the_document(self) -> None:
        content = "<html><body>plain</body></html>"
        self.write("page.html", content.encode("utf-8"))

        self.assertEqual(extract_srcdoc(self.expand("page.html")), content)

    def test_newlines_are_preserved(self) -> None:
        content = "<html>\n<body>\nhi\n</body>\n</html>"
        self.write("page.html", content.encode("utf-8"))

        self.assertEqual(extract_srcdoc(self.expand("page.html")), content)

    # -- escaping ------------------------------------------------------------

    def test_entity_escaping(self) -> None:
        self.write("page.html", b'<html>a & b "q" it')
        result = self.expand("page.html")
        match = re.search(r'<iframe srcdoc="(.*?)"\s+style=', result, re.DOTALL)
        assert match is not None
        srcdoc = match.group(1)

        self.assertNotIn("<html>", srcdoc)
        self.assertIn("&lt;html&gt;", srcdoc)
        self.assertIn("&amp;", srcdoc)
        self.assertIn("&quot;", srcdoc)

    def test_ampersand_is_escaped_first(self) -> None:
        'Escaping `&` last would double-escape the entities introduced for `<`, `>` and `"`.'

        content = "<a> & </a>"
        self.write("page.html", content.encode("utf-8"))
        result = self.expand("page.html")

        self.assertNotIn("&amp;lt;", result)
        self.assertEqual(extract_srcdoc(result), content)

    # -- destructive payloads ------------------------------------------------

    def test_bare_arrow_in_content_is_escaped_and_does_not_truncate(self) -> None:
        "A standalone `-->` would otherwise truncate the CSF comment carrier."

        content = '<html><script>const marker = "-->";</script></html>'
        self.write("page.html", content.encode("utf-8"))
        result = self.expand("page.html")

        self.assertNotIn("-->", result[:-4], "no --> may appear before the closing CSF comment")
        self.assertTrue(result.endswith("</ac:structured-macro> -->"))
        self.assertEqual(extract_srcdoc(result), content)

    def test_cdata_terminator_in_content_is_escaped(self) -> None:
        content = '<html><script>const s = "]]>";</script></html>'
        self.write("page.html", content.encode("utf-8"))
        result = self.expand("page.html")

        self.assertEqual(result.count("]]>"), 1, "only the closing CDATA may contain ]]>")
        self.assertEqual(extract_srcdoc(result), content)

    def test_html_comment_in_content_is_preserved(self) -> None:
        content = '<html><script>const t = "<!-- keep me -->";</script></html>'
        self.write("page.html", content.encode("utf-8"))

        self.assertEqual(extract_srcdoc(self.expand("page.html")), content)

    def test_line_comment_javascript_is_preserved(self) -> None:
        content = "<html><script>\n// a line comment\nwindow.x = 1;\n</script></html>"
        self.write("page.html", content.encode("utf-8"))

        self.assertEqual(extract_srcdoc(self.expand("page.html")), content)

    def test_xml_invalid_control_char_is_encoded_as_numeric_reference(self) -> None:
        "A raw form feed would make the whole document fail XML parsing; a `&#12;` inside CDATA is inert."

        self.write("page.html", b"<html>a\x0cb</html>")
        result = self.expand("page.html")

        self.assertNotIn("\x0c", result)
        self.assertIn("&#12;", result)
        self.assertEqual(extract_srcdoc(result), "<html>a\x0cb</html>")

    def test_tab_and_cr_are_encoded_so_markdown_cannot_rewrite_them(self) -> None:
        "Markdown expands a raw tab to spaces and normalizes CR to LF; numeric references survive."

        self.write("page.html", b"a\tb\rc")
        result = self.expand("page.html")

        self.assertIn("&#9;", result)
        self.assertIn("&#13;", result)
        self.assertEqual(extract_srcdoc(result), "a\tb\rc")

    def test_newline_is_kept_literal_not_encoded(self) -> None:
        self.write("page.html", b"a\nb")
        result = self.expand("page.html")

        self.assertNotIn("&#10;", result)
        self.assertIn("\n", extract_srcdoc(result))

    def test_invalid_utf8_renders_with_replacement_and_warns(self) -> None:
        content = b"<html>\xff\xfe</html>"
        self.write("page.html", content)

        with self.assertLogs("md2conf.macros", level="WARNING") as captured:
            result = self.expand("page.html")

        self.assertEqual(extract_srcdoc(result), content.decode("utf-8", errors="replace"))
        self.assertTrue(any("not valid UTF-8" in message for message in captured.output))

    def test_valid_utf8_does_not_warn(self) -> None:
        self.write("page.html", "<html><body>café — naïve</body></html>".encode("utf-8"))

        # `assertNoLogs` requires Python 3.10; this package supports 3.9
        with unittest.mock.patch.object(macros.LOGGER, "warning") as warning:
            self.expand("page.html")

        self.assertListEqual([str(call) for call in warning.call_args_list], [])

    # -- failure paths -------------------------------------------------------

    def test_missing_file_returns_original_text_unchanged(self) -> None:
        self.assertEqual(self.expand("nonexistent.html"), "<!-- macro:embed_html: nonexistent.html -->")

    def test_empty_path_returns_original_text_unchanged(self) -> None:
        self.assertEqual(self.expand(""), "<!-- macro:embed_html:  -->")

    def test_path_outside_root_dir_is_refused(self) -> None:
        "Otherwise any readable file could be inlined into a Confluence page."

        docs = self.root_dir / "docs"
        docs.mkdir()
        (self.root_dir / "secret.html").write_bytes(b"<html>secret</html>")

        context = MacroContext(base_dir=docs, root_dir=docs)

        self.assertEqual(expand_embed_html("../secret.html", context), "<!-- macro:embed_html: ../secret.html -->")

    def test_symlink_escaping_root_dir_is_refused(self) -> None:
        docs = self.root_dir / "docs"
        docs.mkdir()
        (self.root_dir / "secret.html").write_bytes(b"<html>secret</html>")
        (docs / "link.html").symlink_to(self.root_dir / "secret.html")

        self.assertEqual(
            expand_embed_html("link.html", MacroContext(base_dir=docs, root_dir=docs)),
            "<!-- macro:embed_html: link.html -->",
        )

    def test_absolute_path_is_refused(self) -> None:
        secret = self.root_dir / "secret.html"
        secret.write_bytes(b"<html>secret</html>")

        self.assertEqual(self.expand(str(secret)), f"<!-- macro:embed_html: {secret} -->")

    def test_without_context_nothing_is_read(self) -> None:
        readable = self.root_dir / "page.html"
        readable.write_bytes(b"<html>readable</html>")

        self.assertEqual(expand_embed_html(str(readable), None), f"<!-- macro:embed_html: {readable} -->")

    def test_directory_instead_of_file_returns_original_text(self) -> None:
        (self.base_dir / "subdir").mkdir()

        self.assertEqual(self.expand("subdir"), "<!-- macro:embed_html: subdir -->")

    def test_relative_path_without_context_is_refused(self) -> None:
        self.assertEqual(
            expand_embed_html("definitely-not-here.html", None),
            "<!-- macro:embed_html: definitely-not-here.html -->",
        )

    # -- parameters ----------------------------------------------------------

    def test_default_dimensions_and_title(self) -> None:
        self.write("page.html", b"<html></html>")
        result = self.expand("page.html")

        self.assertIn("width:100%;height:1040px;border:0", result)
        self.assertIn('title="Embedded HTML"', result)
        self.assertIn('loading="lazy"', result)

    def test_named_dimension_and_title_parameters(self) -> None:
        self.write("page.html", b"<html></html>")
        result = self.expand("page.html, height=1400px, width=90%, title=Traceability Explorer")

        self.assertIn("width:90%;height:1400px;border:0", result)
        self.assertIn('title="Traceability Explorer"', result)

    def test_named_parameters_are_case_insensitive(self) -> None:
        self.write("page.html", b"<html></html>")
        result = self.expand("page.html, HEIGHT=200px, Width=80%")

        self.assertIn("width:80%;height:200px", result)

    def test_path_containing_comma_and_equals(self) -> None:
        content = "<html>odd</html>"
        self.write("a,b=c.html", content.encode("utf-8"))
        result = self.expand("a,b=c.html, height=200px")

        self.assertEqual(extract_srcdoc(result), content)
        self.assertIn("height:200px", result)

    def test_quoted_path_is_unquoted_once(self) -> None:
        content = "<html>quoted</html>"
        self.write("page.html", content.encode("utf-8"))

        self.assertEqual(extract_srcdoc(self.expand('"page.html"')), content)

    def test_invalid_dimensions_fall_back_to_defaults(self) -> None:
        self.write("page.html", b"<html></html>")
        result = self.expand("page.html, height=drop table, width=100%' onload='alert(1)")

        self.assertIn("width:100%;height:1040px;border:0", result)
        self.assertNotIn("onload", result)

    def test_title_is_escaped(self) -> None:
        self.write("page.html", b"<html></html>")
        result = self.expand("""page.html, title=a'b&c<d>e"f""")

        self.assertIn("&#39;", result)
        self.assertIn("&amp;", result)
        self.assertNotIn("a'b", result)

    def test_title_is_neutralized_in_the_generated_body(self) -> None:
        self.write("page.html", b"<html></html>")
        result = self.expand("page.html, title=x --> y ]]> z")

        self.assertNotIn("-->", result[:-4])
        self.assertEqual(result.count("]]>"), 1)

    def test_no_sandbox_attribute(self) -> None:
        "The embedded document needs its inline scripts to run."

        self.write("page.html", b"<html></html>")

        self.assertNotIn("sandbox", self.expand("page.html"))


class TestEmbedHtmlEndToEnd(TypedTestCase):
    """
    Drives `embed_html` through the full conversion pipeline.

    The pipeline is where the naive approaches failed: the payload is carried inside an
    HTML comment terminated by the first `-->`, run through Markdown, parsed as XML, and
    finally walked by a converter that used to rewrite every newline in element text to a
    space. These tests assert against the final `doc.xhtml()` rather than the expander's
    return value -- the assertion that would have caught both the original newline bug and
    the live-Confluence empty-body bug.
    """

    def setUp(self) -> None:
        self.maxDiff = None
        self._tmp = tempfile.TemporaryDirectory()
        self.root_dir = Path(self._tmp.name).resolve()
        self.addCleanup(self._tmp.cleanup)

    def convert(self, html: bytes, params: str = "explorer.html") -> str:
        from md2conf.collection import ConfluencePageCollection
        from md2conf.converter import ConfluenceDocument
        from md2conf.domain import ConfluenceDocumentOptions
        from md2conf.metadata import ConfluenceSiteMetadata

        (self.root_dir / "explorer.html").write_bytes(html)
        (self.root_dir / "index.md").write_text(
            f"---\npage_id: '123'\n---\n\n# Embedded\n\n<!-- macro:embed_html: {params} -->\n",
            encoding="utf-8",
        )

        _, doc = ConfluenceDocument.create(
            self.root_dir / "index.md",
            ConfluenceDocumentOptions(),
            self.root_dir,
            ConfluenceSiteMetadata(domain="example.com", base_path="/wiki/", space_key="SPACE_KEY"),
            ConfluencePageCollection(),
        )
        return doc.xhtml()

    def srcdoc_of(self, xhtml: str) -> str:
        match = re.search(r'srcdoc="(.*?)"\s+style=', xhtml, re.DOTALL)
        if match is None:
            raise AssertionError(f"no srcdoc in output: {xhtml[:300]}")
        return unescape_srcdoc(match.group(1))

    def test_body_is_present_and_not_an_empty_macro(self) -> None:
        "The live bug was an empty self-closing <ac:structured-macro/> with no body."

        xhtml = self.convert(b"<html><body>hi</body></html>")

        self.assertIn('<ac:structured-macro ac:name="html">', xhtml)
        self.assertIn("<ac:plain-text-body>", xhtml)
        self.assertIn("<iframe", xhtml)
        self.assertNotIn('ac:name="html"/>', xhtml)

    def test_cdata_is_preserved(self) -> None:
        xhtml = self.convert(b"<html><body>hi</body></html>")

        self.assertIn("CDATA", xhtml)

    def test_newline_sensitive_javascript_survives_the_pipeline(self) -> None:
        "The converter used to rewrite newlines to spaces, letting a `//` comment swallow the script."

        content = b"<html><script>\n// a line comment\nwindow.x = 1;\n</script></html>"
        xhtml = self.convert(content)

        self.assertIn("\n// a line comment\n", self.srcdoc_of(xhtml))
        self.assertEqual(self.srcdoc_of(xhtml), content.decode("utf-8"))

    def test_content_with_bare_arrow_survives_the_pipeline(self) -> None:
        content = b'<html><script>const marker = "-->";</script></html>'
        xhtml = self.convert(content)

        self.assertEqual(self.srcdoc_of(xhtml), content.decode("utf-8"))

    def test_content_with_cdata_terminator_survives_the_pipeline(self) -> None:
        content = b'<html><script>const s = "]]>";</script></html>'
        xhtml = self.convert(content)

        self.assertEqual(self.srcdoc_of(xhtml), content.decode("utf-8"))

    def test_html_comment_in_content_survives_the_pipeline(self) -> None:
        content = b'<html><script>const t = "<!-- keep me -->";</script></html>'
        xhtml = self.convert(content)

        self.assertEqual(self.srcdoc_of(xhtml), content.decode("utf-8"))

    def test_xml_invalid_control_char_does_not_abort_conversion(self) -> None:
        "A raw control char used to raise ConversionError; it must now pass through as a numeric reference."

        xhtml = self.convert(b'<html><script>let x="a\x0cb";</script></html>')

        self.assertIn("<iframe", xhtml)
        self.assertEqual(self.srcdoc_of(xhtml), '<html><script>let x="a\x0cb";</script></html>')

    def test_tab_survives_the_pipeline(self) -> None:
        "Markdown expands a raw tab to spaces; the encoded reference must round-trip instead."

        xhtml = self.convert(b"<html>\tindented</html>")

        self.assertEqual(self.srcdoc_of(xhtml), "<html>\tindented</html>")

    def test_crlf_survives_the_pipeline(self) -> None:
        xhtml = self.convert(b"<html>a\r\nb</html>")

        self.assertEqual(self.srcdoc_of(xhtml), "<html>a\r\nb</html>")

    def test_dimensions_survive_the_pipeline(self) -> None:
        xhtml = self.convert(b"<html></html>", "explorer.html, height=1400px, title=Explorer")

        self.assertIn("height:1400px", xhtml)
        self.assertIn("Explorer", xhtml)


class TestMacroExpanderContext(TypedTestCase):
    "Tests that contextual dispatch does not disturb existing one-argument expanders."

    def test_existing_one_argument_macros_still_expand(self) -> None:
        expander = MacroExpander()
        text = "<!-- macro:status: green, Done --> and <!-- macro:jira: PROJ-123 -->"
        result = expander.expand(text)

        self.assertIn('ac:name="status"', result)
        self.assertIn('ac:name="jira"', result)
        self.assertNotIn("macro:status", result)

    def test_one_argument_expander_is_not_passed_a_context(self) -> None:
        expander = MacroExpander()
        seen: list[str] = []

        def only_params(params: str) -> str:
            seen.append(params)
            return f"<!-- csf: <p>{params}</p> -->"

        expander.register("custom", only_params)
        result = expander.expand("<!-- macro:custom: hello -->", MacroContext(base_dir=Path.cwd()))

        self.assertListEqual(seen, ["hello"])
        self.assertIn("<p>hello</p>", result)

    def test_contextual_expander_receives_the_context(self) -> None:
        expander = MacroExpander()
        received: list[Optional[MacroContext]] = []

        def with_context(params: str, context: Optional[MacroContext]) -> str:
            received.append(context)
            return "<!-- csf: <p>ok</p> -->"

        expander.register_contextual("ctx", with_context)
        context = MacroContext(base_dir=Path("/tmp"), root_dir=Path("/tmp"))
        expander.expand("<!-- macro:ctx: x -->", context)

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0], context)

    def test_arrow_in_parameters_truncates_the_invocation(self) -> None:
        """
        Pins a known limitation of the HTML-comment macro carrier.

        `<!-- macro:NAME: ... -->` ends at the first `-->`, so no macro parameter can
        contain that sequence. This is inherent to the carrier syntax and shared by every
        macro, not specific to `embed_html`. Documented in the README rather than fixed;
        this test exists so the behaviour cannot change unnoticed.
        """

        text = "<!-- macro:embed_html: page.html, title=x --> y -->"
        result = expand_macros(text)

        self.assertIn(" y -->", result, "trailing text after the first --> is left behind")

    def test_unknown_macro_is_left_unchanged(self) -> None:
        expander = MacroExpander()
        text = "<!-- macro:nosuch: whatever -->"

        self.assertEqual(expander.expand(text), text)

    def test_expand_macros_without_base_dir_is_safe(self) -> None:
        text = "<!-- macro:embed_html: nope.html -->"

        self.assertEqual(expand_macros(text), text)


if __name__ == "__main__":
    unittest.main()
