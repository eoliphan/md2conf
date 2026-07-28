# Cross-Effort Page Overwrite: Mechanism, Options, Recommendation

**Status:** analysis only — no behavior changes in this pass.
**Date:** 2026-07-27
**Incident:** Effort A (Award Recommendation) published to space `GSSPACE` (Confluence Server/DC, v1 API) and silently overwrote page `341837572`, owned by Effort B (IAT Track 2 — GMM Financial & Award Interface Modernization), under an unrelated parent tree. Restored manually from version history.

> Reviewed adversarially against the source (Codex, `gpt-5.6-sol`). Findings from that pass are folded in; §2.2 and §7 exist because of it.

> **Separate live defect found during this analysis — see §7.1.** The re-parenting branch attempts `move_page(root_id, root_id)` (root page as its own parent) whenever the root Markdown carries an explicit page id. It is masked on Data Center by §2, but **not masked on Cloud/v2**. This is independent of the collision bug, is not a regression introduced by the proposed fix, and is arguably more urgent. It must be fixed *before* option B, which would unmask it on Data Center too.

---

## 1. Mechanism

### 1.1 The digest is scoped to the publish root, not the space

`md2conf/processor.py:285-292`:

```python
def _generate_hash(self, absolute_path: Path) -> str:
    relative_path = absolute_path.relative_to(self.root_dir)
    hash = hashlib.md5(relative_path.as_posix().encode("utf-8"))
    return "".join(f"{c:x}" for c in hash.digest())
```

The digest input is the path **relative to `self.root_dir`** — the publish root. Two efforts that each publish their own `00-inception/` as root both produce the relative path `source-inventory.md`, hence an identical digest.

Verified:

```
md5("source-inventory.md") = 881c765884af65946576c8b8e62fc475
```

which is exactly the hash embedded in the collided page's title. The digest carries no information about the space, the root page, or the effort.

### 1.2 The synthesized title becomes a space-global key

`md2conf/publisher.py:106-116`:

```python
if node.title is not None:
    title = node.title
else:
    digest = self._generate_hash(node.absolute_path)
    title = f"{node.absolute_path.stem} [{digest}]"

page = self.api.get_or_create_page(title, parent_id.page_id)
```

`node.title` originates from `Scanner` and is populated **only** from front matter (scanner.py:200-209) — an H1 heading does not supply it. So any document without an explicit front-matter `title:` is looked up by the synthesized string `stem [digest]`. Combined with §1.1, that string is identical for any same-named file published from any effort root in the space.

### 1.3 The lookup is space-wide; the parent contributes nothing on v1

`md2conf/api.py:1810-1826`:

```python
def get_or_create_page(self, title: str, parent_id: str) -> ConfluencePage:
    parent_page = self.get_page_properties(parent_id)
    page_id = self.page_exists(title, space_id=parent_page.spaceId)

    if page_id is not None:
        return self.get_page(page_id)
    else:
        return self.create_page(parent_id, title, "")
```

On v2, `parent_id` contributes only `parent_page.spaceId`.

**On v1 it contributes nothing at all.** `_page_exists_v1` (api.py:1712-1763) accepts `space_id` and then ignores it entirely:

```python
if space_key is None:
    space_key = self.site.space_key      # api.py:1734-1735
```

The v1 query is built from `self.site.space_key` — the session-configured space — regardless of what parent was passed. So on the exact deployment where the incident occurred, the target parent influenced the lookup in no way whatsoever. `parent_id` is used only if a *create* turns out to be necessary (api.py:1826).

Either way the conclusion holds and is stronger than first assumed: passing a different `-r` root provides **zero isolation** between efforts sharing a space.

The docstring justifies the space-wide search with "Pages in the same Confluence space must have a unique title" — true on Server/DC, but it makes the auto-generated title a shared global namespace across every effort in the space.

**Secondary defect in the same function:** `page_exists` returns `None` when `len(results) != 1` (api.py:1759, api.py:1803). Ambiguity is therefore treated as absence and triggers a **create attempt** with no ambiguity-specific error. The create does not necessarily succeed — server-side title uniqueness may reject it — so the practical outcome is either a duplicate or an opaque failure, not a clean overwrite.

