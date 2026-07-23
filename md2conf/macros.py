"""
Macro expansion facility for md2conf.

Provides shorthand syntax for common Confluence macros that expand to CSF comments.

Copyright 2022-2025, Levente Hunyadi

:see: https://github.com/hunyadi/md2conf
"""

import base64
import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

LOGGER = logging.getLogger(__name__)


@dataclass
class MacroContext:
    """
    Ambient information about the document a macro is being expanded in.

    :param base_dir: Directory of the source Markdown file; relative paths resolve against it.
    :param root_dir: Root of the documentation tree; resolved paths must stay within it.
    """

    base_dir: Optional[Path] = None
    root_dir: Optional[Path] = None


class MacroExpander:
    """Registry-based macro expander."""

    def __init__(self) -> None:
        self.registry: dict[str, Callable[..., str]] = {}
        self.contextual: set[str] = set()
        self._register_builtin_macros()

    def _register_builtin_macros(self) -> None:
        """Register built-in macro expanders."""
        self.registry["jira"] = expand_jira_macro
        self.registry["status"] = expand_status_macro
        self.registry["emoticon"] = expand_emoticon_macro
        self.register_contextual("embed_html", expand_embed_html)

    def register(self, name: str, expander: Callable[[str], str]) -> None:
        """Register a custom macro expander taking only parameters."""
        self.registry[name] = expander
        self.contextual.discard(name)

    def register_contextual(self, name: str, expander: Callable[[str, Optional[MacroContext]], str]) -> None:
        """
        Register a custom macro expander that also receives a :class:`MacroContext`.

        Membership in this registry -- not the callable's signature -- decides whether a
        context is passed. Inferring it with `inspect` would misjudge bound methods,
        `functools.partial` objects, `*args` callables and keyword-only parameters, and
        `expand` swallows every exception, so such a misjudgement would be invisible.
        """
        self.registry[name] = expander
        self.contextual.add(name)

    def expand(self, text: str, context: Optional[MacroContext] = None) -> str:
        """Expand all macro comments in text."""
        pattern = r"<!--\s*macro:(\w+):\s*(.*?)\s*-->"

        def replace_macro(match: re.Match[str]) -> str:
            macro_name = match.group(1)
            params = match.group(2).strip()

            if macro_name in self.registry:
                try:
                    if macro_name in self.contextual:
                        return self.registry[macro_name](params, context)
                    return self.registry[macro_name](params)
                except Exception:
                    # Return original text if expansion fails
                    LOGGER.warning("macro `%s` failed to expand; leaving invocation unchanged", macro_name, exc_info=True)
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
    show_summary = named.get("showSummary", "false")

    csf = '<ac:structured-macro ac:name="jira" ac:schema-version="1">'
    csf += f'<ac:parameter ac:name="key">{key}</ac:parameter>'

    if show_summary.lower() == "true":
        csf += '<ac:parameter ac:name="showSummary">true</ac:parameter>'

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


# parameters recognized by the `embed_html` macro; anything before the first of these is the path
_EMBED_HTML_NAMED = ("height", "width", "title")
_EMBED_HTML_SPLIT = re.compile(r",\s*(?=(?:" + "|".join(_EMBED_HTML_NAMED) + r")\s*=)", re.IGNORECASE)

# a permissive but closed CSS length grammar; anything else is rejected rather than interpolated
_CSS_LENGTH = re.compile(r"^\d+(?:\.\d+)?(?:px|em|rem|%|vh|vw)$")

# embedded documents beyond this size make for an unreasonably heavy Confluence page
_EMBED_HTML_SIZE_WARN = 5 * 1024 * 1024


def _escape_attribute(value: str) -> str:
    """Escape text for inclusion in a double-quoted HTML attribute."""

    value = value.replace("&", "&amp;")
    value = value.replace("<", "&lt;")
    value = value.replace(">", "&gt;")
    value = value.replace('"', "&quot;")
    value = value.replace("'", "&#39;")
    return value


