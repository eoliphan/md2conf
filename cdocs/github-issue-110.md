# GitHub Issue #110: Does md2conf work with Data Center instead of Cloud?

**Repository:** hunyadi/md2conf
**Status:** Closed (Completed)
**Author:** Jerakin
**Created:** May 21, 2025
**Last Updated:** May 26, 2025
**URL:** https://github.com/hunyadi/md2conf/issues/110

---

## Initial Problem

The user attempted to use md2conf with a Confluence Data Center instance and encountered authentication errors:

> "401 Client Error: for url: https://my-url/api/v2/pages/2998052547?body-format=storage"

The core question: Does md2conf support Confluence Server/Data Center, or only Cloud?

---

## Discussion Summary

### Key Finding: API Version Incompatibility

The Confluence REST API exists in two incompatible versions:
- **v1 API:** Supported by Data Center only (`/rest/api`)
- **v2 API:** Supported by Cloud only (`/api/v2`)

The current md2conf implementation primarily uses v2 endpoints, making it incompatible with Data Center deployments.

### Root Cause Analysis

md2conf version 0.3.0+ switched to using Confluence REST API v2 as the primary API for most operations. This was done to support Cloud deployments, which only support v2 endpoints. However, Data Center installations only support v1 endpoints, creating an incompatibility.

The 401 error occurs because:
1. md2conf attempts to call v2 endpoints (e.g., `/api/v2/pages/{id}`)
2. Data Center doesn't recognize v2 API paths
3. The authentication fails or the endpoint returns 401 Unauthorized

### Solutions Discussed

1. **Version 0.2.7 Workaround (Recommended)**
   - The last release using exclusively v1 API calls works with Data Center
   - User confirmed this version functions properly
   - Command: `pip install markdown-to-confluence==0.2.7`
   - May need `--webui-links` flag for proper cross-page link generation

2. **Revert Specific Commits**
   - One user reported reverting commit `47d7336389b6c4552f17a4a2b37aab8902f2ba2c` restored v1 API functionality
   - Required minimal additional changes
   - Not recommended for production use

3. **Optional Flag Consideration**
   - Some users needed to pass `--webui-links` for proper cross-page link generation with Data Center

### Maintainer Perspective

The project maintainers (hunyadi) stated:
- Confluence Cloud is the primary use case and focus
- Without access to a Data Center environment for testing, they cannot guarantee compatibility
- Data Center support is considered "out of scope" for current development
- Future Data Center support would require:
  1. Identifying all VERSION_2 references in ConfluenceSession class
  2. Implementing equivalent v1 API implementations
  3. Creating abstraction logic to route calls based on deployment type
  4. Access to Data Center testing infrastructure

---

## Technical Requirements for Data Center Support

To add Data Center compatibility to newer versions (0.3.0+), the following would be required:

### 1. API Endpoint Mapping
All v2 endpoints need v1 equivalents:
- **Pages:** `/api/v2/pages/{id}` → `/rest/api/content/{id}`
- **Spaces:** `/api/v2/spaces` → `/rest/api/space`
- **Attachments:** `/api/v2/pages/{id}/attachments` → `/rest/api/content/{id}/child/attachment`
- **Labels:** `/api/v2/pages/{id}/labels` → `/rest/api/content/{id}/label`
- **Properties:** `/api/v2/pages/{id}/properties` → `/rest/api/content/{id}/property`

### 2. Data Structure Differences
Handle incompatibilities between v1 and v2:
- **Space references:** v2 uses `spaceId`, v1 uses `spaceKey`
- **Query parameters:** v2 uses `space-id`, v1 uses `spaceKey`
- **Response structures:** Field names and nesting differ
- **Parent references:** v2 uses `parentId`, v1 uses `ancestors` array
- **Content properties:** v2 uses `property_id`, v1 uses `key`

### 3. Version Detection
Implement mechanism to detect deployment type:
- Configuration-based (environment variable or CLI flag)
- Auto-detection (try v2, fall back to v1)
- Route API calls to appropriate version

### 4. Testing Infrastructure
- Access to Confluence Data Center test instance
- Integration tests for both v1 and v2 APIs
- Regression tests to ensure Cloud compatibility maintained

---

## Related Issues

- **Issue #93:** Discusses REST API v1 vs v2 support in detail
- Both issues highlight the fundamental incompatibility between Cloud and Data Center API versions

---

## Current Status

- Issue is **closed** as Data Center support is out of scope
- Version 0.2.7 remains available for Data Center users
- No timeline for adding Data Center support to newer versions
- Community contributions would be considered if someone with Data Center access implements the feature

---

## Recommendations for Data Center Users

1. **Use version 0.2.7:**
   ```bash
   pip install markdown-to-confluence==0.2.7
   ```

2. **Add `--webui-links` flag if needed:**
   ```bash
   md2conf --webui-links path/to/docs/
   ```

3. **Monitor for future Data Center support:**
   - Watch this issue and #93 for updates
   - Consider contributing if you have Data Center access

4. **Test thoroughly:**
   - Verify all features work in your Data Center environment
   - Report any issues specific to 0.2.7

---

**Note:** This document was created as part of the feature/datacenter implementation effort to add Data Center support to md2conf versions 0.3.0+.
