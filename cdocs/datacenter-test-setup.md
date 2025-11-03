# Data Center Integration Test Setup

This guide explains how to run the Data Center integration tests against your Confluence instance.

## Prerequisites

You have already set up the following environment variables:
- `CONFLUENCE_DOMAIN`
- `CONFLUENCE_PATH`
- `CONFLUENCE_USER_NAME`
- `CONFLUENCE_API_KEY`
- `CONFLUENCE_SPACE_KEY`

## Test Root Page Setup

A dedicated root page has been created for organizing test pages:
- **Page ID**: `293077930`
- **Purpose**: All test pages will be created as children of this page
- **Benefit**: Keeps test pages organized and isolated from production content

## Running the Tests

### Step 1: Environment Variables (Optional)

The tests use these defaults:
- `CONFLUENCE_DEPLOYMENT_TYPE='datacenter'` ✅ (already defaulted)
- `CONFLUENCE_TEST_ROOT_PAGE_ID='293077930'` ✅ (already defaulted)

**You only need to set these if you want to override the defaults.**

For example, to use a different test root page:
```bash
export CONFLUENCE_TEST_ROOT_PAGE_ID='999999999'
```

### Step 2: Run the Integration Tests

```bash
# Run all Data Center integration tests
python -m unittest integration_tests.test_api_datacenter -v
```

### Step 3: Expected Output

If successful, you should see:

```
test_version_detection ... ok
test_space_operations ... ok
test_page_creation_and_deletion ... ok
test_page_update ... ok
test_attachment_operations ... ok
test_label_operations ... ok
test_content_property_operations ... ok

----------------------------------------------------------------------
Ran 7 tests in X.XXXs

OK
```

## What Each Test Does

### 1. test_version_detection
- **Purpose**: Verifies Data Center configuration forces v1 API usage
- **Creates**: Nothing
- **Cleanup**: N/A

### 2. test_space_operations
- **Purpose**: Tests space key ↔ space ID conversion
- **Creates**: Nothing (uses existing space)
- **Cleanup**: N/A

### 3. test_page_creation_and_deletion
- **Purpose**: Tests basic page lifecycle
- **Creates**: Page titled "Data Center API Test Page" under root page 293077930
- **Cleanup**: Deletes the test page

### 4. test_page_update
- **Purpose**: Tests page modification
- **Creates**: Page titled "Data Center Update Test" under root page 293077930
- **Updates**: Changes title and content
- **Cleanup**: Deletes the test page

### 5. test_attachment_operations
- **Purpose**: Tests file upload and retrieval
- **Creates**:
  - Page titled "Data Center Attachment Test" under root page 293077930
  - Temporary .txt file attachment
- **Cleanup**: Deletes temp file and test page

### 6. test_label_operations
- **Purpose**: Tests adding/removing labels
- **Creates**:
  - Page titled "Data Center Label Test" under root page 293077930
  - Labels: "datacenter-test", "integration-test"
- **Cleanup**: Removes one label, then deletes test page

### 7. test_content_property_operations
- **Purpose**: Tests content property CRUD operations
- **Creates**:
  - Page titled "Data Center Property Test" under root page 293077930
  - Content property "test-property" with complex value
- **Updates**: Modifies property value
- **Cleanup**: Removes property, then deletes test page

## Cleanup Behavior

All tests include proper cleanup:
- ✅ Test pages are deleted after each test
- ✅ Temporary files are removed
- ✅ Labels and properties are cleaned up

**Note**: If a test fails before cleanup, orphaned pages may remain under page 293077930. You can manually delete them if needed.

## Troubleshooting

### Issue: Tests are skipped with "Data Center integration tests require..."

**Solution**: The standard Confluence environment variables are missing. Ensure these are set:
```bash
export CONFLUENCE_DOMAIN='your-datacenter.example.com'
export CONFLUENCE_PATH='/wiki/'
export CONFLUENCE_USER_NAME='your-username'
export CONFLUENCE_API_KEY='your-api-key'
export CONFLUENCE_SPACE_KEY='YOURSPACE'
```

Note: `CONFLUENCE_DEPLOYMENT_TYPE` defaults to 'datacenter', so you don't need to set it.

### Issue: Tests fail with connection errors

**Solution**: Verify your existing environment variables are correct:
```bash
echo $CONFLUENCE_DOMAIN
echo $CONFLUENCE_PATH
echo $CONFLUENCE_USER_NAME
# Don't echo API_KEY for security
```

### Issue: Tests create pages at space root instead of under test page

**Unlikely**: The test root page ID defaults to '293077930'. This should only happen if:
1. You explicitly set `CONFLUENCE_TEST_ROOT_PAGE_ID=''` (empty string)
2. You're using a very old version of the test file

**Solution**: Ensure you're using the latest test file, or explicitly set:
```bash
export CONFLUENCE_TEST_ROOT_PAGE_ID='293077930'
```

### Issue: Tests fail with "Page not found" or permission errors

**Possible causes**:
1. Test root page 293077930 doesn't exist or was deleted
2. Test user doesn't have create/edit/delete permissions

**Solution**:
- Verify page exists in Confluence
- Check user permissions in the space

### Issue: Orphaned test pages remain after test failures

**Solution**: Manually delete pages under test root page 293077930:
1. Navigate to page 293077930 in Confluence
2. View child pages
3. Delete any pages with titles like "Data Center * Test"

## Quick Test Command

Since the defaults are already configured, you can simply run:

```bash
python -m unittest integration_tests.test_api_datacenter -v
```

**That's it!** No environment variable setup needed (unless you want to override defaults).

## Verifying Test Root Page Structure

After running tests, you can check your test root page (293077930) to verify:
- ✅ No orphaned pages (all tests cleaned up successfully)
- ✅ Page tree remains clean
- ✅ No unexpected attachments or properties

Navigate to: `https://[your-domain]/wiki/pages/viewpage.action?pageId=293077930`

## Next Steps

Once integration tests pass:
1. ✅ Data Center implementation is verified working
2. ✅ All CRUD operations confirmed functional
3. ✅ Ready to use md2conf with your Data Center instance
4. ✅ Ready to merge feature/datacenter branch

## Running Individual Tests

To run a specific test:

```bash
# Just test page creation
python -m unittest integration_tests.test_api_datacenter.TestDataCenterAPI.test_page_creation_and_deletion -v

# Just test labels
python -m unittest integration_tests.test_api_datacenter.TestDataCenterAPI.test_label_operations -v
```

## Test Execution Time

Expected total runtime: **5-15 seconds** depending on network latency and Data Center performance.
