# Design: Cross-Effort Page Collision Fix

**Date:** 2026-07-27
**Status:** design — approved for planning, not yet implemented
**Analysis:** [2026-07-27-page-collision-analysis.md](2026-07-27-page-collision-analysis.md)

Fixes the defect that let one effort's publish silently overwrite another effort's Confluence page in the shared `GSSPACE` space, plus three related defects found while tracing it.

---

## 1. Goals

1. A publish must never adopt and overwrite a page outside its own tree — **fail closed**, before any write.
2. Stop the recurrence for the already-poisoned checkout, where a foreign page id is now embedded in the source Markdown.
3. Fix the latent defects that mask or enable the above: unpopulated `parentId` on v1, self-parenting on the root node, and ambiguous title matches silently routed to a create.

## 2. Non-goals

Deferred to follow-up work, with rationale in the analysis:

- **Salted digest (analysis §3.D).** Re-keys every published auto-titled page; needs a two-pass migration and is only safe once containment checking exists.
- **`--strict-create` (§3.E).** Independent opt-in policy flag.
- **`--local` dry-run warning (§3.G).** Independent, additive.
- **Digest padding `{c:x}` → `{c:02x}` (§2.2).** Deliberately excluded: it re-keys existing pages exactly as the salt does, so it belongs with that migration rather than in a safety fix.

The manual remediation runbook (analysis §5) is operational and proceeds independently of this change.

---

## 3. Ordering constraint

The four items are interlocked and ship as one change:

- **B** (expand `ancestors`) populates `parentId` on Data Center, which is the data **A**'s guard reads. A without B compares against `None` and rejects every page on DC.
- **B** also unmasks the §7.1 self-parenting bug, which is currently inert on DC only because `parentId` is always `None`. The self-parent guard must land in the same commit.
- The ambiguity fix is in the same function A restructures.

Splitting them produces an intermediate state that is broken on Data Center in one direction or the other.

---

## 4. Components

### 4.1 `api.py` — expand `ancestors` on v1 (item B)

| Site | Current `expand` | New |
|---|---|---|
| `_get_page_v1` (api.py:1141) | `body.storage,version,space` | `body.storage,version,space,ancestors` |
| `_get_page_properties_v1` (api.py:1170) | `version,space,history` | `version,space,history,ancestors` |

The existing mappers (api_mappers.py:57-61, :133-138) already derive `parentId` from `ancestors[-1]`; they need no change. Costs no extra round trip — only a larger response body.

### 4.2 `api.py` — new `get_ancestor_ids(page_id) -> list[str]`

The only new API surface. Returns ancestor page ids, root-first, excluding the page itself.

- **v1:** reads the full `ancestors` chain from the response already expanded by §4.1.
- **v2:** bounded upward walk following `parentId`, memoized per run, with a depth cap.

The walk is chosen over Cloud's `GET /pages/{id}/ancestors` deliberately: no new endpoint dependency, it uses data already in the domain model, and it runs only on the explicit-id branch. The dedicated endpoint is a viable later optimization if call volume becomes a concern.

The depth cap is a safety stop against malformed or cyclic parent data, not a supported tree-depth limit; exceeding it raises rather than silently truncating, because a truncated chain would make containment fail open.

**This resolves the open question in analysis §6:** `ConfluencePageProperties` gains no ancestor-chain field. The chain lives behind this one function.

### 4.3 `publisher.py` — split the lookup/create seam

`get_or_create_page` cannot fail before a write, because its return value does not distinguish adoption from creation (analysis §7.2). It has exactly one caller (publisher.py:116), so the split is contained:

```python
page_id = self.api.page_exists(title, ...)
if page_id is not None:
    props = self.api.get_page_properties(page_id)
    self._assert_adoptable(props, parent_id)   # validates BEFORE any write
    page = self.api.get_page(page_id)
else:
    page = self.api.create_page(parent_id.page_id, title, "")
```

The publisher owns publish policy; the API layer stays mechanical. On a guard violation nothing has been written to Confluence.

`api.get_or_create_page` is then **removed**. It is the unsafe primitive that caused the incident — space-wide adoption with no containment check — and leaving it in a published package invites a consumer to reintroduce the bug. This is a breaking change to the public API surface and must be noted in the changelog.

### 4.4 `publisher.py` — the two containment guards (item A)

Scope differs per branch, per analysis §3.A.1:

| Branch | Rule | Rationale |
|---|---|---|
| Title lookup (publisher.py:107-116) | Found page's `parentId` must equal the target parent | After a first successful publish the page id is recorded, so a moved document takes the explicit-id branch. A title-only match under a different parent is therefore never a legitimate move — it is a collision |
| Explicit `page_id` (publisher.py:85-104) | Page must be contained under the **resolved root**, checked before re-parent or write | A stronger identity assertion justifies the looser scope. This is the rule that catches the already-poisoned `source-inventory.md` |

