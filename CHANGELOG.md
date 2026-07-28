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
- Each project must publish under its own `-r` root page. The containment guard cannot distinguish two projects
  that share one `-r` anchor when neither root document declares an explicit page id — give each project its
  own root page.

### Changed — breaking

- `ConfluenceSession.get_or_create_page` has been removed. It adopted pages space-wide with no ownership check.
  Look the page up with `page_exists`, validate the result, then call `create_page` if absent.
- `ConfluenceSession.page_exists` now raises `PageCollisionError` when more than one page matches, instead of
  returning `None`.
- Two Markdown documents declaring the same `confluence-page-id` is now an error. Previously the second silently
  overwrote the first. Remove the duplicated comment from one of the documents.
- Adopting a page outside the tree being published now fails. Use `--allow-adopt <page-id>` to authorize a
  specific page.
