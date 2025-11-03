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
        v1_response: JSON response from GET /rest/api/content/{id}?expand=body.storage,version,space,history

    Returns:
        ConfluencePage object with mapped fields
    """
    import datetime
    import typing

    from .api import ConfluenceContentVersion, ConfluencePageBody, ConfluencePageStorage

    # Extract basic fields
    page_id = str(v1_response["id"])
    title = str(v1_response["title"])
    status = str(v1_response["status"])

    # Extract space ID from nested structure
    space_dict = typing.cast(Dict[str, JsonType], v1_response.get("space", {}))
    space_id = str(space_dict["id"])

    # Extract parentId from ancestors array (last element)
    ancestors = typing.cast(list[JsonType], v1_response.get("ancestors", []))
    parent_id = None
    if ancestors:
        last_ancestor = typing.cast(Dict[str, JsonType], ancestors[-1])
        parent_id = str(last_ancestor["id"])

    # Extract body content from nested structure
    body_dict = typing.cast(Dict[str, JsonType], v1_response.get("body", {}))
    storage_dict = typing.cast(Dict[str, JsonType], body_dict.get("storage", {}))
    body_value = str(storage_dict.get("value", ""))
    body_representation = str(storage_dict.get("representation", "storage"))

    # Extract version number
    version_dict = typing.cast(Dict[str, JsonType], v1_response.get("version", {}))
    version_number = int(version_dict.get("number", 1))

    # Extract history data if available
    history_dict = typing.cast(Dict[str, JsonType], v1_response.get("history", {}))
    created_by_dict = typing.cast(Dict[str, JsonType], history_dict.get("createdBy", {}))
    author_id = str(created_by_dict.get("accountId", "unknown"))

    # v1 API returns dates in ISO format string
    created_at_str = str(v1_response.get("createdDate", v1_response.get("created", datetime.datetime.now().isoformat())))
    try:
        # Parse ISO format datetime - handle both Z and +00:00 format
        created_at = datetime.datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        created_at = datetime.datetime.now()

    # Build ConfluencePage object
    # Note: v1 API doesn't provide parentType, position, ownerId, lastOwnerId
    # These are set to None/placeholder values
    return ConfluencePage(
        id=page_id,
        spaceId=space_id,
        parentId=parent_id,
        status=status,
        title=title,
        body=ConfluencePageBody(storage=ConfluencePageStorage(value=body_value, representation=body_representation)),
        version=ConfluenceContentVersion(number=version_number),
        parentType=None,  # Not available in v1 API
        position=None,  # Not available in v1 API
        authorId=author_id,
        ownerId=author_id,  # Use author as owner (best guess for v1)
        lastOwnerId=None,  # Not available in v1 API
        createdAt=created_at,
    )


def map_page_properties_v1_to_domain(v1_response: Dict[str, JsonType]) -> ConfluencePageProperties:
    """
    Convert Confluence REST API v1 page response to ConfluencePageProperties domain object.

    This extracts only the properties (metadata) from a v1 page response, excluding body content.

    Args:
        v1_response: JSON response from GET /rest/api/content/{id}?expand=version,space,history

    Returns:
        ConfluencePageProperties object with mapped fields
    """
    import datetime
    import typing

    from .api import ConfluenceContentVersion

    # Extract basic fields
    page_id = str(v1_response["id"])
    title = str(v1_response["title"])
    status = str(v1_response["status"])

    # Extract space ID from nested structure
    space_dict = typing.cast(Dict[str, JsonType], v1_response.get("space", {}))
    space_id = str(space_dict["id"])

    # Extract parentId from ancestors array (last element)
    ancestors = typing.cast(list[JsonType], v1_response.get("ancestors", []))
    parent_id = None
    if ancestors:
        last_ancestor = typing.cast(Dict[str, JsonType], ancestors[-1])
        parent_id = str(last_ancestor["id"])

    # Extract version number
    version_dict = typing.cast(Dict[str, JsonType], v1_response.get("version", {}))
    version_number = int(version_dict.get("number", 1))

    # Extract history data if available
    history_dict = typing.cast(Dict[str, JsonType], v1_response.get("history", {}))
    created_by_dict = typing.cast(Dict[str, JsonType], history_dict.get("createdBy", {}))
    author_id = str(created_by_dict.get("accountId", "unknown"))

    # v1 API returns dates in ISO format string
    created_at_str = str(v1_response.get("createdDate", v1_response.get("created", datetime.datetime.now().isoformat())))
    try:
        # Parse ISO format datetime - handle both Z and +00:00 format
        created_at = datetime.datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        created_at = datetime.datetime.now()

    # Build ConfluencePageProperties object
    # Note: v1 API doesn't provide parentType, position, ownerId, lastOwnerId
    # These are set to None/placeholder values
    return ConfluencePageProperties(
        id=page_id,
        spaceId=space_id,
        parentId=parent_id,
        status=status,
        title=title,
        version=ConfluenceContentVersion(number=version_number),
        parentType=None,  # Not available in v1 API
        position=None,  # Not available in v1 API
        authorId=author_id,
        ownerId=author_id,  # Use author as owner (best guess for v1)
        lastOwnerId=None,  # Not available in v1 API
        createdAt=created_at,
    )


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
    """
    v1_request: Dict[str, JsonType] = {
        "type": "page",
        "title": request.title,
        "space": {"key": space_key},
        "body": {"storage": {"value": request.body.storage.value, "representation": "storage"}},
    }

    # Add ancestors if parentId is provided
    if request.parentId:
        v1_request["ancestors"] = [{"id": request.parentId}]

    # Note: status field is NOT included for create operations
    # The v1 API sets it to "current" by default, and including it
    # may cause Apache/proxy issues with some Data Center configurations

    return v1_request


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
    """
    v1_request: Dict[str, JsonType] = {
        "id": page_id,
        "type": "page",
        "title": request.title,
        "space": {"key": space_key},
        "body": {"storage": {"value": request.body.storage.value, "representation": "storage"}},
        "version": {"number": request.version.number},
        "status": request.status.value,  # Convert enum to string value
    }

    # Add minorEdit if provided
    if hasattr(request.version, "minorEdit") and request.version.minorEdit is not None:
        v1_request["version"]["minorEdit"] = request.version.minorEdit  # type: ignore

    return v1_request


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
    """
    import typing

    # Extract basic fields
    attachment_id = str(v1_response["id"])
    title = str(v1_response["title"])
    media_type = str(v1_response.get("metadata", {}).get("mediaType", "application/octet-stream"))

    # Extract file size from extensions
    extensions = typing.cast(Dict[str, JsonType], v1_response.get("extensions", {}))
    file_size = int(extensions.get("fileSize", 0))

    # Extract pageId from container
    container = typing.cast(Dict[str, JsonType], v1_response.get("container", {}))
    page_id = str(container.get("id", ""))

    # Extract links
    links = typing.cast(Dict[str, JsonType], v1_response.get("_links", {}))
    webui = str(links.get("webui", ""))
    download = str(links.get("download", ""))

    # Build ConfluenceAttachment object
    from .api import ConfluenceAttachment

    return ConfluenceAttachment(id=attachment_id, title=title, mediaType=media_type, fileSize=file_size, webuiLink=webui, downloadLink=download, pageId=page_id)


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
    """
    from .api import ConfluenceIdentifiedLabel

    # Extract label fields
    label_id = str(v1_response["id"])
    name = str(v1_response["name"])
    prefix = str(v1_response.get("prefix", "global"))

    return ConfluenceIdentifiedLabel(id=label_id, name=name, prefix=prefix)


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
    """
    import typing

    from .api import ConfluenceContentVersion

    # Extract property fields
    property_id = str(v1_response["id"])
    key = str(v1_response["key"])
    value = v1_response["value"]

    # Extract version number
    version_dict = typing.cast(Dict[str, JsonType], v1_response.get("version", {}))
    version_number = int(version_dict.get("number", 1))

    return ConfluenceIdentifiedContentProperty(id=property_id, key=key, value=value, version=ConfluenceContentVersion(number=version_number))
