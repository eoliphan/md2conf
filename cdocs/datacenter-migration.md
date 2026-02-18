# Migrating from Confluence Cloud to Data Center/Server

This guide helps users migrate from Confluence Cloud (REST API v2) to Confluence Data Center or Server (REST API v1) when using md2conf.

## Overview

md2conf now supports both Confluence Cloud and Confluence Data Center/Server deployments:

- **Confluence Cloud**: Uses REST API v2 (default)
- **Confluence Data Center**: Uses REST API v1 (requires configuration)
- **Confluence Server**: Uses REST API v1 (requires configuration)

## Quick Migration Checklist

- [ ] Update domain from `*.atlassian.net` to your Data Center domain
- [ ] Update base path (typically from `/wiki/` to your Data Center path)
- [ ] Set `CONFLUENCE_DEPLOYMENT_TYPE=datacenter` or use `--deployment-type datacenter`
- [ ] Verify authentication credentials (username/API key or token)
- [ ] Test with a single page before bulk synchronization
- [ ] Review known limitations (see below)

## Configuration Changes

### Environment Variables

**Before (Cloud):**
```bash
export CONFLUENCE_DOMAIN='example.atlassian.net'
export CONFLUENCE_PATH='/wiki/'
export CONFLUENCE_USER_NAME='user@example.com'
export CONFLUENCE_API_KEY='cloud-api-key'
export CONFLUENCE_SPACE_KEY='SPACE'
```

**After (Data Center):**
```bash
export CONFLUENCE_DOMAIN='confluence.company.com'
export CONFLUENCE_PATH='/wiki/'  # or your Data Center path
export CONFLUENCE_USER_NAME='username'
export CONFLUENCE_API_KEY='datacenter-api-key'
export CONFLUENCE_SPACE_KEY='SPACE'
export CONFLUENCE_DEPLOYMENT_TYPE='datacenter'  # NEW - required for Data Center
```

### Command-Line Usage

**Before (Cloud):**
```bash
python -m md2conf -d example.atlassian.net -s SPACE path/to/file.md
```

**After (Data Center):**
```bash
python -m md2conf \
  --deployment-type datacenter \
  -d confluence.company.com \
  -s SPACE \
  path/to/file.md
```

## Default Behavior

If you **don't** set `CONFLUENCE_DEPLOYMENT_TYPE`, md2conf defaults to REST API v2 (Confluence Cloud behavior). There is no domain-based auto-detection.

For Data Center or Server instances, always **explicitly set** `deployment_type` to avoid using the wrong API version.

## API Version Differences

When migrating from Cloud (v2) to Data Center (v1), be aware of these differences:

### Space References

- **Cloud (v2)**: Uses space IDs in API calls
- **Data Center (v1)**: Uses space keys in API calls
- **Impact**: md2conf handles this automatically via internal space key ↔ ID lookups

### Page Structure

- **Cloud (v2)**: Flat structure with `body.storage.value`
- **Data Center (v1)**: Nested structure with `body.storage.value`
- **Impact**: Transparent - md2conf's mapper layer handles conversion

### Pagination

- **Cloud (v2)**: Cursor-based pagination with `_links.next`
- **Data Center (v1)**: Offset pagination with `start` and `limit` parameters
- **Impact**: Transparent - md2conf's `_fetch()` method routes appropriately

### Content Properties

- **Cloud (v2)**: Operations use property IDs directly
- **Data Center (v1)**: Update/delete require looking up property key first
- **Impact**: Transparent but slower - md2conf performs automatic key lookups

## Known Limitations

When using Data Center/Server (v1 API):

1. **Performance**: Some operations (property updates, label removal) require extra API calls to look up keys/IDs
2. **Feature Parity**: Advanced v2-only features are not available in v1
3. **Error Messages**: v1 API error responses may differ in format from v2

## Troubleshooting

### Issue: "Cannot connect to Confluence"

**Solution**: Verify your Data Center domain and base path are correct. Test connectivity:
```bash
curl -u username:api-key https://confluence.company.com/wiki/rest/api/space
```

### Issue: "Page not found" or "Space not found"

**Possible causes**:
- Auto-detection is using the wrong API version
- Space key is incorrect for Data Center instance

**Solution**: Explicitly set `CONFLUENCE_DEPLOYMENT_TYPE=datacenter` and verify space key.

### Issue: Slow performance compared to Cloud

**Explanation**: Data Center v1 API requires additional lookups for some operations (property updates, label removal).

**Solution**: This is expected behavior. The v1 API requires extra GET requests to map between IDs and keys.

### Issue: Authentication failures

**Possible causes**:
- Data Center uses different authentication than Cloud
- API token format differs

**Solution**:
1. Verify your username (may be different from email on Data Center)
2. Generate a new API token from your Data Center instance
3. Check if your Data Center requires specific authentication methods

## Testing Your Migration

We recommend testing with a single page before migrating all content:

```bash
# Step 1: Test with a single file
export CONFLUENCE_DEPLOYMENT_TYPE='datacenter'
python -m md2conf path/to/test-file.md

# Step 2: Verify the page was created/updated correctly in Data Center

# Step 3: Migrate remaining content
python -m md2conf path/to/all/files/
```

## Getting Help

If you encounter issues during migration:

1. Check the [GitHub Issues](https://github.com/hunyadi/md2conf/issues) for similar problems
2. Enable debug logging: `export LOG_LEVEL=DEBUG`
3. Run with verbose output to see API calls being made
4. Create a GitHub issue with:
   - Your deployment type configuration
   - Error messages (redact sensitive information)
   - md2conf version: `python -m md2conf --version`

## Additional Resources

- [Confluence REST API v1 Documentation](https://developer.atlassian.com/cloud/confluence/rest/v1/)
- [Confluence REST API v2 Documentation](https://developer.atlassian.com/cloud/confluence/rest/v2/)
- [md2conf GitHub Repository](https://github.com/hunyadi/md2conf)
