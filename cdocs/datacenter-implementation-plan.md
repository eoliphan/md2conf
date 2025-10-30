# Implementation Plan: Confluence Data Center Support for md2conf

**Status:** In Progress
**Branch:** feature/datacenter
**GitHub Issues:** #110, #93
**Estimated Timeline:** 17.5 days (3.5 weeks)

---

## Overview

Add REST API v1 support to md2conf to enable compatibility with Confluence Data Center, which doesn't support the v2 API used by current versions (0.3.0+).

---

## Phase 0: Setup (Est. 0.5 days)

- [x] **Task 0.1:** Create feature branch and push to remote
  - Create and switch to `feature/datacenter` branch from `master`
  - Push branch to remote repository (branch created locally, will push when authenticated)
  - **Delegate to:** General-purpose agent
  - **Status:** ✅ Complete

- [x] **Task 0.2:** Document GitHub issues for reference
  - Save issue #110 content to `cdocs/github-issue-110.md`
  - Save issue #93 content to `cdocs/github-issue-93.md`
  - **Delegate to:** General-purpose agent
  - **Status:** ✅ Complete

---

## Phase 1: Infrastructure & Configuration (Est. 2 days)

- [x] **Task 1.1:** Add deployment type configuration
  - Update `md2conf/environment.py`:
    - Add `deployment_type` field to `ConfluenceConnectionProperties`
    - Support values: `"cloud"` (default), `"datacenter"`, `"server"`
    - Add `CONFLUENCE_DEPLOYMENT_TYPE` environment variable support
    - Add validation logic
  - **Delegate to:** General-purpose agent
  - **Status:** ✅ Complete - All tests pass, type checking passes

- [x] **Task 1.2:** Add deployment type CLI argument
  - Update `md2conf/__main__.py`:
    - Add `--deployment-type` CLI argument with choices
    - Pass deployment type to connection properties
    - Update help text
  - **Delegate to:** General-purpose agent
  - **Status:** ✅ Complete - Help output verified, all tests pass

- [x] **Task 1.3:** Add API version detection
  - Update `md2conf/api.py`:
    - Add `api_version: ConfluenceVersion` field to `ConfluenceSession`
    - Create `_detect_api_version()` method:
      - If deployment_type is "datacenter" or "server" → VERSION_1
      - If deployment_type is "cloud" → VERSION_2
      - If auto (None): defaults to VERSION_2 for backward compatibility
    - Update `__init__` to set `self.api_version` based on detection
  - **Delegate to:** General-purpose agent
  - **Status:** ✅ Complete - All tests pass, logging added, routing logic verified

- [x] **Task 1.4:** Create data structure mappers module
  - Create new file: `md2conf/api_mappers.py`
  - Implement mapper functions for v1 ↔ domain objects:
    - `map_page_v1_to_domain()` - Convert v1 page response to ConfluencePage
    - `map_page_properties_v1_to_domain()` - Convert v1 to ConfluencePageProperties
    - `map_create_page_to_v1()` - Convert CreatePageRequest to v1 format
    - `map_update_page_to_v1()` - Convert UpdatePageRequest to v1 format
    - `map_space_v1_to_id()` - Extract space ID from v1 response
    - `map_attachment_v1_to_domain()` - Convert v1 attachment response
    - `map_property_v1_to_domain()` - Convert v1 content property response
    - `map_label_v1_to_domain()` - Convert v1 label response
  - **Delegate to:** General-purpose agent
  - **Status:** ✅ Complete - 8 mapper skeletons created with detailed TODO guidance

---

## Phase 2: Core Space Operations (Est. 2 days)

- [x] **Task 2.1:** Implement `space_key_to_id_v1()`
  - Update `md2conf/api.py`:
    - Add method with endpoint: `GET /rest/api/space/{spaceKey}`
    - Extract `id` from response
    - Cache in `_space_key_to_id`
  - **Delegate to:** General-purpose agent
  - **Status:** ✅ Complete - v1 method implemented, routing added, mapper implemented, all tests pass

