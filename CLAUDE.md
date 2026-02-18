# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**md2conf** is a Python package that converts Markdown files to Confluence wiki pages. It parses Markdown, converts it to Confluence Storage Format (XHTML), and synchronizes content via the Confluence REST API.

## Build and Test Commands

### Setup Development Environment
```bash
python -m venv ".venv"
source .venv/bin/activate
python -m pip install ".[formulas,dev]"
```

### Running Tests
```bash
# Unit tests only
python -m unittest discover -s tests

# Integration tests (requires Confluence environment variables)
python -m unittest discover -s integration_tests
```

### Static Code Checks
```bash
# Run all checks (ruff, mypy, help test, doc generation)
./check.sh  # or check.bat on Windows

# Individual checks
python -m ruff check
python -m ruff format --check
python -m mypy md2conf
python -m mypy tests
python -m mypy integration_tests
```

### Running the Application
```bash
# Single file (Cloud)
python3 -m md2conf path/to/file.md

# Directory (recursive)
python3 -m md2conf path/to/directory/

# With options (Cloud)
python3 -m md2conf -d example.atlassian.net -s SPACE path/to/file.md

# Data Center/Server
python3 -m md2conf -d confluence.company.com --deployment-type datacenter -s SPACE path/to/file.md

# Local mode (generates .csf files without API calls)
python3 -m md2conf --local path/to/file.md
```

## Architecture

### Core Processing Pipeline

1. **Scanner** (`scanner.py`) - Parses Markdown files, extracts front-matter (page ID, space key, title, tags, properties) and Mermaid diagram configurations.

2. **Processor** (`processor.py`) - Abstract base class that:
   - Indexes Markdown files into a DocumentNode tree structure
   - Maintains parent-child relationships based on `index.md`/`README.md` files
   - Builds a cross-reference index for resolving relative links
   - Delegates to concrete implementations for synchronization

3. **Publisher** (`publisher.py`) - Concrete Processor that:
   - Synchronizes Markdown files with Confluence pages via REST API
   - Creates/updates pages and maintains hierarchy
   - Handles page metadata (titles, labels, content properties)

4. **Converter** (`converter.py`, 1924 lines) - The largest and most complex module:
   - Converts Markdown to Confluence Storage Format (XHTML with Confluence-specific tags)
   - Handles images, attachments, diagrams (draw.io, Mermaid), LaTeX formulas
   - Processes relative links, code blocks, tables, admonitions, emojis
   - Manages attachment uploads and URL resolution
   - Implements `ConfluenceDocument` class with `create()` factory method

5. **API** (`api.py`, 1762 lines) - Confluence REST API client:
   - Supports both REST API v1 (Data Center/Server) and v2 (Cloud)
   - Handles authentication (Basic with username/API key, or Bearer with token)
   - Implements `ConfluenceSession` for page/space/attachment operations
   - Uses `requests` library with custom SSL handling (truststore for Python 3.10+)
   - Routes API calls based on detected or configured deployment type

6. **API Mappers** (`api_mappers.py`) - Data structure translation layer:
   - Converts v1 API responses to internal domain objects
   - Converts domain objects to v1 API request formats
   - Handles structural differences between v1 and v2 APIs
   - Maps nested v1 structures (space.id, body.storage.value) to flat domain objects

### Confluence API Version Support

The architecture supports both Confluence Cloud (v2 API) and Data Center/Server (v1 API):

**Version Detection (`ConfluenceSession._detect_api_version`)**:
- **Data Center/Server**: Explicit `deployment_type='datacenter'` or `'server'` → uses v1
- **Cloud**: Explicit `deployment_type='cloud'` → uses v2
- **Default**: When deployment_type is None → v2 (for backward compatibility; no domain-based auto-detection is performed)

**API Routing Pattern**:
- Each public API method (e.g., `get_page`, `create_page`) checks `self.api_version`
- Routes to version-specific private methods (e.g., `_get_page_v1`, `_get_page_v2`)
- v1 methods use `api_mappers` module to convert between API and domain formats
- v2 methods work directly with domain objects (compatible structure)

**Key Differences**:
- **Space references**: v1 uses space keys in URLs, v2 uses space IDs
- **Page structure**: v1 nests content deeply (`body.storage.value`), v2 is flatter
- **Pagination**: v1 uses start/limit, v2 uses cursor-based (`_links.next`)
- **Property operations**: v1 requires key lookups (GET before UPDATE/DELETE), v2 uses property IDs directly
- **Parent relationships**: v1 uses ancestors array, v2 uses parentId field

### Key Module Responsibilities

- **api_mappers.py** - Bidirectional data structure mappers for Confluence REST API v1
  - Functions: `map_page_v1_to_domain`, `map_create_page_to_v1`, `map_update_page_to_v1`
  - Functions: `map_space_v1_to_id`, `map_attachment_v1_to_domain`
  - Functions: `map_label_v1_to_domain`, `map_property_v1_to_domain`
