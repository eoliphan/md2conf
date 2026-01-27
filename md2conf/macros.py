"""
Macro expansion facility for md2conf.

Provides shorthand syntax for common Confluence macros that expand to CSF comments.

Copyright 2022-2025, Levente Hunyadi

:see: https://github.com/hunyadi/md2conf
"""

import re
from typing import Callable


class MacroExpander:
    """Registry-based macro expander."""

    def __init__(self) -> None:
        self.registry: dict[str, Callable[[str], str]] = {}
        self._register_builtin_macros()

    def _register_builtin_macros(self) -> None:
        """Register built-in macro expanders."""
        self.registry["jira"] = expand_jira_macro
        self.registry["status"] = expand_status_macro
        self.registry["emoticon"] = expand_emoticon_macro

    def register(self, name: str, expander: Callable[[str], str]) -> None:
        """Register a custom macro expander."""
        self.registry[name] = expander

    def expand(self, text: str) -> str:
        """Expand all macro comments in text."""
        pattern = r"<!--\s*macro:(\w+):\s*(.*?)\s*-->"

        def replace_macro(match: re.Match[str]) -> str:
            macro_name = match.group(1)
            params = match.group(2).strip()

            if macro_name in self.registry:
                try:
                    return self.registry[macro_name](params)
                except Exception:
                    # Return original text if expansion fails
                    return match.group(0)
            else:
                # Unknown macro - leave as is
                return match.group(0)

        return re.sub(pattern, replace_macro, text)


def parse_parameters(params: str) -> tuple[list[str], dict[str, str]]:
    """
    Parse macro parameters into positional and named arguments.

    Format: "pos1, pos2, key=value, key=value"
    Supports quoted strings: 'key="quoted value"'

    :param params: Parameter string to parse.
    :returns: (positional_args, named_args)
    """
    positional = []
    named = {}

    # Split by comma, but respect quotes
    parts = re.split(r',(?=(?:[^"]*"[^"]*")*[^"]*$)', params)

    for part in parts:
        part = part.strip()
        if "=" in part:
            # Named parameter
            key, value = part.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            named[key] = value
        else:
            # Positional parameter
            positional.append(part.strip('"').strip("'"))

    return positional, named


def expand_jira_macro(params: str) -> str:
    """
    Expand JIRA macro to CSF comment.

    Syntax: PROJ-123, showSummary=true

    :param params: Macro parameters.
    :returns: Expanded CSF comment.
    """
    positional, named = parse_parameters(params)

    if not positional:
        return f"<!-- macro:jira: {params} -->"  # Invalid - return unchanged

    key = positional[0]
    show_summary = named.get("showSummary", "true")

    csf = '<ac:structured-macro ac:name="jira" ac:schema-version="1">'
    csf += f'<ac:parameter ac:name="key">{key}</ac:parameter>'

    if show_summary.lower() != "true":
        csf += f'<ac:parameter ac:name="showSummary">{show_summary}</ac:parameter>'

    csf += "</ac:structured-macro>"

    return f"<!-- csf: {csf} -->"


def expand_status_macro(params: str) -> str:
    """
    Expand status macro to CSF comment.

    Syntax: green, Done  OR  color="green", title="Done"

    :param params: Macro parameters.
    :returns: Expanded CSF comment.
    """
    positional, named = parse_parameters(params)

    # Get color and title from positional or named
    if "color" in named:
        color = named["color"]
    elif len(positional) >= 1:
        color = positional[0]
    else:
        return f"<!-- macro:status: {params} -->"  # Invalid

    if "title" in named:
        title = named["title"]
    elif len(positional) >= 2:
        title = positional[1]
    else:
        return f"<!-- macro:status: {params} -->"  # Invalid

    # Capitalize color for Confluence (Green, Red, etc.)
    color = color.capitalize()

    csf = '<ac:structured-macro ac:name="status" ac:schema-version="1">'
    csf += f'<ac:parameter ac:name="colour">{color}</ac:parameter>'
    csf += f'<ac:parameter ac:name="title">{title}</ac:parameter>'
    csf += "</ac:structured-macro>"

    return f"<!-- csf: {csf} -->"


def expand_emoticon_macro(params: str) -> str:
    """
    Expand emoticon macro to CSF comment.

    Syntax: thumbs-up

    :param params: Macro parameters.
    :returns: Expanded CSF comment.
    """
    name = params.strip()
    csf = f'<ac:emoticon ac:name="{name}" />'
    return f"<!-- csf: {csf} -->"


# Global expander instance
_EXPANDER = MacroExpander()


def expand_macros(text: str) -> str:
    """
    Expand all macro comments in markdown text.

    This is the main entry point called from converter.py.

    :param text: Markdown text with macro comments.
    :returns: Text with macros expanded to CSF comments.
    """
    return _EXPANDER.expand(text)


def register_macro(name: str, expander: Callable[[str], str]) -> None:
    """
    Register a custom macro expander.

    Expander function signature: def expand_xxx(params: str) -> str

    :param name: Macro name.
    :param expander: Expander function.
    """
    _EXPANDER.register(name, expander)