- [ ] **Task 2.2:** Implement `space_id_to_key_v1()`
  - Update `md2conf/api.py`:
    - Handle limitation: v1 has no direct ID lookup
    - Use cached reverse mapping
    - Add fallback with clear error messages if mapping unavailable
    - Document limitation in code comments
  - **Delegate to:** General-purpose agent

- [x] **Task 2.3:** Update space methods with version routing
  - Update `md2conf/api.py`:
    - Modify `space_key_to_id()` to route based on `self.api_version`
    - Modify `space_id_to_key()` to route based on `self.api_version`
    - Update initialization auto-discovery to try v1 if v2 fails
  - **Delegate to:** General-purpose agent
  - **Status:** ✅ Complete - Updated __init__ to use self.api_version for domain/base_path inference and API URL discovery. Data Center/Server deployments now use classic REST API URL directly instead of trying scoped API URL.

---

## Phase 3: Page Operations (Est. 4 days)

- [x] **Task 3.1:** Implement `get_page_v1()`
  - Update `md2conf/api.py`:
    - Endpoint: `GET /rest/api/content/{pageId}?expand=body.storage,version,space`
    - Map v1 response to ConfluencePage using mapper
    - Handle nested structure (space.id, body.storage.value, etc.)
    - Extract spaceId from nested space object
  - **Delegate to:** General-purpose agent
  - **Status:** ✅ Complete - Implemented in api.py:971-985, uses map_page_v1_to_domain

- [x] **Task 3.2:** Implement `get_page_properties_v1()`
  - Update `md2conf/api.py`:
    - Endpoint: `GET /rest/api/content/{pageId}?expand=version,space`
    - Map to ConfluencePageProperties
    - Extract parentId from ancestors array (last element)
  - **Delegate to:** General-purpose agent
  - **Status:** ✅ Complete - Implemented in api.py:1000-1014, uses map_page_properties_v1_to_domain

- [x] **Task 3.3:** Implement `get_page_properties_by_title_v1()`
  - Update `md2conf/api.py`:
    - Endpoint: `GET /rest/api/content?title={title}&spaceKey={spaceKey}&type=page`
    - Critical: Convert spaceId to spaceKey before calling
    - Map response to ConfluencePageProperties
  - **Delegate to:** General-purpose agent
  - **Status:** ✅ Complete - Implemented in api.py:938-982, handles spaceId to spaceKey conversion

- [x] **Task 3.4:** Implement `create_page_v1()`
  - Update `md2conf/api.py`:
    - Endpoint: `POST /rest/api/content/`
    - Critical: Convert spaceId to spaceKey
    - Build v1 request body with space.key and ancestors array
    - Map response back to ConfluencePage
  - **Delegate to:** General-purpose agent
  - **Status:** ✅ Complete - Implemented in api.py:1115-1161, uses map_create_page_to_v1

- [x] **Task 3.5:** Implement `update_page_v1()`
  - Update `md2conf/api.py`:
    - Endpoint: `PUT /rest/api/content/{pageId}`
    - Build v1 request similar to create
    - Include version number for optimistic locking
    - Handle space reference conversion
  - **Delegate to:** General-purpose agent
  - **Status:** ✅ Complete - Implemented in api.py:1087-1135, uses map_update_page_to_v1

- [x] **Task 3.6:** Implement `delete_page_v1()`
  - Update `md2conf/api.py`:
    - Trash: `DELETE /rest/api/content/{pageId}?status=current`
    - Research and implement v1 purge mechanism
  - **Delegate to:** General-purpose agent
  - **Status:** ✅ Complete - Implemented in api.py:1258-1281, supports purge parameter

- [x] **Task 3.7:** Implement `page_exists_v1()`
  - Update `md2conf/api.py`:
    - Reuse `get_page_properties_by_title_v1()` logic
    - Handle 404 as "does not exist"
  - **Delegate to:** General-purpose agent
  - **Status:** ✅ Complete - Implemented in api.py:1309-1364, uses v1 content search

