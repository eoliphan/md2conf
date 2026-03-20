"""
Tests for Kroki diagram rendering integration.

Copyright 2022-2025, Levente Hunyadi

:see: https://github.com/hunyadi/md2conf
"""

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from md2conf.domain import ConfluenceDocumentOptions
from md2conf.kroki import KROKI_DIAGRAM_TYPES, KROKI_FILE_EXTENSIONS, KrokiServer


class TestKrokiRegistries(unittest.TestCase):
    def test_diagram_types_not_empty(self) -> None:
        self.assertGreater(len(KROKI_DIAGRAM_TYPES), 20)

    def test_file_extensions_not_empty(self) -> None:
        self.assertGreater(len(KROKI_FILE_EXTENSIONS), 5)

    def test_all_file_extension_types_in_diagram_types(self) -> None:
        """Every file extension must map to a known Kroki diagram type."""
        for ext, diagram_type in KROKI_FILE_EXTENSIONS.items():
            with self.subTest(ext=ext):
                self.assertIn(diagram_type, KROKI_DIAGRAM_TYPES.values())

    def test_file_extensions_start_with_dot(self) -> None:
        for ext in KROKI_FILE_EXTENSIONS:
            with self.subTest(ext=ext):
                self.assertTrue(ext.startswith("."), f"Extension {ext} must start with '.'")

    def test_known_types_present(self) -> None:
        """Verify key diagram types are registered."""
        for name in ["plantuml", "d2", "graphviz", "ditaa", "erd", "structurizr"]:
            with self.subTest(name=name):
                self.assertIn(name, KROKI_DIAGRAM_TYPES)

    def test_dot_is_alias_for_graphviz(self) -> None:
        self.assertEqual(KROKI_DIAGRAM_TYPES["dot"], "graphviz")


class TestKrokiServerInit(unittest.TestCase):
    def test_default_values(self) -> None:
        server = KrokiServer()
        self.assertEqual(server.image, "yuzutech/kroki")
        self.assertFalse(server._started)
        self.assertTrue(server.available)

    def test_custom_image(self) -> None:
        server = KrokiServer(image="custom/kroki:latest")
        self.assertEqual(server.image, "custom/kroki:latest")


class TestKrokiServerDockerDetection(unittest.TestCase):
    @patch("shutil.which", return_value=None)
    def test_no_docker_sets_unavailable(self, mock_which: MagicMock) -> None:
        server = KrokiServer()
        server._ensure_running()
        self.assertFalse(server.available)

    @patch("shutil.which", return_value="/usr/bin/docker")
    @patch("subprocess.run")
    def test_docker_available_starts_container(self, mock_run: MagicMock, mock_which: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="container_id_123\n")

        server = KrokiServer()
        with patch.object(server, "_wait_for_health"):
            server._ensure_running()

        self.assertTrue(server._started)
        self.assertTrue(server.available)
        self.assertEqual(server._container_id, "container_id_123")


class TestKrokiServerContextManager(unittest.TestCase):
    def test_context_manager_no_start(self) -> None:
        """Container should not start just from entering context."""
        with KrokiServer() as server:
            self.assertFalse(server._started)

    def test_context_manager_cleanup_when_not_started(self) -> None:
        """Exit should not fail when container was never started."""
        with KrokiServer() as _server:
            pass  # No render calls, so no container started


class TestKrokiServerLazyStart(unittest.TestCase):
    @patch("shutil.which", return_value=None)
    def test_render_triggers_ensure_running(self, mock_which: MagicMock) -> None:
        server = KrokiServer()
        result = server.render("plantuml", "@startuml\nA->B\n@enduml", "png")
        self.assertIsNone(result)  # Docker not available, returns None
        self.assertFalse(server.available)

    @patch("shutil.which", return_value=None)
    def test_warn_once_per_type(self, mock_which: MagicMock) -> None:
        """Warning should only be logged once per diagram type."""
        server = KrokiServer()
        server.render("plantuml", "source1", "png")
        server.render("plantuml", "source2", "png")
        self.assertEqual(len(server._warned_types), 1)
        server.render("d2", "source3", "svg")
        self.assertEqual(len(server._warned_types), 2)


