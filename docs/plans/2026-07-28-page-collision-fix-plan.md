# Cross-Effort Page Collision Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop md2conf from adopting and overwriting Confluence pages outside the tree it is publishing, and fix the latent defects that mask or enable that.

**Architecture:** One containment rule applied to both branches that can reach a page — the page must be the managed root or a descendant of it, otherwise `PageCollisionError`. Pages inside the tree but under the wrong parent are re-parented rather than rejected. The boundary is two-stage: the root node is checked against the `-r` anchor, and descendants against the root node's *resolved* page. A new `AncestryResolver` owns ancestor lookups and their cache; `ConfluenceSession` gains `get_ancestor_ids`; the unsafe `get_or_create_page` primitive is split at its single call site and removed.

**Tech Stack:** Python 3.9+, `unittest` (not pytest), `unittest.mock`, mypy strict, ruff.

**Design:** [2026-07-27-page-collision-fix-design.md](2026-07-27-page-collision-fix-design.md)
**Analysis:** [2026-07-27-page-collision-analysis.md](2026-07-27-page-collision-analysis.md)

## Global Constraints

- **Minimum Python: 3.9.** PEP 585 builtin generics (`list[str]`, `dict[str, str]`) are fine; `X | Y` unions are **not** — use `Optional[X]`.
- **Tests use `unittest`**, never pytest. Run a single test with `python -m unittest tests.test_module.TestClass.test_name -v`.
- **Full unit suite:** `python -m unittest discover -s tests` — must be green before any commit.
- **Static checks:** `./check.sh` runs ruff + mypy strict over `md2conf`, `tests`, `integration_tests`. Must pass before any commit.
- **Line length 160** (ruff config).
- Use `LOGGER = logging.getLogger(__name__)` in each module.
- Use `@override` from `md2conf/extra.py` on overridden methods.
- Custom exceptions live in `md2conf/environment.py`.
- Type hints required on all public functions and methods (mypy strict).
- **Both deployment types.** Any behavior touching the API is tested for `datacenter` (v1) and `cloud` (v2), per CLAUDE.md.

---

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `tests/utility.py` | Shared test helpers — gains `make_session()` | 1 |
| `md2conf/environment.py` | Gains `PageCollisionError` | 1 |
| `md2conf/domain.py` | `ConfluenceDocumentOptions` gains `allow_adopt` | 1 |
| `md2conf/__main__.py` | Repeatable `--allow-adopt` CLI flag | 1 |
| `md2conf/api.py` | v1 `expand` fix; `get_ancestor_ids`; `page_exists` ambiguity; `get_or_create_page` removal | 2, 3, 4, 9 |
| `md2conf/ancestry.py` | **New.** `AncestryResolver` — ancestor lookup, caching, containment predicate | 5 |
| `md2conf/processor.py` | Duplicate local page-id detection | 6 |
| `md2conf/publisher.py` | Seam split, two-stage containment, re-parent, self/cycle guards | 7, 8 |

`ancestry.py` is a new module rather than more methods on `Publisher`: containment is a self-contained question with one dependency (`get_ancestor_ids`), it needs its own cache lifetime, and isolating it makes tasks 5, 7 and 8 independently testable.

---

## Task Order and Rationale

Tasks 1-6 are additive and ship no behavior change. **Task 7 is where behavior changes**, and it depends on 1-5. Task 8 must land with 7 (design §3: expanding `ancestors` unmasks the self-parent bug). Task 9 is cleanup.

---

### Task 1: Error type, option plumbing, and shared test helper

No behavior change. Establishes what later tasks reference.

**Files:**
- Modify: `md2conf/environment.py:17-19`
- Modify: `md2conf/domain.py:49-68`
- Modify: `md2conf/__main__.py` (arg definition; options construction at :433-453)
- Modify: `tests/utility.py`
- Modify: `tests/test_api_move.py:19-37`
- Test: `tests/test_collision_options.py` (new)

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
        options = ConfluenceDocumentOptions()
        self.assertEqual(options.allow_adopt, frozenset())

    def test_allow_adopt_accepts_page_ids(self) -> None:
        options = ConfluenceDocumentOptions(allow_adopt=frozenset({"123", "456"}))
        self.assertIn("123", options.allow_adopt)
        self.assertNotIn("789", options.allow_adopt)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_collision_options -v`
Expected: FAIL with `ImportError: cannot import name 'PageCollisionError'`

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

and add the field at the end of the field list (after `user_mentions: bool = True`):

```python
    allow_adopt: frozenset[str] = frozenset()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m unittest tests.test_collision_options -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Wire the CLI flag**

In `md2conf/__main__.py`, add alongside the other `parser.add_argument` calls:

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