### 1.4 Why exactly one file collided

All 17 of Effort A's documents lacked a front-matter `title:`, so all 17 looked themselves up by `stem [hash]`. Sixteen found nothing and created pages. One matched, because Effort B still had a page sitting at its placeholder title `source-inventory [881c765884af65946576c8b8e62fc475]` from an earlier publish that never completed. Effort B's other pages had already been renamed to real titles and were invisible to the lookup.

> **The landmine is any page left at a `stem [hash]` placeholder title.** That string is the lookup key, and it is identical for any same-named file published from any effort root in that space.

### 1.5 Stage two: the incident writes itself back into the source repo

This was not in the original trace and it is still live.

On the adoption path, `publisher.py:122` sets `update = True`, and lines 126-131 then call:

```python
self._update_markdown(node.absolute_path, page_id=page.id, space_key=space_key)
```

`_update_markdown` (publisher.py:271-294) inserts `<!-- confluence-page-id: {page_id} -->` into the source Markdown — at the top of the file, or immediately after the YAML front matter if present (publisher.py:281-291). **Effort A's `source-inventory.md` now contains Effort B's page id, `341837572`.**

Consequence: on Effort A's next publish, `node.page_id is not None` takes the branch at publisher.py:85-104, skipping the title lookup entirely and overwriting page `341837572` directly. The collision is now permanent and no longer depends on the placeholder title existing. Fixing the title/lookup logic alone does **not** stop the recurrence — see §5.

Note this write happens on the create path too, which is its normal intended function; only the adopted-foreign-page case is harmful.

### 1.6 What stage two does *not* do on Data Center

The branch at publisher.py:89-97 would normally also re-parent the page:

```python
if page.parentId is not None and page.parentId != parent_id.page_id:
    self.api.move_page(node.page_id, parent_id.page_id)
```

On paper this rips the page out of Effort B's tree. **On v1 it does not fire**, because `parentId` is `None` on the relevant GET paths — see §2. So the realistic worst case on DC is repeated content clobbering, not relocation. On Cloud/v2 the relocation would occur.

---

## 2. Prerequisite defect: `parentId` is not populated on the v1 sync paths

`map_page_properties_v1_to_domain` (api_mappers.py:133-138) and `map_page_v1_to_domain` (api_mappers.py:57ff) both derive `parentId` **solely** from the response's `ancestors` array:

```python
ancestors = typing.cast(list[JsonType], v1_response.get("ancestors", []))
parent_id = None
if ancestors:
    parent_id = str(typing.cast(Dict[str, JsonType], ancestors[-1])["id"])
```

But neither v1 fetch requests `ancestors`:

| Function | Site | `expand` |
|---|---|---|
| `_get_page_v1` | api.py:1141 | `body.storage,version,space` |
| `_get_page_properties_v1` | api.py:1170 | `version,space,history` |

So on the GET paths used by synchronization, `ancestors` is absent and **`parentId` is `None` on Data Center/Server**.

Stated precisely rather than absolutely: the mapper populates `parentId` whenever a response *does* carry `ancestors`, and v1 create responses pass through the same mapper (api.py:1574, api.py:1616). The claim is not that the field is unconditionally `None` in all code paths — it is that the two GET paths synchronization actually uses never request the data. That is sufficient for the consequences below.

1. **Pre-existing bug, independent of this incident.** The re-parenting logic at publisher.py:89-97 is dead on DC. md2conf silently never re-parents pages on Server/DC; a document moved between directories keeps its old Confluence parent forever, with no error and no log line. Track as its own defect.
2. **It gates the fix.** Any containment guard built on `parentId` would compare `None` against the target parent and reject *every* page on DC. Adding `ancestors` to both `expand` strings is a prerequisite. It costs no additional round trip — only a larger response body.

### 2.1 Expanding `ancestors` is necessary but not sufficient for subtree checks