- [x] **Task 3.8:** Add version routing to all page methods
  - Update `md2conf/api.py`:
    - Update each page method to check `self.api_version`
    - Route to v1 or v2 implementation appropriately
    - Methods: `get_page()`, `get_page_properties()`, `get_page_properties_by_title()`, `create_page()`, `update_page()`, `delete_page()`, `page_exists()`
  - **Delegate to:** General-purpose agent
  - **Status:** ✅ Complete - All page methods now have version routing

---

## Phase 4: Attachment Operations (Est. 1 day)

- [x] **Task 4.1:** Implement `get_attachment_by_name_v1()`
  - Update `md2conf/api.py`:
    - Endpoint: `GET /rest/api/content/{pageId}/child/attachment?filename={filename}`
    - Map v1 response to ConfluenceAttachment
    - Handle field name differences in v1 structure
  - **Delegate to:** General-purpose agent
  - **Status:** ✅ Complete - Implemented in api.py:775-790, uses map_attachment_v1_to_domain

- [x] **Task 4.2:** Verify existing attachment operations
  - Update `md2conf/api.py`:
    - Confirm `upload_attachment()` works with Data Center (already uses v1)
    - Confirm `_update_attachment()` works (already uses v1)
    - Add version routing if needed
  - **Delegate to:** General-purpose agent
  - **Status:** ✅ Complete - Verified upload_attachment (line 851) and _update_attachment (line 936) already use v1 API

---

## Phase 5: Label Operations (Est. 1 day)

- [x] **Task 5.1:** Implement `get_labels_v1()` with pagination
  - Update `md2conf/api.py`:
    - Endpoint: `GET /rest/api/content/{pageId}/label`
    - Use v1 pagination helper (to be created)
    - Map to ConfluenceIdentifiedLabel
  - **Delegate to:** General-purpose agent
  - **Status:** ✅ Complete - Implemented in api.py:1448-1480 with custom v1 pagination (start/limit pattern)

- [x] **Task 5.2:** Verify existing label write operations
  - Update `md2conf/api.py`:
    - Confirm `add_labels()` works (already uses v1)
    - Confirm `remove_labels()` works (already uses v1)
    - Ensure proper version routing
  - **Delegate to:** General-purpose agent
  - **Status:** ✅ Complete - Verified add_labels (line 1469) and remove_labels (line 1483) already use v1 API

---

## Phase 6: Content Properties (Est. 2 days)

- [ ] **Task 6.1:** Implement `get_content_properties_for_page_v1()`
  - Update `md2conf/api.py`:
    - Endpoint: `GET /rest/api/content/{pageId}/property`
    - Use v1 pagination helper
    - Map to ConfluenceIdentifiedContentProperty
  - **Delegate to:** General-purpose agent

- [ ] **Task 6.2:** Implement `add_content_property_to_page_v1()`
  - Update `md2conf/api.py`:
    - Endpoint: `POST /rest/api/content/{pageId}/property`
    - Map domain object to v1 request format
    - Map response to domain object
  - **Delegate to:** General-purpose agent

- [ ] **Task 6.3:** Implement `remove_content_property_from_page_v1()`
  - Update `md2conf/api.py`:
    - Endpoint: `DELETE /rest/api/content/{pageId}/property/{key}`
    - Critical: v1 uses property `key` not `property_id`
    - Track key-to-id mapping
  - **Delegate to:** General-purpose agent

- [ ] **Task 6.4:** Implement `update_content_property_for_page_v1()`
  - Update `md2conf/api.py`:
    - Endpoint: `PUT /rest/api/content/{pageId}/property/{key}`
    - Use property key not ID
    - Handle version number correctly
  - **Delegate to:** General-purpose agent

