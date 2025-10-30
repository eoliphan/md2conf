"""
Data structure mappers for Confluence REST API v1.

This module provides bidirectional mapping functions between Confluence REST API v1
responses and the internal domain objects used by md2conf.

The v1 API uses different field names, nesting structures, and data formats compared
to v2. These mappers enable md2conf to work with v1 endpoints when necessary while
maintaining a consistent internal domain model.
"""

from typing import Dict

from strong_typing.core import JsonType

from .api import (
    ConfluenceAttachment,
    ConfluenceCreatePageRequest,
    ConfluenceIdentifiedContentProperty,
    ConfluenceIdentifiedLabel,
    ConfluencePage,
    ConfluencePageProperties,
    ConfluenceUpdatePageRequest,
)


def map_page_v1_to_domain(v1_response: Dict[str, JsonType]) -> ConfluencePage:
    """
    Convert Confluence REST API v1 page response to ConfluencePage domain object.

    The v1 API response structure differs from v2 in several ways:
    - Uses nested structure for space (space.id instead of spaceId)
    - Uses nested structure for body content (body.storage.value)
    - Uses ancestors array instead of parentId
    - Field names may differ (e.g., version structure)

    Args:
        v1_response: JSON response from GET /rest/api/content/{id}

    Returns:
        ConfluencePage object with mapped fields

    Note:
        TODO: Implement v1 to domain mapping
    """
    # TODO: Extract fields from v1 response structure
    # - Extract id from v1_response["id"]
    # - Extract space ID from v1_response["space"]["id"]
    # - Extract title from v1_response["title"]
    # - Extract status from v1_response["status"]
    # - Extract parentId from v1_response["ancestors"][-1]["id"] if ancestors exist
    # - Extract body from v1_response["body"]["storage"]["value"]
    # - Extract version from v1_response["version"]["number"]
    # - Extract other metadata fields
    raise NotImplementedError("TODO: Implement v1 page mapper")


def map_page_properties_v1_to_domain(v1_response: Dict[str, JsonType]) -> ConfluencePageProperties:
    """
    Convert Confluence REST API v1 page response to ConfluencePageProperties domain object.

    This extracts only the properties (metadata) from a v1 page response, excluding body content.

    Args:
        v1_response: JSON response from GET /rest/api/content/{id}

    Returns:
        ConfluencePageProperties object with mapped fields

    Note:
        TODO: Implement v1 to domain mapping
    """
    # TODO: Extract property fields from v1 response structure
    # - Similar to map_page_v1_to_domain but without body content
    # - Extract parentId from ancestors array: v1_response.get("ancestors", [])[-1]["id"]
    # - Map field names to match ConfluencePageProperties structure
    raise NotImplementedError("TODO: Implement v1 page properties mapper")


def map_create_page_to_v1(request: ConfluenceCreatePageRequest, space_key: str) -> Dict[str, JsonType]:
    """
    Convert ConfluenceCreatePageRequest to v1 API POST body format.

    The v1 API expects:
    - space.key instead of spaceId
    - ancestors array instead of parentId
    - body.storage.value instead of body.storage

    Args:
        request: Internal create page request object
        space_key: Confluence space key (v1 uses key instead of ID)

    Returns:
        Dictionary formatted for v1 POST /rest/api/content

    Note:
        TODO: Implement domain to v1 mapping
    """
    # TODO: Build v1 structure from domain request
    # {
    #     "type": "page",
    #     "title": request.title,
    #     "space": {"key": space_key},
    #     "ancestors": [{"id": request.parentId}] if request.parentId else [],
    #     "body": {
    #         "storage": {
    #             "value": request.body.storage.value,
    #             "representation": "storage"
    #         }
    #     },
    #     "status": request.status.value if request.status else "current"
    # }
    raise NotImplementedError("TODO: Implement create page to v1 mapper")