Both v1 mappers reduce the whole chain to its last element (`ancestors[-1]`), and `ConfluencePageProperties` (api.py:255-259) has a `parentId` field but **no ancestor-chain field**. So expanding the request makes the data arrive and then discards it.

An immediate-parent check works with the expand change alone. A **root-descendant** check, or an error message quoting the offending page's actual ancestor chain, additionally requires carrying the chain into the domain model. Still no extra round trip on v1 — but it is a mapper and dataclass change, not a one-word fix.

| | Server/DC (v1) | Cloud (v2) |
|---|---|---|
| Data available in one response | Full `ancestors` chain | `parentId` (immediate only) |
| Immediate-parent check | Free after expand fix | Free today |
| Full-subtree check | Free after expand **+ model change** | One `GET` per level, or `GET /pages/{id}/ancestors` |
| CQL `ancestor = <id>` | Via `/rest/api/content/search` | Available |

### 2.2 The digest is not always 32 hex characters

`processor.py:292` formats each byte with `f"{c:x}"`, not `f"{c:02x}"`. Any byte below `0x10` renders as a single character, so the digest is shorter than 32.

The rate follows in closed form. Each of the 16 digest bytes is independently below `0x10` with probability `16/256`, so a full-length 32-character result requires all 16 to avoid that:

```
P(not 32 chars) = 1 - (1 - 16/256)^16 = 1 - (15/16)^16 ≈ 0.644
```

**About 64% of digests are shorter than 32 characters**, most commonly 30 or 31; the theoretical floor is 16. A 3,000-sample empirical check agrees (1,919 short, 64.0%). The incident's own digest happened to contain no low bytes, which is why it appeared as a clean 32-hex string and disguised the defect.

Two consequences:

- **The audit in §5 cannot search for a fixed 32-hex pattern** — it would miss roughly two thirds of the landmine pages. Use `\[[0-9a-f]{16,32}\]`, where 16 is the true theoretical floor; see §5 step 4.
- Unpadded concatenation is not injective in principle (bytes `0a bc` and `ab 0c` both render `abc`), adding a theoretical collision channel on top of md5. Empirically this is negligible: **zero collisions in 400,000 generated paths.** Do not present it as a contributing cause of the incident — it is a latent formatting bug worth fixing on its own merits, not a second collision vector in practice.

---

## 3. Options

### A. Refuse to adopt a page outside the expected location (fail closed)

Before returning a found page, verify its position in the hierarchy. If wrong, abort.

- **Correctness:** Directly addresses the failure. Independent of how titles are generated, so it also covers explicit-`title:` collisions and any future title scheme. Would have stopped this incident with **zero content writes** (see the caveat in §7 about *where* the check must sit).
- **Blast radius:** Bounded. The only behavior that changes is adoption of a mislocated page — which is the bug.
- **Backward compatibility:** Breaks trees that rely on space-wide adoption. Mitigated by a scoped override.
- **Server/DC vs Cloud:** Requires option B first on DC. Cost depends on the containment scope chosen — see §3.A.1.

#### 3.A.1 Containment scope: immediate-parent, per branch

The natural instinct is root-subtree containment ("must be a descendant of `-r`"). On review, that is too loose for the title-lookup branch and it misses:

- two efforts sharing one `-r`;
- nested project roots;
- a collision with another document elsewhere under the *same* root;
- a poisoned explicit page id that happens to point inside the allowed subtree.

The objection to immediate-parent equality was that it would break legitimate directory moves. **That objection does not hold.** After a document's first successful publish, `_update_markdown` records its page id (publisher.py:126-131), so every subsequent publish — including one after a directory move — takes the explicit-id branch at publisher.py:85, never the title branch. A title-only lookup that lands on a page under a *different* parent is therefore not a moved document; it is a collision.

Recommended branch-specific policy:

| Branch | Rule on violation |
|---|---|
| Title-only lookup (publisher.py:107-116) | Require **immediate-parent equality**. Hard error otherwise — never create-and-orphan, since the title is space-unique and the create would fail opaquely anyway |
| Explicit `page_id` (publisher.py:85-104) | Require **containment under the resolved root page** before re-parenting or writing. Stronger identity assertion, so a looser scope is defensible |

