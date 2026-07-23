# Design: `embed_html` macro

Date: 2026-07-23
Branch: `feat/embed-html-macro`
Status: revised after adversarial Codex review (see "Transport" below)

## Purpose

Embed a self-contained interactive HTML file into a Confluence page as a **live**
rendering, via the Confluence `html` macro wrapping an `<iframe>`.

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

| Parameter | Kind       | Default         | Notes                                     |
| --------- | ---------- | --------------- | ----------------------------------------- |
| path      | positional | *(required)*    | Resolved relative to the source `.md` dir |
| `height`  | named      | `1040px`        | Validated CSS length                      |
| `width`   | named      | `100%`          | Validated CSS length                      |
| `title`   | named      | `Embedded HTML` | iframe `title` attribute (escaped)        |

## Transport: base64 (the central decision)

The original design carried the raw HTML inside a `<!-- csf: ... -->` comment. An
adversarial review found three **confirmed blockers**, each reproduced end-to-end:

1. **Payload newlines are destroyed.** `ConfluenceStorageFormatConverter.transform()`
   unconditionally runs `child.text.replace("\n", " ")` (`converter.py:1976`), and
   `NodeVisitor.visit()` recurses into the materialized `<ac:structured-macro>`
   (`converter.py:223`). Verified: `<script>\n// a line comment\nwindow.x = 1;` became
   `<script> // a line comment window.x = 1;` — the `//` then comments out the rest of
   the script. Any embedded JS using line comments would be dead on arrival.
2. **A bare `-->` breaks the carrier.** Stripping *paired* HTML comments leaves a
   standalone `-->` (e.g. `const marker = "-->";`), which truncates the non-greedy
   `<!--\s*csf:\s*(.+?)\s*-->` match in `preprocess_csf_comments_in_html()`
   (`converter.py:115`), corrupting the output mid-CDATA.
3. **Comment stripping corrupts legitimate JavaScript.** `re.sub(r"<!--.*?-->", "")` is
   not HTML-aware. Verified: `const t = "<!-- keep me -->";` → `const t = "";`. Silent
   data loss in any file containing HTML syntax inside a string or template literal.

(The review also noted the visitor converts CDATA into ordinary escaped XML text. That
is real but **harmless**: `&lt;iframe` and `<![CDATA[<iframe` parse to the same text
node, so Confluence receives identical content.)

These are transport failures, not escaping bugs; no amount of escaping fixes them.

**Decision: base64-encode the payload.**

The file is read as **bytes** and base64-encoded. The resulting payload is a single
line drawn from `[A-Za-z0-9+/=]`, which structurally eliminates every blocker at once:

| Hazard                          | Why base64 removes it                          |
| ------------------------------- | ---------------------------------------------- |
| Newline destruction             | No newlines in the payload; replacement is a no-op |
| Bare `-->` truncating carrier   | `-` and `>` are not in the base64 alphabet     |
| `]]>` breaking CDATA            | `]` is not in the base64 alphabet              |
| Comment stripping corrupting JS | **No comment stripping needed at all**         |
| XML-1.0-invalid control chars   | Alphabet is printable ASCII                    |
| Markdown list/indent mangling   | Single line, no leading `*`/`-`/digits+`.`     |
| `UnicodeDecodeError`            | File read as bytes; never decoded in Python    |

The file is therefore preserved **byte-for-byte**. Cost: +33 % size (230 KB → ~307 KB),
comfortably within Confluence Data Center page-storage limits.

### Delivery: JS-decoded `srcdoc`

A one-line shim decodes the base64 into the iframe's `srcdoc`:

```html
<iframe id="mdc-embed-{id}" style="width:{width};height:{height};border:0" loading="lazy" title="{title}"></iframe><script>(function(){var b="{base64}";var e=document.getElementById("mdc-embed-{id}");e.srcdoc=new TextDecoder().decode(Uint8Array.from(atob(b),function(c){return c.charCodeAt(0)}));})();</script>
```

- `srcdoc` (not a `data:` URI) so the iframe inherits the parent origin — the
  explorer's light/dark toggle can use `localStorage`, which an opaque-origin `data:`
  iframe would reject with a `SecurityError`.
- `TextDecoder` + `Uint8Array.from(atob(...))` correctly reconstructs UTF-8; plain
  `atob()` alone would mangle non-ASCII.
- Emitted as a **single line with no `//` comments**, so the visitor's
  newline→space rewrite cannot damage it.
- `{id}` is the first 8 hex chars of the payload MD5 — deterministic (so tests are
  stable) and short enough not to collide with `standardize()`'s 36-char UUID regex.

### No `sandbox` attribute