- **markdown.py** - Wraps Python-Markdown library with extensions (PyMdown Extensions for emoji, etc.)
- **csf.py** - Confluence Storage Format utilities (XML parsing, element manipulation, constants)
- **matcher.py** - File system traversal with `.mdignore` support (fnmatch patterns)
- **collection.py** - `ConfluencePageCollection` manages path-to-page-metadata mapping
- **drawio.py** - Extracts/renders draw.io diagrams (PNG/SVG)
- **mermaid.py** - Interfaces with mermaid-cli (mmdc) for diagram rendering
- **latex.py** - Renders LaTeX formulas using Matplotlib
- **xml.py** - XML comparison and manipulation utilities
- **toc.py** - Generates table of contents from headings
- **emoticon.py** - Converts emoji short names to Confluence emoticon format
- **text.py** - Text manipulation utilities
- **uri.py** - URL parsing and UUID generation
- **local.py** - LocalConverter for offline .csf generation
- **domain.py** - Core data types (ConfluenceDocumentOptions, ConfluencePageID)
- **environment.py** - Configuration and error types (ConfluenceConnectionProperties, custom exceptions)
- **metadata.py** - Site and page metadata structures
- **macros.py** - Macro expansion facility; shorthand syntax (`<!-- macro:name: params -->`) for common Confluence macros (jira, status, emoticon) that expand to CSF comments
- **skill.py** - Claude Code skill generation; `generate_skill()` writes a `.md` skill file from the package's own documentation

### Page Association

Each Markdown file associates with a Confluence page via:
```markdown
<!-- confluence-page-id: 20250001023 -->
```

Or uses front-matter:
```yaml
---
page_id: "20250001023"
space_key: "SPACE"
title: "My Page Title"
tags: ["markdown", "wiki"]
synchronized: true
---
```

### Directory Hierarchy Mapping

- `index.md` or `README.md` in a directory becomes the parent page for that directory
- All other `.md` files in the directory become child pages
- Nested directories follow the same pattern, creating a tree structure in Confluence
- The top-level directory must have `index.md` or `README.md` mapping to the root page (specified with `-r` option)
- Use `--keep-hierarchy` to maintain directory structure or `--flatten-hierarchy` to flatten directories without index files

## Configuration

### Environment Variables

**Cloud (v2 API):**
```bash
CONFLUENCE_DOMAIN='example.atlassian.net'
CONFLUENCE_PATH='/wiki/'
CONFLUENCE_USER_NAME='user@example.com'
CONFLUENCE_API_KEY='0123456789abcdef'
CONFLUENCE_SPACE_KEY='SPACE'
CONFLUENCE_API_URL='https://api.atlassian.com/ex/confluence/CLOUD_ID/'  # For scoped tokens
```

**Data Center/Server (v1 API):**
```bash
CONFLUENCE_DOMAIN='confluence.company.com'
CONFLUENCE_DEPLOYMENT_TYPE='datacenter'  # or 'server'
CONFLUENCE_PATH='/wiki/'                 # Defaults to '/wiki/' if not set; adjust for your instance
CONFLUENCE_API_KEY='your-personal-access-token'
CONFLUENCE_SPACE_KEY='SPACE'
# NOTE: CONFLUENCE_USER_NAME is optional.
#   If set: uses Basic auth (username + API key).
#   If omitted: uses Bearer token auth (recommended for Data Center PATs).
```

### Permissions for Scoped API Tokens
Required scopes: read/write/delete for attachment, content, label, page; read for content-details, space.

## Python Requirements

- Minimum Python version: 3.9
- Type hints enforced with mypy (strict mode)
- Code formatting with ruff (line length: 160)
- Dependencies: lxml, markdown, pymdown-extensions, PyYAML, requests, json_strong_typing
- Optional: matplotlib (for LaTeX formulas)

## External Dependencies

- **draw.io** (optional) - For rendering `.drawio` and `.drawio.xml` files
- **mermaid-cli** (optional) - For rendering Mermaid diagrams: `npm install -g @mermaid-js/mermaid-cli`
- **Marketplace apps** (optional) - For displaying diagrams/formulas directly in Confluence without pre-rendering

## Docker

Entry point: `python3 -m md2conf`
Working directory: `/data`
Mount current directory: `docker run --rm -v $(pwd):/data leventehunyadi/md2conf:latest ./`

## Testing

- **tests/** - Unit tests (no external dependencies)
  - `test_api_mappers.py` - Tests for v1 API mapper functions
  - `test_version_detection.py` - Tests for deployment type detection logic
- **integration_tests/** - Integration tests requiring live Confluence instance with environment variables set
  - `test_api.py` - Cloud/v2 API integration tests
  - `test_api_datacenter.py` - Data Center/v1 API integration tests (requires `CONFLUENCE_DEPLOYMENT_TYPE=datacenter`)
- Test files use standard `unittest` framework
- **sample/** directory contains example Markdown files for testing

### Testing Both Deployment Types

When adding new features or fixing bugs, ensure tests cover both Cloud (v2) and Data Center (v1):

**Unit Tests**:
- Add mapper tests in `test_api_mappers.py` if v1 API data structures are involved
- Test version detection logic in `test_version_detection.py` for configuration changes

**Integration Tests**:
- Update `test_api.py` for Cloud/v2 features
- Update `test_api_datacenter.py` for Data Center/v1 features
- Ensure both test suites cover the same CRUD operations when possible

**Running Data Center Integration Tests**:
```bash
# Set environment variables for Data Center instance
export CONFLUENCE_DEPLOYMENT_TYPE='datacenter'
export CONFLUENCE_DOMAIN='confluence.company.com'
export CONFLUENCE_PATH='/wiki/'
export CONFLUENCE_USER_NAME='username'
export CONFLUENCE_API_KEY='api-key'
export CONFLUENCE_SPACE_KEY='TEST'

# Run Data Center integration tests
python -m unittest integration_tests.test_api_datacenter
```

## Code Style

- Use `@override` decorator from `extra.py` for overridden methods
- Type hints required for all public functions and methods
- Dataclasses preferred for structured data (see `domain.py`, `metadata.py`)
- Use `LOGGER = logging.getLogger(__name__)` pattern in each module
- Error handling: custom exceptions in `environment.py` (ArgumentError, PageError, ConfluenceError)