The explicit-id rule is what catches the already-poisoned `source-inventory.md` — page `341837572` sits outside Effort A's root, so the guard fires even though the file now names the id directly.

**Containment root is the resolved root, not the `-r` flag.** Publishing without `-r` is legal when the root Markdown carries its own page id (publisher.py:60-71, branch at 70-71). The rule must be expressed against `real_id` as resolved at publisher.py:67-71; a rule phrased purely in terms of `-r` has no root in that supported mode.

### B. Expand `ancestors` on the v1 fetches

Add `ancestors` to the `expand` parameter at api.py:1141 and api.py:1170.

- **Correctness:** Fixes §2.
- **Blast radius: not a no-op, and it carries a regression — see §7.1.** Populating a field that is currently always `None` brings the dead re-parenting branch (publisher.py:89-97) to life on DC. That must ship together with A so newly-live re-parenting is containment-checked before it moves anything.
- **Server/DC vs Cloud:** v1 only.

### C. Warn loudly on a containment violation, but continue

Same detection as A, log-only.

- **Correctness:** Detects but does not prevent. In an automated publish nobody reads the log until after the damage.
- **Blast radius / compatibility:** None / perfect.
- **Verdict:** Too weak as the primary control. Correct shape for A's override path.

### D. Salt the digest (space key + root page id + relative path)

- **Correctness:** Removes the cross-effort collision at its source.
- **Blast radius: large, and worse than the bug being fixed.** Changing the digest inputs re-keys **every** auto-titled page already published. On the next publish each such page's lookup misses, creates a new page, and silently orphans the old one. A team with 200 auto-titled pages gets 200 orphans and no error.
- **Backward compatibility:** Not deployable on its own.
- **Migration path** (what would make it safe):
  1. Compute the new salted digest; look up `stem [new]`.
  2. On miss, fall back to `stem [old]` (current algorithm — including its unpadded formatting, so the fallback must reproduce the *buggy* output, not the fixed one).
  3. If the old-key page is found **and** passes the A containment check, rename it in place and adopt. If it fails containment, abort — this is exactly the collided-page case, and the fallback must not become a new collision vector.
  4. On miss for both, create.
  5. Keep the fallback one release cycle, log every rename, then drop it.

  Step 3 is why this is **only safe after A ships**. Without containment checking, the old-key fallback reproduces the original bug throughout the migration window. Step 2 is why fixing §2.2's padding bug and shipping the salt are entangled: whichever lands first dictates what the compatibility path must emulate.
- **Server/DC vs Cloud:** Identical; purely local computation.
- **Verdict:** Worthwhile hardening, strictly after A, never standalone.

### E. Require explicit `confluence-page-id` or front-matter `title:` (`--strict-create`)

- **Correctness:** Eliminates the synthesized-title namespace for opted-in users. Attacks §1.2 rather than §1.3.
- **Blast radius:** As a default it breaks the zero-config workflow — publishing a directory of plain Markdown is md2conf's headline use case.
- **Verdict:** Ship opt-in. Good house rule for shared spaces like `GSSPACE`. Not a default.

### F. Scope the existence search by ancestor (CQL `ancestor = <id>`)

- **Correctness:** Similar protection, achieved by never *finding* the foreign page rather than finding and rejecting it.
- **Blast radius:** New query surface (`/rest/api/content/search`) with its own pagination, escaping (titles containing `"` or `~`), and permission semantics; two new paths across v1 and v2.
- **Downside vs A:** A **fails closed and says why** — the operator learns that page `341837572` in another tree holds the title. F returns nothing and attempts a create, which on Server/DC then collides with the space-unique title constraint and fails with an opaque 400. Worse diagnostics, more code.
- **Verdict:** Not recommended.

### G. Surface the risk in `--local` dry-run