def map_update_page_to_v1(page_id: str, request: ConfluenceUpdatePageRequest, space_key: str) -> Dict[str, JsonType]:
    """
    Convert ConfluenceUpdatePageRequest to v1 API PUT body format.

    The v1 API PUT expects:
    - id field in the body
    - type field set to "page"
    - space.key instead of spaceId
    - version.number instead of version
    - body.storage.value nested structure

    Args:
        page_id: The page ID being updated
        request: Internal update page request object
        space_key: Confluence space key (v1 uses key instead of ID)

    Returns:
        Dictionary formatted for v1 PUT /rest/api/content/{id}

    Note:
        TODO: Implement domain to v1 mapping
    """
    # TODO: Build v1 structure from domain request
    # {
    #     "id": page_id,
    #     "type": "page",
    #     "title": request.title,
    #     "space": {"key": space_key},
    #     "body": {
    #         "storage": {
    #             "value": request.body.storage.value,
    #             "representation": "storage"
    #         }
    #     },
    #     "version": {
    #         "number": request.version.number,
    #         "minorEdit": request.version.minorEdit
    #     },
    #     "status": request.status.value
    # }
    raise NotImplementedError("TODO: Implement update page to v1 mapper")


def map_space_v1_to_id(v1_response: Dict[str, JsonType]) -> str:
    """
    Extract space ID from Confluence REST API v1 space response.

    Args:
        v1_response: JSON response from GET /rest/api/space/{spaceKey}

    Returns:
        Space ID as a string
    """
    return str(v1_response["id"])


def map_attachment_v1_to_domain(v1_response: Dict[str, JsonType]) -> ConfluenceAttachment:
    """
    Convert Confluence REST API v1 attachment response to ConfluenceAttachment domain object.

    The v1 API uses different field names and nesting for attachments:
    - Different structure for metadata
    - Different URL field names (_links structure)
    - Version information may be nested differently

    Args:
        v1_response: JSON response from GET /rest/api/content/{id}/child/attachment

    Returns:
        ConfluenceAttachment object with mapped fields

    Note:
        TODO: Implement v1 attachment mapping
    """
    # TODO: Extract and map attachment fields from v1 response
    # - Extract id, title, mediaType, fileSize
    # - Map _links structure to webuiLink and downloadLink
    # - Extract version information
    # - Extract pageId from container or metadata
    # - Map other metadata fields
    raise NotImplementedError("TODO: Implement v1 attachment mapper")


def map_label_v1_to_domain(v1_response: Dict[str, JsonType]) -> ConfluenceIdentifiedLabel:
    """
    Convert Confluence REST API v1 label response to ConfluenceIdentifiedLabel domain object.

    The v1 API label structure includes:
    - id: Label identifier
    - name: Label name
    - prefix: Label prefix (e.g., "global", "my", "team")

    Args:
        v1_response: JSON response from GET /rest/api/content/{id}/label

    Returns:
        ConfluenceIdentifiedLabel object with mapped fields

    Note:
        TODO: Implement v1 label mapping
    """
    # TODO: Extract label fields from v1 response
    # - Extract id from v1_response["id"]
    # - Extract name from v1_response["name"]
    # - Extract prefix from v1_response["prefix"]
    raise NotImplementedError("TODO: Implement v1 label mapper")


def map_property_v1_to_domain(v1_response: Dict[str, JsonType]) -> ConfluenceIdentifiedContentProperty:
    """
    Convert Confluence REST API v1 content property response to ConfluenceIdentifiedContentProperty.

    The v1 API content property structure includes:
    - id: Property identifier
    - key: Property key
    - value: Property value (JSON object)
    - version: Version information with number field

    Args:
        v1_response: JSON response from GET /rest/api/content/{id}/property/{key}

    Returns:
        ConfluenceIdentifiedContentProperty object with mapped fields

    Note:
        TODO: Implement v1 content property mapping
    """
    # TODO: Extract content property fields from v1 response
    # - Extract id from v1_response["id"]
    # - Extract key from v1_response["key"]
    # - Extract value from v1_response["value"]
    # - Extract version.number from v1_response["version"]["number"]
    raise NotImplementedError("TODO: Implement v1 content property mapper")
