# Changelog

## Unreleased

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
- A non-root document whose resolved Confluence page is the same page as its parent document's resolved page is
  now an error, even when the two documents do not declare the same `confluence-page-id` in front-matter — for
  example, two documents whose titles both resolve to one existing Confluence page. Previously the second
  document would silently overwrite the first.
- Moving a page under a page that is one of its own descendants is now refused, because it would create a cycle
  in the page tree. Previously nothing prevented this from being attempted.

### Known limitations

- Each project must publish under its own `-r` root page. The containment guard cannot distinguish two projects
  that share one `-r` anchor when neither root document declares an explicit page id — give each project its
  own root page.
