"""
Publish Markdown files to Confluence wiki.

Copyright 2022-2025, Levente Hunyadi

:see: https://github.com/hunyadi/md2conf
"""

import logging

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
