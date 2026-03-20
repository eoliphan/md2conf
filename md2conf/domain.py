"""
Publish Markdown files to Confluence wiki.

Copyright 2022-2025, Levente Hunyadi

:see: https://github.com/hunyadi/md2conf
"""

from dataclasses import dataclass
from typing import Literal, Optional


@dataclass
class ConfluencePageID:
    page_id: str


@dataclass
class ConfluenceDocumentOptions:
    """
    Options that control the generated page content.

    :param ignore_invalid_url: When true, ignore invalid URLs in input, emit a warning and replace the anchor with
        plain text; when false, raise an exception.
    :param heading_anchors: When true, emit a structured macro *anchor* for each section heading using GitHub
        conversion rules for the identifier.
    :param generated_by: Text to use as the generated-by prompt (or `None` to omit a prompt).
    :param root_page_id: Confluence page to assume root page role for publishing a directory of Markdown files.
    :param keep_hierarchy: Whether to maintain source directory structure when exporting to Confluence.
    :param prefer_raster: Whether to choose PNG files over SVG files when available.
    :param render_drawio: Whether to pre-render (or use the pre-rendered version of) draw.io diagrams.
    :param render_mermaid: Whether to pre-render Mermaid diagrams into PNG/SVG images.
    :param render_latex: Whether to pre-render LaTeX formulas into PNG/SVG images.
    :param diagram_output_format: Target image format for diagrams.
    :param webui_links: When true, convert relative URLs to Confluence Web UI links.
    :param alignment: Alignment for block-level images and formulas.
    :param use_panel: Whether to transform admonitions and alerts into a Confluence custom panel.
    :param render_kroki: Whether to render Kroki-supported diagrams using a Docker-managed Kroki server.
    :param kroki_image: Docker image to use for the Kroki server.
    :param skip_title_heading: Whether to remove the first heading from document body when used as page title.
    :param max_image_width: Maximum display width for images in pixels. Images wider than this
        will be scaled down for display while preserving the original size for full-size viewing.
    :param pass_through_languages: When true, pass through unsupported code block language names as-is to
        Confluence. When false, unsupported languages are replaced with 'none'.
    """

    ignore_invalid_url: bool = False
    heading_anchors: bool = False
    generated_by: Optional[str] = "This page has been generated with a tool."
    root_page_id: Optional[ConfluencePageID] = None
    keep_hierarchy: bool = False
    prefer_raster: bool = True
    render_drawio: bool = False
    render_mermaid: bool = False
    render_latex: bool = False
    diagram_output_format: Literal["png", "svg"] = "png"
    webui_links: bool = False
    alignment: Literal["center", "left", "right"] = "center"
    use_panel: bool = False
    render_kroki: bool = True
    kroki_image: str = "yuzutech/kroki"
    skip_title_heading: bool = False
    max_image_width: Optional[int] = None
    pass_through_languages: bool = False