Move the helper out of `tests/test_api_move.py` so later tasks can reuse it. Append to `tests/utility.py`:

```python
import requests

from md2conf.api import ConfluenceSession
from md2conf.environment import ConfluenceConnectionProperties


def make_session(deployment_type: str) -> ConfluenceSession:
    """
    Builds a ConfluenceSession backed by a mocked transport, performing no network calls.

    :param deployment_type: One of `cloud`, `datacenter` or `server`.
    """

    from unittest.mock import Mock

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

In `tests/test_api_move.py`, delete the local `_make_session` definition (lines 19-37) and replace its uses by importing the shared one:

```python
from .utility import make_session as _make_session
```

- [ ] **Step 8: Run the full suite and static checks**

Run: `python -m unittest discover -s tests`
Expected: OK — same test count as before plus 3.

Run: `./check.sh`
Expected: no ruff or mypy errors.

- [ ] **Step 9: Commit**

```bash
git add md2conf/environment.py md2conf/domain.py md2conf/__main__.py tests/utility.py tests/test_api_move.py tests/test_collision_options.py
git commit -m "feat: add PageCollisionError and --allow-adopt option plumbing"
```

---

### Task 2: Expand `ancestors` on the v1 fetches

Populates `parentId` on Data Center, which every later guard reads. See design §5.1.

**Files:**
- Modify: `md2conf/api.py:1141` (`_get_page_v1`), `md2conf/api.py:1170` (`_get_page_properties_v1`)
- Test: `tests/test_api_ancestors.py` (new)

**Interfaces:**
- Consumes: `tests.utility.make_session` (Task 1)
- Produces: v1 responses carry `ancestors`, so `ConfluencePageProperties.parentId` is populated on v1.

- [ ] **Step 1: Write the failing test**

Create `tests/test_api_ancestors.py`:

```python
"""
Tests for ancestor retrieval and v1 ancestor expansion.

Copyright 2022-2025, Levente Hunyadi

:see: https://github.com/hunyadi/md2conf
"""

import unittest
from typing import Any
from unittest.mock import Mock

import requests

from .utility import make_session


def _json_response(payload: dict[str, Any]) -> Mock:
    response = Mock(spec=requests.Response)
    response.status_code = 200
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


class TestV1AncestorExpansion(unittest.TestCase):
    def test_get_page_properties_v1_requests_ancestors(self) -> None:
        session = make_session("datacenter")
        transport: Mock = session.session  # type: ignore[assignment]
        transport.get.return_value = _json_response(_v1_page("300", "Child", ["100", "200"]))

        properties = session.get_page_properties("300")

        expand = transport.get.call_args.kwargs["params"]["expand"]
        self.assertIn("ancestors", expand)
        self.assertEqual(properties.parentId, "200")

    def test_get_page_v1_requests_ancestors(self) -> None:
        session = make_session("datacenter")
        transport: Mock = session.session  # type: ignore[assignment]
        transport.get.return_value = _json_response(_v1_page("300", "Child", ["100", "200"]))

        page = session.get_page("300")

        expand = transport.get.call_args.kwargs["params"]["expand"]
        self.assertIn("ancestors", expand)
        self.assertEqual(page.parentId, "200")


if __name__ == "__main__":
    unittest.main()
```

> If `ConfluenceSession` stores its transport under a different attribute name than `session`, adjust the two `transport` lines to match; read `md2conf/api.py` around the `ConfluenceSession.__init__` to confirm. Likewise, if `_get` passes the query as a positional `params=` versus inline in the URL, read `_build_url` and `_get` and assert against whichever the code actually does — the assertion must observe the real request.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_api_ancestors -v`
Expected: FAIL — `ancestors` not in the expand string, and `parentId` is `None`.

- [ ] **Step 3: Add `ancestors` to both expand strings**

In `md2conf/api.py:1141` (`_get_page_v1`):

```python
        query = {"expand": "body.storage,version,space,ancestors"}
```

In `md2conf/api.py:1170` (`_get_page_properties_v1`):

```python
        query = {"expand": "version,space,history,ancestors"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_api_ancestors -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Run the full suite**

Run: `python -m unittest discover -s tests`
Expected: OK.

> This is the change that brings the previously-dead re-parenting branch (`publisher.py:89-97`) to life on Data Center. If any existing test breaks here, it is revealing that dead branch — do not suppress it; note the failure and continue to Task 8, which guards it.

- [ ] **Step 6: Commit**

```bash
git add md2conf/api.py tests/test_api_ancestors.py
git commit -m "fix(api): expand ancestors on v1 fetches so parentId is populated"
```

---

### Task 3: `ConfluenceSession.get_ancestor_ids`

See design §5.2.

**Files:**
- Modify: `md2conf/api.py` (add near `get_page_properties`, around :1185)
- Test: `tests/test_api_ancestors.py` (extend)

**Interfaces:**
- Produces: `ConfluenceSession.get_ancestor_ids(page_id: str) -> list[str]` — ancestor IDs ordered outermost-first, excluding the page itself. Raises `ConfluenceError` when the chain exceeds `ANCESTOR_DEPTH_LIMIT`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_api_ancestors.py`:

```python
class TestGetAncestorIds(unittest.TestCase):
    def test_v1_returns_full_chain_root_first(self) -> None:
        session = make_session("datacenter")
        transport: Mock = session.session  # type: ignore[assignment]
        transport.get.return_value = _json_response(_v1_page("300", "Child", ["100", "200"]))

        self.assertEqual(session.get_ancestor_ids("300"), ["100", "200"])

    def test_v1_root_page_has_no_ancestors(self) -> None:
        session = make_session("datacenter")
        transport: Mock = session.session  # type: ignore[assignment]
        transport.get.return_value = _json_response(_v1_page("100", "Root", []))

        self.assertEqual(session.get_ancestor_ids("100"), [])

    def test_v2_walks_parent_chain_root_first(self) -> None:
        session = make_session("cloud")
        chain = {"300": "200", "200": "100", "100": None}

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

Add `import unittest.mock` to the imports at the top of the file.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_api_ancestors.TestGetAncestorIds -v`
Expected: FAIL with `AttributeError: 'ConfluenceSession' object has no attribute 'get_ancestor_ids'`

- [ ] **Step 3: Implement**

Add a module-level constant near the top of `md2conf/api.py`, beside the other module constants:

```python
ANCESTOR_DEPTH_LIMIT = 100
"Maximum page hierarchy depth traversed when resolving ancestors; a stop against cyclic parent data."
```

Add the methods after `get_page_properties` (`md2conf/api.py:1185`):

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
        """
        Retrieves ancestors using the v1 API, which returns the whole chain in a single response.
        """
        path = f"/content/{page_id}"
        query = {"expand": "ancestors"}
        response = self._get(ConfluenceVersion.VERSION_1, path, dict[str, JsonType], query=query)
        ancestors = typing.cast(list[JsonType], response.get("ancestors", []))
        return [str(typing.cast(dict[str, JsonType], item)["id"]) for item in ancestors]

    def _get_ancestor_ids_v2(self, page_id: str) -> list[str]:
        """
        Retrieves ancestors using the v2 API by walking up the parent chain.
        """
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

Ensure `ConfluenceError` is imported in `api.py` from `.environment`; add it to the existing import if absent.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_api_ancestors -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Run full suite and static checks**

Run: `python -m unittest discover -s tests && ./check.sh`
Expected: OK, no errors.

- [ ] **Step 6: Commit**

```bash
git add md2conf/api.py tests/test_api_ancestors.py
git commit -m "feat(api): add get_ancestor_ids for v1 chain and v2 parent walk"
```

---

### Task 4: `page_exists` raises on an ambiguous match

See design §5.5. Correct **only** because the caller supplies the parent's `spaceId` (Task 7) — the test below locks that in.

**Files:**
- Modify: `md2conf/api.py:1759` (`_page_exists_v1`), `md2conf/api.py:1805` (`page_exists` v2 branch)
- Test: `tests/test_api_page_exists.py` (new)

**Interfaces:**
- Produces: `page_exists` raises `PageCollisionError` when more than one page matches; still returns `None` for zero matches and the ID for exactly one.

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

from .utility import make_session


def _json_response(payload: dict[str, Any]) -> Mock:
    response = Mock(spec=requests.Response)
    response.status_code = 200
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def _result(page_id: str, title: str) -> dict[str, Any]:
    return {
        "id": page_id,
        "title": title,
        "status": "current",
        "spaceId": "1",
        "parentId": None,
        "authorId": "user",
        "createdAt": "2026-01-01T00:00:00.000Z",
        "version": {"number": 1},
    }