`local.py:53-79` assigns the digest itself as the page id and makes **no network calls**. It is structurally incapable of detecting a cross-effort collision — the colliding page exists only on the server. Today's dry-run passed cleanly and the live run still clobbered another team's page; no offline change alters that.

What local mode *can* do is warn:

> `N of M documents have no front-matter title and will publish under auto-generated "stem [hash]" titles, which are space-global keys. Any existing page in this space at the same placeholder title will be adopted and overwritten.`

- **Correctness:** Signals the risk class, not the instance. Do not describe it as collision detection.
- **Verdict:** Cheap, honest, worth doing. Not a substitute for A.

---

## 4. Recommendation

Ship **B + A** together, with **C** as A's scoped override, **G** as an additive warning, **E** as an opt-in flag, and **D** deferred to a follow-up that depends on A.

1. **B — expand `ancestors` on both v1 fetches**, plus the mapper/model change from §2.1 if subtree (not just parent) checks are wanted. Prerequisite; also closes the DC re-parenting defect. Must land with A and with the §7.1 self-parent guard.
2. **A — containment guard, hard error by default**, applied per branch as in §3.A.1: immediate-parent equality on the title branch, root containment on the explicit-id branch. Both branches must be covered — the explicit-id branch is how the already-poisoned repo re-offends.
3. **Error message quality matters.** Name both page ids, both titles, and the offending page's location, so the operator can see whose page they nearly overwrote.
4. **C — a scoped override, not a blanket `--force`.** A global flag would disable the guard for every page in the run, including ones nobody reviewed. Prefer `--allow-adopt <page-id>` (repeatable), so an operator authorizes exactly the collision they inspected.
5. **Make `len(results) > 1` an unconditional error** (§1.3). It is a distinct latent defect in the same function and shipping the guard without it leaves ambiguity silently routed to a create attempt.
6. **Fix `f"{c:x}"` → `f"{c:02x}"`** (§2.2), coordinated with D's migration fallback.
7. **G — dry-run warning**; **E — `--strict-create`** opt-in; **D — salted digest** as a follow-up with the §3-D migration.

Rationale for A as the core: it is the only option that fails closed, is independent of the title scheme, covers both branches that can reach a foreign page, and would have caught this incident before the content write. Every other option either narrows the odds (D, E) or reports after the fact (C, G).

**Default fail mode: hard error.** In a shared space the cost of a false abort is one re-run with an explicit allow; the cost of a false adopt is another team restoring from version history.

---

## 5. Remediation runbook for the live incident

Independent of any code change. Do this before either effort publishes again.

1. **Strip the injected page id from Effort A's checkout.** `_update_markdown` wrote it into the source, so it is in git:

   ```bash
   rg -n "confluence-page-id: 341837572" path/to/effort-a/
   ```

   Remove that line and the adjacent `confluence-space-key` line from `00-inception/source-inventory.md`. Until this is removed, **every** Effort A publish overwrites Effort B's page directly, and no title-side fix prevents it.

2. **Check the rest of Effort A for other injected ids.** The same run wrote ids into all 17 documents; sixteen point at pages Effort A legitimately created, one is foreign. Verify each id's parent against Effort A's root page before trusting it:

   ```bash
   rg -n "confluence-page-id:" path/to/effort-a/00-inception/
   ```

3. **Confirm Effort B's page is fully restored** — title *and* body, plus labels and content properties. Version-history restore covers title and body; confirm labels separately.

4. **Audit the space for remaining landmines.** Any page still at a `stem [hash]` placeholder title is a live collision target.

   **Do not search for exactly 32 hex characters** — per §2.2, about two thirds of digests are shorter. Use the full theoretical range rather than a guessed lower bound, since a miss here reproduces exactly the failure this step exists to prevent:

   ```
   \[[0-9a-f]{16,32}\]$
   ```

   16 is the true floor (all 16 bytes below `0x10`), not a heuristic. The looser bound costs a few false positives in an audit that is reviewed by hand anyway.

   Rename such pages to their real titles, or delete abandoned ones. This is the highest-value manual step: it removes the precondition that made the collision possible.

