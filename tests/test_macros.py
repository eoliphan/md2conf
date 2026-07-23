"""
Publish Markdown files to Confluence wiki.

Copyright 2022-2025, Levente Hunyadi

:see: https://github.com/hunyadi/md2conf
"""

import base64
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


def extract_payload(result: str) -> bytes:
    "Recovers the original file bytes from the base64 payload embedded in an expansion result."

    match = re.search(r'var b="([A-Za-z0-9+/=]*)"', result)
    if match is None:
        raise AssertionError(f"no base64 payload found in: {result[:200]}")

    encoded = match.group(1)
    decoded = base64.b64decode(encoded, validate=True)

    # `b64decode` tolerates non-canonical input that a browser's `atob()` rejects (for
    # example "AAAA="), so require the payload to be exactly what `b64encode` produces
    if base64.b64encode(decoded).decode("ascii") != encoded:
        raise AssertionError("payload is not canonical base64 and would be rejected by atob()")

    return decoded


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

    def test_produces_csf_wrapped_html_macro_with_iframe(self) -> None:
        self.write("page.html", b"<html><body>hi</body></html>")
        result = self.expand("page.html")

        self.assertStartsWith(result, "<!-- csf: ")
        self.assertTrue(result.endswith(" -->"))
        self.assertIn('<ac:structured-macro ac:name="html">', result)
        self.assertIn("<ac:plain-text-body><![CDATA[", result)
        self.assertIn("<iframe ", result)
        self.assertIn("srcdoc", result)

    def test_payload_round_trips_byte_for_byte(self) -> None:
        content = b"<html><body>plain</body></html>"
        self.write("page.html", content)

        self.assertEqual(extract_payload(self.expand("page.html")), content)

    def test_emits_a_single_line(self) -> None:
        "The converter rewrites newlines to spaces, so the emitted body must contain none."

        self.write("page.html", b"<html>\n<body>\nhi\n</body>\n</html>")

        self.assertNotIn("\n", self.expand("page.html"))

    def test_no_double_slash_comments_in_shim(self) -> None:
        """
        A `//` comment would swallow the rest of the shim once newlines become spaces.

        The base64 alphabet includes `/`, so `//` may appear inside the payload string
        literal, where it is inert; only the surrounding code is checked.
        """

        self.write("page.html", b"<html></html>")
        result = self.expand("page.html")
        shim = result[result.index("<script>") :]
        code = re.sub(r'var b="[A-Za-z0-9+/=]*"', "", shim)

        self.assertNotIn("//", code)

    # -- destructive payloads ------------------------------------------------

    def test_bare_arrow_in_javascript_is_preserved_and_does_not_truncate(self) -> None:
        "A standalone `-->` would truncate the non-greedy CSF comment regex."

        content = b'<html><script>const marker = "-->";</script></html>'
        self.write("page.html", content)
        result = self.expand("page.html")

        self.assertEqual(result.count("-->"), 1, "only the closing CSF comment may contain -->")
        self.assertTrue(result.endswith("</ac:structured-macro> -->"))
        self.assertEqual(extract_payload(result), content)

    def test_html_comment_inside_javascript_string_is_preserved(self) -> None:
        "Regex comment-stripping would silently delete this; base64 must preserve it."

        content = b'<html><script>const t = "<!-- keep me -->";</script></html>'
        self.write("page.html", content)

        self.assertEqual(extract_payload(self.expand("page.html")), content)

    def test_newline_sensitive_javascript_is_preserved(self) -> None:
        content = b"<html><script>\n// a line comment\nwindow.x = 1;\n</script></html>"
        self.write("page.html", content)

        self.assertEqual(extract_payload(self.expand("page.html")), content)

    def test_cdata_terminator_in_payload_is_preserved_and_does_not_escape(self) -> None:
        content = b'<html><script>const s = "]]>";</script></html>'
        self.write("page.html", content)
        result = self.expand("page.html")

        self.assertEqual(result.count("]]>"), 1, "only the closing CDATA may contain ]]>")
        self.assertEqual(extract_payload(result), content)

    def test_xml_invalid_control_characters_are_tolerated(self) -> None:
        "A form feed is valid UTF-8 but invalid in XML 1.0; base64 keeps it out of the document."

        content = b"<html>\x0c<body>hi</body></html>"
        self.write("page.html", content)
        result = self.expand("page.html")

        self.assertNotIn("\x0c", result)
        self.assertEqual(extract_payload(result), content)

    def test_invalid_utf8_bytes_transport_intact_but_are_warned_about(self) -> None:
        """
        The file is read as bytes, so undecodable content still embeds.

        The browser-side decoder is UTF-8 in replacement mode, so such a file renders as
        U+FFFD rather than its original bytes. Transport fidelity is asserted here; the
        rendering caveat is surfaced as a warning rather than silently accepted.
        """

        content = b"<html>\xff\xfe</html>"
        self.write("page.html", content)

        with self.assertLogs("md2conf.macros", level="WARNING") as captured:
            result = self.expand("page.html")

        self.assertEqual(extract_payload(result), content)
        self.assertTrue(any("not valid UTF-8" in message for message in captured.output))

    def test_valid_utf8_does_not_warn(self) -> None:
        self.write("page.html", "<html><body>café — naïve</body></html>".encode("utf-8"))

        # `assertNoLogs` requires Python 3.10; this package supports 3.9
        with unittest.mock.patch.object(macros.LOGGER, "warning") as warning:
            self.expand("page.html")

        self.assertListEqual([str(call) for call in warning.call_args_list], [])

    def test_ampersand_and_quote_in_payload_are_preserved(self) -> None:
        content = b"""<html><body>a &amp; b, it's here & "quoted"</body></html>"""
        self.write("page.html", content)

        self.assertEqual(extract_payload(self.expand("page.html")), content)

    # -- failure paths -------------------------------------------------------

    def test_missing_file_returns_original_text_unchanged(self) -> None:
        result = self.expand("nonexistent.html")

        self.assertEqual(result, "<!-- macro:embed_html: nonexistent.html -->")

    def test_empty_path_returns_original_text_unchanged(self) -> None:
        self.assertEqual(self.expand(""), "<!-- macro:embed_html:  -->")

    def test_path_outside_root_dir_is_refused(self) -> None:
        "Otherwise any readable file could be inlined into a Confluence page."

        # every artifact stays inside the temporary directory this test owns
        docs = self.root_dir / "docs"
        docs.mkdir()
        (self.root_dir / "secret.html").write_bytes(b"<html>secret</html>")

        context = MacroContext(base_dir=docs, root_dir=docs)
        result = expand_embed_html("../secret.html", context)

        self.assertEqual(result, "<!-- macro:embed_html: ../secret.html -->")

    def test_symlink_escaping_root_dir_is_refused(self) -> None:
        docs = self.root_dir / "docs"
        docs.mkdir()
        (self.root_dir / "secret.html").write_bytes(b"<html>secret</html>")
        (docs / "link.html").symlink_to(self.root_dir / "secret.html")

        result = expand_embed_html("link.html", MacroContext(base_dir=docs, root_dir=docs))

        self.assertEqual(result, "<!-- macro:embed_html: link.html -->")

    def test_absolute_path_is_refused(self) -> None:
        "Joining an absolute path discards base_dir, so it must be rejected outright."

        secret = self.root_dir / "secret.html"
        secret.write_bytes(b"<html>secret</html>")

        result = self.expand(str(secret))

        self.assertEqual(result, f"<!-- macro:embed_html: {secret} -->")

    def test_without_context_nothing_is_read(self) -> None:
        "The containment check needs a context; without one the macro must refuse."

        readable = self.root_dir / "page.html"
        readable.write_bytes(b"<html>readable</html>")

        result = expand_embed_html(str(readable), None)

        self.assertEqual(result, f"<!-- macro:embed_html: {readable} -->")

    def test_directory_instead_of_file_returns_original_text(self) -> None:
        (self.base_dir / "subdir").mkdir()

        self.assertEqual(self.expand("subdir"), "<!-- macro:embed_html: subdir -->")

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

    def test_path_containing_comma_and_equals(self) -> None:
        content = b"<html>odd</html>"
        self.write("a,b=c.html", content)
        result = self.expand("a,b=c.html, height=200px")

        self.assertEqual(extract_payload(result), content)
        self.assertIn("height:200px", result)

    def test_named_parameters_are_case_insensitive(self) -> None:
        "The path/parameter split is case-insensitive, so the lookup must match."

        self.write("page.html", b"<html></html>")
        result = self.expand("page.html, HEIGHT=200px, Width=80%")

        self.assertIn("width:80%;height:200px", result)

    def test_quoted_path_is_unquoted_once(self) -> None:
        content = b"<html>quoted</html>"
        self.write("page.html", content)

        self.assertEqual(extract_payload(self.expand('"page.html"')), content)

    def test_locates_frame_via_current_script(self) -> None:
        "Two embeds of the same file share a payload hash, so the id alone is not enough."

        self.write("page.html", b"<html></html>")
        result = self.expand("page.html")

        self.assertIn("document.currentScript", result)
        # the id lookup remains as a fallback for environments without `currentScript`,
        # and is also reached when `previousElementSibling` is null
        self.assertIn('(s&&s.previousElementSibling)||document.getElementById("mdc-embed-', result)

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
        """
        Escaping the title keeps `-->` and `]]>` out of the generated body.

        This covers the expander's own output. The macro *invocation* is a separate
        matter -- see `test_arrow_in_parameters_truncates_the_invocation`.
        """

        self.write("page.html", b"<html></html>")
        result = self.expand("page.html, title=x --> y ]]> z")

        self.assertEqual(result.count("-->"), 1)
        self.assertEqual(result.count("]]>"), 1)

    def test_no_sandbox_attribute(self) -> None:
        "The embedded document needs its inline scripts to run."

        self.write("page.html", b"<html></html>")

        self.assertNotIn("sandbox", self.expand("page.html"))

    def test_relative_path_without_context_is_refused(self) -> None:
        self.assertEqual(
            expand_embed_html("definitely-not-here.html", None),
            "<!-- macro:embed_html: definitely-not-here.html -->",
        )


