# Cross-Effort Page Collision Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop md2conf from adopting and overwriting Confluence pages outside the tree it is publishing, and fix the latent defects that mask or enable that.

**Architecture:** One containment rule applied to both branches that can reach a page — the page must be the managed root or a descendant of it, otherwise `PageCollisionError`. Pages inside the tree but under the wrong parent are re-parented rather than rejected. The boundary is two-stage: the root node is checked against the `-r` anchor, descendants against the root node's *resolved* page. A new `AncestryResolver` owns ancestor lookups and their cache; `ConfluenceSession` gains `get_ancestor_ids`; the unsafe `get_or_create_page` is split at its single call site and removed.

**Tech Stack:** Python 3.9+, `unittest` (not pytest), `unittest.mock`, mypy strict, ruff.

**Design:** [2026-07-27-page-collision-fix-design.md](2026-07-27-page-collision-fix-design.md)
**Analysis:** [2026-07-27-page-collision-analysis.md](2026-07-27-page-collision-analysis.md)

> **Revision note.** This plan was stress-tested by Codex (`gpt-5.6-sol`) and corrected. Findings incorporated: the synchronization methods live on `SynchronizingProcessor`, **not** `Publisher`; `_get()` encodes its query into the URL and has no `params` kwarg; `DocumentNode` appends via `add_child`; the v1 mapper leaves `status` a plain string so the archived check is already broken on DC; and `_page_exists_v1` ignores `space_id` entirely. §Rejected Findings records what was considered and not adopted.

## Global Constraints

- **Minimum Python: 3.9.** PEP 585 builtin generics (`list[str]`, `dict[str, str]`) are fine; `X | Y` unions are **not** — use `Optional[X]`.
- **Tests use `unittest`**, never pytest. Single test: `python -m unittest tests.test_module.TestClass.test_name -v`.
- **Full unit suite:** `python -m unittest discover -s tests` — green before any commit.
- **Static checks:** `./check.sh` (ruff + mypy strict over `md2conf`, `tests`, `integration_tests`). **It does not pass on `master`** — baseline is 82 mypy errors and 2 ruff errors. The bar is *no new errors versus that baseline*, not a clean exit.

  **Verify both linters separately — they use different output formats and one grep cannot see both:**

  ```bash
  python -m ruff check          # baseline: "Found 2 errors."  — ruff never prints "error:"
  python -m ruff format --check
  python -m mypy md2conf tests  # baseline: 82 errors, each line containing "error:"
  ```

  Grepping `check.sh` output for `error:` catches mypy only and is **structurally blind to ruff** — an unused import will sail straight through it. Run `ruff check` on its own and compare the count.

  **mypy is strict** — annotate every helper; no bare `dict`, no `object` where a real type exists. Do not import a name "for a later task"; an unused import is a lint failure now.
- **Test imports:** use `from tests.utility import ...`, not `from .utility import ...`. Relative imports break under `python -m unittest discover -s tests`, the canonical command.
- **Line length 160.**
- `LOGGER = logging.getLogger(__name__)` per module; `@override` from `md2conf/extra.py` on overrides; custom exceptions in `md2conf/environment.py`.
- **Both deployment types** tested for anything touching the API, per CLAUDE.md.

### Key facts about this codebase (verified — do not assume otherwise)

| Fact | Location |
|---|---|
| Sync methods live on `SynchronizingProcessor`, not `Publisher` | `publisher.py:28` vs `publisher.py:308` |
| `SynchronizingProcessor(api, options, root_dir, kroki_server=None)`; reads `api.site` in `super().__init__` | `publisher.py:35` |
| `_get(version, path, response_type, *, query=None)` builds the query **into the URL**; no `params` kwarg | `api.py:624-639` |
| `_page_exists_v1` calls `session.get(url, params=query, ...)` directly — `params` **is** correct there | `api.py:1746-1748` |
| `_page_exists_v1` **ignores** `space_id` and uses `self.site.space_key` | `api.py:1734-1735` |
| `DocumentNode.add_child(child)` | `processor.py:62` |
| v1 mappers set `status = str(...)`, a plain string, not `ConfluenceStatus` | `api_mappers.py:51, 127` |

---

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `tests/utility.py` | Shared test helpers — gains `make_session()` | 1 |
| `md2conf/environment.py` | Gains `PageCollisionError` | 1 |
| `md2conf/domain.py` | `ConfluenceDocumentOptions` gains `allow_adopt` | 1 |
| `md2conf/__main__.py` | Repeatable `--allow-adopt` CLI flag | 1 |
| `md2conf/api.py` | v1 `expand` fix; `get_ancestor_ids`; `page_exists` ambiguity; `get_or_create_page` removal | 2, 3, 4, 9 |
| `md2conf/ancestry.py` | **New.** `AncestryResolver` — ancestor lookup, caching, containment | 5 |
| `md2conf/processor.py` | Duplicate local page-id detection | 6 |
| `md2conf/publisher.py` | Seam split, two-stage containment, re-parent, self/cycle guards | 7, 8 |

---

## Task Order

Tasks 1, 3, 5 are genuinely additive. **Tasks 2, 4, 6, 7, 8 all change behavior.**

**Tasks 2, 7 and 8 must not be released separately.** Task 2 populates `parentId` on Data Center, which activates the previously-dead re-parenting branch *including its self-parenting bug*; only Task 8 guards it. Committing them individually is fine for reviewability — shipping between them is not. If this lands as a release boundary, squash 2+7+8.

---

### Task 1: Error type, option plumbing, and shared test helper

No behavior change.

**Files:** Modify `md2conf/environment.py:17-19`, `md2conf/domain.py:49-68`, `md2conf/__main__.py` (:433-453), `tests/utility.py`, `tests/test_api_move.py:19-37`. Test: `tests/test_collision_options.py` (new).

**Interfaces:**
- Produces: `PageCollisionError(PageError)`; `ConfluenceDocumentOptions.allow_adopt: frozenset[str]`; `tests.utility.make_session(deployment_type: str) -> ConfluenceSession`

- [ ] **Step 1: Write the failing test**

Create `tests/test_collision_options.py`:

```python
"""
Tests for collision-guard option plumbing.

Copyright 2022-2025, Levente Hunyadi

:see: https://github.com/hunyadi/md2conf
"""

import unittest

from md2conf.domain import ConfluenceDocumentOptions
from md2conf.environment import PageCollisionError, PageError


class TestCollisionOptions(unittest.TestCase):
    def test_collision_error_is_a_page_error(self) -> None:
        self.assertTrue(issubclass(PageCollisionError, PageError))

    def test_allow_adopt_defaults_to_empty(self) -> None:
        self.assertEqual(ConfluenceDocumentOptions().allow_adopt, frozenset())

    def test_allow_adopt_accepts_page_ids(self) -> None:
        options = ConfluenceDocumentOptions(allow_adopt=frozenset({"123", "456"}))
        self.assertIn("123", options.allow_adopt)
        self.assertNotIn("789", options.allow_adopt)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_collision_options -v`
Expected: FAIL — `ImportError: cannot import name 'PageCollisionError'`

- [ ] **Step 3: Add the exception**

In `md2conf/environment.py`, after `PageError` (line 17-18):

```python
class PageCollisionError(PageError):
    "Raised when a page lookup resolves to a page outside the tree being published."
```