5. **Interim mitigation** until the fix ships: give every document an explicit front-matter `title:`, or a verified `confluence-page-id:`. A document with a real title never enters the synthesized-key namespace.

---

## 6. Open questions for implementation

- Confirm no existing workflow depends on adopting pages outside the resolved root; §3.A.1 assumes none.
- Should the ancestor chain be added to `ConfluencePageProperties`, or should subtree checks walk via repeated `get_page_properties` on v2 and the chain on v1? The former unifies the logic at the cost of a domain-model change.
- Does B's newly-live re-parenting on DC need a one-time opt-in for users whose trees have silently drifted?

---

## 7. Failure modes the guard does not cover

These surfaced in adversarial review and should be resolved during implementation rather than discovered in production.

### 7.1 Self-parenting regression when `ancestors` is expanded

`_synchronize_structure` accepts a root document whose embedded page id equals `-r`, validates the two match, and sets `real_id` to it (publisher.py:63-71). It then calls `_synchronize_subtree(root, real_id, ...)` (publisher.py:76) — so for the root node, `node.page_id == parent_id.page_id`.

Inside, the guard at publisher.py:90 compares the root page's *actual* Confluence parent against `real_id` (itself). They differ, so it calls:

```python
move_page(root_id, root_id)
```

attempting to make the root page its own parent.

**Reachability — verified by tracing.** Two of the three branches at publisher.py:60-71 set `real_id` to the root's own page id: 63-67 (`-r` and the embedded id both present and equal) and 70-71 (`-r` absent, embedded id present). In both, the root node enters `_synchronize_subtree` with `node.page_id == parent_id.page_id`, takes the `node.page_id is not None` branch at line 85, and reaches the comparison at line 90 with nothing intervening. The third branch (68-69, `-r` given and no embedded id) leaves `root.page_id` as `None` and safely falls through to the title-lookup path instead.

The guard `page.parentId is not None` means it fires only when the root page itself has a parent page — the normal case, since a page sitting under a space homepage has that homepage as its parent. A root page at the very top of a space would be spared.

**What is verified vs. inferred.** The code path is definitively reachable and definitively issues `move_page(root_id, root_id)`. What Confluence *does* with a self-parenting request is **not** verified here — it needs a live instance. Both plausible outcomes are bad:

- The server rejects it with a 4xx. `_move_page_v2` calls `response.raise_for_status()` (api.py:1400ff), so this surfaces as a **hard publish failure** for any Cloud user whose root Markdown carries an explicit page id.
- The server accepts it, and the root page is self-parented or silently detached.

State it as "attempts, with unverified server behavior" until someone reproduces it against a live Cloud instance. That reproduction should be the first task in the fix.

Masking on Data Center is incidental — `parentId` is `None` there (§2), so the comparison never passes. **Shipping B removes that accident**, which is why the fix must land first. The remedy is small: skip the re-parent check when `node.page_id == parent_id.page_id`. This is a prerequisite for B, not a follow-up.

### 7.2 The guard cannot fail before a write where it currently sits

`get_or_create_page` (api.py:1810) returns a `ConfluencePage` with **no indicator of whether it was adopted or created**. A containment check placed on its return value cannot distinguish the two, and in the create case the page already exists on the server by then.

Achieving genuine "zero writes before validation" requires splitting the call — lookup, then validate, then create — or returning an adopted/created flag. Worth deciding before implementation, since the fail-closed claim in §3.A depends on it.

### 7.3 Time-of-check/time-of-use window

Structure synchronization runs before content synchronization and ordering (processor.py:135, processor.py:153). A page validated during the structure pass can be moved by another user before `_update_page` writes it. The window is small and this does not undermine the guard, but the guard is not an atomic reservation and should not be described as one.

### 7.4 Test coverage is absent

No tests currently cover v1 ancestor mapping, title-based adoption, containment, the self-parent case, or the digest padding. Existing targeted tests pass (8 passed), which is not evidence any of these paths work. Each item in §4 needs a test written with it — particularly §7.1, which is a live Cloud bug that no current test detects.