class TestKrokiDomainOptions(unittest.TestCase):
    def test_default_render_kroki_true(self) -> None:
        opts = ConfluenceDocumentOptions()
        self.assertTrue(opts.render_kroki)

    def test_default_kroki_image(self) -> None:
        opts = ConfluenceDocumentOptions()
        self.assertEqual(opts.kroki_image, "yuzutech/kroki")

    def test_custom_kroki_image(self) -> None:
        opts = ConfluenceDocumentOptions(kroki_image="custom/kroki:v1")
        self.assertEqual(opts.kroki_image, "custom/kroki:v1")

    def test_render_kroki_false(self) -> None:
        opts = ConfluenceDocumentOptions(render_kroki=False)
        self.assertFalse(opts.render_kroki)


class TestKrokiPipelineWiring(unittest.TestCase):
    def test_kroki_server_accessible_from_converter(self) -> None:
        """Verify the converter constructor accepts a kroki_server parameter."""
        from md2conf.collection import ConfluencePageCollection
        from md2conf.converter import ConfluenceConverterOptions, ConfluenceStorageFormatConverter
        from md2conf.metadata import ConfluenceSiteMetadata

        test_dir = Path(__file__).parent / "source"
        test_file = test_dir / "basic.md"
        site = ConfluenceSiteMetadata(domain="test.atlassian.net", base_path="/wiki/", space_key="TEST")
        pages = ConfluencePageCollection()
        options = ConfluenceConverterOptions()
        server = KrokiServer()

        converter = ConfluenceStorageFormatConverter(options, test_file, test_dir, site, pages, kroki_server=server)
        self.assertIs(converter.kroki_server, server)

    def test_converter_works_without_kroki_server(self) -> None:
        """Verify the converter still works when kroki_server is None."""
        from md2conf.collection import ConfluencePageCollection
        from md2conf.converter import ConfluenceConverterOptions, ConfluenceStorageFormatConverter
        from md2conf.metadata import ConfluenceSiteMetadata

        test_dir = Path(__file__).parent / "source"
        test_file = test_dir / "basic.md"
        site = ConfluenceSiteMetadata(domain="test.atlassian.net", base_path="/wiki/", space_key="TEST")
        pages = ConfluencePageCollection()
        options = ConfluenceConverterOptions()

        converter = ConfluenceStorageFormatConverter(options, test_file, test_dir, site, pages)
        self.assertIsNone(converter.kroki_server)


class TestKrokiFencedCodeBlocks(unittest.TestCase):
    def test_plantuml_fenced_block_dispatches_to_kroki(self) -> None:
        """A ```plantuml fenced block should render via Kroki when available."""
        from md2conf.collection import ConfluencePageCollection
        from md2conf.converter import ConfluenceDocument
        from md2conf.metadata import ConfluenceSiteMetadata

        test_dir = Path(__file__).parent / "source"
        test_file = test_dir / "kroki.md"
        site = ConfluenceSiteMetadata(domain="test.atlassian.net", base_path="/wiki/", space_key="TEST")
        pages = ConfluencePageCollection()
        options = ConfluenceDocumentOptions(render_kroki=True)

        mock_server = MagicMock(spec=KrokiServer)
        mock_server.render.return_value = b"\x89PNG fake image data"
        mock_server.available = True

        page_id, doc = ConfluenceDocument.create(test_file, options, test_dir, site, pages, kroki_server=mock_server)

        render_calls = mock_server.render.call_args_list
        diagram_types = [call.args[0] for call in render_calls]
        self.assertIn("plantuml", diagram_types)
        self.assertIn("d2", diagram_types)
        self.assertIn("graphviz", diagram_types)
        self.assertGreater(len(doc.embedded_files), 0)

    def test_kroki_unavailable_falls_back_to_code_block(self) -> None:
        """When Kroki render returns None, emit as code blocks."""
        from md2conf.collection import ConfluencePageCollection
        from md2conf.converter import ConfluenceDocument
        from md2conf.metadata import ConfluenceSiteMetadata

        test_dir = Path(__file__).parent / "source"
        test_file = test_dir / "kroki.md"
        site = ConfluenceSiteMetadata(domain="test.atlassian.net", base_path="/wiki/", space_key="TEST")
        pages = ConfluencePageCollection()
        options = ConfluenceDocumentOptions(render_kroki=True)

        mock_server = MagicMock(spec=KrokiServer)
        mock_server.render.return_value = None
        mock_server.available = False

        page_id, doc = ConfluenceDocument.create(test_file, options, test_dir, site, pages, kroki_server=mock_server)
        self.assertEqual(len(doc.embedded_files), 0)

    def test_render_kroki_false_emits_code_blocks(self) -> None:
        """When render_kroki is False, Kroki types should be plain code blocks."""
        from md2conf.collection import ConfluencePageCollection
        from md2conf.converter import ConfluenceDocument
        from md2conf.metadata import ConfluenceSiteMetadata

        test_dir = Path(__file__).parent / "source"
        test_file = test_dir / "kroki.md"
        site = ConfluenceSiteMetadata(domain="test.atlassian.net", base_path="/wiki/", space_key="TEST")
        pages = ConfluencePageCollection()
        options = ConfluenceDocumentOptions(render_kroki=False)

        page_id, doc = ConfluenceDocument.create(test_file, options, test_dir, site, pages, kroki_server=None)
        self.assertEqual(len(doc.embedded_files), 0)