The embedded file needs its inline `<script>` to run. A `sandbox` without
`allow-scripts` breaks it outright, and `allow-scripts` largely defeats the purpose.
The Confluence `html` macro is itself the trust boundary — admin-enabled and restricted
on the target instance.

## Path resolution decision

**Decision: resolve relative to the source Markdown file's directory, and enforce the
`root_dir` bounds check.**

`expand_macros(text)` is invoked from `ConfluenceDocument.__init__`
(`converter.py:2245`), which already receives the document `path` and `root_dir`.
Therefore `path.parent` — the same `base_dir` that `ConfluenceStorageFormatConverter`
uses to resolve images, drawio diagrams, and linked attachments — **is** reachable at
the macro layer. We thread it rather than falling back to the current working directory.

This gives `embed_html` the same *path resolution* semantics as existing file
attachments. The difference in *delivery*: attachments are uploaded to Confluence and
referenced by URL, whereas `embed_html` inlines the file's bytes into the page.

`root_dir` is threaded too and enforced with `is_directory_within()` after `.resolve()`,
matching `converter.py:952-959`. Without it, `<!-- macro:embed_html: ../../../etc/... -->`
or a symlink would let any file readable by the publishing process be inlined into a
Confluence page — a local-file disclosure primitive. This is **not** deferred.

Because the bounds check is what makes this safe, it is **mandatory**: if no context is
supplied (e.g. a direct `expand_macros(text)` call), `embed_html` refuses to expand
rather than falling back to `Path.cwd()` unchecked. Absolute paths are likewise rejected
outright, since joining an absolute path discards `base_dir` entirely.

## Threading design

Expanders are registered as `Callable[[str], str]`, and `MacroExpander.expand()` wraps
every call in `except Exception: return match.group(0)`. That swallow is the governing
constraint: **any signature mismatch fails silently** — the macro simply stops
expanding, with no error surfaced.

**Decision: explicit contextual registration.** A second registry records which macros
take a context; `expand()` does a set-membership lookup, never introspection.

```python
@dataclass
class MacroContext:
    base_dir: Optional[Path] = None
    root_dir: Optional[Path] = None

def expand(self, text, context=None):
    ...
    if macro_name in self.contextual:
        return self.registry[macro_name](params, context)
    return self.registry[macro_name](params)
```

- Existing built-ins (`jira`, `status`, `emoticon`) keep their one-argument signature.
- `register_macro()`'s public contract is preserved; `register_contextual_macro()` is
  added for two-argument expanders.

Rejected alternatives:

- *Uniform two-argument signature* — changes the public contract; any external
  one-argument expander would raise `TypeError`, be swallowed, and silently stop.
- *Arity detection via `inspect.signature`* — unsound as a capability test: bound
  methods omit `self`, `functools.partial` rewrites the signature, `*args` looks
  variadic but accepts a context, keyword-only parameters cannot be passed
  positionally, an unrelated optional second parameter would wrongly receive the
  context, and some C-backed callables raise on inspection. Every misdetection would be
  swallowed and invisible.

## Parameter parsing

`parse_parameters()` splits on commas respecting double quotes and classifies any part
containing `=` as named. That mis-parses real paths: `foo=bar.html` becomes a named
parameter with no path, and `'foo,bar.html'` splits into fragments.

**Decision: split the path off before delegating.** Find the first `,` that is followed
by a recognized named parameter (`height` / `width` / `title`) and treat everything
before it as the path; parse only the remainder with `parse_parameters()`. Paths
containing `,` or `=` therefore work. An empty path is rejected explicitly (note
`parse_parameters("")` yields `[""]`, so `if not positional` alone is insufficient).

## Attribute safety

`title`, `width` and `height` are attacker-influenced text that lands inside
single-quoted attributes and inside the macro body:

- `width` / `height` are validated against `^\d+(\.\d+)?(px|em|rem|%|vh|vw)$`; anything
  else falls back to the default with a warning. This blocks
  `width=100%' onload='...` breaking out of the `style` attribute.
- `title` is HTML-escaped (`&`, `<`, `>`, `"`, `'`).
- The **final assembled body** — not just the file payload — is swept for `]]>` and
  `-->` as defence in depth, so no parameter can break the enclosing CDATA or the CSF
  comment carrier.

## Expander algorithm

`expand_embed_html(params: str, context: Optional[MacroContext]) -> str`

1. Split path from named params; reject an empty path (return original text).
2. Validate `height` / `width`; escape `title`.
3. Resolve `(context.base_dir or Path.cwd()) / path` → `.resolve()`.
4. If `context.root_dir` is set, enforce `is_directory_within()`; else warn + return
   original text.