- [ ] **Step 4: Add the option**

In `md2conf/domain.py`, add to the `ConfluenceDocumentOptions` docstring parameter list:

```
    :param allow_adopt: Confluence page IDs that may be adopted even though they fall outside the tree being
        published. Each ID must be authorized explicitly.
```

and add the field after `user_mentions: bool = True`:

```python
    allow_adopt: frozenset[str] = frozenset()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m unittest tests.test_collision_options -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Wire the CLI flag**

In `md2conf/__main__.py`, alongside the other `parser.add_argument` calls:

```python
    parser.add_argument(
        "--allow-adopt",
        dest="allow_adopt",
        action="append",
        metavar="PAGE_ID",
        default=[],
        help="Authorize adopting the Confluence page with this ID even though it lies outside the tree being published. Repeatable.",
    )
```

In the `ConfluenceDocumentOptions(...)` construction at `__main__.py:433-453`, add:

```python
        allow_adopt=frozenset(args.allow_adopt),
```

- [ ] **Step 7: Extract the shared session helper**

Append to `tests/utility.py`:

```python
from unittest.mock import Mock

import requests

from md2conf.api import ConfluenceSession
from md2conf.environment import ConfluenceConnectionProperties


def make_session(deployment_type: str) -> ConfluenceSession:
    """
    Builds a ConfluenceSession backed by a mocked transport, performing no network calls.

    :param deployment_type: One of `cloud`, `datacenter` or `server`.
    """

    session_mock = Mock(spec=requests.Session)
    properties = ConfluenceConnectionProperties(
        domain="example.com",
        base_path="/wiki/",
        user_name="user",
        api_key="key",
        space_key="TEST",
        deployment_type=deployment_type,
    )
    return ConfluenceSession(
        session_mock,
        properties=properties,
        api_url="https://example.com/wiki/",
        domain="example.com",
        base_path="/wiki/",
        space_key="TEST",
    )
```

In `tests/test_api_move.py`, delete the local `_make_session` (lines 19-37) and import the shared one:

```python
from tests.utility import make_session as _make_session
```

- [ ] **Step 8: Run the full suite and static checks**

Run: `python -m unittest discover -s tests && ./check.sh`
Expected: OK; previous count + 3.

- [ ] **Step 9: Commit**

```bash
git add md2conf/environment.py md2conf/domain.py md2conf/__main__.py tests/utility.py tests/test_api_move.py tests/test_collision_options.py
git commit -m "feat: add PageCollisionError and --allow-adopt option plumbing"
```

---

### Task 2: Expand `ancestors` on the v1 fetches

**Behavior change.** Populates `parentId` on Data Center. Design §5.1.

**Files:** Modify `md2conf/api.py:1141`, `md2conf/api.py:1170`. Test: `tests/test_api_ancestors.py` (new).

**Interfaces:**
- Consumes: `tests.utility.make_session` (Task 1)
- Produces: v1 responses carry `ancestors`, so `ConfluencePageProperties.parentId` is populated on v1.

> **`_get` builds the query into the URL** (`api.py:634`) — there is no `params` kwarg on these calls. Assert against the requested URL, not `call_args.kwargs["params"]`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_api_ancestors.py`:

```python
"""
Tests for ancestor retrieval and v1 ancestor expansion.

Copyright 2022-2025, Levente Hunyadi

:see: https://github.com/hunyadi/md2conf
"""

import unittest
import unittest.mock
from typing import Any, Optional
from unittest.mock import Mock

import requests

from tests.utility import make_session


def _json_response(payload: dict[str, Any]) -> Mock:
    response = Mock(spec=requests.Response)
    response.status_code = 200
    response.text = ""
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def _v1_page(page_id: str, title: str, ancestors: list[str]) -> dict[str, Any]:
    return {
        "id": page_id,
        "title": title,
        "status": "current",
        "space": {"id": "1", "key": "TEST"},
        "version": {"number": 1},
        "history": {"createdBy": {"accountId": "user"}},
        "createdDate": "2026-01-01T00:00:00.000Z",
        "ancestors": [{"id": a} for a in ancestors],
        "body": {"storage": {"value": "", "representation": "storage"}},
    }


def _requested_url(transport: Mock) -> str:
    """Returns the URL of the most recent GET, which is where _get encodes its query."""

    return str(transport.get.call_args.args[0])


class TestV1AncestorExpansion(unittest.TestCase):
    def test_get_page_properties_v1_requests_ancestors(self) -> None:
        session = make_session("datacenter")
        transport: Mock = session.session
        transport.get.return_value = _json_response(_v1_page("300", "Child", ["100", "200"]))

        properties = session.get_page_properties("300")

        self.assertIn("ancestors", _requested_url(transport))
        self.assertEqual(properties.parentId, "200")

    def test_get_page_v1_requests_ancestors(self) -> None:
        session = make_session("datacenter")
        transport: Mock = session.session
        transport.get.return_value = _json_response(_v1_page("300", "Child", ["100", "200"]))

        page = session.get_page("300")

        self.assertIn("ancestors", _requested_url(transport))
        self.assertEqual(page.parentId, "200")


if __name__ == "__main__":
    unittest.main()
```

> If `ConfluenceSession` stores its transport under a name other than `session`, adjust the `transport` lines; confirm by reading `ConfluenceSession.__init__`. If `_get` is reached through `_retry_request` such that the URL is not `call_args.args[0]`, read `_retry_request` and assert against whatever it actually passes.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_api_ancestors -v`
Expected: FAIL — `ancestors` absent from the URL; `parentId` is `None`.

- [ ] **Step 3: Add `ancestors` to both expand strings**

`md2conf/api.py:1141` (`_get_page_v1`):

```python
        query = {"expand": "body.storage,version,space,ancestors"}
