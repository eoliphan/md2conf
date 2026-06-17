# User Mentions Design

**Date:** 2026-06-16 (revised 2026-06-17)

## Overview

Translate standard Markdown email links of the form `[Name](mailto:email@example.com)` into Confluence user mention macros in the generated Confluence Storage Format (CSF). When a mention cannot be resolved (email not matched to a Confluence user), emit a warning and leave the link as a standard mailto anchor.

This follows the upstream `hunyadi/md2conf` implementation from commit `d2f3e8e`.

## Syntax

Users are referenced using standard Markdown link syntax with a `mailto:` URL:

```markdown
Please review with [John Smith](mailto:jsmith@example.com) before merging.
```

This renders as a normal email hyperlink in GitHub, VS Code, and other Markdown renderers. When synchronized to Confluence, md2conf replaces matching `mailto:` links with user mention macros.

## Scope

**In scope:**
- `[Name](mailto:email)` link syntax → Confluence mention
- Resolution by exact email address match against Confluence user profiles
- Cloud/v2: emits `<ac:link><ri:user ri:account-id="..."/></ac:link>`
- Data Center/v1: emits `<ac:link><ri:user ri:username="..."/></ac:link>` (login username from API response)
- New `--user-mentions` / `--no-user-mentions` CLI flag (default: enabled)
- Warn-and-skip for unresolvable emails
- No-op in `--local` mode (links left as mailto anchors)

**Out of scope:**
- `@username` bare-word syntax
- Partial name matching or fuzzy lookup
- Caching user lookups across invocations

## Architecture

Six files change. One new module.

| File | Change |
|---|---|
| `md2conf/text.py` | New `user_references(text)` function |
| `md2conf/collection.py` | New `ConfluenceUserCollection` class |
| `md2conf/domain.py` | Add `user_mentions: bool = True` to `ConfluenceDocumentOptions` |
| `md2conf/processor.py` | `DocumentNode` gets `users` field; `_synchronize_content` drives user resolution; new abstract `_synchronize_users` |
| `md2conf/converter.py` | `ConfluenceStorageFormatConverter` gets `user_metadata`; `_transform_mention` handles `mailto:` links |
| `md2conf/publisher.py` | `SynchronizingProcessor._synchronize_users` resolves emails via API |
| `md2conf/__main__.py` | Add `--user-mentions` / `--no-user-mentions` arguments |

`LocalConverter` returns an empty `ConfluenceUserCollection` from its `_synchronize_users` override.

## Data Flow

```
Index phase (per file):
  Scanner reads Markdown text
  user_references(text) → set of (email, name) tuples
  stored on DocumentNode.users

_synchronize_content phase:
  Collect users = union of node.users for all descendants
  if options.user_mentions:
      self.user_metadata = self._synchronize_users(users)
  else:
      self.user_metadata = ConfluenceUserCollection()  # empty

_synchronize_users (SynchronizingProcessor):
  for each (email, name) in users:
      api.get_users(name)  → list[ConfluenceUser]
      find entry where user.email == email
      store (email → (attr_name, attr_val)) in ConfluenceUserCollection

_synchronize_page:
  ConfluenceDocument.create(..., user_metadata=self.user_metadata)
  converter receives user_metadata

Conversion phase:
  _transform_anchor: if href starts with "mailto:"
      email = href[len("mailto:"):]
      result = user_metadata.get(email)
      if result: return <ac:link><ri:user {attr_name}="{attr_val}"/></ac:link>
      else: return None (leave as standard mailto link)
```

## New Functions and Types

### `md2conf/text.py`

```python
import re

def user_references(text: str) -> set[tuple[str, str]]:
    """
    Extracts [Name](mailto:email) patterns from Markdown text.
    Returns a set of (email, name) tuples.
    """
    return set(
        (m.group("email"), m.group("name"))
        for m in re.finditer(
            r"\[(?P<name>[^\[\]]+)\]\(mailto:(?P<email>[^()]+)\)", text
        )
    )
```

### `md2conf/collection.py`