- [ ] **Task 6.5:** Handle property key vs ID abstraction
  - Update `md2conf/api.py`:
    - Add key-to-id mapping for content properties
    - Update property data structures if needed
    - Add version routing to all property methods
    - Document limitation in code comments
  - **Delegate to:** General-purpose agent

---

## Phase 7: Pagination Helper (Est. 1 day)

- [ ] **Task 7.1:** Create `_fetch_v1()` pagination method
  - Update `md2conf/api.py`:
    - Implement v1 pagination pattern with start/limit parameters
    - Handle `_links.next` in responses
    - Return flattened list of results
  - **Delegate to:** General-purpose agent

- [ ] **Task 7.2:** Create version-aware `_fetch()` wrapper
  - Update `md2conf/api.py`:
    - Check `self.api_version`
    - Route to `_fetch_v1()` or existing `_fetch()` (v2)
  - **Delegate to:** General-purpose agent

- [ ] **Task 7.3:** Update all paginated calls
  - Update `md2conf/api.py`:
    - Update `get_labels()` to use version-aware fetch
    - Update `get_content_properties_for_page()` to use version-aware fetch
  - **Delegate to:** General-purpose agent

---

## Phase 8: Testing Infrastructure (Est. 2 days)

- [ ] **Task 8.1:** Create unit tests for mappers
  - Create new file: `tests/test_api_mappers.py`
  - Test all v1-to-domain mappers with sample data
  - Test all domain-to-v1 mappers
  - Test edge cases (null fields, missing data)
  - **Delegate to:** General-purpose agent

- [ ] **Task 8.2:** Create Data Center integration test structure
  - Create file: `integration_tests/test_api_datacenter.py`
  - Copy structure from `test_api.py`
  - Set `CONFLUENCE_DEPLOYMENT_TYPE=datacenter`
  - Add placeholder tests for all CRUD operations
  - Note: Requires access to Confluence Data Center test instance
  - **Delegate to:** General-purpose agent

- [ ] **Task 8.3:** Add regression tests for Cloud
  - Update `integration_tests/test_api.py`:
    - Ensure existing v2 tests still pass
    - Add explicit v2 version checks
    - Test auto-detection logic
  - **Delegate to:** General-purpose agent

- [ ] **Task 8.4:** Create version detection tests
  - Create new file: `tests/test_version_detection.py`
  - Test detection with different deployment types
  - Test fallback mechanism (v2 → v1)
  - Test explicit configuration
  - **Delegate to:** General-purpose agent

---

## Phase 9: Documentation (Est. 1 day)

- [ ] **Task 9.1:** Update README.md with Data Center support
  - Update `README.md`:
    - Add "Confluence Data Center Support" section
    - Document `CONFLUENCE_DEPLOYMENT_TYPE` environment variable
    - Document `--deployment-type` CLI flag
    - Add compatibility matrix (Cloud → v2, Data Center → v1)
    - Document known limitations
    - Add example usage for Data Center
  - **Delegate to:** General-purpose agent

- [ ] **Task 9.2:** Update CLAUDE.md with architecture changes
  - Update `CLAUDE.md`:
    - Document new architecture (version detection, routing)
    - Add notes about api_mappers.py module
    - Document testing requirements for both deployment types
  - **Delegate to:** General-purpose agent

- [ ] **Task 9.3:** Create migration guide
  - Create new file: `cdocs/datacenter-migration.md`
  - Guide for users migrating from Cloud to Data Center
  - Document configuration changes needed
  - List known differences and workarounds
  - **Delegate to:** General-purpose agent

- [ ] **Task 9.4:** Update CONTRIBUTING.md
  - Update `CONTRIBUTING.md`:
    - Add notes about testing with Data Center
    - Document how to run tests for both versions
    - Add Data Center setup instructions
  - **Delegate to:** General-purpose agent

---

## Phase 10: Code Quality & Finalization (Est. 1 day)

