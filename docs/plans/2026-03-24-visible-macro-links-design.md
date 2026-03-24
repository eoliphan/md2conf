# Visible Macro Links Design

## Problem

md2conf macros use HTML comment syntax (`<!-- macro:jira: PROJ-123 -->`) which is invisible in local Markdown rendering. For visual elements like Jira ticket references and status badges, this means the content disappears when previewing in VS Code, Obsidian, or any other Markdown viewer.

## Solution

Add support for standard Markdown link syntax with custom URL schemes (`jira:`, `status:`) that render visibly in local Markdown previews and convert to proper Confluence macros on upload.

## Syntax

### Jira Links

```markdown
[PROJ-123](jira:PROJ-123)
[PROJ-123](jira:PROJ-123?showSummary=true)
```

- Link text renders locally as "PROJ-123" in any Markdown viewer
- Converts to `<ac:structured-macro ac:name="jira">` on upload
- Query parameters map to macro parameters

### Status Badges

```markdown
[Done](status:green)
[In Progress](status:yellow)
[Blocked](status:red)
```

- Link text becomes the status title, path becomes the color
- Converts to `<ac:structured-macro ac:name="status">` on upload

### Coexistence

The existing comment syntax (`<!-- macro:jira: PROJ-123 -->`) continues to work unchanged. Both syntaxes coexist — use link syntax for visible inline references, comment syntax for edge cases or macros without a natural visual representation.

## Approach

Intercept custom URL schemes in `_transform_link()` in `converter.py`, before the existing `is_absolute_url` bail-out. This works on the parsed HTML DOM, so no false matches inside code blocks.

### Detection Point

At the top of `_transform_link`, parse the URL and check for `jira:` or `status:` schemes before any other processing:

```python
parsed = urlparse(url)
if parsed.scheme == "jira":
    return self._transform_jira_link(anchor, parsed)
elif parsed.scheme == "status":
    return self._transform_status_link(anchor, parsed)
```

`urlparse("jira:PROJ-123?showSummary=true")` yields:
- `scheme = "jira"`, `path = "PROJ-123"`, `query = "showSummary=true"`

### Jira Transformation

```python
def _transform_jira_link(self, anchor, parsed):
    key = parsed.path
    params = parse_qs(parsed.query)
    show_summary = params.get("showSummary", ["false"])[0]

    # Build <ac:structured-macro ac:name="jira"> with key parameter
    # Only emit showSummary parameter when explicitly true
```

### Status Transformation

```python
def _transform_status_link(self, anchor, parsed):
    color = parsed.path
    title = anchor.text

    # Build <ac:structured-macro ac:name="status"> with colour and title parameters
```

## Files Changed

- **Modified:** `md2conf/converter.py` — scheme detection in `_transform_link`, two new methods (~30 lines total)
- **No new files, no new dependencies, no new CLI flags**

## Testing

- Unit tests for Jira link syntax (basic, with showSummary, without showSummary)
- Unit tests for status link syntax (various colors)
- Verify comment syntax still works alongside link syntax
- Verify regular links are unaffected

## Not In Scope

- Emoticon link syntax (emoji already renders visibly)
- Full Jira URL detection (`https://jira.example.com/browse/PROJ-123` → macro)
- Deprecating comment syntax