```

`md2conf/api.py:1170` (`_get_page_properties_v1`):

```python
        query = {"expand": "version,space,history,ancestors"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_api_ancestors -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Run the full suite**

Run: `python -m unittest discover -s tests`
Expected: OK.

> This activates the previously-dead re-parenting branch on Data Center, **including its self-parenting bug**. Any new failure here is that branch waking up. Do not suppress it — Task 8 guards it, and Tasks 2+7+8 ship together.

- [ ] **Step 6: Commit**

```bash
git add md2conf/api.py tests/test_api_ancestors.py
git commit -m "fix(api): expand ancestors on v1 fetches so parentId is populated"
```

---

### Task 3: `ConfluenceSession.get_ancestor_ids`

Additive. Design §5.2.

**Files:** Modify `md2conf/api.py` (after `get_page_properties`, ~:1185). Test: `tests/test_api_ancestors.py` (extend).

**Interfaces:**
- Produces: `ConfluenceSession.get_ancestor_ids(page_id: str) -> list[str]` — ancestor IDs outermost-first, excluding the page itself. Raises `ConfluenceError` beyond `ANCESTOR_DEPTH_LIMIT`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_api_ancestors.py`:

```python
class TestGetAncestorIds(unittest.TestCase):
    def test_v1_returns_full_chain_root_first(self) -> None:
        session = make_session("datacenter")
        transport: Mock = session.session
        transport.get.return_value = _json_response(_v1_page("300", "Child", ["100", "200"]))

        self.assertEqual(session.get_ancestor_ids("300"), ["100", "200"])

    def test_v1_root_page_has_no_ancestors(self) -> None:
        session = make_session("datacenter")
        transport: Mock = session.session
        transport.get.return_value = _json_response(_v1_page("100", "Root", []))

        self.assertEqual(session.get_ancestor_ids("100"), [])

    def test_v2_walks_parent_chain_root_first(self) -> None:
        session = make_session("cloud")
        chain: dict[str, Optional[str]] = {"300": "200", "200": "100", "100": None}

        def fake_properties(page_id: str) -> Mock:
            properties = Mock()
            properties.id = page_id
            properties.parentId = chain[page_id]
            return properties

        with unittest.mock.patch.object(session, "get_page_properties", side_effect=fake_properties):
            self.assertEqual(session.get_ancestor_ids("300"), ["100", "200"])

    def test_v2_depth_limit_raises_rather_than_truncating(self) -> None:
        from md2conf.environment import ConfluenceError

        session = make_session("cloud")

        def cyclic_properties(page_id: str) -> Mock:
            properties = Mock()
            properties.id = page_id
            properties.parentId = "999" if page_id == "888" else "888"
            return properties

        with unittest.mock.patch.object(session, "get_page_properties", side_effect=cyclic_properties):
            with self.assertRaises(ConfluenceError):
                session.get_ancestor_ids("777")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_api_ancestors.TestGetAncestorIds -v`
Expected: FAIL — `AttributeError: ... has no attribute 'get_ancestor_ids'`

- [ ] **Step 3: Implement**

Module-level constant in `md2conf/api.py`, beside the other constants:

```python
ANCESTOR_DEPTH_LIMIT = 100
"Maximum page hierarchy depth traversed when resolving ancestors; a stop against cyclic parent data."
```

Methods after `get_page_properties` (`api.py:1185`):

```python
    def get_ancestor_ids(self, page_id: str) -> list[str]:
        """
        Retrieves the ancestors of a Confluence page, ordered outermost first.

        The page itself is not included in the result.

        :param page_id: The Confluence page ID.
        :returns: Ancestor page IDs, from the topmost ancestor down to the immediate parent.
        """
        if self.api_version == ConfluenceVersion.VERSION_1:
            return self._get_ancestor_ids_v1(page_id)
        else:
            return self._get_ancestor_ids_v2(page_id)

    def _get_ancestor_ids_v1(self, page_id: str) -> list[str]:
        "Retrieves ancestors using the v1 API, which returns the whole chain in a single response."

        path = f"/content/{page_id}"
        query = {"expand": "ancestors"}
        response = self._get(ConfluenceVersion.VERSION_1, path, dict[str, JsonType], query=query)
        ancestors = typing.cast(list[JsonType], response.get("ancestors", []))
        return [str(typing.cast(dict[str, JsonType], item)["id"]) for item in ancestors]

    def _get_ancestor_ids_v2(self, page_id: str) -> list[str]:
        "Retrieves ancestors using the v2 API by walking up the parent chain."

        ancestors: list[str] = []
        current = page_id
        for _ in range(ANCESTOR_DEPTH_LIMIT):
            parent_id = self.get_page_properties(current).parentId
            if parent_id is None:
                ancestors.reverse()
                return ancestors
            ancestors.append(parent_id)
            current = parent_id

        raise ConfluenceError(f"ancestor chain for page {page_id} exceeds the depth limit of {ANCESTOR_DEPTH_LIMIT}; the page hierarchy may contain a cycle")
```

Ensure `ConfluenceError` is imported from `.environment` in `api.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_api_ancestors -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Run full suite and static checks**

Run: `python -m unittest discover -s tests && ./check.sh`

- [ ] **Step 6: Commit**

```bash
git add md2conf/api.py tests/test_api_ancestors.py
git commit -m "feat(api): add get_ancestor_ids for v1 chain and v2 parent walk"
```

---

### Task 4: `page_exists` raises on an ambiguous match

**Behavior change** — ambiguity goes from `None` (→ create attempt) to an exception. Design §5.5.

**Files:** Modify `md2conf/api.py:1759`, `md2conf/api.py:1805`. Test: `tests/test_api_page_exists.py` (new).

**Interfaces:**
- Produces: `page_exists` raises `PageCollisionError` on >1 match; `None` for zero; the ID for exactly one.

> **Scoping reality:** on v1 the query is scoped by `self.site.space_key` — `_page_exists_v1` ignores the `space_id` argument entirely (`api.py:1734-1735`). On v2 the caller's `space_id` is used. Both are single-space scopes, so "more than one match" is genuinely anomalous in both; the tests below assert the scope is actually applied rather than assuming who supplies it.

- [ ] **Step 1: Write the failing test**

Create `tests/test_api_page_exists.py`:

```python
"""
Tests for page lookup ambiguity handling.

Copyright 2022-2025, Levente Hunyadi

:see: https://github.com/hunyadi/md2conf
"""

import unittest
from typing import Any
from unittest.mock import Mock

import requests

from md2conf.environment import PageCollisionError

from tests.utility import make_session


def _json_response(payload: dict[str, Any]) -> Mock:
    response = Mock(spec=requests.Response)
    response.status_code = 200
    response.text = ""
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def _v1_result(page_id: str, title: str) -> dict[str, Any]:
    return {"id": page_id, "title": title, "status": "current"}


class TestPageExistsAmbiguityDataCenter(unittest.TestCase):
    def test_single_match_returns_id(self) -> None:
        session = make_session("datacenter")
        transport: Mock = session.session
        transport.get.return_value = _json_response({"results": [_v1_result("300", "Guide")]})

        self.assertEqual(session.page_exists("Guide", space_key="TEST"), "300")

    def test_no_match_returns_none(self) -> None:
        session = make_session("datacenter")
        transport: Mock = session.session
        transport.get.return_value = _json_response({"results": []})

        self.assertIsNone(session.page_exists("Guide", space_key="TEST"))

    def test_multiple_matches_raise_naming_ids(self) -> None:
        session = make_session("datacenter")
        transport: Mock = session.session
        transport.get.return_value = _json_response({"results": [_v1_result("300", "Guide"), _v1_result("400", "Guide")]})

        with self.assertRaises(PageCollisionError) as context:
            session.page_exists("Guide", space_key="TEST")

        message = str(context.exception)
        self.assertIn("300", message)
        self.assertIn("400", message)

    def test_query_is_scoped_to_a_single_space(self) -> None:
        """Identical titles in different spaces are legitimate, so the query must carry a space filter."""

        session = make_session("datacenter")
        transport: Mock = session.session
        transport.get.return_value = _json_response({"results": [_v1_result("300", "Guide")]})

        session.page_exists("Guide", space_key="TEST")

        self.assertEqual(transport.get.call_args.kwargs["params"]["spaceKey"], "TEST")


if __name__ == "__main__":
    unittest.main()
```

`_page_exists_v1` calls `session.get(url, params=query, ...)` directly (`api.py:1746-1748`), so `call_args.kwargs["params"]` is correct **here** — unlike the `_get`-based calls in Task 2.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_api_page_exists -v`
Expected: FAIL on `test_multiple_matches_raise_naming_ids`.

- [ ] **Step 3: Implement for v1**

Replace the tail of `_page_exists_v1` (`api.py:1759-1763`):

```python
        if len(results) == 1:
            result = typing.cast(dict[str, JsonType], results[0])
            return str(result["id"])
        elif not results:
            return None
        else:
            matches = ", ".join(f"{typing.cast(dict[str, JsonType], item)['id']} (status: {typing.cast(dict[str, JsonType], item).get('status')})" for item in results)
            raise PageCollisionError(f"ambiguous page lookup: {len(results)} pages in space {space_key} match the title {title!r}: {matches}")
```

- [ ] **Step 4: Implement for v2**

Replace the tail of the v2 branch of `page_exists` (`api.py:1805-1808`):

```python
            if len(results) == 1:
                return results[0].id
            elif not results:
                return None
            else:
                matches = ", ".join(f"{item.id} (status: {item.status})" for item in results)
                raise PageCollisionError(f"ambiguous page lookup: {len(results)} pages in space {space_id} match the title {title!r}: {matches}")
```

Import `PageCollisionError` from `.environment` in `api.py`.

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m unittest tests.test_api_page_exists -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Add the Cloud mirror tests**

Append `TestPageExistsAmbiguityCloud` mirroring the four cases with `make_session("cloud")`.

The v2 branch deserializes results into `ConfluencePageProperties`, so each result payload must carry **every required field** or deserialization fails before the ambiguity check runs. Read the dataclass at `api.py:237-270` and build a complete payload — at minimum `id`, `status`, `title`, `spaceId`, `parentId`, `parentType`, `position`, `authorId`, `ownerId`, `lastOwnerId`, `createdAt`, `version`. Use `space-id` as the query-parameter key. Confirm PASS.

- [ ] **Step 7: Run full suite and static checks**

Run: `python -m unittest discover -s tests && ./check.sh`

- [ ] **Step 8: Commit**

```bash
git add md2conf/api.py tests/test_api_page_exists.py
git commit -m "fix(api): raise on ambiguous title match instead of falling through to create"
```

---

### Task 5: `AncestryResolver`

Additive. Design §5.2 (caching) and §4.

**Files:** Create `md2conf/ancestry.py`. Test: `tests/test_ancestry.py` (new).

**Interfaces:**
- Consumes: `ConfluenceSession.get_ancestor_ids` (Task 3)
- Produces: `AncestryResolver(api)` with `ancestors(page_id) -> list[str]`, `contains(root_id, page_id) -> bool`, `invalidate() -> None`

- [ ] **Step 1: Write the failing test**

Create `tests/test_ancestry.py`:

```python
"""
Tests for page-tree containment checks.

Copyright 2022-2025, Levente Hunyadi

:see: https://github.com/hunyadi/md2conf
"""

import unittest
from unittest.mock import Mock

from md2conf.ancestry import AncestryResolver
from md2conf.api import ConfluenceSession


def _resolver(chains: dict[str, list[str]]) -> "tuple[AncestryResolver, Mock]":
    api = Mock(spec=ConfluenceSession)
    api.get_ancestor_ids.side_effect = lambda page_id: chains[page_id]
    return AncestryResolver(api), api


class TestAncestryResolver(unittest.TestCase):
    def test_page_is_contained_in_itself(self) -> None:
        resolver, api = _resolver({"100": []})
        self.assertTrue(resolver.contains("100", "100"))
        api.get_ancestor_ids.assert_not_called()

    def test_descendant_is_contained(self) -> None:
        resolver, _ = _resolver({"300": ["100", "200"]})
        self.assertTrue(resolver.contains("100", "300"))
        self.assertTrue(resolver.contains("200", "300"))

    def test_unrelated_page_is_not_contained(self) -> None:
        resolver, _ = _resolver({"300": ["100", "200"]})
        self.assertFalse(resolver.contains("999", "300"))

    def test_chain_is_cached(self) -> None:
        resolver, api = _resolver({"300": ["100", "200"]})
        resolver.contains("100", "300")
        resolver.contains("200", "300")
        self.assertEqual(api.get_ancestor_ids.call_count, 1)

    def test_walk_populates_intermediate_chains(self) -> None:
        """A resolved chain also answers for each page along it, so siblings do not re-walk."""

        resolver, api = _resolver({"300": ["100", "200"]})
        resolver.ancestors("300")
        self.assertEqual(resolver.ancestors("200"), ["100"])
        self.assertEqual(resolver.ancestors("100"), [])
        self.assertEqual(api.get_ancestor_ids.call_count, 1)

    def test_invalidate_forces_refetch(self) -> None:
        resolver, api = _resolver({"300": ["100", "200"]})
        resolver.contains("100", "300")
        resolver.invalidate()
        resolver.contains("100", "300")
        self.assertEqual(api.get_ancestor_ids.call_count, 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_ancestry -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'md2conf.ancestry'`

- [ ] **Step 3: Implement**

Create `md2conf/ancestry.py`:

```python
"""
Containment checks over a Confluence page hierarchy.

Copyright 2022-2025, Levente Hunyadi

:see: https://github.com/hunyadi/md2conf
"""

import logging

from .api import ConfluenceSession

LOGGER = logging.getLogger(__name__)


class AncestryResolver:
    """
    Answers whether a Confluence page lies within a given page sub-tree.

    Ancestor chains are cached for the lifetime of this object. The cache is deliberately *not* held on
    `ConfluenceSession`, which outlives a single publish run; callers create one resolver per run and call
    `invalidate` whenever a page is moved.
    """

    api: ConfluenceSession

    def __init__(self, api: ConfluenceSession) -> None:
        self.api = api
        self._cache: dict[str, list[str]] = {}

    def ancestors(self, page_id: str) -> list[str]:
        """
        Returns the ancestors of a page, outermost first, excluding the page itself.
        """

        chain = self._cache.get(page_id)
        if chain is None:
            chain = self.api.get_ancestor_ids(page_id)
            self._cache[page_id] = chain

            # every prefix of the chain is the ancestry of the page that ends it, so siblings
            # elsewhere in the tree do not trigger a second walk over the same spine
            for index, ancestor_id in enumerate(chain):
                self._cache.setdefault(ancestor_id, chain[:index])

        return chain

    def contains(self, root_id: str, page_id: str) -> bool:
        """
        Whether the page is the given root, or a descendant of it.

        :param root_id: Page ID of the sub-tree root.
        :param page_id: Page ID to test.
        """

        if page_id == root_id:
            return True
        return root_id in self.ancestors(page_id)

    def invalidate(self) -> None:
        """
        Discards all cached chains. Call after any operation that re-parents a page.
        """

        self._cache.clear()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_ancestry -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Run full suite and static checks**

Run: `python -m unittest discover -s tests && ./check.sh`

- [ ] **Step 6: Commit**

```bash
git add md2conf/ancestry.py tests/test_ancestry.py
git commit -m "feat: add AncestryResolver for page sub-tree containment checks"
```

---

### Task 6: Reject duplicate local page IDs

**Behavior change** — previously two documents sharing an ID published in sequence, the second silently overwriting the first. Design §5.4, §7. Purely local, so it covers `--local` too.

**Files:** Modify `md2conf/processor.py:130-136`. Test: `tests/test_processor.py` (extend).

**Interfaces:**
- Produces: `Processor._assert_unique_page_ids(root: DocumentNode) -> None`, called first in `_process_items`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_processor.py` (match the file's existing import style):

```python
class TestDuplicatePageIds(unittest.TestCase):
    @staticmethod
    def _node(path: str, page_id: "Optional[str]") -> "DocumentNode":
        from pathlib import Path

        from md2conf.processor import DocumentNode

        return DocumentNode(
            absolute_path=Path(path),
            page_id=page_id,
            space_key=None,
            title=None,
            synchronized=True,
            users=set(),
        )

    def test_duplicate_page_ids_are_rejected(self) -> None:
        from md2conf.environment import PageCollisionError
        from md2conf.processor import Processor

        root = self._node("/docs/index.md", "100")
        root.add_child(self._node("/docs/a.md", "200"))
        root.add_child(self._node("/docs/b.md", "200"))

        with self.assertRaises(PageCollisionError) as context:
            Processor._assert_unique_page_ids(root)

        message = str(context.exception)
        self.assertIn("200", message)
        self.assertIn("a.md", message)
        self.assertIn("b.md", message)

    def test_distinct_page_ids_are_accepted(self) -> None:
        from md2conf.processor import Processor

        root = self._node("/docs/index.md", "100")
        root.add_child(self._node("/docs/a.md", "200"))

        Processor._assert_unique_page_ids(root)  # must not raise

    def test_documents_without_ids_are_ignored(self) -> None:
        from md2conf.processor import Processor

        root = self._node("/docs/index.md", None)
        root.add_child(self._node("/docs/a.md", None))
        root.add_child(self._node("/docs/b.md", None))

        Processor._assert_unique_page_ids(root)  # must not raise
```

Add `from typing import Optional` and import `DocumentNode` at module scope if the file's style prefers it.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_processor.TestDuplicatePageIds -v`
Expected: FAIL — `AttributeError: type object 'Processor' has no attribute '_assert_unique_page_ids'`

- [ ] **Step 3: Implement**

Add to `Processor` in `md2conf/processor.py`; import `PageCollisionError` from `.environment`:

```python
    @staticmethod
    def _assert_unique_page_ids(root: DocumentNode) -> None:
        """
        Verifies that no two documents claim the same Confluence page.

        Two documents mapping to a single page would publish in sequence, the second silently overwriting
        the first. There is no correct way to proceed, so this fails rather than choosing a silent loser.
        """

        seen: dict[str, Path] = {}
        for node in root.all():
            if node.page_id is None:
                continue
            previous = seen.get(node.page_id)
            if previous is not None:
                raise PageCollisionError(
                    f"duplicate Confluence page ID {node.page_id} declared in both {previous} and {node.absolute_path}; "
                    f"remove the 'confluence-page-id' comment from one of them"
                )
            seen[node.page_id] = node.absolute_path
```

Call it first in `_process_items` (`processor.py:130`):

```python
    def _process_items(self, root: DocumentNode) -> None:
        """
        Processes a sub-tree rooted at an ancestor node.
        """

        self._assert_unique_page_ids(root)

        # synchronize directory tree structure with page hierarchy in space (find matching pages in Confluence)
        parent_to_children = self._synchronize_structure(root)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_processor -v`
Expected: PASS.

- [ ] **Step 5: Run full suite and static checks**

Run: `python -m unittest discover -s tests && ./check.sh`

- [ ] **Step 6: Commit**

```bash
git add md2conf/processor.py tests/test_processor.py
git commit -m "fix: reject two documents declaring the same Confluence page ID"
```

---

### Task 7: Seam split and two-stage containment guard

**The core behavior change.** Design §4, §4.1, §5.3.

**Files:** Modify `md2conf/publisher.py:49-146`. Test: `tests/test_collision_guard.py` (new).

**Interfaces:**
- Consumes: `AncestryResolver` (5), `PageCollisionError` + `options.allow_adopt` (1), `page_exists` (4)
- Produces: `SynchronizingProcessor._assert_owned(page_id: str, page_title: str, managed_root_id: str, source_path: Path) -> None`; `_synchronize_subtree(node, parent_id, managed_root_id, parent_to_children, *, is_root=False)`

> **These methods go on `SynchronizingProcessor` (`publisher.py:28`), not `Publisher` (`publisher.py:308`).** `Publisher` is a `Converter` subclass that owns a factory; it has no `_synchronize_subtree`. Tests construct `SynchronizingProcessor(api, options, root_dir)` through its real `__init__`, which reads `api.site` — so the mock must provide it.

- [ ] **Step 1: Write the failing test**

Create `tests/test_collision_guard.py`:

```python
"""
Tests for the cross-effort page collision guard.

Copyright 2022-2025, Levente Hunyadi

:see: https://github.com/hunyadi/md2conf
"""

import unittest
from pathlib import Path
from typing import Optional
from unittest.mock import Mock

from md2conf.api import ConfluenceSession
from md2conf.domain import ConfluenceDocumentOptions
from md2conf.environment import PageCollisionError
from md2conf.metadata import ConfluenceSiteMetadata
from md2conf.publisher import SynchronizingProcessor


def _properties(page_id: str, title: str, parent_id: Optional[str]) -> Mock:
    properties = Mock()
    properties.id = page_id
    properties.title = title
    properties.parentId = parent_id
    properties.status = "current"
    return properties


def _processor(chains: dict[str, list[str]], *, allow_adopt: "frozenset[str]" = frozenset()) -> "tuple[SynchronizingProcessor, Mock]":
    """Builds a real SynchronizingProcessor over a mocked ConfluenceSession."""

    api = Mock(spec=ConfluenceSession)
    api.site = ConfluenceSiteMetadata(domain="example.com", base_path="/wiki/", space_key="TEST")
    api.get_ancestor_ids.side_effect = lambda page_id: chains[page_id]

    processor = SynchronizingProcessor(api, ConfluenceDocumentOptions(allow_adopt=allow_adopt), Path("/docs"))
    return processor, api


class TestContainmentGuard(unittest.TestCase):
    """
        100 (anchor / -r)
         └── 200 (managed root: the root document's page)
              └── 300 (a child document's page)

        800 (unrelated tree)
         └── 900 (a foreign effort's page)
    """

    CHAINS = {"100": [], "200": ["100"], "300": ["100", "200"], "800": [], "900": ["800"], "901": ["800"]}

    def test_adopting_a_page_outside_the_managed_root_raises(self) -> None:
        processor, _ = _processor(self.CHAINS)
        processor.ancestry = __import__("md2conf.ancestry", fromlist=["AncestryResolver"]).AncestryResolver(processor.api)

        with self.assertRaises(PageCollisionError) as context:
            processor._assert_owned("900", "Foreign Page", "200", Path("/docs/source-inventory.md"))

        message = str(context.exception)
        self.assertIn("900", message)
        self.assertIn("Foreign Page", message)
        self.assertIn("--allow-adopt 900", message)

    def test_adopting_a_page_inside_the_managed_root_is_allowed(self) -> None:
        processor, _ = _processor(self.CHAINS)
        processor.ancestry = __import__("md2conf.ancestry", fromlist=["AncestryResolver"]).AncestryResolver(processor.api)

        processor._assert_owned("300", "Child", "200", Path("/docs/a.md"))  # must not raise

    def test_managed_root_itself_is_adoptable(self) -> None:
        processor, _ = _processor(self.CHAINS)
        processor.ancestry = __import__("md2conf.ancestry", fromlist=["AncestryResolver"]).AncestryResolver(processor.api)

        processor._assert_owned("200", "Root", "200", Path("/docs/index.md"))  # must not raise

    def test_allow_adopt_authorizes_exactly_one_page(self) -> None:
        processor, _ = _processor(self.CHAINS, allow_adopt=frozenset({"900"}))
        processor.ancestry = __import__("md2conf.ancestry", fromlist=["AncestryResolver"]).AncestryResolver(processor.api)

        processor._assert_owned("900", "Foreign Page", "200", Path("/docs/a.md"))  # authorized

        with self.assertRaises(PageCollisionError):
            processor._assert_owned("901", "Another Foreign Page", "200", Path("/docs/b.md"))


if __name__ == "__main__":
    unittest.main()
```

> Replace the `__import__(...)` idiom with a plain `from md2conf.ancestry import AncestryResolver` at module top and `processor.ancestry = AncestryResolver(processor.api)` — it is written inline here only to keep each test self-contained. Also confirm `ConfluenceSiteMetadata`'s real constructor signature in `md2conf/metadata.py` and adjust the `api.site` line to match.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_collision_guard -v`
Expected: FAIL — `AttributeError: 'SynchronizingProcessor' object has no attribute '_assert_owned'`

- [ ] **Step 3: Implement the guard**

Add to `SynchronizingProcessor` in `md2conf/publisher.py`; import `AncestryResolver` from `.ancestry` and `PageCollisionError` from `.environment`; declare `ancestry: AncestryResolver` in the class attribute block beside `api: ConfluenceSession`:

```python
    def _assert_owned(self, page_id: str, page_title: str, managed_root_id: str, source_path: Path) -> None:
        """
        Verifies that a page found by lookup belongs to the tree being published.

        :param page_id: Confluence page ID the lookup resolved to.
        :param page_title: Title of that page, for diagnostics.
        :param managed_root_id: Confluence page ID bounding the tree being published.
        :param source_path: Markdown document whose publication triggered the lookup.
        """

        if page_id in self.options.allow_adopt:
            LOGGER.warning(
                "Adopting page %s ('%s') outside the tree rooted at %s, authorized by --allow-adopt",
                page_id,
                page_title,
                managed_root_id,
            )
            return

        if self.ancestry.contains(managed_root_id, page_id):
            return

        ancestors = self.ancestry.ancestors(page_id) or ["<none>"]
        raise PageCollisionError(
            f"refusing to publish {source_path} to Confluence page {page_id} ('{page_title}'): "
            f"the page is not the root of the tree being published ({managed_root_id}) nor a descendant of it; "
            f"its ancestors are {' > '.join(ancestors)}. "
            f"This usually means another effort owns the page. "
            f"If adopting it is intended, re-run with --allow-adopt {page_id}"
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_collision_guard -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit the guard**

```bash
git add md2conf/publisher.py tests/test_collision_guard.py
git commit -m "feat: add containment guard refusing pages outside the published tree"
```

- [ ] **Step 6: Split the seam and thread the boundary**

In `md2conf/publisher.py`, the root-ID resolution at :60-73 is unchanged. Replace the tail of `_synchronize_structure` and all of `_synchronize_subtree`:

```python
        parent_to_children: dict[str, list[str]] = {}
        self.ancestry = AncestryResolver(self.api)
        self._synchronize_subtree(root, real_id, real_id.page_id, parent_to_children, is_root=True)
        return parent_to_children

    def _synchronize_subtree(
        self,
        node: DocumentNode,
        parent_id: ConfluencePageID,
        managed_root_id: str,
        parent_to_children: dict[str, list[str]],
        *,
        is_root: bool = False,
    ) -> None:
        page: ConfluencePageProperties

        if node.page_id is not None:
            # verify the page exists, and that it belongs to the tree being published
            page = self.api.get_page_properties(node.page_id)
            self._assert_owned(page.id, page.title, managed_root_id, node.absolute_path)
            self._reparent_if_needed(node, page, parent_id, is_root=is_root)
            update = False
        else:
            if node.title is not None:
                # use title extracted from source metadata
                title = node.title
            else:
                # assign an auto-generated title
                digest = self._generate_hash(node.absolute_path)
                title = f"{node.absolute_path.stem} [{digest}]"

            # on v2 the space is derived from the parent; on v1 page_exists uses the session space key
            parent_page = self.api.get_page_properties(parent_id.page_id)
            found_id = self.api.page_exists(title, space_id=parent_page.spaceId)

            if found_id is not None:
                properties = self.api.get_page_properties(found_id)
                self._assert_owned(found_id, properties.title, managed_root_id, node.absolute_path)

                found_page = self.api.get_page(found_id)
                if found_page.status is ConfluenceStatus.ARCHIVED:
                    # user has archived a page with this (auto-generated) title
                    raise PageError(f"unable to update archived page with ID {found_page.id}")

                self._reparent_if_needed(node, properties, parent_id, is_root=is_root)
                page = found_page
            else:
                LOGGER.debug("Creating new page with title: %s", title)
                page = self.api.create_page(parent_id.page_id, title, "")

            update = True

        # For v1 API, use space key from session properties (reverse lookup not supported)
        space_key = self.api.site.space_key
        if update:
            self._update_markdown(
                node.absolute_path,
                page_id=page.id,
                space_key=space_key,
            )

        data = ConfluencePageMetadata(
            page_id=page.id,
            space_key=space_key,
            title=page.title,
            synchronized=node.synchronized,
        )
        self.page_metadata.add(node.absolute_path, data)

        # Record the current Confluence child order for this page
        child_ids = self.api.get_child_page_ids(page.id)
        parent_to_children[page.id] = child_ids

        # descendants are bounded by the root document's resolved page, not by the -r anchor
        child_root_id = page.id if is_root else managed_root_id
        for child_node in node.children():
            self._synchronize_subtree(child_node, ConfluencePageID(page.id), child_root_id, parent_to_children)
```

Add a stub `_reparent_if_needed` so this task's tests run; Task 8 replaces it:

```python
    def _reparent_if_needed(
        self,
        node: DocumentNode,
        page: ConfluencePageProperties,
        parent_id: ConfluencePageID,
        *,
        is_root: bool,
    ) -> None:
        if page.parentId is not None and page.parentId != parent_id.page_id:
            LOGGER.info("Moving page %s from parent %s to %s", page.id, page.parentId, parent_id.page_id)
            self.api.move_page(page.id, parent_id.page_id)
            self.ancestry.invalidate()
```

Import `ConfluencePageProperties` and `ConfluenceStatus` from `.api` if not already imported.

> **Behavior preserved deliberately:** the archived check, `_update_markdown`, `page_metadata.add`, `parent_to_children`, and child recursion are all unchanged in effect. The `get_page_properties(parent_id.page_id)` call is retained because the v2 lookup needs the parent's `spaceId` (`api.py:1818-1819`); dropping it would let the lookup match a same-titled page in another space.

- [ ] **Step 7: Add an end-to-end test through the real sync path**

The `_assert_owned` tests above prove the predicate, not the wiring — the guard function never writes, so "no write" is trivially true there. Add a test that drives `_synchronize_subtree` and asserts no mutation occurred:

```python
class TestGuardStopsWritesEndToEnd(unittest.TestCase):
    CHAINS = {"100": [], "200": ["100"], "800": [], "900": ["800"]}

    def test_explicit_foreign_id_writes_nothing(self) -> None:
        from md2conf.ancestry import AncestryResolver
        from md2conf.domain import ConfluencePageID
        from md2conf.processor import DocumentNode

        processor, api = _processor(self.CHAINS)
        processor.ancestry = AncestryResolver(api)
        api.get_page_properties.side_effect = lambda page_id: _properties(page_id, "Foreign Page", "800")

        node = DocumentNode(
            absolute_path=Path("/docs/source-inventory.md"),
            page_id="900",
            space_key=None,
            title=None,
            synchronized=True,
            users=set(),
        )

        with self.assertRaises(PageCollisionError):
            processor._synchronize_subtree(node, ConfluencePageID("200"), "200", {}, is_root=False)

        api.move_page.assert_not_called()
        api.create_page.assert_not_called()
        api.update_page.assert_not_called()
```

Confirm the mutating method names against `ConfluenceSession` and assert on all of them. Run and confirm PASS.

- [ ] **Step 8: Run the full suite and static checks**

Run: `python -m unittest discover -s tests && ./check.sh`

> Existing publisher tests that assumed space-wide adoption may now fail. Each such failure is the guard working. Fix the *test* to publish inside a managed tree; do not weaken the guard.

- [ ] **Step 9: Commit**

```bash
git add md2conf/publisher.py tests/test_collision_guard.py
git commit -m "fix: validate page ownership before adopting, and bound descendants by the resolved root"
```

---

### Task 8: Self-parent, non-root equality, and cycle guards

Design §5.4. **Must land with Tasks 2 and 7.**

**Files:** Modify `md2conf/publisher.py` (`_reparent_if_needed`). Test: `tests/test_collision_guard.py` (extend).

**Interfaces:**
- Consumes: `AncestryResolver.contains` (5)
- Produces: final `_reparent_if_needed`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_collision_guard.py`:

```python
class TestReparentGuards(unittest.TestCase):
    CHAINS = {"100": [], "200": ["100"], "300": ["100", "200"]}

    def _node(self, path: str) -> Mock:
        node = Mock()
        node.absolute_path = Path(path)
        return node

    def test_root_node_equal_to_its_parent_is_not_moved(self) -> None:
        from md2conf.ancestry import AncestryResolver
        from md2conf.domain import ConfluencePageID

        processor, api = _processor(self.CHAINS)
        processor.ancestry = AncestryResolver(api)

        processor._reparent_if_needed(self._node("/docs/index.md"), _properties("200", "Root", "100"), ConfluencePageID("200"), is_root=True)

        api.move_page.assert_not_called()

    def test_non_root_node_equal_to_its_parent_raises(self) -> None:
        from md2conf.ancestry import AncestryResolver
        from md2conf.domain import ConfluencePageID

        processor, api = _processor(self.CHAINS)
        processor.ancestry = AncestryResolver(api)

        with self.assertRaises(PageCollisionError):
            processor._reparent_if_needed(self._node("/docs/a.md"), _properties("200", "Child", "100"), ConfluencePageID("200"), is_root=False)

        api.move_page.assert_not_called()

    def test_moving_a_page_under_its_own_descendant_raises(self) -> None:
        from md2conf.ancestry import AncestryResolver
        from md2conf.domain import ConfluencePageID

        processor, api = _processor(self.CHAINS)
        processor.ancestry = AncestryResolver(api)

        with self.assertRaises(PageCollisionError):
            processor._reparent_if_needed(self._node("/docs/a.md"), _properties("200", "Parent", "100"), ConfluencePageID("300"), is_root=False)

        api.move_page.assert_not_called()

    def test_legitimate_move_invalidates_the_ancestor_cache(self) -> None:
        from md2conf.ancestry import AncestryResolver
        from md2conf.domain import ConfluencePageID

        processor, api = _processor(self.CHAINS)
        processor.ancestry = AncestryResolver(api)
        processor.ancestry.contains("100", "300")
        calls_before = api.get_ancestor_ids.call_count

        processor._reparent_if_needed(self._node("/docs/a.md"), _properties("300", "Child", "200"), ConfluencePageID("100"), is_root=False)

        api.move_page.assert_called_once_with("300", "100")
        processor.ancestry.contains("100", "300")
        self.assertGreater(api.get_ancestor_ids.call_count, calls_before)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_collision_guard.TestReparentGuards -v`
Expected: FAIL — the stub neither raises on non-root equality nor detects cycles.

- [ ] **Step 3: Implement**

Replace the stub in `md2conf/publisher.py`:

```python
    def _reparent_if_needed(
        self,
        node: DocumentNode,
        page: ConfluencePageProperties,
        parent_id: ConfluencePageID,
        *,
        is_root: bool,
    ) -> None:
        """
        Moves a page under its intended parent, if it is not already there.

        :param node: Document being published.
        :param page: Properties of the Confluence page the document maps to.
        :param parent_id: Confluence page ID the document's parent maps to.
        :param is_root: Whether this is the root document, which is compared against itself.
        """

        if page.id == parent_id.page_id:
            if is_root:
                # the root document is its own parent by construction; nothing to move
                return
            raise PageCollisionError(
                f"document {node.absolute_path} maps to Confluence page {page.id}, which is also the page of its parent document; "
                f"two documents cannot map to the same Confluence page"
            )

        if page.parentId == parent_id.page_id:
            return

        if self.ancestry.contains(page.id, parent_id.page_id):
            raise PageCollisionError(
                f"refusing to move Confluence page {page.id} under {parent_id.page_id} for document {node.absolute_path}: "
                f"the intended parent is a descendant of the page, so the move would create a cycle"
            )

        LOGGER.info("Moving page %s from parent %s to %s", page.id, page.parentId, parent_id.page_id)
        self.api.move_page(page.id, parent_id.page_id)
        self.ancestry.invalidate()
```

> Note the `page.parentId is None` early-return from the stub is deliberately **dropped**. A page with an unknown parent that was adopted via `--allow-adopt` must still be moved into the tree, which the design promises; leaving it unmoved would strand it outside.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_collision_guard -v`
Expected: PASS.

- [ ] **Step 5: Run full suite and static checks**

Run: `python -m unittest discover -s tests && ./check.sh`

- [ ] **Step 6: Commit**

```bash
git add md2conf/publisher.py tests/test_collision_guard.py
git commit -m "fix: guard self-parenting, duplicate parent mapping, and move cycles"
```

---

### Task 9: Remove `get_or_create_page` and document the breaks

Design §5.3, §7.

**Files:** Modify `md2conf/api.py:1810-1826` (delete), `CHANGELOG.md`. Test: `tests/test_collision_guard.py` (extend).

- [ ] **Step 1: Confirm there are no remaining callers**

Run: `rg -n "get_or_create_page" --type py`
Expected: only the definition in `md2conf/api.py`. Anything else must be migrated to the split form from Task 7 first.

- [ ] **Step 2: Write the failing test**

```python
class TestUnsafePrimitiveRemoved(unittest.TestCase):
    def test_get_or_create_page_is_gone(self) -> None:
        self.assertFalse(hasattr(ConfluenceSession, "get_or_create_page"))
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m unittest tests.test_collision_guard.TestUnsafePrimitiveRemoved -v`
Expected: FAIL — the attribute still exists.

- [ ] **Step 4: Delete the method**

Remove `get_or_create_page` entirely from `md2conf/api.py:1810-1826`.

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m unittest tests.test_collision_guard -v`

- [ ] **Step 6: Record the breaking changes**

Add to `CHANGELOG.md` under a new unreleased entry (match existing heading style):

```markdown
### Fixed

- Publishing no longer adopts and overwrites a Confluence page that lies outside the tree being published.
  Previously the lookup for a page title searched the whole space, so two projects publishing similarly-named
  files to one space could silently overwrite each other's pages.
- `parentId` is now populated on Confluence Server/Data Center, so pages are re-parented when a document moves
  between directories. This previously failed silently.
- Publishing no longer attempts to make the root page its own parent.
- An ambiguous page-title lookup is now reported instead of falling through to a page creation.

### Changed — breaking

- `ConfluenceSession.get_or_create_page` has been removed. It adopted pages space-wide with no ownership check.
  Look the page up with `page_exists`, validate the result, then call `create_page` if absent.
- `ConfluenceSession.page_exists` now raises `PageCollisionError` when more than one page matches, instead of
  returning `None`.
- Two Markdown documents declaring the same `confluence-page-id` is now an error. Previously the second silently
  overwrote the first. Remove the duplicated comment from one of the documents.
- Adopting a page outside the tree being published now fails. Use `--allow-adopt <page-id>` to authorize a
  specific page.
```

- [ ] **Step 7: Run the full suite and static checks**

Run: `python -m unittest discover -s tests && ./check.sh`

- [ ] **Step 8: Commit**

```bash
git add md2conf/api.py CHANGELOG.md tests/test_collision_guard.py
git commit -m "refactor!: remove unsafe get_or_create_page primitive"
```

---

## Verification

Append to `tests/test_collision_guard.py`:

```python
class TestIncidentScenario(unittest.TestCase):
    """
    The GSSPACE incident topology.

        100  Effort A anchor (-r)
         └── 200  Effort A root document
        800  unrelated tree
         └── 900  Effort B's 'source-inventory' page
    """

    CHAINS = {"100": [], "200": ["100"], "800": [], "900": ["800"]}

    def test_poisoned_page_id_is_refused(self) -> None:
        from md2conf.ancestry import AncestryResolver

        processor, api = _processor(self.CHAINS)
        processor.ancestry = AncestryResolver(api)

        with self.assertRaises(PageCollisionError):
            processor._assert_owned("900", "source-inventory", "200", Path("/effort-a/00-inception/source-inventory.md"))

        api.move_page.assert_not_called()


class TestSharedAnchorTopologies(unittest.TestCase):
    """
    Design cases 11 and 11b — the two topologies where a naive boundary fails open.

        100  shared -r container
         ├── 200  Effort A root document
         │    └── 300  Effort A child
         └── 500  Effort B root document
              └── 600  Effort B child
    """

    CHAINS = {"100": [], "200": ["100"], "300": ["100", "200"], "500": ["100"], "600": ["100", "500"]}

    def test_11_shared_anchor_poisoned_id_into_sibling_effort_is_refused(self) -> None:
        """
        Both efforts publish under the same -r (100). Effort A's managed root is its own resolved root
        document (200), NOT the anchor. A poisoned ID pointing at Effort B's child (600) must be refused
        even though 600 IS a descendant of the shared anchor.
        """

        from md2conf.ancestry import AncestryResolver

        processor, api = _processor(self.CHAINS)
        processor.ancestry = AncestryResolver(api)

        with self.assertRaises(PageCollisionError):
            processor._assert_owned("600", "Effort B Child", "200", Path("/effort-a/a.md"))

        # the same page IS contained by the anchor -- proving the boundary is not the anchor
        self.assertTrue(processor.ancestry.contains("100", "600"))

    def test_11b_root_node_resolving_to_a_foreign_root_is_refused(self) -> None:
        """
        The collapse case. Both efforts publish 00-inception/, so both root documents synthesize the SAME
        title and Effort A's root node can title-resolve to Effort B's root page (500).

        Stage 1 must check the root node against its own anchor. Without it, Effort A's managed root becomes
        500, every later descendant check passes, and Effort A publishes its whole tree inside Effort B.
        """

        from md2conf.ancestry import AncestryResolver

        chains = dict(self.CHAINS)
        chains["700"] = []
        chains["500"] = ["700"]

        processor, api = _processor(chains)
        processor.ancestry = AncestryResolver(api)

        with self.assertRaises(PageCollisionError):
            processor._assert_owned("500", "index", "100", Path("/effort-a/00-inception/index.md"))
```

Run: `python -m unittest discover -s tests && ./check.sh`

---

## Known Gaps

Stated so they are not mistaken for oversights.

- **Not atomic.** Structure sync is depth-first, so nodes earlier in traversal are created, moved, and have IDs written to disk before a later node's violation is found. The guarantee is "no write to the offending page", not "no writes at all".
- **A poisoned root ID with no `-r` is trusted.** When `-r` is absent, `real_id` comes from the root document itself (`publisher.py:70-71`), so stage 1 validates that page against itself and always passes. There is no independent boundary to check it against. **`-r` is therefore the security boundary**; document this in the README as the recommended invocation for shared spaces. Out of scope here — closing it requires a trusted external anchor.
- **The archived check is already broken on Data Center.** v1 mappers set `status` to a plain string (`api_mappers.py:51, 127`), so `page.status is ConfluenceStatus.ARCHIVED` never matches on v1. Task 7 preserves the existing line verbatim rather than silently changing behavior. This is a **separate pre-existing defect** and should be filed as its own issue.
- **v2 ancestor cost.** Each uncached walk is one `GET` per level. `AncestryResolver` caches every page along a resolved chain (Task 5), so a spine is walked once per run rather than once per sibling — but a wide, deep tree on Cloud still adds calls. v1 pays nothing extra.
- **TOCTOU** (design §8). A page validated during structure sync can be moved by another user before content sync writes it.
- **Deferred** (design §2): salted digest, `--strict-create`, `--local` dry-run warning, digest padding `{c:x}` → `{c:02x}`.
- **Live verification outstanding.** No Confluence Cloud instance is available here, so self-parenting server behavior remains unverified. Task 8 prevents the call rather than relying on how the server answers it.

## Rejected Findings

From the Codex stress-test, considered and **not** adopted:

- **"Fix the v1 `status` string/enum mismatch as part of this work."** It is a real defect, but unrelated to collisions and it changes archived-page handling on every DC publish. Widening scope here would mix an independent behavior change into a safety fix. Recorded in Known Gaps for separate filing instead.
- **"Task 4's ambiguity change is unsafe because v1 ignores `space_id`."** The premise is right, the conclusion is not: v1 scopes by `self.site.space_key`, which is still a single space. Ambiguity within one space remains anomalous, so raising is correct on both versions. The plan's *justification* was wrong and has been corrected; the change stands.
