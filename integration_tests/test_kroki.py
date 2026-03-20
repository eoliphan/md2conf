"""
Integration tests for Kroki diagram rendering.

Requires Docker to be available and running.

Copyright 2022-2025, Levente Hunyadi

:see: https://github.com/hunyadi/md2conf
"""

import shutil
import unittest

from md2conf.kroki import KrokiServer


@unittest.skipUnless(shutil.which("docker"), "Docker is not available")
class TestKrokiIntegration(unittest.TestCase):
    def test_render_plantuml_png(self) -> None:
        with KrokiServer() as server:
            result = server.render("plantuml", "@startuml\nAlice -> Bob: Hello\n@enduml", "png")
            self.assertIsNotNone(result)
            assert result is not None
            self.assertIn(b"PNG", result)

    def test_render_plantuml_svg(self) -> None:
        with KrokiServer() as server:
            result = server.render("plantuml", "@startuml\nAlice -> Bob: Hello\n@enduml", "svg")
            self.assertIsNotNone(result)
            assert result is not None
            self.assertIn(b"<svg", result)

    def test_render_d2(self) -> None:
        with KrokiServer() as server:
            result = server.render("d2", "x -> y: hello", "svg")
            self.assertIsNotNone(result)
            assert result is not None
            self.assertIn(b"<svg", result)

    def test_render_graphviz(self) -> None:
        with KrokiServer() as server:
            result = server.render("graphviz", "digraph { a -> b }", "svg")
            self.assertIsNotNone(result)
            assert result is not None
            self.assertIn(b"<svg", result)

    def test_render_ditaa(self) -> None:
        with KrokiServer() as server:
            result = server.render("ditaa", "+--------+\n| Hello  |\n+--------+", "svg")
            self.assertIsNotNone(result)

    def test_container_reused_across_renders(self) -> None:
        """Multiple renders should use the same container."""
        with KrokiServer() as server:
            server.render("plantuml", "@startuml\nA->B\n@enduml", "svg")
            container_id = server._container_id
            server.render("d2", "x -> y", "svg")
            self.assertEqual(server._container_id, container_id)

    def test_container_cleaned_up_on_exit(self) -> None:
        """Container should be stopped after context manager exits."""
        container_id = None
        with KrokiServer() as server:
            result = server.render("plantuml", "@startuml\nA->B\n@enduml", "svg")
            if not server.available:
                self.skipTest("Kroki container failed to start")
            container_id = server._container_id
        self.assertIsNotNone(container_id)
        self.assertIsNone(server._container_id)


if __name__ == "__main__":
    unittest.main()
