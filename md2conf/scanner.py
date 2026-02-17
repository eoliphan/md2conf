"""
Publish Markdown files to Confluence wiki.

Copyright 2022-2025, Levente Hunyadi

:see: https://github.com/hunyadi/md2conf
"""

import re
import typing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Optional, TypeVar

import yaml
from strong_typing.core import JsonType
from strong_typing.serialization import DeserializerOptions, json_to_object

from .mermaid import MermaidConfigProperties

T = TypeVar("T")


def _json_to_object(
    typ: type[T],
    data: JsonType,
) -> T:
    return json_to_object(typ, data, options=DeserializerOptions(skip_unassigned=True))


def extract_value(pattern: str, text: str) -> tuple[Optional[str], str]:
    values: list[str] = []

    def _repl_func(matchobj: re.Match[str]) -> str:
        values.append(matchobj.group(1))
        return ""

    text = re.sub(pattern, _repl_func, text, count=1, flags=re.ASCII)
    value = values[0] if values else None
    return value, text


def extract_frontmatter_block(text: str) -> tuple[Optional[str], str]:
    "Extracts the front-matter from a Markdown document as a blob of unparsed text."

    return extract_value(r"(?ms)\A---$(.+?)^---$", text)


def extract_frontmatter_properties(text: str) -> tuple[Optional[dict[str, JsonType]], str]:
    "Extracts the front-matter from a Markdown document as a dictionary."

    block, text = extract_frontmatter_block(text)

    properties: Optional[dict[str, Any]] = None
    if block is not None:
        data = yaml.safe_load(block)
        if isinstance(data, dict):
            properties = typing.cast(dict[str, JsonType], data)

    return properties, text


@dataclass
class SkillProperties:
    """
    An object that holds skill-specific properties extracted from the front-matter of a Markdown document.

    :param name: The skill name (lowercase alphanumeric + hyphens).
    :param description: A short description of the skill.
    :param version: Skill version string.
    :param allowed_tools: Comma-separated list of allowed tools.
    :param argument_hint: Hint text for the skill argument.
    :param model: Model to use for the skill.
    :param disable_model_invocation: Whether to disable model invocation.
    :param user_invocable: Whether the skill can be invoked by the user.
    """

    name: Optional[str] = None
    description: Optional[str] = None
    version: Optional[str] = None
    allowed_tools: Optional[str] = None
    argument_hint: Optional[str] = None
    model: Optional[str] = None
    disable_model_invocation: Optional[bool] = None
    user_invocable: Optional[bool] = None


_SKILL_KEYS = {"name", "description", "version", "allowed-tools", "argument-hint", "model", "disable-model-invocation", "user-invocable"}


def _extract_skill_properties(data: dict[str, JsonType]) -> Optional["SkillProperties"]:
    """Extracts skill properties from top-level frontmatter keys.

    Detects a skill source file by the presence of a 'description' key (the required
    skill field). Returns None if no skill fields are found.
    """

    if "description" not in data:
        return None

    normalized = {k.replace("-", "_"): v for k, v in data.items() if k in _SKILL_KEYS}
    if not normalized:
        return None

    return _json_to_object(SkillProperties, normalized)


@dataclass
class DocumentProperties:
    """
    An object that holds properties extracted from the front-matter of a Markdown document.

    :param page_id: Confluence page ID.
    :param space_key: Confluence space key.
    :param confluence_page_id: Confluence page ID. (Alternative name for JSON de-serialization.)
    :param confluence_space_key: Confluence space key. (Alternative name for JSON de-serialization.)
    :param generated_by: Text identifying the tool that generated the document.
    :param title: The title extracted from front-matter.
    :param tags: A list of tags (content labels) extracted from front-matter.
    :param synchronized: True if the document content is parsed and synchronized with Confluence.
    :param properties: A dictionary of key-value pairs extracted from front-matter to apply as page properties.
    :param alignment: Alignment for block-level images and formulas.
    """

    page_id: Optional[str]
    space_key: Optional[str]
    confluence_page_id: Optional[str]
    confluence_space_key: Optional[str]
    generated_by: Optional[str]
    title: Optional[str]
    tags: Optional[list[str]]
    synchronized: Optional[bool]
    properties: Optional[dict[str, JsonType]]
    alignment: Optional[Literal["center", "left", "right"]]