**Threading the resolved root.** `_synchronize_subtree` recurses with a *per-level* parent (publisher.py:146), so the root is not available at depth. It is passed as an explicit additional parameter rather than stored on `self`, keeping the recursion free of hidden state.

The containment root is `real_id` as resolved at publisher.py:67-71 — **not** the `-r` flag. Publishing without `-r` is legal when the root Markdown carries its own page id (branch at :70-71), and a rule phrased against the flag would have no root in that mode.

### 4.5 `publisher.py` — self-parent guard (analysis §7.1)

Skip the re-parent check when `node.page_id == parent_id.page_id`. This is the root node comparing against itself; the current code attempts `move_page(root_id, root_id)`.

Server behavior for a self-parenting request is **unverified** — no Cloud instance is available in this environment. The fix is defensive and does not depend on knowing which way the server responds. Both plausible outcomes (a 4xx surfacing through `raise_for_status`, or silent acceptance) are prevented by not issuing the call.

### 4.6 `api.py` — ambiguous match becomes an error

`page_exists` currently returns `None` when `len(results) != 1` (api.py:1759, :1803), so ambiguity is indistinguishable from absence and falls through to a create attempt. Change both versions to raise when `len(results) > 1`. Zero results still returns `None`.

### 4.7 Error type and CLI

- `environment.py`: new `PageCollisionError(PageError)`, consistent with the existing custom-exception pattern.
- `domain.py`: `ConfluenceDocumentOptions` gains `allow_adopt: frozenset[str] = frozenset()`.
- CLI: repeatable `--allow-adopt <page-id>`.

A blanket `--force` is rejected: it would disable the guard for every page in the run, including pages nobody inspected. `--allow-adopt` authorizes exactly the collision the operator reviewed.

**Error message contents** (analysis §4.3): both page ids, both titles, the offending page's location, and the `--allow-adopt <id>` invocation that would permit it. The operator should be able to see whose page they nearly overwrote without opening Confluence.

---

## 5. Testing

`tests/test_api_move.py` provides a `_make_session(deployment_type)` helper that builds a `ConfluenceSession` against a mocked `requests.Session` with no network. Every case below is unit-testable through it — which matters, because no Cloud instance is available to reproduce §7.1 live.

Tests are written before implementation, per the project's TDD rule. Both deployment types are covered per CLAUDE.md's dual-deployment requirement.

| # | Case | Expectation |
|---|---|---|
| 1 | v1 page fetch after the expand change | `parentId` populated from `ancestors[-1]` |
| 2 | `get_ancestor_ids` on v1 | Full chain, root-first, page itself excluded |
| 3 | `get_ancestor_ids` on v2 | Same result via `parentId` walk; memoized; depth cap raises |
| 4 | Title branch, parent matches | Page adopted |
| 5 | Title branch, parent differs | `PageCollisionError`; **no write issued** |
| 6 | Explicit id, inside root | Proceeds |
| 7 | Explicit id, outside root | `PageCollisionError`; **no write issued** — the incident's recurrence path |
| 8 | Root node where `node.page_id == parent_id` | No `move_page` call |
| 9 | `page_exists` with >1 result | Raises; 0 results still returns `None` |
| 10 | `--allow-adopt` naming the offending id | Adoption proceeds for that id only; a second violation still raises |

Case 5 and 7 must assert on the *absence* of write calls against the mock, not merely that the exception was raised — the fail-closed claim is about writes, not about control flow.

---

## 6. Backward compatibility

**The hard error is a deliberate behavior change.** Trees that relied on space-wide adoption will now fail loudly. This is the point of the change; `--allow-adopt` is the escape hatch, and the error message names the exact invocation needed.

**Data Center re-parenting comes back to life.** md2conf has silently never re-parented pages on DC (analysis §2). Once B lands, trees that drifted will re-parent on the next publish — now containment-checked first, so no cross-effort moves are possible. Behavior is normal re-parenting with the existing INFO log per move; no phase-in flag. Adding a flag would leave a genuine bug disabled by default.

**Removing `get_or_create_page`** breaks any external consumer calling it directly. Changelog note required.

---

## 7. Risks

| Risk | Mitigation |
|---|---|
| Self-parent server behavior unverified | Fix is defensive; correct under either outcome. Case 8 asserts the call is not issued |
| v2 ancestor walk adds API calls | Only on the explicit-id branch; memoized per run; trees are shallow |
| Hard error breaks an unknown legitimate workflow | `--allow-adopt`; error names the fix. Analysis §6 flags confirming no such workflow exists as an open item |
| Depth cap hit on a legitimately deep tree | Raises rather than truncating, so containment never fails open. Cap set well above realistic depth |

---

## 8. Out of scope for this design

Carried forward from analysis §6 and §7.3:

- **TOCTOU window (§7.3).** Structure sync runs before content sync, so a page validated during the structure pass can be moved before the write. The window is small and the guard is not an atomic reservation. Not addressed here; documented so it is not mistaken for a guarantee.
- Confirming no existing workflow depends on adopting pages outside the resolved root (analysis §6).
