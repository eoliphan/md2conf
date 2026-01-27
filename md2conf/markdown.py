"""
Publish Markdown files to Confluence wiki.

Copyright 2022-2025, Levente Hunyadi

:see: https://github.com/hunyadi/md2conf
"""

import xml.etree.ElementTree
from typing import Any, Optional

import markdown


def _emoji_generator(
    index: str,
    shortname: str,
    alias: Optional[str],
    uc: Optional[str],
    alt: str,
    title: Optional[str],
    category: Optional[str],
    options: dict[str, Any],
    md: markdown.Markdown,
) -> xml.etree.ElementTree.Element:
    """
    Custom generator for `pymdownx.emoji`.
    """

    name = (alias or shortname).strip(":")
    emoji = xml.etree.ElementTree.Element("x-emoji", {"data-shortname": name})
    if uc is not None:
        emoji.attrib["data-unicode"] = uc

        # convert series of Unicode code point hexadecimal values into characters
        emoji.text = "".join(chr(int(item, base=16)) for item in uc.split("-"))
    else:
        emoji.text = alt

    return emoji


def _verbatim_formatter(
    source: str,
    language: str,
    css_class: str,
    options: dict[str, Any],
    md: markdown.Markdown,
    classes: Optional[list[str]] = None,
    id_value: str = "",
    attrs: Optional[dict[str, str]] = None,
    **kwargs: Any,
) -> str:
    """
    Custom formatter for `pymdownx.superfences`.

    Used by language `math` (a.k.a. `pymdownx.arithmatex`) and pseudo-language `csf` (Confluence Storage Format pass-through).
    """

    if classes is None:
        classes = [css_class]
    else:
        classes.insert(0, css_class)

    html_id = f' id="{id_value}"' if id_value else ""
    html_class = ' class="{}"'.format(" ".join(classes))
    html_attrs = " " + " ".join(f'{k}="{v}"' for k, v in attrs.items()) if attrs else ""

    return f"<div{html_id}{html_class}{html_attrs}>{source}</div>"


_CONVERTER = markdown.Markdown(
    extensions=[
        "admonition",
        "footnotes",
        "markdown.extensions.tables",
        "md_in_html",
        "pymdownx.arithmatex",
        "pymdownx.caret",
        "pymdownx.emoji",
        "pymdownx.highlight",  # required by `pymdownx.superfences`
        "pymdownx.magiclink",
        "pymdownx.mark",
        "pymdownx.superfences",
        "pymdownx.tilde",
        "sane_lists",
    ],
    extension_configs={
        "footnotes": {"BACKLINK_TITLE": ""},
        "pymdownx.arithmatex": {
            "generic": True,
            "preview": False,
            "tex_inline_wrap": ["\\(", "\\)"],
            "tex_block_wrap": ["\\[", "\\]"],
            "smart_dollar": False,  # Disable $...$ detection to avoid conflicts with bash variables
        },
        "pymdownx.emoji": {"emoji_generator": _emoji_generator},
        "pymdownx.highlight": {
            "use_pygments": False,
        },
        "pymdownx.superfences": {
            "custom_fences": [
                {"name": "math", "class": "arithmatex", "format": _verbatim_formatter},
                {"name": "csf", "class": "csf", "format": _verbatim_formatter},
            ]
        },
    },
)


def _preprocess_lists(content: str) -> str:
    """
    Preprocesses markdown content to ensure lists are properly recognized by adding
    blank lines before list markers when needed.

    Python-Markdown requires a blank line before lists, but standard Markdown/CommonMark
    allows lists to immediately follow paragraphs. This function adds the required blank
    lines to make standard Markdown work with Python-Markdown.

    :param content: Markdown input as a string.
    :returns: Preprocessed markdown with blank lines added before lists.
    """
    import re

    lines = content.split('\n')
    result = []
    in_code_block = False
    code_block_indent = 0

    for i, line in enumerate(lines):
        # Track code block state (fenced code blocks with ``` or ~~~)
        # Need to handle both top-level and indented code blocks
        fence_match = re.match(r'^(\s*)(`{3,}|~{3,})', line)
        if fence_match:
            if not in_code_block:
                # Starting a code block
                in_code_block = True
                code_block_indent = len(fence_match.group(1))
            elif len(fence_match.group(1)) == code_block_indent:
                # Ending a code block (same indentation level)
                in_code_block = False
                code_block_indent = 0
            result.append(line)
            continue

        # Skip processing inside code blocks
        if in_code_block:
            result.append(line)
            continue

        # Check if current line starts a list AT TOP LEVEL (not indented more than 3 spaces)
        # List markers: -, *, +, or numbers followed by . or )
        is_list_start = re.match(r'^(\s{0,3})([-*+]|\d+[.)])\s', line)

        if is_list_start and i > 0:
            prev_line = lines[i - 1]
            indent = len(is_list_start.group(1))

            # Only add blank line if:
            # 1. Previous line is non-blank
            # 2. Previous line is not a list item at same or less indentation
            # 3. Current line is at top level (indent <= 3)
            prev_is_list = re.match(r'^(\s{0,3})([-*+]|\d+[.)])\s', prev_line)

            if (prev_line.strip() and
                (not prev_is_list or len(prev_is_list.group(1)) > indent) and
                indent <= 3):
                # Add blank line before this list
                result.append('')

        result.append(line)

    return '\n'.join(result)


def markdown_to_html(content: str) -> str:
    """
    Converts a Markdown document into XHTML with Python-Markdown.

    :param content: Markdown input as a string.
    :returns: XHTML output as a string.
    :see: https://python-markdown.github.io/
    """

    # Preprocess to add blank lines before lists (Python-Markdown requirement)
    content = _preprocess_lists(content)

    _CONVERTER.reset()
    html = _CONVERTER.convert(content)
    return html