def expand_embed_html(params: str, context: Optional[MacroContext] = None) -> str:
    """
    Expand an `embed_html` macro, inlining a self-contained HTML file as a live iframe.

    Syntax: `path/to/file.html, height=1400px, width=90%, title=Explorer`

    The file path resolves relative to the directory of the *source Markdown file* (the
    same `base_dir` that images, drawio diagrams and linked attachments use), and must
    stay within the documentation root.

    The file is read as bytes and base64-encoded rather than inlined verbatim. The
    payload then consists solely of `[A-Za-z0-9+/=]` on a single line, which is what
    makes the surrounding transports safe: the Confluence Storage Format passthrough
    carries it inside an HTML comment terminated by the first `-->`, Markdown runs over
    it, and the converter rewrites every newline in element text to a space. A raw HTML
    payload would be corrupted by all three; base64 cannot contain `-->`, `]]>`, a
    newline or an XML-invalid control character, so the file survives byte for byte and
    needs no lossy pre-processing. A one-line script decodes it into the iframe's
    `srcdoc`, which keeps the frame same-origin so embedded pages may use `localStorage`.

    :param params: Macro parameters.
    :param context: Ambient document information supplying the base and root directories.
    :returns: Expanded CSF comment, or the original macro text if expansion is not possible.
    """

    original = f"<!-- macro:embed_html: {params} -->"

    # split the path from the named parameters, so paths may contain `,` and `=`
    parts = _EMBED_HTML_SPLIT.split(params, maxsplit=1)
    path_text = parts[0].strip().strip('"').strip("'").strip()
    named: dict[str, str] = {}
    if len(parts) > 1:
        _, named = parse_parameters(parts[1])

    if not path_text:
        LOGGER.warning("macro `embed_html` requires a file path; leaving invocation unchanged")
        return original

    height = named.get("height", "1040px").strip()
    if not _CSS_LENGTH.match(height):
        LOGGER.warning("macro `embed_html` ignoring invalid height %r; using default", height)
        height = "1040px"

    width = named.get("width", "100%").strip()
    if not _CSS_LENGTH.match(width):
        LOGGER.warning("macro `embed_html` ignoring invalid width %r; using default", width)
        width = "100%"

    title = _escape_attribute(named.get("title", "Embedded HTML").strip())

    base_dir = context.base_dir if context is not None and context.base_dir is not None else Path.cwd()
    absolute_path = (base_dir / path_text).resolve()

    if context is not None and context.root_dir is not None:
        root_dir = context.root_dir.resolve()
        if not absolute_path.is_relative_to(root_dir):
            LOGGER.warning("macro `embed_html` refusing %s; path points outside root path %s", absolute_path, root_dir)
            return original

    try:
        data = absolute_path.read_bytes()
    except OSError as exc:
        LOGGER.warning("macro `embed_html` cannot read %s: %s", absolute_path, exc)
        return original

    if len(data) > _EMBED_HTML_SIZE_WARN:
        LOGGER.warning("macro `embed_html` embedding %d bytes from %s; this makes for a heavy page", len(data), absolute_path)

    payload = base64.b64encode(data).decode("ascii")
    identifier = hashlib.md5(payload.encode("ascii")).hexdigest()[:8]
    frame_id = f"mdc-embed-{identifier}"

    # emitted as a single line without `//` comments: the converter rewrites newlines to spaces
    body = (
        f'<iframe id="{frame_id}" style="width:{width};height:{height};border:0" loading="lazy" title="{title}"></iframe>'
        f'<script>(function(){{var b="{payload}";'
        f'var e=document.getElementById("{frame_id}");'
        f"e.srcdoc=new TextDecoder().decode(Uint8Array.from(atob(b),function(c){{return c.charCodeAt(0)}}));}})();</script>"
    )

    # defence in depth: neither sequence can survive parameter escaping or the base64 alphabet
    body = body.replace("]]>", "]]]]><![CDATA[>")
    body = body.replace("-->", "--&gt;")

    csf = f'<ac:structured-macro ac:name="html"><ac:plain-text-body><![CDATA[{body}]]></ac:plain-text-body></ac:structured-macro>'

    return f"<!-- csf: {csf} -->"


# Global expander instance
_EXPANDER = MacroExpander()


def expand_macros(text: str, base_dir: Optional[Path] = None, root_dir: Optional[Path] = None) -> str:
    """
    Expand all macro comments in markdown text.

    This is the main entry point called from converter.py.

    :param text: Markdown text with macro comments.
    :param base_dir: Directory of the source Markdown file; relative paths resolve against it.
    :param root_dir: Root of the documentation tree; resolved paths must stay within it.
    :returns: Text with macros expanded to CSF comments.
    """
    return _EXPANDER.expand(text, MacroContext(base_dir=base_dir, root_dir=root_dir))


def register_macro(name: str, expander: Callable[[str], str]) -> None:
    """
    Register a custom macro expander.

    Expander function signature: def expand_xxx(params: str) -> str

    :param name: Macro name.
    :param expander: Expander function.
    """
    _EXPANDER.register(name, expander)


def register_contextual_macro(name: str, expander: Callable[[str, Optional[MacroContext]], str]) -> None:
    """
    Register a custom macro expander that also receives the document context.

    Expander function signature: def expand_xxx(params: str, context: Optional[MacroContext]) -> str

    :param name: Macro name.
    :param expander: Expander function.
    """
    _EXPANDER.register_contextual(name, expander)
