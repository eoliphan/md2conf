# Design: Cross-Effort Page Collision Fix

**Date:** 2026-07-27
**Status:** design — revised after adversarial review, pending approval
**Analysis:** [2026-07-27-page-collision-analysis.md](2026-07-27-page-collision-analysis.md)

Fixes the defect that let one effort's publish silently overwrite another effort's Confluence page in the shared `GSSPACE` space, plus related defects found while tracing it.

> **Revision note.** An earlier draft proposed *immediate-parent equality* for the title branch and used the resolved `real_id` as the containment boundary. Adversarial review (Codex, `gpt-5.6-sol`) refuted both. See §9 for what changed and why — the reasoning matters, because the rejected design would have broken stateless CI and still permitted the original incident under a shared `-r`.

---

## 1. Goals

1. A publish must never adopt and overwrite a page **outside its own managed tree** — fail closed, before writing to that page.
2. Stop the recurrence for the already-poisoned checkout, where a foreign page id is embedded in the source Markdown.
3. Fix the latent defects that mask or enable the above: unpopulated `parentId` on v1, self-parenting and cycles on re-parent, and ambiguous title matches silently routed to a create.

## 2. Non-goals

Deferred, with rationale in the analysis: salted digest (§3.D), `--strict-create` (§3.E), `--local` dry-run warning (§3.G), and the digest padding fix (§2.2 — excluded deliberately, since it re-keys existing pages exactly as the salt does and belongs with that migration).

The manual remediation runbook (analysis §5) is operational and proceeds independently.

---

## 3. Ordering constraint

The items are interlocked and ship as one change. **B** (expand `ancestors`) populates `parentId` on Data Center, which is the data **A**'s guard reads — A without B compares against `None` and rejects every page on DC. B also unmasks the self-parenting bug, so that guard must land in the same commit. The ambiguity fix is in the same function A restructures.

---

## 4. The containment rule

One rule, applied to **both** branches that can reach a page:

> The page must be the **managed root** itself, or a descendant of it. Otherwise raise `PageCollisionError`.

Inside-but-misplaced is *not* an error — it is a re-parent, matching the behavior the explicit-id branch already implements (publisher.py:89-97). This separates two distinct questions that the earlier draft conflated:

| Question | Mechanism |
|---|---|
| Does this effort own the page? | Subtree containment → error if not |
| Is the page where the local hierarchy says it should be? | Immediate-parent comparison → re-parent if not |

Containment is **inclusive of the root**, so the root node adopting its own page is legal.

### 4.1 The managed root is the root node's resolved page

The boundary is **not** `real_id`. At publisher.py:60-73, `real_id` is resolved three ways, and in the `-r`-only branch (:68-69) it is the `-r` **anchor** — a container that may sit above the effort's actual tree. The root node then resolves to or creates a *different* page, and the recursion correctly uses `page.id` as the parent for children (:146).

Using `real_id` as the boundary would therefore permit a poisoned explicit id pointing at a **sibling effort sharing the same `-r` container** — the exact shape of the original incident.

The boundary is established in two stages:

1. **Root node:** validated against the `real_id` anchor, allowing equality (the root node may legitimately resolve to the anchor page itself).
2. **All descendants:** validated against the root node's *resolved* `page.id`, threaded through `_synchronize_subtree` as an explicit parameter.

When the root Markdown already identifies the `-r` page (branches :63-67 and :70-71), the anchor and the managed root coincide and the two stages agree.

---

## 5. Components

### 5.1 `api.py` — expand `ancestors` on v1 (item B)

| Site | Current `expand` | New |
|---|---|---|
| `_get_page_v1` (api.py:1141) | `body.storage,version,space` | `body.storage,version,space,ancestors` |
| `_get_page_properties_v1` (api.py:1170) | `version,space,history` | `version,space,history,ancestors` |

Existing mappers (api_mappers.py:57-61, :133-138) already derive `parentId` from `ancestors[-1]` and need no change. No extra round trip.

### 5.2 `api.py` — new `get_ancestor_ids(page_id) -> list[str]`

Returns ancestor page ids root-first, excluding the page itself.

- **v1:** reads the full chain from the response expanded by §5.1.
- **v2:** bounded upward walk following `parentId`, depth-capped.

The walk is chosen over Cloud's `GET /pages/{id}/ancestors` deliberately: no new endpoint dependency, uses data already modeled. The endpoint remains a later optimization.

The depth cap guards against malformed or cyclic parent data. Exceeding it **raises** rather than truncating — a truncated chain would make containment fail *open*.