5. Read as **bytes**. On `OSError`: `LOGGER.warning` + return original text unchanged.
6. `LOGGER.warning` if the file exceeds 5 MB (page weight).
7. `base64.b64encode(data).decode("ascii")`.
8. Build the iframe + decoder shim (single line).
9. Sweep the assembled body for `]]>` / `-->`.
10. Wrap in `<ac:structured-macro ac:name="html"><ac:plain-text-body><![CDATA[...]]></ac:plain-text-body></ac:structured-macro>`.
11. Return `<!-- csf: {macro} -->`.

Registered as a **contextual** macro named `embed_html`.

### Error handling

The expander is internally defensive (warn + return original text); `expand()`'s outer
`except Exception` remains the backstop. On graceful failure the raw
`<!-- macro:embed_html: ... -->` passes through Markdown as a comment and disappears
from the rendered page — so every failure path logs a warning, making an absent embed
diagnosable rather than silent.

## Testing

**Unit** — `tests/test_macros.py` (new). Beyond the happy path, the destructive cases
the review identified:

- payload containing a **bare `-->`** in a JS string — must not truncate the carrier
- payload containing `"<!-- ... -->"` inside a JS string — must be preserved
  byte-for-byte (round-trip the base64 and compare to the original bytes)
- payload containing **newline-sensitive `//` JavaScript** — verified end-to-end
- payload containing `]]>` and XML-invalid control characters (e.g. `\x0c`)
- payload containing invalid UTF-8 bytes (byte read must not raise)
- missing file → original text unchanged
- path escaping `root_dir` (`../..`) → refused, original text unchanged
- paths containing `,` and `=`
- `]]>`, `-->` and `'` in `title`; `width=100%' onload='` injection attempt
- invalid `height`/`width` → falls back to default
- arity regression: existing one-argument expanders still expand through `expand()`

**End-to-end** — `tests/source/embed_html.md` + fixture `tests/source/embed_html.html`
+ `tests/target/embed_html.xml`, auto-discovered by `TestConversion.test_markdown`
(which scans `tests/source/*.md`). Asserts the **final `doc.xhtml()`**, so the newline
and CDATA behaviour of the real pipeline is covered rather than assumed. The fixture
must contain no 36-character hex-ish run, because `standardize()` rewrites those to
`UUID` on the actual side only.

**Gate** — full `pytest` suite plus `ruff check` and `ruff format --check` green.

## Hardening from the implementation review

A second adversarial review of the implementation confirmed the base64 transport claim
("all three prior payload-corruption blockers are neutralized") and found further
defects, all since fixed:

- **Non-UTF-8 files rendered as `U+FFFD`.** The bytes transport intact, but the
  browser-side `TextDecoder` defaults to UTF-8 in replacement mode. The file is now
  validated as UTF-8 at expansion time and a warning is logged; the test that claimed
  "invalid UTF-8 embeds fine" was overclaiming and now asserts the warning instead.
- **Duplicate embeds left the second iframe blank.** The frame id derived only from the
  payload hash, so embedding the same file twice made both shims target the first
  iframe via `getElementById`. The shim now locates its frame with
  `document.currentScript.previousElementSibling`, falling back to the id.
- **Contextless absolute paths bypassed containment.** `Path("/a") / "/etc/hosts"`
  discards the base, and `root_dir` was optional, so `expand_macros(text)` with no
  context could read any readable file. Context is now mandatory for `embed_html` and
  absolute paths are rejected outright.
- **Case-insensitive split, case-sensitive lookup.** `HEIGHT=200px` split the
  parameters but was then ignored. Named keys are now lower-cased.
- **Quote stripping.** `.strip('"').strip("'")` removed quote characters independently;
  it now removes a single matching enclosing pair.
- **The test suite wrote to `/tmp/secret.html`** — outside the temporary directory it
  owned — and deleted it, which could clobber an unrelated file and race parallel runs.
  All artifacts now stay inside the owned temporary directory.
- `base64.b64decode` in the test helper is now `validate=True`, since a browser's
  `atob()` rejects trailing content that Python tolerates.
- The `]]>` / `-->` sweep is unreachable by construction, so it now logs a warning if it
  ever fires rather than silently applying a lossy rewrite.

Accepted limitations, documented in the README rather than fixed: macro parameters
cannot contain `-->` (inherent to the comment carrier, shared by all macros), a `title`
containing a comma must be double-quoted, and a path containing `,height=` / `,width=` /
`,title=` cannot be expressed.

## Out of scope

The sibling `matilionglueanalysis` repo is not touched. It will add the macro
invocation to its own docs and run `md2conf` itself.
