# Page Order Synchronization Design

**Date:** 2026-06-17

## Overview

After synchronizing the content of a directory tree with Confluence, reorder child pages under each parent to match the local directory/file sort order. Foreign pages (created directly in Confluence, not managed by md2conf) are left in place; only the relative order of locally-managed pages is enforced.

This follows the upstream `hunyadi/md2conf` implementation from commit `e3c8c87` (with fail-safe patch `cae8cea`).

## Scope

**In scope:**
- Always-on when syncing a directory tree (no separate flag)
- Foreign Confluence pages ignored (their relative position unchanged)
- Minimum number of API calls using LIS-based algorithm
- Both Cloud/v2 and Data Center/v1 API paths

**Out of scope:**
- Ordering when syncing a single file
- User-defined manual ordering (e.g., via frontmatter `order:` key)

## Algorithm

A new `md2conf/order.py` module (ported from upstream) contains `sort_items_in_order()`, which reorders items using the **minimum number of insert operations**:

1. Compute the target order from the supplied key function.
2. Find the **Longest Increasing Subsequence (LIS)** of the current order relative to the target — these items stay in place.
3. For each item NOT in the LIS (in target order), issue exactly one `insert_before` or `insert_after` call.

In the worst case (completely reversed order) this is N calls. In the best case (already in order) it is 0 calls. Average case is significantly below N.

```python
def sort_items_in_order(
    items: Iterable[T],
    *,
    key: Callable[[T], Any],
    insert_before: Callable[[T, T], None],
    insert_after: Callable[[T, T], None],
) -> None: ...
```

## Architecture

Five files change. One new module.

| File | Change |
|---|---|
| `md2conf/order.py` | New — LIS algorithm and `sort_items_in_order` |
| `md2conf/api.py` | New `get_child_page_ids`, `move_page_before_sibling`, `move_page_after_sibling` methods (v1 + v2) |
| `md2conf/processor.py` | `_synchronize_structure` returns `dict[str, list[str]]`; new abstract `_synchronize_order`; `_synchronize_content` orchestrates both |
| `md2conf/publisher.py` | `SynchronizingProcessor._synchronize_order` calls `sort_items_in_order` |
| `md2conf/local.py` | `LocalConverter._synchronize_order` is a no-op |

## Structural Change to Processor

Currently `_synchronize_tree(root, root_id) -> None`. This changes to:

```python
@abstractmethod
def _synchronize_structure(self, tree: DocumentNode) -> dict[str, list[str]]:
    """
    Synchronizes directory tree structure with Confluence page hierarchy.
    Returns parent_id → [child_id, ...] map (Confluence ordering).
    """
    ...
```

`_synchronize_content(tree, parent_to_children: dict[str, list[str]])` is called with the returned map:

```python
def _synchronize_content(self, tree: DocumentNode, parent_to_children: dict[str, list[str]]) -> None:
    # 1. resolve user mentions
    # 2. synchronize page order  ← NEW
    self._synchronize_order(tree, parent_to_children)
    # 3. synchronize page content
    for path, metadata in self.page_metadata.items():
        if metadata.synchronized:
            self._synchronize_page(path, ConfluencePageID(metadata.page_id))
```

New abstract method:
```python
@abstractmethod
def _synchronize_order(self, tree: DocumentNode, parent_to_children: dict[str, list[str]]) -> None: ...
```

## Building the parent→children Map

`SynchronizingProcessor._synchronize_structure` (formerly `_synchronize_tree`) builds the map as it traverses the tree. After each page is confirmed/created, its Confluence children are fetched and recorded:

```python
parent_to_children: dict[str, list[str]] = {}

def record_children(parent_id: str) -> None:
    children = self.api.get_child_page_ids(parent_id)
    parent_to_children[parent_id] = children

# called after establishing/confirming each node's page_id
record_children(resolved_page_id)
```

This piggybacks on the existing traversal — no separate pass needed.

## `_synchronize_order` Implementation

```python
@override
def _synchronize_order(self, tree: DocumentNode, parent_to_children: dict[str, list[str]]) -> None:
    metadata = self.page_metadata.get(tree.absolute_path)
    if metadata is None:
        return

    parent_id = metadata.page_id

    # build desired order: page IDs of children we manage
    local_order: list[str] = []
    for child in tree.children():
        child_meta = self.page_metadata.get(child.absolute_path)
        if child_meta is not None:
            local_order.append(child_meta.page_id)

    if not local_order:
        return

    child_pages = parent_to_children.get(parent_id)
    if child_pages:
        # extract only managed pages, preserving Confluence order
        remote_order = [cid for cid in child_pages if cid in local_order]

        def index_of(page_id: str) -> int:
            return local_order.index(page_id)

        def insert_before(page_id: str, ref_id: str) -> None:
            self.api.move_page_before_sibling(page_id, ref_id)

        def insert_after(page_id: str, ref_id: str) -> None:
            self.api.move_page_after_sibling(page_id, ref_id)

        sort_items_in_order(remote_order, key=index_of, insert_before=insert_before, insert_after=insert_after)

    # recurse into children
    for child in tree.children():
        self._synchronize_order(child, parent_to_children)
```

## New API Methods

### `get_child_page_ids(parent_id: str) -> list[str]`

Returns the page IDs of direct child pages in their current Confluence display order.

- v2: `GET /wiki/api/v2/pages/{parent_id}/children?limit=250&sort=child-position` → extract `id` fields
- v1: `GET /rest/api/content/{parent_id}/child/page?limit=250` → extract `id` fields (default ordering is position-based)

Returns `[]` if the parent has no children or the API call fails (fail-safe).

### `move_page_before_sibling(page_id: str, ref_id: str) -> None`

Moves `page_id` to appear immediately before `ref_id` (both must share the same parent).

- v2: `PUT /wiki/api/v2/pages/{page_id}` with `{"position": "before", "targetId": ref_id}` — or equivalent position endpoint
- v1: `PUT /rest/api/content/{page_id}/move/before/{ref_id}`

### `move_page_after_sibling(page_id: str, ref_id: str) -> None`

Moves `page_id` to appear immediately after `ref_id`.

- v2: `PUT /wiki/api/v2/pages/{page_id}` with `{"position": "after", "targetId": ref_id}`
- v1: `PUT /rest/api/content/{page_id}/move/after/{ref_id}`

**Note:** These are distinct from the existing `move_page(page_id, new_parent_id)` which handles re-parenting. Sibling ordering and re-parenting are separate API operations.

**Implementation note:** The exact v2 request body for sibling positioning should be verified against the Confluence Cloud REST API v2 docs during implementation. The v1 endpoints are confirmed from Confluence Data Center REST API documentation.

## Fail-Safe Behavior

If `get_child_page_ids` returns `None` or an empty list (e.g., API error, page has no tracked children), `_synchronize_order` skips ordering for that parent silently. This prevents a transient API failure from blocking the entire sync (upstream patch `cae8cea`).

## Testing

### Unit tests (`tests/test_order.py`)

- Already-sorted list → 0 moves
- Fully reversed list → N-1 moves
- One item out of place → 1 move
- Single item list → 0 moves
- Empty list → 0 moves
- `sort_items_in_order` with mock `insert_before`/`insert_after` callables: verify call count and arguments

### Integration behavior tests

- `_synchronize_order` with a mock API: verify `move_page_before_sibling` / `move_page_after_sibling` called with correct page IDs
- Foreign pages (not in `local_order`) are filtered from `remote_order` and never moved
- Empty `parent_to_children` (no Confluence children returned): no moves attempted