**Resolves analysis §6:** `ConfluencePageProperties` gains no ancestor-chain field; the chain lives behind this one function.

**Caching.** Results are memoized, but the cache is **owned by the publisher for one `process()` call**, not by `ConfluenceSession` — the session is shared across publisher runs (publisher.py:297), so a session-scoped cache has undefined lifetime. Any successful `move_page` **invalidates the cache**, since the structure pass moves pages during traversal (publisher.py:97) and a stale chain would answer a containment question with pre-move data.

### 5.3 `publisher.py` — split the lookup/create seam

`get_or_create_page` cannot fail before a write: its return value does not distinguish adoption from creation (analysis §7.2). One caller (publisher.py:116), so the split is contained:

```python
parent_page = self.api.get_page_properties(parent_id.page_id)
page_id = self.api.page_exists(title, space_id=parent_page.spaceId)
if page_id is not None:
    props = self.api.get_page_properties(page_id)
    self._assert_owned(props, managed_root)     # containment, before any write
    page = self.api.get_page(page_id)
    self._reparent_if_needed(props, parent_id)  # inside-but-misplaced
else:
    page = self.api.create_page(parent_id.page_id, title, "")
```

**The `get_page_properties(parent_id)` call is retained deliberately.** It is how the v2 lookup derives `spaceId` (api.py:1818-1819). Dropping it would let the lookup match a same-titled page in a *different space* — introducing a new cross-space collision while fixing the cross-effort one.

The publisher owns policy; the API layer stays mechanical.

`api.get_or_create_page` is then **removed** — it is the unsafe primitive behind the incident, and leaving it in a published package invites a consumer to reintroduce the bug. Breaking change; changelog required.

### 5.4 `publisher.py` — self-parent and cycle guards

Three distinct cases, currently conflated:

| Case | Behavior |
|---|---|
| Root node, `node.page_id == parent_id.page_id` | **Skip** the re-parent — legitimate self-comparison (analysis §7.1) |
| Non-root node, `node.page_id == parent_id.page_id` | **Error** — two documents claim the same page id; silently skipping would map both to one page and let the child overwrite the parent during content sync |
| Target parent is a descendant of the page being moved | **Error** — the move would create a cycle. Both pages can be inside the managed root, so containment does not catch this |

Duplicate page ids across local documents are rejected during indexing rather than discovered here.

The self-parent guard must also apply **after title resolution**, not only to a pre-existing `node.page_id` — a title lookup can resolve to the anchor page itself (§4.1 stage 1).

Server behavior for a self-parenting request is **unverified** (no Cloud instance available). The fix is defensive and correct under either outcome, since the call is simply not issued.

### 5.5 `api.py` — ambiguous match becomes an error

`page_exists` returns `None` when `len(results) != 1` (api.py:1759, :1803), so ambiguity is indistinguishable from absence and falls through to a create. Change both versions to raise when `len(results) > 1`; zero results still returns `None`. The error names the matched ids and their statuses rather than reporting generic ambiguity.

This is correct **only because §5.3 keeps the space scoping**. Identical titles across different spaces are legitimate; without correct `spaceId` scoping this change would raise on healthy data.

`page_exists` is public API, so this is a **second breaking change** alongside the `get_or_create_page` removal. Both belong in the changelog.

### 5.6 Error type and CLI

- `environment.py`: `PageCollisionError(PageError)`, following the existing custom-exception pattern.
- `domain.py`: `ConfluenceDocumentOptions` gains `allow_adopt: frozenset[str] = frozenset()`.
- CLI: repeatable `--allow-adopt <page-id>`.

A blanket `--force` is rejected: it would disable the guard for every page in the run. `--allow-adopt` authorizes exactly the collision the operator reviewed.

**Error message** (analysis §4.3): both page ids, both titles, the offending page's ancestor location, and the literal `--allow-adopt <id>` invocation that would permit it.

When `--allow-adopt` authorizes a boundary crossing, the adopted page **is** re-parented into the managed tree, and the ancestor cache is invalidated accordingly.

---

## 6. Testing

`tests/test_api_move.py` provides `_make_session(deployment_type)` — a `ConfluenceSession` over a mocked `requests.Session`, no network. Every case is unit-testable through it, which matters because no Cloud instance is available to reproduce the self-parent case live. Tests precede implementation per the project's TDD rule; **cases 4-14 run against both deployment types** per CLAUDE.md's dual-deployment requirement.