- [ ] **Task 10.1:** Run all static checks
  - Execute `./check.sh` (ruff, mypy, etc.)
  - Fix any type errors or linting issues
  - Ensure all code follows project conventions
  - **Delegate to:** General-purpose agent

- [ ] **Task 10.2:** Run all tests
  - Run unit tests: `python -m unittest discover -s tests`
  - Run integration tests (Cloud): `python -m unittest discover -s integration_tests`
  - Fix any test failures
  - Note: Data Center integration tests require test instance
  - **Delegate to:** General-purpose agent

- [ ] **Task 10.3:** Manual testing checklist
  - Test single file sync with Data Center (if available)
  - Test directory sync with Data Center (if available)
  - Test page creation, updates, deletions
  - Test attachments, labels, properties
  - Verify error handling and logging
  - **Delegate to:** General-purpose agent

- [ ] **Task 10.4:** Prepare for pull request
  - Review all changes
  - Ensure commit messages are descriptive
  - Update this plan document with final status
  - Prepare PR description referencing issues #110 and #93
  - **Delegate to:** General-purpose agent

---

## Key Implementation Decisions

### Critical Decisions Made:

1. **Space ID to Key Lookup Strategy:**
   - **Decision:** Maintain strict cache with clear error messages if not available (Option C)
   - **Rationale:** Prevents expensive API calls; forces proper initialization

2. **Content Property ID vs Key:**
   - **Decision:** Store both in property structures (Option B)
   - **Rationale:** Allows seamless operation with both API versions

3. **Auto-Detection:**
   - **Decision:** Require explicit configuration via deployment_type (Option B)
   - **Rationale:** Provides predictability and avoids unnecessary API probing

4. **Backward Compatibility:**
   - **Decision:** Default to Cloud/v2 behavior (no breaking changes)
   - **Rationale:** Existing users unaffected; Data Center is explicit opt-in

### Risk Mitigation Strategies:

1. **No Data Center access:** Use mock responses for unit tests, document integration test requirements
2. **Undocumented API differences:** Add extensive logging, implement graceful degradation
3. **Breaking changes:** Feature flag approach, comprehensive testing, staged rollout
4. **Performance:** Aggressive space mapping cache, minimize API calls

---

## Success Criteria

- [ ] All 17 v2 endpoints have functional v1 equivalents
- [ ] Version detection works automatically or via config
- [ ] Data structure mapping handles all known differences
- [ ] Space ID/Key translation works bidirectionally
- [ ] All unit tests pass
- [ ] Integration tests structure created (execution requires Data Center instance)
- [ ] No regression in Cloud/v2 functionality
- [ ] Documentation complete and clear
- [ ] Code passes all static checks (ruff, mypy)
- [ ] Feature can be safely enabled via configuration

---

## Timeline Summary

| Phase | Duration | Status |
|-------|----------|--------|
| Phase 0: Setup | 0.5 days | ⏳ Not Started |
| Phase 1: Infrastructure | 2 days | ⏳ Not Started |
| Phase 2: Space Operations | 2 days | ⏳ Not Started |
| Phase 3: Page Operations | 4 days | ⏳ Not Started |
| Phase 4: Attachments | 1 day | ⏳ Not Started |
| Phase 5: Labels | 1 day | ⏳ Not Started |
| Phase 6: Content Properties | 2 days | ⏳ Not Started |
| Phase 7: Pagination | 1 day | ⏳ Not Started |
| Phase 8: Testing | 2 days | ⏳ Not Started |
| Phase 9: Documentation | 1 day | ⏳ Not Started |
| Phase 10: Finalization | 1 day | ⏳ Not Started |
| **TOTAL** | **17.5 days** | |

---

## Notes

- This plan assumes single developer working sequentially
- Data Center instance access is not available for full integration testing
- Unit tests and mocked integration tests will provide confidence
- Real Data Center testing should be done by users with access
- Version 0.2.7 remains available as fallback for legacy support

---

**Last Updated:** 2025-10-28
**Document Version:** 1.0
