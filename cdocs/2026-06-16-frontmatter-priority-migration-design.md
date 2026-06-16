# Frontmatter Priority & Migration Design

**Date:** 2026-06-16
**Status:** Approved

## Summary

Two related changes to md2conf's metadata handling:

1. Flip priority so YAML frontmatter wins over HTML comment-based metadata.
2. Add a `migrate` subcommand that rewrites existing `.md` files from comment-based to frontmatter-based metadata, with deprecation warnings during normal sync to drive discovery.

## Background

md2conf already supports both HTML comment metadata and YAML frontmatter. Currently HTML comments take precedence:

```markdown
<!-- confluence-page-id: 12345 -->   ← wins today
---
page_id: "99999"
---
```

This is backwards: frontmatter is the richer, more standard format (supports `title`, `tags`, `synchronized`, `properties`, `layout`) while comments only support three fields (`page_id`, `space_key`, `generated_by`). Frontmatter should be the canonical form.

## Design

### 1. Priority Flip (`scanner.py`)

In `Scanner.read()`, reverse merge order for the three fields shared between comments and frontmatter:

```python
# Before (comments win):
page_id = page_id or p.confluence_page_id or p.page_id

# After (frontmatter wins):
page_id = p.page_id or p.confluence_page_id or page_id
```

Same pattern for `space_key` and `generated_by`. Three one-line changes. HTML comments remain valid as a fallback for files that haven't been migrated.

### 2. Deprecation Warning During Sync

After metadata extraction in `Scanner.read()`, check whether any field's value originated from an HTML comment (i.e., was present in the raw text before frontmatter parsing). If so, emit a `logging.warning()` per file:

```
WARNING: path/to/file.md uses HTML comment metadata (<!-- confluence-page-id: ... -->).
Run `python -m md2conf migrate <path>` to convert to YAML frontmatter.
```

One warning per file, non-fatal. Does not block sync.

Implementation detail: track whether any comment-based value was actually used (i.e., after the priority flip, the comment value was the only source — no frontmatter equivalent existed) to avoid spurious warnings on files that have both forms but frontmatter already wins.

### 3. `migrate` Subcommand

**Invocation:**
```bash
python -m md2conf migrate [--dry-run] [--no-backup] <path>
```

**Options:**
- `--dry-run`: Print what would change for each file; make no writes. Default: off.
- `--no-backup`: Skip writing `.md.bak` backup files. Default: backups enabled.
- `<path>`: A single `.md` file or a directory (recursively scanned, respects `.mdignore`).

**Per-file behavior:**
1. Parse the file using `Scanner` to detect comment-based metadata.
2. If no comment-based metadata is found, skip the file (already clean).
3. Otherwise:
   - Extract comment values that have no frontmatter equivalent.
   - If frontmatter block exists: merge extracted comment values into it (only for keys not already present in frontmatter).
   - If no frontmatter block: create a new frontmatter block at the top of the file with the extracted values.
   - Remove the now-redundant HTML comment lines from the body.
   - In dry-run: print a diff-style summary. No writes.
   - Otherwise: write `.md.bak` backup (unless `--no-backup`), then write the updated file.

**Edge cases:**
- File has both comments and frontmatter for the same key: frontmatter value wins (already authoritative after the priority flip); just remove the dangling comment.
- `generated_by` is an internal field; migrate it but don't surface it prominently in user-facing docs.
- Files already fully using frontmatter: silently skipped.

**Output summary:**
```
Scanned 42 files.
  Migrated:          12
  Already clean:     28
  Skipped (errors):   2
Backups written to *.md.bak
```

### 4. Where `migrate` Lives

`migrate` is a new subcommand in `__main__.py`, registered alongside the existing root sync command. The root invocation (`python -m md2conf <path>`) is unchanged.

```
python -m md2conf <path>              # sync (unchanged)
python -m md2conf migrate <path>      # migrate comment metadata → frontmatter
python -m md2conf migrate --dry-run   # preview changes
```

## Files Affected

| File | Change |
|---|---|
| `md2conf/scanner.py` | Flip priority (3 lines); add deprecation warning logic |
| `md2conf/__main__.py` | Register `migrate` subcommand |
| `md2conf/migrator.py` | New module: migration logic (scan, backup, rewrite) |
| `tests/test_scanner.py` | Tests for new priority behavior and warning emission |
| `tests/test_migrator.py` | Tests for migrate dry-run, backup, merge, edge cases |

## Testing

- **Unit**: `test_scanner.py` — verify frontmatter wins over comments for each of the three shared fields; verify warning is emitted only when comment value was the sole source.
- **Unit**: `test_migrator.py` — cover: comment-only file, frontmatter-only file (no-op), mixed file (merge), dry-run produces no writes, backup written by default, `--no-backup` skips backup.
- **Existing tests**: Run full test suite to confirm no regression in current sync behavior.

## Out of Scope

- Upstream cherry-picks (page order, user mentions, PlantUML) — separate specs.
- Removing comment support entirely — comments remain valid as a fallback indefinitely.
- Auto-migration during sync (silently rewriting files during a sync run is too surprising).