@dataclass
class ScannedDocument:
    """
    An object that holds properties extracted from a Markdown document, including remaining source text.

    :param page_id: Confluence page ID.
    :param space_key: Confluence space key.
    :param generated_by: Text identifying the tool that generated the document.
    :param title: The title extracted from front-matter.
    :param tags: A list of tags (content labels) extracted from front-matter.
    :param synchronized: True if the document content is parsed and synchronized with Confluence.
    :param properties: A dictionary of key-value pairs extracted from front-matter to apply as page properties.
    :param alignment: Alignment for block-level images and formulas.
    :param skill: Skill-specific properties for Claude Code skill generation.
    :param text: Text that remains after front-matter and inline properties have been extracted.
    """

    page_id: Optional[str]
    space_key: Optional[str]
    generated_by: Optional[str]
    title: Optional[str]
    tags: Optional[list[str]]
    synchronized: Optional[bool]
    properties: Optional[dict[str, JsonType]]
    alignment: Optional[Literal["center", "left", "right"]]
    skill: Optional[SkillProperties]
    text: str


class Scanner:
    def read(self, absolute_path: Path) -> ScannedDocument:
        """
        Extracts essential properties from a Markdown document.
        """

        # parse file
        with open(absolute_path, "r", encoding="utf-8") as f:
            text = f.read()

        # extract Confluence page ID
        page_id, text = extract_value(r"<!--\s+confluence[-_]page[-_]id:\s*(\d+)\s+-->", text)

        # extract Confluence space key
        space_key, text = extract_value(r"<!--\s+confluence[-_]space[-_]key:\s*(\S+)\s+-->", text)

        # extract 'generated-by' tag text
        generated_by, text = extract_value(r"<!--\s+generated[-_]by:\s*(.*)\s+-->", text)

        title: Optional[str] = None
        tags: Optional[list[str]] = None
        synchronized: Optional[bool] = None
        properties: Optional[dict[str, JsonType]] = None
        alignment: Optional[Literal["center", "left", "right"]] = None
        skill: Optional[SkillProperties] = None

        # extract front-matter
        data, text = extract_frontmatter_properties(text)
        if data is not None:
            # extract skill properties from top-level frontmatter keys before DocumentProperties deserialization
            skill = _extract_skill_properties(data)

            p = _json_to_object(DocumentProperties, data)
            page_id = page_id or p.confluence_page_id or p.page_id
            space_key = space_key or p.confluence_space_key or p.space_key
            generated_by = generated_by or p.generated_by
            title = p.title
            tags = p.tags
            synchronized = p.synchronized
            properties = p.properties
            alignment = p.alignment

        return ScannedDocument(
            page_id=page_id,
            space_key=space_key,
            generated_by=generated_by,
            title=title,
            tags=tags,
            synchronized=synchronized,
            properties=properties,
            alignment=alignment,
            skill=skill,
            text=text,
        )


@dataclass
class MermaidProperties:
    """
    An object that holds the front-matter properties structure for Mermaid diagrams.

    :param title: The title of the diagram.
    :param config: Configuration options for rendering.
    """

    title: Optional[str] = None
    config: Optional[MermaidConfigProperties] = None


class MermaidScanner:
    """
    Extracts properties from the JSON/YAML front-matter of a Mermaid diagram.
    """

    def read(self, content: str) -> MermaidProperties:
        """
        Extracts rendering preferences from a Mermaid front-matter content.

        ```
        ---
        title: Tiny flow diagram
        config:
            scale: 1
        ---
        flowchart LR
            A[Component A] --> B[Component B]
            B --> C[Component C]
        ```
        """

        properties, _ = extract_frontmatter_properties(content)
        if properties is not None:
            front_matter = _json_to_object(MermaidProperties, properties)
            config = front_matter.config or MermaidConfigProperties()

            return MermaidProperties(title=front_matter.title, config=config)

        return MermaidProperties()