class TestKrokiFileReferences(unittest.TestCase):
    def test_puml_file_dispatches_to_kroki(self) -> None:
        """A .puml image reference should render via Kroki."""
        from md2conf.converter import ConfluenceDocument
        from md2conf.collection import ConfluencePageCollection
        from md2conf.metadata import ConfluenceSiteMetadata

        test_dir = Path(__file__).parent / "source"
        test_file = test_dir / "kroki-files.md"
        site = ConfluenceSiteMetadata(domain="test.atlassian.net", base_path="/wiki/", space_key="TEST")
        pages = ConfluencePageCollection()
        options = ConfluenceDocumentOptions(render_kroki=True)

        mock_server = MagicMock(spec=KrokiServer)
        mock_server.render.return_value = b"\x89PNG fake image data"
        mock_server.available = True

        page_id, doc = ConfluenceDocument.create(test_file, options, test_dir, site, pages, kroki_server=mock_server)

        mock_server.render.assert_called_once()
        call_args = mock_server.render.call_args
        self.assertEqual(call_args.args[0], "plantuml")
        self.assertGreater(len(doc.embedded_files), 0)

    def test_puml_file_kroki_unavailable_fallback(self) -> None:
        """A .puml file with Kroki unavailable should not crash."""
        from md2conf.converter import ConfluenceDocument
        from md2conf.collection import ConfluencePageCollection
        from md2conf.metadata import ConfluenceSiteMetadata

        test_dir = Path(__file__).parent / "source"
        test_file = test_dir / "kroki-files.md"
        site = ConfluenceSiteMetadata(domain="test.atlassian.net", base_path="/wiki/", space_key="TEST")
        pages = ConfluencePageCollection()
        options = ConfluenceDocumentOptions(render_kroki=True)

        mock_server = MagicMock(spec=KrokiServer)
        mock_server.render.return_value = None
        mock_server.available = False

        # Should not raise
        page_id, doc = ConfluenceDocument.create(test_file, options, test_dir, site, pages, kroki_server=mock_server)
        self.assertEqual(len(doc.embedded_files), 0)


class TestMermaidFallback(unittest.TestCase):
    def test_mermaid_not_dispatched_to_kroki(self) -> None:
        """Mermaid should use existing handler, not Kroki, even when Kroki is available."""
        from md2conf.converter import ConfluenceDocument
        from md2conf.collection import ConfluencePageCollection
        from md2conf.metadata import ConfluenceSiteMetadata

        test_dir = Path(__file__).parent / "source"

        # Create a minimal markdown file with only a mermaid block
        mermaid_md = test_dir / "kroki-mermaid-test.md"
        mermaid_md.write_text(
            "<!-- confluence-page-id: 0 -->\n\n```mermaid\ngraph TD\n  A-->B\n```\n",
            encoding="utf-8",
        )

        try:
            site = ConfluenceSiteMetadata(domain="test.atlassian.net", base_path="/wiki/", space_key="TEST")
            pages = ConfluencePageCollection()
            # render_mermaid=False so it goes through the non-render path (no mmdc needed)
            options = ConfluenceDocumentOptions(render_kroki=True, render_mermaid=False)

            mock_server = MagicMock(spec=KrokiServer)
            mock_server.available = True

            page_id, doc = ConfluenceDocument.create(mermaid_md, options, test_dir, site, pages, kroki_server=mock_server)

            # Kroki render should NOT have been called for mermaid
            mock_server.render.assert_not_called()
        finally:
            mermaid_md.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
