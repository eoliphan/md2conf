# Page Collision Fix — Follow-Up Backlog

**Date:** 2026-07-28
**Branch:** `fix/page-collision-guard`
**Context:** [analysis](2026-07-27-page-collision-analysis.md) · [design](2026-07-27-page-collision-fix-design.md) · [plan](2026-07-28-page-collision-fix-plan.md)

What the shipped branch does **not** close, ranked. Recorded so none of it is rediscovered the hard way.

---

## 1. The root cause is still there — salted digest (highest priority)

`Processor._generate_hash` (`processor.py:308-315`) is unchanged: it still hashes the path **relative to the publish root**, so two projects publishing their own `00-inception/` still generate the identical lookup key.

The branch's strategy is **detect-and-abort, not don't-collide**. That was the right call for the incident — Confluence enforces unique titles per space, so md2conf cannot sidestep by suffixing — but it means the collision still occurs and is merely caught.

**This and item 2 are the same defect seen from two angles.** Closing it needs the salted digest (space key + root page id + relative path) with the two-pass migration in design §3.D. That migration is only safe now that containment checking exists, which was the stated precondition.

## 2. Two projects sharing one `-r` anchor defeat the guard

If two projects pass the **same** `-r` and neither root document carries an explicit page id, both synthesize the same root title. Project A's root lookup resolves to Project B's root page; that page genuinely *is* a descendant of the shared anchor, so containment passes; the boundary is then rebound to B's root and A publishes its whole tree inside B's.

Found during implementation, reproduced, and confirmed by code reading (`publisher.py:111` passes the anchor, `:183` rebinds to the resolved page). Design §4.1 originally overstated its protection — it holds only when the anchors **differ**.

Hierarchical containment cannot express ownership when the hierarchy is shared. A real fix needs an independent ownership signal — e.g. a Confluence content property naming the owning project, checked before adoption.

**Currently mitigated by documentation only:** CHANGELOG "Known limitations" and README both state that each project must use its own `-r`.

## 3. Publishing without `-r` is unguarded

`-r` is optional. When absent, `real_id` comes from the root document itself (`publisher.py:104-105`), so the root's containment check evaluates `contains(x, x)` — always true. A poisoned root document re-published without `-r` publishes the tree into the foreign page.

The branch now emits a `LOGGER.warning` on this branch, but nothing enforces it, and the zero-config invocation is precisely the one that skips it. Closing it properly needs a trusted external anchor.

## 4. The archived-page check is broken on Data Center

`api_mappers.py:51` and `:127` set `status = str(...)` — a plain string — where the field is typed `ConfluenceStatus`. So `page.status is ConfluenceStatus.ARCHIVED` never matches on v1, and the archived-page guard silently does nothing on Server/DC.

mypy already reports this (`api_mappers.py:94`, `:164`). Deliberately left out of scope: it is unrelated to collisions and fixing it changes archived-page handling on every DC publish. **File as its own issue.**

Note `map_space_v1_to_id`-adjacent code at `api_mappers.py:282-283` *does* convert properly, so the file is internally inconsistent.

## 5. Smaller items

| Item | Where |
|---|---|
| The guard is not atomic — depth-first traversal writes earlier nodes before a later node trips it. Guarantee is "no write to the offending page", not "no writes". | design §8 |
| TOCTOU: a page validated during structure sync can be moved before content sync writes it. Unavoidable without server-side locking. | design §8 |
| v2 ancestor walk costs one GET per level. Mitigated by prefix caching (a spine is walked once per run, not once per sibling), but wide deep trees on Cloud still add calls. `GET /pages/{id}/ancestors` would replace the walk. | `ancestry.py:43-44` |
| `_properties` test helper sets `status = "current"` (a `str`) where the real field is `ConfluenceStatus`, so the archived check passes for the wrong mechanical reason. Would mask an inverted check. | `tests/test_collision_guard.py` |
| `publisher.py` fetches `get_page_properties(found_id)` then `get_page(found_id)` — two round trips for data the second call already returns, since `ConfluencePage` subclasses `ConfluencePageProperties`. | `publisher.py:145`, `:148` |
| `AncestryResolver.__init__` type-hints the concrete `ConfluenceSession` rather than a narrow Protocol exposing only `get_ancestor_ids`. | `ancestry.py` |
| Self-parenting server behavior never verified against a live Cloud instance — no Cloud instance was available. The fix prevents the call rather than depending on the server's answer. | design §5.5 |
| `ruff format --check` reports 7 pre-existing files needing reformat; none touched by this branch. | repo-wide |

---

## Operational note

The manual remediation runbook for the original incident (analysis §5) is **independent of this branch** and still applies. In particular: any page left at a `stem [hash]` placeholder title remains a live collision target, and the audit pattern must be `\[[0-9a-f]{16,32}\]` — not a fixed 32 hex characters, because `_generate_hash` uses `{c:x}` rather than `{c:02x}` and about 64% of digests are shorter than 32 characters.