class TestPageExistsAmbiguity(unittest.TestCase):
    def test_v1_single_match_returns_id(self) -> None:
        session = make_session("datacenter")
        transport: Mock = session.session  # type: ignore[assignment]
        transport.get.return_value = _json_response({"results": [_result("300", "Guide")]})

        self.assertEqual(session.page_exists("Guide", space_key="TEST"), "300")

    def test_v1_no_match_returns_none(self) -> None:
        session = make_session("datacenter")
        transport: Mock = session.session  # type: ignore[assignment]
        transport.get.return_value = _json_response({"results": []})

        self.assertIsNone(session.page_exists("Guide", space_key="TEST"))

    def test_v1_multiple_matches_raise_naming_ids(self) -> None:
        session = make_session("datacenter")
        transport: Mock = session.session  # type: ignore[assignment]
        transport.get.return_value = _json_response({"results": [_result("300", "Guide"), _result("400", "Guide")]})

        with self.assertRaises(PageCollisionError) as context:
            session.page_exists("Guide", space_key="TEST")

        message = str(context.exception)
        self.assertIn("300", message)
        self.assertIn("400", message)

    def test_v1_query_is_scoped_to_a_space(self) -> None:
        """Two same-titled pages in different spaces must not collide: the query must carry a space filter."""

        session = make_session("datacenter")
        transport: Mock = session.session  # type: ignore[assignment]
        transport.get.return_value = _json_response({"results": [_result("300", "Guide")]})

        session.page_exists("Guide", space_key="TEST")

        self.assertEqual(transport.get.call_args.kwargs["params"]["spaceKey"], "TEST")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_api_page_exists -v`
Expected: FAIL on `test_v1_multiple_matches_raise_naming_ids` — currently returns `None` instead of raising.

- [ ] **Step 3: Implement for v1**

Replace the tail of `_page_exists_v1` (`md2conf/api.py:1759-1763`):

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

Replace the tail of the v2 branch of `page_exists` (`md2conf/api.py:1805-1808`):

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

- [ ] **Step 6: Add the v2 mirror tests**

Append a `TestPageExistsAmbiguityCloud` class mirroring the four cases with `make_session("cloud")`. The v2 response shape is `{"results": [...]}` with the same `_result` payload, and the space filter key is `space-id` rather than `spaceKey`. Run and confirm PASS.

- [ ] **Step 7: Run full suite and static checks**

Run: `python -m unittest discover -s tests && ./check.sh`
Expected: OK.

- [ ] **Step 8: Commit**

```bash
git add md2conf/api.py tests/test_api_page_exists.py
git commit -m "fix(api): raise on ambiguous title match instead of falling through to create"
```

---

### Task 5: `AncestryResolver`

See design §5.2 (caching) and §4. Pure logic over `get_ancestor_ids`; no HTTP in its tests.

**Files:**
- Create: `md2conf/ancestry.py`
- Test: `tests/test_ancestry.py` (new)

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


def _resolver(chains: dict[str, list[str]]) -> tuple[AncestryResolver, Mock]:
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
Expected: FAIL with `ModuleNotFoundError: No module named 'md2conf.ancestry'`

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
Expected: PASS (5 tests)

- [ ] **Step 5: Run full suite and static checks**

Run: `python -m unittest discover -s tests && ./check.sh`
Expected: OK.

- [ ] **Step 6: Commit**

```bash
git add md2conf/ancestry.py tests/test_ancestry.py
git commit -m "feat: add AncestryResolver for page sub-tree containment checks"
```

---

### Task 6: Reject duplicate local page IDs

See design §5.4 and §7. Purely local, so it also covers `--local`.

**Files:**
- Modify: `md2conf/processor.py:130-136` (`_process_items`)
- Test: `tests/test_processor.py` (extend)

**Interfaces:**
- Produces: `Processor._assert_unique_page_ids(root: DocumentNode) -> None`, called at the top of `_process_items`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_processor.py` (match the file's existing import style; `DocumentNode` comes from `md2conf.processor`):

```python
class TestDuplicatePageIds(unittest.TestCase):
    def test_duplicate_page_ids_are_rejected(self) -> None:
        from pathlib import Path

        from md2conf.environment import PageCollisionError
        from md2conf.processor import DocumentNode, Processor

        root = DocumentNode(
            absolute_path=Path("/docs/index.md"),
            page_id="100",
            space_key=None,
            title=None,
            synchronized=True,
            users=set(),
        )
        first = DocumentNode(
            absolute_path=Path("/docs/a.md"),
            page_id="200",
            space_key=None,
            title=None,
            synchronized=True,
            users=set(),
        )
        second = DocumentNode(
            absolute_path=Path("/docs/b.md"),
            page_id="200",
            space_key=None,
            title=None,
            synchronized=True,
            users=set(),
        )
        root.add(first)
        root.add(second)

        with self.assertRaises(PageCollisionError) as context:
            Processor._assert_unique_page_ids(root)

        message = str(context.exception)
        self.assertIn("200", message)
        self.assertIn("a.md", message)
        self.assertIn("b.md", message)

    def test_distinct_page_ids_are_accepted(self) -> None:
        from pathlib import Path

        from md2conf.processor import DocumentNode, Processor

        root = DocumentNode(
            absolute_path=Path("/docs/index.md"),
            page_id="100",
            space_key=None,
            title=None,
            synchronized=True,
            users=set(),
        )
        child = DocumentNode(
            absolute_path=Path("/docs/a.md"),
            page_id="200",
            space_key=None,
            title=None,
            synchronized=True,
            users=set(),
        )
        root.add(child)

        Processor._assert_unique_page_ids(root)  # must not raise
```

> Read `md2conf/processor.py:29-64` for `DocumentNode`'s real constructor signature and the name of its child-appending method (`add` here is a placeholder if the real name differs) and adjust both tests accordingly before running.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_processor.TestDuplicatePageIds -v`
Expected: FAIL with `AttributeError: type object 'Processor' has no attribute '_assert_unique_page_ids'`

- [ ] **Step 3: Implement**

Add to `Processor` in `md2conf/processor.py`, and import `PageCollisionError` from `.environment`:

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

Call it as the first statement of `_process_items` (`md2conf/processor.py:130`):

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
Expected: OK.

- [ ] **Step 6: Commit**

```bash
git add md2conf/processor.py tests/test_processor.py
git commit -m "fix: reject two documents declaring the same Confluence page ID"
```

---

### Task 7: Seam split and two-stage containment guard

**The behavior change.** See design §4, §4.1, §5.3.

**Files:**
- Modify: `md2conf/publisher.py:48-146`
- Test: `tests/test_collision_guard.py` (new)

**Interfaces:**
- Consumes: `AncestryResolver` (Task 5), `PageCollisionError` and `options.allow_adopt` (Task 1), `page_exists` (Task 4)
- Produces: `Publisher._assert_owned(page_id, page_title, managed_root_id, source_path) -> None`; `_synchronize_subtree(node, parent_id, managed_root_id, parent_to_children, *, is_root=False)`

- [ ] **Step 1: Write the failing test**

Create `tests/test_collision_guard.py`. Build a `Publisher` with a mocked `ConfluenceSession`, so no HTTP occurs:

```python
"""
Tests for the cross-effort page collision guard.

Copyright 2022-2025, Levente Hunyadi

:see: https://github.com/hunyadi/md2conf
"""

import unittest
from pathlib import Path
from unittest.mock import Mock

from md2conf.api import ConfluenceSession
from md2conf.domain import ConfluenceDocumentOptions, ConfluencePageID
from md2conf.environment import PageCollisionError


def _properties(page_id: str, title: str, parent_id: "str | None") -> Mock:
    properties = Mock()
    properties.id = page_id
    properties.title = title
    properties.parentId = parent_id
    properties.status = "current"
    return properties


class TestContainmentGuard(unittest.TestCase):
    """
    Tree used throughout:

        100 (anchor / -r)
         └── 200 (managed root: the root document's page)
              └── 300 (a child document's page)

        900 (a foreign effort's page, outside the anchor)
    """

    CHAINS = {"100": [], "200": ["100"], "300": ["100", "200"], "900": ["800"], "800": []}

    def _api(self) -> Mock:
        api = Mock(spec=ConfluenceSession)
        api.get_ancestor_ids.side_effect = lambda page_id: self.CHAINS[page_id]
        return api

    def test_adopting_a_page_outside_the_managed_root_raises(self) -> None:
        from md2conf.ancestry import AncestryResolver
        from md2conf.publisher import Publisher

        api = self._api()
        publisher = Publisher.__new__(Publisher)
        publisher.api = api
        publisher.options = ConfluenceDocumentOptions()
        publisher.ancestry = AncestryResolver(api)

        with self.assertRaises(PageCollisionError) as context:
            publisher._assert_owned("900", "Foreign Page", "200", Path("/docs/source-inventory.md"))

        message = str(context.exception)
        self.assertIn("900", message)
        self.assertIn("Foreign Page", message)
        self.assertIn("--allow-adopt 900", message)

    def test_adopting_a_page_inside_the_managed_root_is_allowed(self) -> None:
        from md2conf.ancestry import AncestryResolver
        from md2conf.publisher import Publisher

        api = self._api()
        publisher = Publisher.__new__(Publisher)
        publisher.api = api
        publisher.options = ConfluenceDocumentOptions()
        publisher.ancestry = AncestryResolver(api)

        publisher._assert_owned("300", "Child", "200", Path("/docs/a.md"))  # must not raise

    def test_managed_root_itself_is_adoptable(self) -> None:
        from md2conf.ancestry import AncestryResolver
        from md2conf.publisher import Publisher

        api = self._api()
        publisher = Publisher.__new__(Publisher)
        publisher.api = api
        publisher.options = ConfluenceDocumentOptions()
        publisher.ancestry = AncestryResolver(api)

        publisher._assert_owned("200", "Root", "200", Path("/docs/index.md"))  # must not raise

    def test_allow_adopt_authorizes_exactly_one_page(self) -> None:
        from md2conf.ancestry import AncestryResolver
        from md2conf.publisher import Publisher

        api = self._api()
        publisher = Publisher.__new__(Publisher)
        publisher.api = api
        publisher.options = ConfluenceDocumentOptions(allow_adopt=frozenset({"900"}))
        publisher.ancestry = AncestryResolver(api)

        publisher._assert_owned("900", "Foreign Page", "200", Path("/docs/a.md"))  # authorized

        self.CHAINS["901"] = ["800"]
        with self.assertRaises(PageCollisionError):
            publisher._assert_owned("901", "Another Foreign Page", "200", Path("/docs/b.md"))


if __name__ == "__main__":
    unittest.main()
```

Replace `"str | None"` with `Optional[str]` and add `from typing import Optional` — the `|` form is not valid on Python 3.9.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_collision_guard -v`
Expected: FAIL with `AttributeError: 'Publisher' object has no attribute '_assert_owned'`

- [ ] **Step 3: Implement the guard**

Add to `Publisher` in `md2conf/publisher.py`, importing `AncestryResolver` from `.ancestry` and `PageCollisionError` from `.environment`:

```python
    def _assert_owned(self, page_id: str, page_title: str, managed_root_id: str, source_path: Path) -> None:
        """
        Verifies that a page found by lookup belongs to the tree being published.

        :param page_id: Confluence page ID the lookup resolved to.
        :param page_title: Title of that page, for diagnostics.
        :param managed_root_id: Confluence page ID that bounds the tree being published.
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

Replace `_synchronize_structure` and `_synchronize_subtree` in `md2conf/publisher.py:48-146`. The root-ID resolution at :60-73 is unchanged; what changes is creating the resolver, and passing `managed_root_id` plus `is_root`:

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
        if node.page_id is not None:
            # verify if page exists, and that it belongs to the tree being published
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

            # the parent supplies the space to search; dropping this would match same-titled pages in other spaces
            parent_page = self.api.get_page_properties(parent_id.page_id)
            found_id = self.api.page_exists(title, space_id=parent_page.spaceId)

            if found_id is not None:
                properties = self.api.get_page_properties(found_id)
                self._assert_owned(found_id, properties.title, managed_root_id, node.absolute_path)
                page = self.api.get_page(found_id)

                if page.status is ConfluenceStatus.ARCHIVED:
                    # user has archived a page with this (auto-generated) title
                    raise PageError(f"unable to update archived page with ID {page.id}")

                self._reparent_if_needed(node, properties, parent_id, is_root=is_root)
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

`_reparent_if_needed` is added in Task 8; until then, stub it so this task's tests run:

```python
    def _reparent_if_needed(self, node: DocumentNode, page: ConfluencePageProperties, parent_id: ConfluencePageID, *, is_root: bool) -> None:
        if page.parentId is not None and page.parentId != parent_id.page_id:
            LOGGER.info("Moving page %s from parent %s to %s", page.id, page.parentId, parent_id.page_id)
            self.api.move_page(page.id, parent_id.page_id)
            self.ancestry.invalidate()
```

Declare `ancestry: AncestryResolver` in the `Publisher` class attribute block, and import `ConfluencePageProperties` and `ConfluenceStatus` if not already imported.

- [ ] **Step 7: Run the full suite**

Run: `python -m unittest discover -s tests`
Expected: OK.

> Existing publisher tests that assumed space-wide adoption may now fail. Each such failure is the guard working. Fix the *test* to publish inside a managed tree; do not weaken the guard.

- [ ] **Step 8: Run static checks**

Run: `./check.sh`
Expected: no errors.

- [ ] **Step 9: Commit**

```bash
git add md2conf/publisher.py
git commit -m "fix: validate page ownership before adopting, and bound descendants by the resolved root"
```

---

### Task 8: Self-parent, non-root equality, and cycle guards

See design §5.4. Must land with Task 7 — Task 2 unmasked the self-parent bug on Data Center.

**Files:**
- Modify: `md2conf/publisher.py` (`_reparent_if_needed` from Task 7)
- Test: `tests/test_collision_guard.py` (extend)

**Interfaces:**
- Consumes: `AncestryResolver.contains` (Task 5)
- Produces: final `_reparent_if_needed`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_collision_guard.py`:

```python
class TestReparentGuards(unittest.TestCase):
    CHAINS = {"100": [], "200": ["100"], "300": ["100", "200"]}

    def _publisher(self) -> tuple[object, Mock]:
        from md2conf.ancestry import AncestryResolver
        from md2conf.publisher import Publisher

        api = Mock(spec=ConfluenceSession)
        api.get_ancestor_ids.side_effect = lambda page_id: self.CHAINS[page_id]
        publisher = Publisher.__new__(Publisher)
        publisher.api = api
        publisher.options = ConfluenceDocumentOptions()
        publisher.ancestry = AncestryResolver(api)
        return publisher, api

    def test_root_node_equal_to_its_parent_is_not_moved(self) -> None:
        publisher, api = self._publisher()
        page = _properties("200", "Root", "100")

        publisher._reparent_if_needed(Mock(absolute_path=Path("/docs/index.md")), page, ConfluencePageID("200"), is_root=True)

        api.move_page.assert_not_called()

    def test_non_root_node_equal_to_its_parent_raises(self) -> None:
        publisher, api = self._publisher()
        page = _properties("200", "Child", "100")

        with self.assertRaises(PageCollisionError):
            publisher._reparent_if_needed(Mock(absolute_path=Path("/docs/a.md")), page, ConfluencePageID("200"), is_root=False)

        api.move_page.assert_not_called()

    def test_moving_a_page_under_its_own_descendant_raises(self) -> None:
        publisher, api = self._publisher()
        page = _properties("200", "Parent", "100")

        with self.assertRaises(PageCollisionError):
            publisher._reparent_if_needed(Mock(absolute_path=Path("/docs/a.md")), page, ConfluencePageID("300"), is_root=False)

        api.move_page.assert_not_called()

    def test_legitimate_move_invalidates_the_ancestor_cache(self) -> None:
        publisher, api = self._publisher()
        publisher.ancestry.contains("100", "300")
        page = _properties("300", "Child", "200")

        publisher._reparent_if_needed(Mock(absolute_path=Path("/docs/a.md")), page, ConfluencePageID("100"), is_root=False)

        api.move_page.assert_called_once_with("300", "100")
        publisher.ancestry.contains("100", "300")
        self.assertEqual(api.get_ancestor_ids.call_count, 2)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_collision_guard.TestReparentGuards -v`
Expected: FAIL — the stub neither raises on non-root equality nor detects cycles.

- [ ] **Step 3: Implement**

Replace the stub `_reparent_if_needed` in `md2conf/publisher.py`:

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

        if page.parentId is None or page.parentId == parent_id.page_id:
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

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_collision_guard -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Run full suite and static checks**

Run: `python -m unittest discover -s tests && ./check.sh`
Expected: OK.

- [ ] **Step 6: Commit**

```bash
git add md2conf/publisher.py tests/test_collision_guard.py
git commit -m "fix: guard self-parenting, duplicate parent mapping, and move cycles"
```

---

### Task 9: Remove `get_or_create_page` and document the breaks

See design §5.3 and §7.

**Files:**
- Modify: `md2conf/api.py:1810-1826` (delete)
- Modify: `CHANGELOG.md`
- Test: `tests/test_collision_guard.py` (extend)

**Interfaces:**
- Produces: `ConfluenceSession.get_or_create_page` no longer exists.

- [ ] **Step 1: Confirm there are no remaining callers**

Run: `rg -n "get_or_create_page" --type py`
Expected: only the definition in `md2conf/api.py`. If anything else appears, it must be migrated to the split form from Task 7 before proceeding.

- [ ] **Step 2: Write the failing test**

Append to `tests/test_collision_guard.py`:

```python
class TestUnsafePrimitiveRemoved(unittest.TestCase):
    def test_get_or_create_page_is_gone(self) -> None:
        self.assertFalse(hasattr(ConfluenceSession, "get_or_create_page"))
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m unittest tests.test_collision_guard.TestUnsafePrimitiveRemoved -v`
Expected: FAIL — the attribute still exists.

- [ ] **Step 4: Delete the method**

Remove `get_or_create_page` in its entirety from `md2conf/api.py:1810-1826`.

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m unittest tests.test_collision_guard -v`
Expected: PASS (9 tests)

- [ ] **Step 6: Record the breaking changes**

Add to `CHANGELOG.md` under a new unreleased entry (match the file's existing heading style):

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
  Callers should look the page up with `page_exists`, validate the result, then call `create_page` if absent.
- `ConfluenceSession.page_exists` now raises `PageCollisionError` when more than one page matches, instead of
  returning `None`.
- Two Markdown documents declaring the same `confluence-page-id` is now an error. Previously the second document
  silently overwrote the first. Remove the duplicated comment from one of the documents.
- Adopting a page outside the tree being published now fails. Use `--allow-adopt <page-id>` to authorize a
  specific page.
```

- [ ] **Step 7: Run the full suite and static checks**

Run: `python -m unittest discover -s tests && ./check.sh`
Expected: OK.

- [ ] **Step 8: Commit**

```bash
git add md2conf/api.py CHANGELOG.md tests/test_collision_guard.py
git commit -m "refactor!: remove unsafe get_or_create_page primitive"
```

---

## Verification

After Task 9, confirm the incident scenario is closed. Add to `tests/test_collision_guard.py`:

```python
class TestIncidentScenario(unittest.TestCase):
    """
    Reproduces the GSSPACE incident topology.

        100  Effort A anchor (-r)
         └── 200  Effort A root document
        800  unrelated tree
         └── 900  Effort B's 'source-inventory' page
    """

    CHAINS = {"100": [], "200": ["100"], "800": [], "900": ["800"]}

    def test_poisoned_page_id_is_refused(self) -> None:
        """Effort A's source-inventory.md now carries Effort B's page ID; the guard must refuse it."""

        from md2conf.ancestry import AncestryResolver
        from md2conf.publisher import Publisher

        api = Mock(spec=ConfluenceSession)
        api.get_ancestor_ids.side_effect = lambda page_id: self.CHAINS[page_id]
        publisher = Publisher.__new__(Publisher)
        publisher.api = api
        publisher.options = ConfluenceDocumentOptions()
        publisher.ancestry = AncestryResolver(api)

        with self.assertRaises(PageCollisionError):
            publisher._assert_owned("900", "source-inventory", "200", Path("/effort-a/00-inception/source-inventory.md"))

        api.move_page.assert_not_called()


class TestSharedAnchorTopologies(unittest.TestCase):
    """
    Design cases 11 and 11b — the two topologies where a naive boundary silently fails open.

        100  shared -r container
         ├── 200  Effort A root document
         │    └── 300  Effort A child
         └── 500  Effort B root document
              └── 600  Effort B child

        700  Effort B's own -r anchor (separate-anchor case)
         └── 500
    """

    CHAINS = {
        "100": [],
        "200": ["100"],
        "300": ["100", "200"],
        "500": ["100"],
        "600": ["100", "500"],
    }

    def _publisher(self, chains: dict) -> tuple[object, Mock]:
        from md2conf.ancestry import AncestryResolver
        from md2conf.publisher import Publisher

        api = Mock(spec=ConfluenceSession)
        api.get_ancestor_ids.side_effect = lambda page_id: chains[page_id]
        publisher = Publisher.__new__(Publisher)
        publisher.api = api
        publisher.options = ConfluenceDocumentOptions()
        publisher.ancestry = AncestryResolver(api)
        return publisher, api

    def test_11_shared_anchor_poisoned_id_into_sibling_effort_is_refused(self) -> None:
        """
        Both efforts publish under the same -r (100). Effort A's managed root is its own resolved
        root document (200), NOT the anchor. A poisoned ID pointing at Effort B's child (600) must
        be refused even though 600 IS a descendant of the shared anchor.
        """

        publisher, api = self._publisher(self.CHAINS)

        with self.assertRaises(PageCollisionError):
            publisher._assert_owned("600", "Effort B Child", "200", Path("/effort-a/a.md"))

        # the same page IS contained by the anchor -- proving the boundary is not the anchor
        self.assertTrue(publisher.ancestry.contains("100", "600"))

    def test_11b_root_node_resolving_to_a_foreign_root_is_refused(self) -> None:
        """
        The collapse case. Both efforts publish 00-inception/, so both root documents synthesize the
        SAME title and Effort A's root node can title-resolve to Effort B's root page (500).

        Stage 1 must check the root node against its own anchor (700). Without this, Effort A's
        managed root becomes 500, every later descendant check passes, and Effort A publishes its
        whole tree inside Effort B.
        """

        chains = dict(self.CHAINS)
        chains["700"] = []
        chains["500"] = ["700"]

        publisher, _ = self._publisher(chains)

        # Effort A's anchor is 100; the lookup resolved to Effort B's root page 500, under anchor 700
        with self.assertRaises(PageCollisionError):
            publisher._assert_owned("500", "index", "100", Path("/effort-a/00-inception/index.md"))
```

Run: `python -m unittest discover -s tests && ./check.sh`

---

## Known Gaps

Stated so they are not mistaken for oversights:

- **Not atomic.** Structure sync is depth-first, so nodes earlier in traversal are created, moved, and have IDs written to disk before a later node's violation is found. The guarantee is "no write to the offending page", not "no writes at all".
- **TOCTOU** (design §8). A page validated during structure sync can be moved by another user before content sync writes it.
- **Deferred** (design §2): salted digest, `--strict-create`, `--local` dry-run warning, digest padding `{c:x}` → `{c:02x}`.
- **Live verification outstanding.** No Confluence Cloud instance is available here, so self-parenting server behavior remains unverified. Task 8 prevents the call rather than relying on how the server answers it.