class TestEmbedHtmlEndToEnd(TypedTestCase):
    """
    Drives `embed_html` through the full conversion pipeline.

    The pipeline is where the naive approach failed: the payload is carried inside an
    HTML comment terminated by the first `-->`, run through Markdown, parsed as XML, and
    finally walked by a converter that rewrites every newline in element text to a
    space. These tests assert against the final `doc.xhtml()` rather than the expander's
    return value.
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

    def test_newline_sensitive_javascript_survives_the_pipeline(self) -> None:
        "The converter rewrites newlines to spaces, which would let a `//` comment swallow the script."

        content = b"<html><script>\n// a line comment\nwindow.x = 1;\n</script></html>"
        xhtml = self.convert(content)

        self.assertIn('ac:name="html"', xhtml)
        self.assertEqual(extract_payload(xhtml), content)

    def test_payload_with_bare_arrow_survives_the_pipeline(self) -> None:
        "A standalone `-->` would otherwise truncate the CSF comment carrier mid-CDATA."

        content = b'<html><script>const marker = "-->";</script></html>'
        xhtml = self.convert(content)

        self.assertEqual(extract_payload(xhtml), content)

    def test_payload_with_cdata_terminator_survives_the_pipeline(self) -> None:
        content = b'<html><script>const s = "]]>";</script></html>'
        xhtml = self.convert(content)

        self.assertEqual(extract_payload(xhtml), content)

    def test_html_comment_in_javascript_survives_the_pipeline(self) -> None:
        content = b'<html><script>const t = "<!-- keep me -->";</script></html>'
        xhtml = self.convert(content)

        self.assertEqual(extract_payload(xhtml), content)

    def test_xml_invalid_control_character_survives_the_pipeline(self) -> None:
        content = b"<html>\x0c<body>hi</body></html>"
        xhtml = self.convert(content)

        self.assertEqual(extract_payload(xhtml), content)

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
