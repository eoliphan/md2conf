"""
Generate a Claude Code skill for md2conf.

Copyright 2022-2025, Levente Hunyadi

:see: https://github.com/hunyadi/md2conf
"""

import logging
import os
from pathlib import Path

from . import __version__

LOGGER = logging.getLogger(__name__)

_SKILL_NAME = "md2conf"

_SKILL_FRONTMATTER = f"""\
---
name: {_SKILL_NAME}
description: >-
  This skill should be used when the user asks to "publish markdown to Confluence",
  "convert markdown to Confluence", "sync docs to wiki", "upload to Confluence",
  or mentions md2conf, markdown-to-confluence, or Confluence Storage Format.
version: "{__version__}"
allowed-tools: Bash,Read,Write,Glob,Grep
user-invocable: false
---
"""

_SKILL_BODY = """\
# md2conf - Publish Markdown to Confluence

Convert Markdown files to Confluence wiki pages. Parses Markdown, converts to
Confluence Storage Format (XHTML), and synchronizes content via the Confluence REST API.

## Quick Start

```bash
# Single file
python3 -m md2conf path/to/file.md

# Directory (recursive)
python3 -m md2conf path/to/directory/

# Local mode (generates .csf files without API calls)
python3 -m md2conf --local path/to/file.md
```

## Page Association

Each Markdown file associates with a Confluence page via an HTML comment:

```markdown
<!-- confluence-page-id: 20250001023 -->
```

Or via YAML front-matter:

```yaml
---
page_id: "20250001023"
space_key: "SPACE"
title: "My Page Title"
tags: ["markdown", "wiki"]
---
```

## Directory Hierarchy

- `index.md` or `README.md` in a directory becomes the parent page
- All other `.md` files become child pages
- Nested directories follow the same pattern
- Use `--keep-hierarchy` to maintain directory structure

## Environment Variables

### Cloud (v2 API)

```bash
CONFLUENCE_DOMAIN='example.atlassian.net'
CONFLUENCE_PATH='/wiki/'
CONFLUENCE_USER_NAME='user@example.com'
CONFLUENCE_API_KEY='your-api-key'
CONFLUENCE_SPACE_KEY='SPACE'
```

### Data Center / Server (v1 API)

```bash
CONFLUENCE_DOMAIN='confluence.company.com'
CONFLUENCE_DEPLOYMENT_TYPE='datacenter'
CONFLUENCE_API_KEY='your-personal-access-token'
CONFLUENCE_SPACE_KEY='SPACE'
```

## Key Options

| Option | Description |
|---|---|
| `-d DOMAIN` | Confluence organization domain |
| `-s SPACE` | Confluence space key |
| `-u USERNAME` | Confluence user name |
| `-a API_KEY` | Confluence API key |
| `-r ROOT_PAGE` | Root page ID for new pages |
| `--local` | Generate .csf files locally (no API) |
| `--keep-hierarchy` | Maintain source directory structure |
| `--render-mermaid` / `--no-render-mermaid` | Pre-render Mermaid diagrams |
| `--render-drawio` / `--no-render-drawio` | Pre-render draw.io diagrams |
| `--render-latex` / `--no-render-latex` | Pre-render LaTeX formulas |
| `--heading-anchors` | Add anchors at section headings |
| `--ignore-invalid-url` | Warn instead of error on bad URLs |
| `--deployment-type` | `cloud`, `datacenter`, or `server` |

## Supported Features

- **Text formatting**: bold, italic, monospace, underline, strikethrough
- **Code blocks**: syntax-highlighted fenced code blocks
- **Tables**: standard Markdown tables
- **Images**: local and remote, with alignment options
- **Diagrams**: Mermaid, draw.io (rendered or as attachments)
- **LaTeX**: inline and block math formulas
- **Admonitions**: info, tip, note, warning panels
- **Alerts**: GitHub-style `[!NOTE]`, `[!TIP]`, etc.
- **Collapsed sections**: `<details>` elements
- **Emojis**: `:emoji_name:` shortcodes
- **Cross-references**: relative links between pages
- **Table of contents**: `[[_TOC_]]` macro
- **Confluence Storage Format passthrough**: fenced code with `csf` language
"""


def generate_skill(out_dir: Path) -> Path:
    """Generates a Claude Code skill directory for md2conf.

    :param out_dir: Parent directory in which to create the skill directory.
    :returns: Path to the generated skill directory.
    """

    skill_dir = out_dir / _SKILL_NAME
    os.makedirs(skill_dir, exist_ok=True)

    skill_md_path = skill_dir / "SKILL.md"
    with open(skill_md_path, "w", encoding="utf-8") as f:
        f.write(_SKILL_FRONTMATTER)
        f.write(_SKILL_BODY)

    LOGGER.info("Generated skill '%s' at %s", _SKILL_NAME, skill_dir)

    # Write CLI reference to references/ subdirectory
    references_dir = skill_dir / "references"
    os.makedirs(references_dir, exist_ok=True)

    cli_ref_path = references_dir / "cli-help.md"
    with open(cli_ref_path, "w", encoding="utf-8") as f:
        from .__main__ import get_help

        f.write("# md2conf CLI Reference\n\n")
        f.write("```\n")
        f.write(get_help())
        f.write("```\n")

    LOGGER.info("Generated CLI reference at %s", cli_ref_path)

    return skill_dir
