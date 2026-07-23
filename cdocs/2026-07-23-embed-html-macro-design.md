# Design: `embed_html` macro

Date: 2026-07-23
Branch: `feat/embed-html-macro`

## Purpose

Embed a self-contained interactive HTML file into a Confluence page as a **live**
rendering, via the Confluence `html` macro wrapping an `<iframe srcdoc='...'>`.

Motivating case: a sibling repo generates a ~230 KB self-contained "traceability
explorer" (inline CSS + JS, no external dependencies: tabs, search/filter, a canvas
force-directed dependency graph, its own light/dark toggle). The team publishes to
GrantSolutions Confluence (space `GSSPACE`, Server/Data Center, HTML macro enabled)
using this md2conf fork and wants the explorer rendered live rather than linked.

## Invocation

```markdown
<!-- macro:embed_html: path/to/file.html -->
<!-- macro:embed_html: explorer.html, height=1400px, width=90%, title=Traceability Explorer -->
```

| Parameter | Kind       | Default              | Notes                                     |
| --------- | ---------- | -------------------- | ----------------------------------------- |
| path      | positional | *(required)*         | Resolved relative to the source `.md` dir |
| `height`  | named      | `1040px`             | CSS length, used verbatim                 |
| `width`   | named      | `100%`               | CSS length, used verbatim                 |
| `title`   | named      | `Embedded HTML`      | iframe `title` attribute (escaped)        |

## Path resolution decision

**Decision: resolve relative to the source Markdown file's directory.**

`expand_macros(text)` is invoked from `ConfluenceDocument.__init__`
(`md2conf/converter.py`), which already receives the document `path`. Therefore
`path.parent` — the same `base_dir` that `ConfluenceStorageFormatConverter` uses to
resolve images, drawio diagrams, and linked attachments — **is** reachable at the
macro layer. We thread it rather than falling back to the current working directory.

This gives `embed_html` the same *path resolution* semantics as existing file
attachments. The difference in *delivery*: attachments are uploaded to Confluence and
referenced by URL, whereas `embed_html` inlines the file's bytes into the page via the
iframe `srcdoc` attribute.

If no context is supplied (e.g. a direct unit-test call to `expand_macros(text)`), the
expander falls back to `Path.cwd()`.

*Deferred:* attachments additionally bounds-check the resolved path against `root_dir`
via `is_directory_within()`. Applying that here would require threading `root_dir` and
the warn-or-raise option through the macro layer. Not done — YAGNI for now, noted as
possible later hardening.

## Threading design

Expanders are registered as `Callable[[str], str]`, and `MacroExpander.expand()` wraps
every call in `except Exception: return match.group(0)`. That swallow is the governing
constraint: **any signature mismatch fails silently** — the macro simply stops
expanding, with no error surfaced.

**Decision: arity-detected opt-in.** `expand()` introspects each expander's parameter
count and passes a context object only to expanders that accept one.

```python
@dataclass
class MacroContext:
    base_dir: Optional[Path] = None

def expand(self, text: str, context: Optional[MacroContext] = None) -> str:
    ...
    fn = self.registry[macro_name]
    if _accepts_context(fn):
        return fn(params, context)
    return fn(params)
```

- Existing built-ins (`jira`, `status`, `emoticon`) keep their one-argument signature,
  untouched.
- The public `register_macro()` contract is preserved, so any externally registered
  one-argument expander keeps working.
- `expand_macros(text, base_dir=None)` builds the `MacroContext`;
  `converter.py` passes `path.parent`.

Rejected alternative — a uniform two-argument signature — would have been simpler
control flow but changes the documented public contract, and any external one-argument
expander would raise `TypeError`, be swallowed, and silently stop expanding.

## Expander algorithm

`expand_embed_html(params: str, context: Optional[MacroContext]) -> str`

1. Parse `params` with the existing `parse_parameters()` helper → positional path plus
   named `height` / `width` / `title`. Missing path → return original text unchanged.
2. Resolve `(context.base_dir or Path.cwd()) / path`, then `.resolve()`.
3. Read the file as UTF-8. On `OSError` (missing/unreadable): `LOGGER.warning` and
   return the original `<!-- macro:embed_html: ... -->` text unchanged.
4. If the content exceeds a size threshold (5 MB), `LOGGER.warning` about page weight.
5. **Strip HTML comments:** `re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)`.
   Required because `preprocess_csf_comments_in_html()` matches
   `<!--\s*csf:\s*(.+?)\s*-->` non-greedily — a literal `-->` inside the embedded file
   would truncate the CSF comment and corrupt the output.
6. **Neutralize CDATA breakout:** `html.replace("]]>", "]]]]><![CDATA[>")`. A literal
   `]]>` in the payload would otherwise close the `plain-text-body` CDATA section early.
7. **Escape for a single-quote-delimited `srcdoc`:** `&` → `&amp;` first, then
   `'` → `&#39;`. Only those two. The payload is overwhelmingly double-quoted, so
   single-quote delimiting keeps it roughly the same size instead of exploding it.
8. Build the iframe (title escaped the same way):
   `<iframe srcdoc='...' style='width:{width};height:{height};border:0' loading='lazy' title='{title}'></iframe>`
9. Wrap:
   `<ac:structured-macro ac:name="html"><ac:plain-text-body><![CDATA[{iframe}]]></ac:plain-text-body></ac:structured-macro>`
10. Return `<!-- csf: {macro} -->`.

Registered as `embed_html` in `_register_builtin_macros()`.

### No `sandbox` attribute

The embedded file needs its inline `<script>` to run (tabs, search, canvas graph). A
`sandbox` without `allow-scripts` breaks it outright, and `allow-scripts` largely
defeats the purpose. The Confluence `html` macro is itself the trust boundary — it is
admin-enabled and restricted on the target instance.

### Error handling

The expander is internally defensive (warn + return original text on file errors);
`expand()`'s outer `except Exception` remains the backstop. On graceful failure the raw
`<!-- macro:embed_html: ... -->` passes through Markdown as a comment and disappears
from the rendered page — so every failure path logs a warning, making an absent embed
diagnosable instead of silent.

## Testing

**Unit** — `tests/test_macros.py` (new), driving a small fixture HTML that contains an
inline `<!-- comment -->`, a `]]>`, and `&` / `'` characters:

- result is a `<!-- csf: ... -->` wrapping `ac:name="html"` containing `<iframe srcdoc=`
- HTML comments are stripped
- `&` → `&amp;` and `'` → `&#39;`
- `]]>` is neutralized
- missing file returns the original macro text unchanged
- `height` / `width` / `title` params are honoured; defaults applied when absent
- arity regression: existing one-argument expanders still expand through `expand()`

**End-to-end** — `tests/source/embed_html.md` + fixture `tests/source/embed_html.html`
+ `tests/target/embed_html.xml`, auto-discovered by `TestConversion.test_markdown`
(which scans `tests/source/*.md`). The fixture HTML must contain no 36-character
hex-ish string, because `standardize()` rewrites those to `UUID` on the actual side
only, which would cause a spurious mismatch. CDATA round-tripping is not a concern:
the harness normalizes both sides through `canonicalize()`.

**Gate** — full `pytest` suite plus `ruff check` and `ruff format --check` green.

## Out of scope

The sibling `matilionglueanalysis` repo is not touched. It will add the macro
invocation to its own docs and run `md2conf` itself.
