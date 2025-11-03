# First Test Run - Incremental Approach

This guide walks you through running the Data Center integration tests incrementally, starting with the simplest test first.

## Recommended Test Order

Run tests in this order to catch issues early:

### 1. Version Detection Test (Simplest - Start Here!)

**What it does:** Just verifies the API version is v1 (Data Center)
**Creates:** Nothing
**Risk:** None - read-only check

```bash
python -m unittest integration_tests.test_api_datacenter.TestDataCenterAPI.test_version_detection -v
```

**Expected output:**
```
test_version_detection (integration_tests.test_api_datacenter.TestDataCenterAPI.test_version_detection)
Verify that deployment_type=datacenter forces v1 API usage. ... ok

----------------------------------------------------------------------
Ran 1 test in 0.123s

OK
```

**What success means:**
- ✅ Connection to Data Center works
- ✅ Authentication is valid
- ✅ Deployment type is correctly configured as 'datacenter'
- ✅ API routing is working

**If this fails:** Check your basic Confluence environment variables

---

### 2. Space Operations Test (Read-Only)

**What it does:** Tests space key ↔ space ID conversion
**Creates:** Nothing
**Risk:** Low - just reads existing space info

```bash
python -m unittest integration_tests.test_api_datacenter.TestDataCenterAPI.test_space_operations -v
```

**Expected output:**
```
test_space_operations (integration_tests.test_api_datacenter.TestDataCenterAPI.test_space_operations)
Test space lookup operations with v1 API. ... ok

----------------------------------------------------------------------
Ran 1 test in 0.456s

OK
```

**What success means:**
- ✅ Space exists and is accessible
- ✅ v1 API space operations work correctly
- ✅ Space key to ID mapping works

---

### 3. Page Creation Test (First Write Operation)

**What it does:** Creates a page under 293077930, then deletes it
**Creates:** 1 temporary page
**Risk:** Low - creates and immediately deletes

```bash
python -m unittest integration_tests.test_api_datacenter.TestDataCenterAPI.test_page_creation_and_deletion -v
```

**Expected output:**
```
test_page_creation_and_deletion (integration_tests.test_api_datacenter.TestDataCenterAPI.test_page_creation_and_deletion)
Test creating and deleting a page using v1 API. ... ok

----------------------------------------------------------------------
Ran 1 test in 1.234s

OK
```

**What success means:**
- ✅ User has create page permission
- ✅ Test root page (293077930) exists and accepts child pages
- ✅ Page creation via v1 API works
- ✅ Page deletion works
- ✅ Cleanup is successful

**Manual verification:**
Check page 293077930 - should have NO child pages after test

---

### 4. Page Update Test

**What it does:** Creates page, updates it, deletes it
**Creates:** 1 temporary page
**Risk:** Low - tests update operations

```bash
python -m unittest integration_tests.test_api_datacenter.TestDataCenterAPI.test_page_update -v
```

---

### 5. Attachment Operations Test

**What it does:** Creates page, uploads file, retrieves it, deletes all
**Creates:** 1 temporary page + 1 attachment
**Risk:** Low - tests file operations

```bash
python -m unittest integration_tests.test_api_datacenter.TestDataCenterAPI.test_attachment_operations -v
```

---

### 6. Label Operations Test

**What it does:** Creates page, adds/removes labels, deletes page
**Creates:** 1 temporary page + labels
**Risk:** Low - tests label CRUD

```bash
python -m unittest integration_tests.test_api_datacenter.TestDataCenterAPI.test_label_operations -v
```

---

### 7. Content Property Operations Test (Most Complex)

**What it does:** Creates page, adds/updates/removes properties, deletes page
**Creates:** 1 temporary page + content property
**Risk:** Low - tests property CRUD

```bash
python -m unittest integration_tests.test_api_datacenter.TestDataCenterAPI.test_content_property_operations -v
```

---

## Quick Troubleshooting

### Test 1 Fails (Version Detection)

**Common causes:**
1. Environment variables not set
2. Wrong domain/path
3. Invalid credentials
4. Network/firewall issues

**Quick check:**
```bash
echo $CONFLUENCE_DOMAIN
echo $CONFLUENCE_PATH
echo $CONFLUENCE_USER_NAME
echo $CONFLUENCE_SPACE_KEY
```

### Test 2 Fails (Space Operations)

**Common causes:**
1. Space key is wrong
2. User doesn't have access to space
3. Space doesn't exist

**Quick check:**
Try accessing your space in browser:
`https://[domain]/wiki/spaces/[SPACE_KEY]`

### Test 3 Fails (Page Creation)

**Common causes:**
1. User doesn't have create page permission
2. Test root page 293077930 doesn't exist
3. Test root page doesn't allow child pages

**Quick check:**
1. Navigate to: `https://[domain]/wiki/pages/viewpage.action?pageId=293077930`
2. Verify page exists
3. Try manually creating a child page

### Cleanup Check After Each Test

After each test that creates pages, verify cleanup worked:

```bash
# Navigate to test root page
# Should see NO child pages if cleanup worked
```

Browser URL: `https://[domain]/wiki/pages/viewpage.action?pageId=293077930`

---

## After All Individual Tests Pass

Once all 7 tests pass individually, run the full suite:

```bash
python -m unittest integration_tests.test_api_datacenter -v
```

**Expected output:**
```
test_version_detection ... ok
test_space_operations ... ok
test_page_creation_and_deletion ... ok
test_page_update ... ok
test_attachment_operations ... ok
test_label_operations ... ok
test_content_property_operations ... ok

----------------------------------------------------------------------
Ran 7 tests in 8.234s

OK
```

---

## What To Report If Tests Fail

If you encounter failures, please report:

1. **Which test failed:**
   ```
   test_page_creation_and_deletion ... FAIL
   ```

2. **Error message:**
   ```
   AssertionError: ...
   HTTPError: 403 Forbidden
   ```

3. **Environment info (safe parts):**
   ```bash
   echo $CONFLUENCE_DOMAIN    # OK to share
   echo $CONFLUENCE_PATH      # OK to share
   echo $CONFLUENCE_SPACE_KEY # OK to share
   # DON'T share: API_KEY, USER_NAME
   ```

4. **Browser test:**
   - Can you access page 293077930 in browser?
   - Can you manually create a child page under it?

---

## Success Criteria

✅ All 7 tests pass
✅ No orphaned pages under 293077930
✅ No errors in output
✅ Test root page structure is clean

Once all tests pass, the Data Center implementation is **verified working** on your instance! 🎉
