# GitHub Issue #93: Confluence API v1 Support

**Repository:** hunyadi/md2conf
**Status:** Closed (Completed)
**Author:** [@fragpit](https://github.com/fragpit)
**Created:** March 26, 2025
**Last Updated:** April 2, 2025
**URL:** https://github.com/hunyadi/md2conf/issues/93

---

## Description

The issue reporter noted that md2conf versions 3.0 and later (presumably 0.3.0+) lack support for Confluence API v1, which affects compatibility with Confluence Server and Data Center deployments. The reporter questioned whether this limitation was intentional or a misunderstanding of a related issue.

---

## Key Points Raised

### The Problem

- md2conf versions ≥0.3.0 do not support Confluence REST API v1
- This makes the tool incompatible with:
  - Confluence Server installations
  - Confluence Data Center installations
- Both Server and Data Center only support API v1, not v2

### Question to Maintainers

The issue author asked whether the lack of v1 support was:
1. An intentional decision, or
2. A misunderstanding about API compatibility

---

## Maintainer Response (@hunyadi)

### Confirmation of Intent

The maintainer confirmed this was **intentional**, stating:

> "we have been primarily interested in Confluence Cloud, which is what we use and what we can test."

### Rationale for Decision

The maintainer explained several reasons for focusing on API v2:

1. **Primary Use Case:**
   - The development team uses Confluence Cloud
   - Cloud is their testing environment
   - Cloud only supports API v2

2. **API Evolution:**
   - Atlassian/Confluence is discontinuing several API v1 endpoints
   - The platform is moving toward v2 as the standard
   - Supporting deprecated APIs is not sustainable

3. **Backwards Incompatibility:**
   - Significant backwards-incompatible changes exist between v1 and v2
   - Specific differences mentioned:
     - Parent-child page relationships handled differently
     - Space references: v1 uses `spaceKey`, v2 uses `spaceId`
   - Maintaining dual support would introduce unnecessary complexity

4. **Testing Limitations:**
   - No access to Server/Data Center environments for testing
   - Cannot guarantee v1 functionality without proper testing infrastructure

---

## Solution Provided

### For API v1 Users

Users requiring API v1 support should use **version 0.2.7** (or earlier):

```bash
pip install markdown-to-confluence==0.2.7
```

**Why version 0.2.7?**
- Last release using exclusively Confluence REST API v1 endpoints
- Stable and safe for environments limited to API v1
- Available on PyPI: https://pypi.org/project/markdown-to-confluence/0.2.7/
- Fully functional for Server/Data Center installations

### Version History

- **Versions < 0.3.0:** Use API v1 exclusively
- **Version 0.3.0+:** Use API v2 primarily, with some v1 fallback for operations not yet available in v2
- **Recommended for Data Center:** Version 0.2.7

---

## Technical Details

### API v1 vs v2 Differences

From maintainer's comments and related discussions:

1. **URL Structure:**
   - v1: `/rest/api/content/{id}`
   - v2: `/api/v2/pages/{id}`

2. **Space References:**
   - v1: Uses string `spaceKey` (e.g., "SPACE")
   - v2: Uses numeric/ID `spaceId` (e.g., "123456")

3. **Parent-Child Relationships:**
   - v1: Uses `ancestors` array
   - v2: Uses `parentId` field

4. **Query Parameters:**
   - v1: Uses `spaceKey`, `expand` notation
   - v2: Uses `space-id`, `body-format` parameters

5. **Response Structures:**
   - Field names differ between versions
   - Nesting levels vary
   - Some fields only exist in one version

### Why Not Both?

The maintainer explained that maintaining compatibility with both APIs would require:
- Duplicate implementations for every API call
- Translation layer between different data models
- Extensive testing on both platforms
- Ongoing maintenance as APIs evolve
- Complexity that outweighs benefits for their use case

---

## Resolution

### Issue Closed

The issue was closed as **completed** with the following understanding:

1. **No plans to restore API v1 support** in versions 0.3.0+
2. **Version 0.2.7 remains available** for v1 users
3. **Focus will remain on Cloud/v2** for future development
4. **No active support** for Server/Data Center in newer versions

### Community Contributions

While not explicitly stated, the issue implies that:
- Community contributions for v1 support might be considered
- Would require someone with Data Center access to implement and test
- Would need to follow existing architecture patterns
- Maintainers cannot actively support without testing environment

---

## Recommendations

### For Data Center/Server Users:

1. **Use version 0.2.7:**
   ```bash
   pip install markdown-to-confluence==0.2.7
   ```

2. **Pin the version** in requirements.txt:
   ```
   markdown-to-confluence==0.2.7
   ```

3. **Do not upgrade** to 0.3.0+ unless you migrate to Confluence Cloud

4. **Monitor for updates:**
   - Watch issues #93 and #110 for any future changes
   - Check if community adds Data Center support

### For Cloud Users:

1. **Use latest version** (0.3.0+)
2. **Benefit from v2 API features:**
   - Better performance
   - Modern API patterns
   - Active development and support
3. **No action needed** - default installation works

### For Those Considering Adding v1 Support:

If you want to contribute v1 support to newer versions:

1. **Fork the repository**
2. **Identify all v2 API calls** in the codebase
3. **Implement v1 equivalents** for each operation
4. **Create abstraction layer** for version routing
5. **Add comprehensive tests** (requires Data Center access)
6. **Submit pull request** with clear documentation

---

## Related Issues

- **Issue #110:** User report of Data Center incompatibility with specific error messages
- Both issues document the same fundamental problem: v1 vs v2 API incompatibility

---

## Additional Context

### Atlassian's API Deprecation

Per maintainer comments, Atlassian is deprecating various v1 endpoints:
- Cloud stopped supporting some v1 endpoints as of March 31, 2025
- v2 is the future direction for Confluence Cloud
- Server/Data Center timelines for v2 support unknown

### Python Version Requirements

- **Version 0.2.7:** Python 3.9+ (needs verification)
- **Version 0.3.0+:** Python 3.9+ minimum

---

**Note:** This document was created as part of the feature/datacenter implementation effort to add Data Center support to md2conf versions 0.3.0+. The goal is to bridge the gap by implementing v1 API support alongside existing v2 support.