```python
class ConfluenceUserCollection(KeyValueCollection[str, tuple[str, str]]):
    """
    Maps Confluence user email addresses to their CSF attribute tuple.
    Stored as (ri_attribute_name, ri_attribute_value), e.g.:
      v2: ("ri:account-id", "557058:abc-def")
      v1: ("ri:username",   "jsmith")
    """
    ...
```

### `md2conf/domain.py`

Add to `ConfluenceDocumentOptions`:
```python
user_mentions: bool = True
```

### `md2conf/processor.py`

`DocumentNode` gains:
```python
users: set[tuple[str, str]]  # (email, name) pairs from user_references()
```

`Processor` gains:
```python
user_metadata: ConfluenceUserCollection

@abstractmethod
def _synchronize_users(self, users: set[tuple[str, str]]) -> ConfluenceUserCollection: ...
```

`_synchronize_content(tree, parent_to_children)` collects users from all descendants, calls `_synchronize_users`, stores `self.user_metadata`, then proceeds to `_synchronize_order` and `_synchronize_page`.

### `md2conf/publisher.py`

```python
@override
def _synchronize_users(self, users: set[tuple[str, str]]) -> ConfluenceUserCollection:
    user_metadata = ConfluenceUserCollection()
    for email, name in users:
        if email in user_metadata:
            continue
        remote_users = self.api.get_users(name)
        for remote_user in remote_users:
            if remote_user.email == email:
                user_metadata.add(email, remote_user.account_tuple)
                break
        else:
            LOGGER.warning("Cannot resolve mention for email %s (name: %s): user not found", email, name)
    return user_metadata
```

### `md2conf/api.py` — new `get_users` method

```python
def get_users(self, name: str) -> list[ConfluenceUser]: ...
```

- v2: `GET /wiki/rest/api/user/search?query={name}&limit=10` → returns list of matching users with `accountId` and `email`
- v1: `GET /rest/api/user/search?username={name}` → returns list; for each, fetch `/rest/api/user?username={username}` to get email

`ConfluenceUser` domain object:
```python
@dataclass
class ConfluenceUser:
    email: Optional[str]
    account_tuple: tuple[str, str]  # (ri_attr, ri_val) ready for CSF emission
```

For v2: `account_tuple = ("ri:account-id", accountId)`
For v1: `account_tuple = ("ri:username", username)`

### `md2conf/converter.py`

`ConfluenceStorageFormatConverter.__init__` gains `user_metadata: ConfluenceUserCollection`.

`_transform_anchor` (existing link handler) gains a branch:

```python
if url.startswith("mailto:"):
    mention = self._transform_mention(url)
    if mention is not None:
        return mention
```

New `_transform_mention`:
```python
def _transform_mention(self, url: str) -> Optional[ElementType]:
    email = url[len("mailto:"):]
    result = self.user_metadata.get(email)
    if result is None:
        return None
    attr_name, attr_val = result
    return AC_ELEM("link", {}, RI_ELEM("user", {RI_ATTR(attr_name.split(":")[1]): attr_val}))
```

## CLI

```
--user-mentions         Translate [Name](mailto:email) links to Confluence user mentions (default).
--no-user-mentions      Leave mailto: links as standard hyperlinks.
```

## Testing

### Unit tests (`tests/test_mentions.py`)

- `user_references("[Alice](mailto:alice@example.com) and [Bob](mailto:bob@example.com)")` → `{("alice@example.com", "Alice"), ("bob@example.com", "Bob")}`
- `user_references("no mentions here")` → `set()`
- `user_references` does not match bare `mailto:alice@example.com` (no link text)

### Conversion tests (`tests/test_conversion.py`)

- `[Name](mailto:known@example.com)` with populated `ConfluenceUserCollection` → `<ac:link><ri:user ri:account-id="557058:abc"/></ac:link>` (v2 form)
- `[Name](mailto:unknown@example.com)` with empty collection → standard `<a href="mailto:...">` preserved
- `--no-user-mentions`: mailto links always left as anchors

### API unit tests (`tests/test_api_mentions.py`)

- `get_users` v2: mock response with matching email → returns `ConfluenceUser` with correct `account_tuple`
- `get_users` v2: mock response with no email match → returns empty list
- `get_users` v1: mock search + profile responses → correct `("ri:username", "jsmith")` tuple