| # | Case | Expectation |
|---|---|---|
| 1 | `_get_page_v1` and `_get_page_properties_v1` after expand | `parentId` populated from `ancestors[-1]` — **both** paths |
| 2 | `get_ancestor_ids` v1 | Full chain root-first from a realistic mapped response, page excluded |
| 3 | `get_ancestor_ids` v2 | Same result via `parentId` walk; depth cap raises rather than truncating |
| 4 | Cache invalidation | Chain re-fetched after `move_page`; not reused across `process()` calls |
| 5 | Title branch, page inside managed root, correct parent | Adopted, no move |
| 6 | Title branch, page inside managed root, wrong parent | Adopted **and re-parented** — the CI/hierarchy-migration case, must not error |
| 7 | Title branch, page outside managed root | `PageCollisionError`; no write to that page |
| 8 | Explicit id, outside managed root | `PageCollisionError`; no write — the incident's recurrence path |
| 9 | Lookup scoping | Asserts the lookup received the **target parent's** `spaceId`; two same-titled pages in different spaces do not raise |
| 10 | Root node resolving to the `-r` anchor itself | Adopted, no move, no error — containment is root-inclusive |
| 11 | Two efforts sharing one `-r`; poisoned id points into the sibling effort | `PageCollisionError` — proves the boundary is the resolved root, not the anchor |
| 12 | Root vs non-root id equality | Root skips re-parent; non-root **raises** |
| 13 | Move target is a descendant of the page | Raises (cycle) |
| 14 | `page_exists` >1 result | Raises with ids and statuses; 0 results returns `None` |
| 15 | `--allow-adopt` | Bypasses for the named id only; a second violation still raises; adopted page is re-parented; CLI parses the repeated flag |
| 16 | Error message contents | Contains both ids, both titles, and the `--allow-adopt` invocation |

**Scope of the fail-closed claim.** Cases 7 and 8 assert no write *to the offending page*. They do **not** establish that a run is atomic: structure sync is depth-first, so nodes earlier in the traversal are created, moved, and have ids written to disk (publisher.py:97, :116, :126) before a later node's violation is discovered. A test placing the violating node last must confirm this scoping is understood rather than contradicted.

---

## 7. Backward compatibility

**Hard error is a deliberate behavior change**, but the surface is much smaller than the earlier draft: only pages *outside* the managed tree fail. Legitimate moves within the tree re-parent silently, so hierarchy migrations, stateless CI, and manual UI moves keep working.

**Data Center re-parenting comes back to life.** md2conf has silently never re-parented on DC (analysis §2). Once B lands, drifted trees re-parent on the next publish — containment-checked first. Normal behavior with the existing INFO log per move; no phase-in flag, which would leave a real bug disabled by default.

**Two public-API breaks:** `get_or_create_page` removed; `page_exists` raises on ambiguity.

---

## 8. Risks

| Risk | Mitigation |
|---|---|
| Self-parent server behavior unverified | Fix is defensive; correct either way. Case 12 asserts the call is not issued |
| v2 ancestor walk adds API calls | Memoized per `process()`; invalidated on move; trees are shallow |
| Cache invalidation missed on some write path | Case 4; invalidate on every successful `move_page` rather than selectively |
| Unknown workflow adopts pages outside the tree | `--allow-adopt`; error names the fix. Analysis §6 open item |
| Deep tree hits the depth cap | Raises rather than failing open; cap well above realistic depth |

---

## 9. What the adversarial review changed

Recorded because the rejected design is superficially attractive and may be re-proposed.

**Immediate-parent equality on the title branch — rejected.** Its justification was that `_update_markdown` records the page id, so a moved document takes the explicit-id branch, making any title match under a different parent a collision. **That invariant does not hold:**

- Stateless CI discards the workspace, so every run re-enters the title branch.
- Documents with an explicit front-matter `title:` use the title branch and never acquire an id (publisher.py:107, scanner.py:200).
- A crash or read-only checkout between `create_page` and `_update_markdown` leaves a real page with no local id.
- Hierarchy flags (`--flatten-hierarchy` / `--keep-hierarchy`) and `.mdignore` edits change a document's computed parent between runs while its path-derived title stays the same (processor.py:212, :228, :237, :249, :285).

Concretely: a CI job publishes flattened, the workspace is discarded, a later job uses `--keep-hierarchy`, the title lookup correctly finds the old page under the old parent — and immediate-parent equality raises on a legitimate migration.

It was also **not sufficient**: a foreign page already sitting under the same target parent passes it.

**`real_id` as the containment boundary — rejected.** In the `-r`-only branch it is the anchor container, not the effort's tree root (§4.1). Efforts sharing one `-r` would pass containment while pointing at each other's pages.

Both corrections make the rule simpler: one containment check, applied uniformly, with re-parenting rather than erroring for in-tree misplacement.
