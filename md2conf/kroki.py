"""
Publish Markdown files to Confluence wiki.

Copyright 2022-2025, Levente Hunyadi

:see: https://github.com/hunyadi/md2conf
"""

import logging
import shutil
import socket
import subprocess
import time
from typing import Literal, Optional

import requests

LOGGER = logging.getLogger(__name__)

# Maps fenced code block language names to Kroki diagram type identifiers.
# These are the types supported by the core Kroki Docker image (no companion containers).
KROKI_DIAGRAM_TYPES: dict[str, str] = {
    "plantuml": "plantuml",
    "c4plantuml": "c4plantuml",
    "d2": "d2",
    "graphviz": "graphviz",
    "dot": "graphviz",
    "blockdiag": "blockdiag",
    "seqdiag": "seqdiag",
    "actdiag": "actdiag",
    "nwdiag": "nwdiag",
    "packetdiag": "packetdiag",
    "rackdiag": "rackdiag",
    "ditaa": "ditaa",
    "erd": "erd",
    "nomnoml": "nomnoml",
    "svgbob": "svgbob",
    "wavedrom": "wavedrom",
    "vega": "vega",
    "vegalite": "vegalite",
    "structurizr": "structurizr",
    "bytefield": "bytefield",
    "pikchr": "pikchr",
    "umlet": "umlet",
    "wireviz": "wireviz",
    "symbolator": "symbolator",
}

# Maps file extensions to Kroki diagram type identifiers.
KROKI_FILE_EXTENSIONS: dict[str, str] = {
    ".puml": "plantuml",
    ".plantuml": "plantuml",
    ".c4puml": "c4plantuml",
    ".d2": "d2",
    ".dot": "graphviz",
    ".gv": "graphviz",
    ".blockdiag": "blockdiag",
    ".seqdiag": "seqdiag",
    ".actdiag": "actdiag",
    ".nwdiag": "nwdiag",
    ".packetdiag": "packetdiag",
    ".rackdiag": "rackdiag",
    ".ditaa": "ditaa",
    ".erd": "erd",
    ".nomnoml": "nomnoml",
    ".bob": "svgbob",
    ".wavedrom": "wavedrom",
    ".vega": "vega",
    ".vegalite": "vegalite",
    ".structurizr": "structurizr",
    ".bytefield": "bytefield",
    ".pikchr": "pikchr",
    ".umlet": "umlet",
    ".wireviz": "wireviz",
    ".symbolator": "symbolator",
}


class KrokiServer:
    """
    Manages a Kroki Docker container lifecycle for rendering diagrams.

    Use as a context manager. The container is lazy-started on the first render() call
    and stopped/removed on exit.
    """

    image: str
    _started: bool
    _container_id: Optional[str]
    _port: Optional[int]
    _warned_types: set[str]
    available: bool

    def __init__(self, image: str = "yuzutech/kroki") -> None:
        self.image = image
        self._started = False
        self._container_id = None
        self._port = None
        self._warned_types = set()
        self.available = True

    def __enter__(self) -> "KrokiServer":
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop()

    def _find_free_port(self) -> int:
        """Find a free port by binding to port 0."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            port: int = s.getsockname()[1]
            return port

    def _ensure_running(self) -> None:
        """Start the Kroki container if not already running."""
        if self._started:
            return

        if shutil.which("docker") is None:
            LOGGER.warning("Docker is not available; Kroki diagrams will not be rendered")
            self.available = False
            return

        port = self._find_free_port()
        cmd = [
            "docker",
            "run",
            "-d",
            "--rm",
            "-p",
            f"{port}:8000",
            "--name",
            f"md2conf-kroki-{port}",
            self.image,
        ]
        LOGGER.debug("Starting Kroki container: %s", " ".join(cmd))

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                LOGGER.warning("Failed to start Kroki container: %s", result.stderr.strip())
                self.available = False
                return
            self._container_id = result.stdout.strip()
            self._port = port
            self._started = True
            self._wait_for_health()
            LOGGER.info("Kroki container started on port %d (container: %s)", port, self._container_id[:12])
        except (subprocess.TimeoutExpired, OSError) as e:
            LOGGER.warning("Failed to start Kroki container: %s", e)
            self.available = False

    def _wait_for_health(self, timeout: float = 30.0, interval: float = 0.5) -> None:
        """Poll the Kroki health endpoint until it responds or timeout."""
        url = f"http://localhost:{self._port}/health"
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                resp = requests.get(url, timeout=2)
                if resp.status_code == 200:
                    return
            except requests.ConnectionError:
                pass
            time.sleep(interval)
        LOGGER.warning("Kroki container health check timed out after %.0fs", timeout)
        self._stop()
        self.available = False

    def _stop(self) -> None:
        """Stop and remove the Kroki container."""
        if self._container_id is not None:
            LOGGER.debug("Stopping Kroki container: %s", self._container_id[:12])
            try:
                subprocess.run(
                    ["docker", "stop", self._container_id],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
            except (subprocess.TimeoutExpired, OSError) as e:
                LOGGER.warning("Failed to stop Kroki container: %s", e)
            self._container_id = None
            self._started = False

    def render(self, diagram_type: str, source: str, output_format: Literal["png", "svg"] = "png") -> Optional[bytes]:
        """
        Render a diagram using the Kroki server.

        :param diagram_type: Kroki diagram type (e.g. "plantuml", "d2", "graphviz").
        :param source: Diagram source text.
        :param output_format: Output format ("png" or "svg").
        :returns: Rendered image bytes, or None if Kroki is unavailable.
        """
        self._ensure_running()
        if not self.available:
            if diagram_type not in self._warned_types:
                LOGGER.warning("Kroki unavailable; cannot render %s diagram", diagram_type)
                self._warned_types.add(diagram_type)
            return None

        url = f"http://localhost:{self._port}/{diagram_type}/{output_format}"
        try:
            resp = requests.post(url, data=source.encode("utf-8"), headers={"Content-Type": "text/plain"}, timeout=30)
            if resp.status_code != 200:
                LOGGER.error("Kroki render failed for %s: HTTP %d — %s", diagram_type, resp.status_code, resp.text[:200])
                return None
            return resp.content
        except requests.RequestException as e:
            LOGGER.error("Kroki render failed for %s: %s", diagram_type, e)
            return None
