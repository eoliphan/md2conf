# User @mentions Design

**Date:** 2026-06-16

## Overview

Translate `@username` syntax in Markdown documents into Confluence user mention macros in the generated Confluence Storage Format (CSF). When a mention cannot be resolved (user not found, or running in local mode), emit a warning and leave the token as plain text.

## Scope

**In scope:**
- `@username` bare-word syntax (letters, digits, dots, hyphens, underscores)
- Resolution via Confluence login username (not email, not display name)
- Both Cloud/v2 (`ri:account-id`) and Data Center/v1 (`ri:username`) API paths
- Warn-and-skip for unresolvable mentions
- Silent plain-text fallback in `--local` mode (no resolver available)

**Out of scope:**
- `@{Display Name with spaces}` syntax
- Caching of user lookups
- `--no-resolve-mentions` opt-out flag

## Architecture

Four files change. No new files.

| File | Change |
|---|---|
| `md2conf/markdown.py` | New `MentionExtension` and `MentionInlineProcessor` |
| `md2conf/converter.py` | Thread `mention_resolver` through `create()` and `__init__()`; handle `<mention>` placeholder elements in CSF transformer |
| `md2conf/api.py` | New `get_user_by_name(username)` public method; v1 and v2 private implementations |
| `md2conf/processor.py` | Add `mention_resolver` attribute alongside `kroki_server`; pass to `ConfluenceDocument.create()` |

`SynchronizingProcessor.__init__` sets `mention_resolver = api.get_user_by_name` at construction time. `LocalConverter` leaves it `None`.

## Resolver Interface

```python
# In md2conf/converter.py
from typing import Callable, Optional
MentionResolver = Callable[[str], Optional[tuple[str, str]]]
```

The resolver accepts a username string and returns either:
- `("ri:account-id", "557058:abc-def")` — Cloud/v2
- `("ri:username", "jsmith")` — Data Center/v1
- `None` — user not found

The converter is version-agnostic: it assembles the CSF element from the returned attribute pair without knowing which Confluence deployment is in use.

## Conversion Flow

Given `@jsmith` in Markdown text:

1. `MentionInlineProcessor.handleMatch()` fires on the regex `@([A-Za-z][A-Za-z0-9._-]*)`.
2. If `mention_resolver` is `None` (local mode): leave `@jsmith` as plain text, no warning.
3. If `mention_resolver("jsmith")` returns `None`: emit `LOGGER.warning("Cannot resolve mention @jsmith: user not found")` and leave as plain text.
4. If resolver returns `(attr_name, attr_val)`: emit a placeholder element into the Markdown HTML output:
   ```html
   <mention ri-attr="ri:account-id" ri-val="557058:abc">@jsmith</mention>
   ```
5. The CSF transformer in `converter.py` converts `<mention>` elements to:
   ```xml
   <ac:link><ri:user ri:account-id="557058:abc"/></ac:link>
   ```

## Markdown Extension

```python
class MentionInlineProcessor(InlineProcessor):
    def __init__(self, pattern: str, md: Markdown, resolver: Optional[MentionResolver]) -> None:
        super().__init__(pattern, md)
        self.resolver = resolver

    def handleMatch(self, m: re.Match, data: str) -> tuple[Optional[Element], int, int]:
        username = m.group(1)
        if self.resolver is None:
            return None, m.start(0), m.end(0)  # leave as-is
        result = self.resolver(username)
        if result is None:
            LOGGER.warning("Cannot resolve mention @%s: user not found in Confluence", username)
            return None, m.start(0), m.end(0)  # leave as-is
        attr_name, attr_val = result
        el = Element("mention")
        el.set("ri-attr", attr_name)
        el.set("ri-val", attr_val)
        el.text = f"@{username}"
        return el, m.start(0), m.end(0)


class MentionExtension(Extension):
    def __init__(self, resolver: Optional[MentionResolver] = None) -> None:
        self.resolver = resolver
        super().__init__()

    def extendMarkdown(self, md: Markdown) -> None:
        # Priority 175 — runs after links (170) but before emphasis (180)
        md.inlinePatterns.register(
            MentionInlineProcessor(r"@([A-Za-z][A-Za-z0-9._-]*)", md, self.resolver),
            "mention",
            175,
        )
```

`markdown_to_html()` gains an optional `mention_resolver` parameter and includes `MentionExtension(mention_resolver)` in the extensions list.

## CSF Transformer

In `converter.py`, the element visitor for the `<mention>` tag:

```python
# Converts <mention ri-attr="ri:account-id" ri-val="557058:abc">@jsmith</mention>
# to <ac:link><ri:user ri:account-id="557058:abc"/></ac:link>
def _visit_mention(self, el: ElementType) -> ElementType:
    link = Element(AC("link"))
    user = SubElement(link, RI("user"))
    user.set(el.get("ri-attr"), el.get("ri-val"))
    return link
```

## API Methods

### v2 (Cloud)

```
GET /wiki/rest/api/user/search?query={username}&limit=5
```

Iterate results; find the entry where `username` field matches exactly. Return `("ri:account-id", result["accountId"])`. Return `None` if no exact match.

### v1 (Data Center/Server)

```
GET /rest/api/user?username={username}
```

On HTTP 200: return `("ri:username", username)` — the login username is used directly in CSF, no internal key needed.
On HTTP 404 or error: return `None`.

Public method signature:

```python
def get_user_by_name(self, username: str) -> Optional[tuple[str, str]]: ...
```

## Threading Through Processor

`Processor.__init__` gets a new `mention_resolver: Optional[MentionResolver] = None` parameter, stored as `self.mention_resolver`. `_synchronize_page` passes it to `ConfluenceDocument.create()`:

```python
def _synchronize_page(self, path: Path, page_id: ConfluencePageID) -> None:
    page_id, document = ConfluenceDocument.create(
        path, self.options, self.root_dir, self.site, self.page_metadata,
        kroki_server=self.kroki_server,
        mention_resolver=self.mention_resolver,
    )
    self._update_page(page_id, document, path)
```

`SynchronizingProcessor.__init__` sets it at construction:

```python
super().__init__(
    options, api.site, root_dir,
    kroki_server=kroki_server,
    mention_resolver=api.get_user_by_name,
)
```

`ProcessorFactory` propagates the same parameter to allow `LocalConverter` to pass `None`.

## Testing

### Unit tests (`tests/test_mentions.py`)
- `@username` with a mock resolver returning v2 account-id → correct `<ac:link>` CSF
- `@username` with a mock resolver returning v1 username → correct `<ac:link>` CSF
- `@unknown` with resolver returning `None` → plain text output + WARNING logged
- `@username` with `mention_resolver=None` (local mode) → plain text, no warning
- `@username` inside a fenced code block → not converted (Markdown InlineProcessor does not run inside code spans/blocks)

### API unit tests (`tests/test_api_mappers.py` or new `tests/test_api_mentions.py`)
- `_get_user_by_name_v2`: mock response with matching `username` field → returns `("ri:account-id", ...)`
- `_get_user_by_name_v2`: mock response with no exact match → returns `None`
- `_get_user_by_name_v1`: mock 200 response → returns `("ri:username", "jsmith")`
- `_get_user_by_name_v1`: mock 404 response → returns `None`
