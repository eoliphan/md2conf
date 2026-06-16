"""
Publish Markdown files to Confluence wiki.

Copyright 2022-2025, Levente Hunyadi

:see: https://github.com/hunyadi/md2conf
"""

import logging
from pathlib import Path
from typing import Any

import yaml

from .scanner import (
    _GENERATED_BY_RE,
    _PAGE_ID_RE,
    _SPACE_KEY_RE,
    extract_frontmatter_block,
    extract_value,
)

LOGGER = logging.getLogger(__name__)


def migrate_file(path: Path, dry_run: bool = False, backup: bool = True) -> bool:
    """
    Migrates HTML comment-based metadata in a single Markdown file to YAML frontmatter.

    :returns: True if the file was (or in dry_run mode, would be) modified.
    """
    text = path.read_text(encoding="utf-8")

    # extract comment values, stripping each comment from the text
    page_id, text_clean = extract_value(_PAGE_ID_RE, text)
    space_key, text_clean = extract_value(_SPACE_KEY_RE, text_clean)
    generated_by, text_clean = extract_value(_GENERATED_BY_RE, text_clean)

    if page_id is None and space_key is None and generated_by is None:
        return False  # nothing to migrate

    # build dict of comment-sourced fields
    comment_fields: dict[str, str] = {}
    if page_id is not None:
        comment_fields["page_id"] = page_id
    if space_key is not None:
        comment_fields["space_key"] = space_key
    if generated_by is not None:
        comment_fields["generated_by"] = generated_by

    # strip leading blank lines that may result from comment removal at the file top
    text_trimmed = text_clean.lstrip("\n")

    # parse any existing frontmatter from the comment-stripped text
    frontmatter_block, body = extract_frontmatter_block(text_trimmed)

    if frontmatter_block is not None:
        data = yaml.safe_load(frontmatter_block)
        existing: dict[str, Any] = data if isinstance(data, dict) else {}
        # existing frontmatter values win; comment values fill in only missing keys
        merged: dict[str, Any] = {**comment_fields, **existing}
        new_fm = yaml.dump(merged, default_flow_style=False, allow_unicode=True).rstrip()
        new_text = f"---\n{new_fm}\n---\n{body}"
    else:
        new_fm = yaml.dump(comment_fields, default_flow_style=False, allow_unicode=True).rstrip()
        new_text = f"---\n{new_fm}\n---\n{text_trimmed}"

    if dry_run:
        LOGGER.info("Would migrate: %s (fields: %s)", path, list(comment_fields.keys()))
        return True

    if backup:
        path.with_suffix(path.suffix + ".bak").write_text(text, encoding="utf-8")

    path.write_text(new_text, encoding="utf-8")
    LOGGER.info("Migrated: %s", path)
    return True


def migrate(path: Path, dry_run: bool = False, backup: bool = True) -> tuple[int, int, int]:
    """
    Scans path (file or directory) for Markdown files with HTML comment metadata
    and migrates them to YAML frontmatter.

    :returns: Tuple of (migrated, clean, errors) counts.
    """
    files = [path] if path.is_file() else sorted(path.rglob("*.md"))

    migrated = 0
    clean = 0
    errors = 0

    for file in files:
        try:
            changed = migrate_file(file, dry_run=dry_run, backup=backup)
            if changed:
                migrated += 1
            else:
                clean += 1
        except Exception as e:
            LOGGER.error("Error migrating %s: %s", file, e)
            errors += 1

    return migrated, clean, errors
