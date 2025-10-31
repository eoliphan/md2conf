"""
Publish Markdown files to Confluence wiki.

Copyright 2022-2025, Levente Hunyadi

:see: https://github.com/hunyadi/md2conf
"""

import datetime
import enum
import io
import logging
import mimetypes
import ssl
import sys
import typing
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any, Optional, TypeVar, overload
from urllib.parse import urlencode, urlparse, urlunparse

import requests
from requests.adapters import HTTPAdapter
from strong_typing.core import JsonType
from strong_typing.serialization import DeserializerOptions, json_dump_string, json_to_object, object_to_json

from .environment import ArgumentError, ConfluenceConnectionProperties, ConfluenceError, PageError
from .extra import override
from .metadata import ConfluenceSiteMetadata

if sys.version_info >= (3, 10):
    import truststore
else:
    import certifi

T = TypeVar("T")

mimetypes.add_type("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx", strict=True)
mimetypes.add_type("text/vnd.mermaid", ".mmd", strict=True)
mimetypes.add_type("application/vnd.oasis.opendocument.presentation", ".odp", strict=True)
mimetypes.add_type("application/vnd.oasis.opendocument.spreadsheet", ".ods", strict=True)
mimetypes.add_type("application/vnd.oasis.opendocument.text", ".odt", strict=True)
mimetypes.add_type("application/vnd.openxmlformats-officedocument.presentationml.presentation", ".pptx", strict=True)
mimetypes.add_type("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx", strict=True)


def _json_to_object(
    typ: type[T],
    data: JsonType,
) -> T:
    return json_to_object(typ, data, options=DeserializerOptions(skip_unassigned=True))


def build_url(base_url: str, query: Optional[dict[str, str]] = None) -> str:
    "Builds a URL with scheme, host, port, path and query string parameters."

    scheme, netloc, path, params, query_str, fragment = urlparse(base_url)

    if params:
        raise ValueError("expected: url with no parameters")
    if query_str:
        raise ValueError("expected: url with no query string")
    if fragment:
        raise ValueError("expected: url with no fragment")

    url_parts = (scheme, netloc, path, None, urlencode(query) if query else None, None)
    return urlunparse(url_parts)


LOGGER = logging.getLogger(__name__)


@overload
def response_cast(response_type: None, response: requests.Response) -> None: ...


@overload
def response_cast(response_type: type[T], response: requests.Response) -> T: ...


def response_cast(response_type: Optional[type[T]], response: requests.Response) -> Optional[T]:
    "Converts a response body into the expected type."

    if response.text:
        LOGGER.debug("Received HTTP payload:\n%s", response.text)
    response.raise_for_status()
    if response_type is None:
        return None
    else:
        return _json_to_object(response_type, response.json())


@enum.unique
class ConfluenceVersion(enum.Enum):
    """
    Confluence REST API version an HTTP request corresponds to.

    For some operations, Confluence Cloud supports v2 endpoints exclusively. However, for other operations, only v1 endpoints are available via REST API.
    Some versions of Confluence Server and Data Center, unfortunately, don't support v2 endpoints at all.

    The principal use case for *md2conf* is Confluence Cloud. As such, *md2conf* uses v2 endpoints when available, and resorts to v1 endpoints only when
    necessary.
    """

    VERSION_1 = "rest/api"
    VERSION_2 = "api/v2"


@enum.unique
class ConfluencePageParentContentType(enum.Enum):
    """
    Content types that can be a parent to a Confluence page.
    """

    PAGE = "page"
    WHITEBOARD = "whiteboard"
    DATABASE = "database"
    EMBED = "embed"
    FOLDER = "folder"


@enum.unique
class ConfluenceRepresentation(enum.Enum):
    STORAGE = "storage"
    ATLAS = "atlas_doc_format"
    WIKI = "wiki"


@enum.unique
class ConfluenceStatus(enum.Enum):
    CURRENT = "current"
    DRAFT = "draft"
    ARCHIVED = "archived"


@enum.unique
class ConfluenceLegacyType(enum.Enum):
    ATTACHMENT = "attachment"


@dataclass(frozen=True)
class ConfluenceLinks:
    next: str
    base: str


@dataclass(frozen=True)
class ConfluenceResultSet:
    results: list[JsonType]
    _links: ConfluenceLinks


@dataclass(frozen=True)
class ConfluenceContentVersion:
    number: int
    minorEdit: bool = False
    createdAt: Optional[datetime.datetime] = None
    message: Optional[str] = None
    authorId: Optional[str] = None


@dataclass(frozen=True)
class ConfluenceAttachment:
    """
    Holds data for an object uploaded to Confluence as a page attachment.

    :param id: Unique ID for the attachment.
    :param status: Attachment status.
    :param title: Attachment title.
    :param createdAt: Date and time when the attachment was created.
    :param pageId: The Confluence page that the attachment is coupled with.
    :param mediaType: MIME type for the attachment.
    :param mediaTypeDescription: Media type description for the attachment.
    :param comment: Description for the attachment.
    :param fileId: File ID of the attachment, distinct from the attachment ID.
    :param fileSize: Size in bytes.
    :param webuiLink: WebUI link of the attachment.
    :param downloadLink: Download link of the attachment.
    :param version: Version information for the attachment.
    """

    id: str
    status: ConfluenceStatus
    title: Optional[str]
    createdAt: datetime.datetime
    pageId: str
    mediaType: str
    mediaTypeDescription: Optional[str]
    comment: Optional[str]
    fileId: str
    fileSize: int
    webuiLink: str
    downloadLink: str
    version: ConfluenceContentVersion


@dataclass(frozen=True)
class ConfluencePageProperties:
    """
    Holds Confluence page properties used for page synchronization.

    :param id: Confluence page ID.
    :param status: Page status.
    :param title: Page title.
    :param spaceId: Confluence space ID.
    :param parentId: Confluence page ID of the immediate parent.
    :param parentType: Identifies the content type of the parent.
    :param position: Position of child page within the given parent page tree.
    :param authorId: The account ID of the user who created this page originally.
    :param ownerId: The account ID of the user who owns this page.
    :param lastOwnerId: The account ID of the user who owned this page previously, or `None` if there is no previous owner.
    :param createdAt: Date and time when the page was created.
    :param version: Page version. Incremented when the page is updated.
    """

    id: str
    status: ConfluenceStatus
    title: str
    spaceId: str
    parentId: Optional[str]
    parentType: Optional[ConfluencePageParentContentType]
    position: Optional[int]
    authorId: str
    ownerId: str
    lastOwnerId: Optional[str]
    createdAt: datetime.datetime
    version: ConfluenceContentVersion


@dataclass(frozen=True)
class ConfluencePageStorage:
    """
    Holds Confluence page content.

    :param representation: Type of content representation used (e.g. Confluence Storage Format).
    :param value: Body of the content, in the format found in the representation field.
    """

    representation: ConfluenceRepresentation
    value: str


@dataclass(frozen=True)
class ConfluencePageBody:
    """
    Holds Confluence page content.

    :param storage: Encapsulates content with meta-information about its representation.
    """

    storage: ConfluencePageStorage


@dataclass(frozen=True)
class ConfluencePage(ConfluencePageProperties):
    """
    Holds Confluence page data used for page synchronization.

    :param body: Page content.
    """

    body: ConfluencePageBody

    @property
    def content(self) -> str:
        return self.body.storage.value


@dataclass(frozen=True, eq=True, order=True)
class ConfluenceLabel:
    """
    Holds information about a single label.

    :param name: Name of the label.
    :param prefix: Prefix of the label.
    """

    name: str
    prefix: str


@dataclass(frozen=True, eq=True, order=True)
class ConfluenceIdentifiedLabel(ConfluenceLabel):
    """
    Holds information about a single label.

    :param id: ID of the label.
    """

    id: str


@dataclass(frozen=True)
class ConfluenceContentProperty:
    """
    Represents a content property.

    :param key: Property key.
    :param value: Property value as JSON.
    """

    key: str
    value: JsonType


@dataclass(frozen=True)
class ConfluenceVersionedContentProperty(ConfluenceContentProperty):
    """
    Represents a content property.

    :param version: Version information about the property.
    """

    version: ConfluenceContentVersion


@dataclass(frozen=True)
class ConfluenceIdentifiedContentProperty(ConfluenceVersionedContentProperty):
    """
    Represents a content property.

    :param id: Property ID.
    """

    id: str


@dataclass(frozen=True)
class ConfluenceCreatePageRequest:
    spaceId: str
    status: Optional[ConfluenceStatus]
    title: Optional[str]
    parentId: Optional[str]
    body: ConfluencePageBody


@dataclass(frozen=True)
class ConfluenceUpdatePageRequest:
    id: str
    status: ConfluenceStatus
    title: str
    body: ConfluencePageBody
    version: ConfluenceContentVersion


@dataclass(frozen=True)
class ConfluenceUpdateAttachmentRequest:
    id: str
    type: ConfluenceLegacyType
    status: ConfluenceStatus
    title: str
    version: ConfluenceContentVersion


class TruststoreAdapter(HTTPAdapter):
    """
    Provides a general-case interface for HTTPS sessions to connect to HTTPS URLs.

    This class implements the Transport Adapter interface in the Python library `requests`.

    This class will usually be created by the :class:`requests.Session` class under the covers.
    """

    @override
    def init_poolmanager(self, connections: int, maxsize: int, block: bool = False, **pool_kwargs: Any) -> None:
        """
        Adapts the pool manager to use the provided SSL context instead of the default.
        """

        if sys.version_info >= (3, 10):
            ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        else:
            ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=certifi.where())
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
        super().init_poolmanager(connections, maxsize, block, ssl_context=ctx, **pool_kwargs)  # type: ignore[no-untyped-call]


class ConfluenceAPI:
    """
    Encapsulates operations that can be invoked via the [Confluence REST API](https://developer.atlassian.com/cloud/confluence/rest/v2/).
    """

    properties: ConfluenceConnectionProperties
    session: Optional["ConfluenceSession"] = None

    def __init__(self, properties: Optional[ConfluenceConnectionProperties] = None) -> None:
        self.properties = properties or ConfluenceConnectionProperties()

    def __enter__(self) -> "ConfluenceSession":
        """
        Opens a connection to a Confluence server.
        """

        session = requests.Session()
        session.mount("https://", TruststoreAdapter())

        if self.properties.user_name:
            session.auth = (self.properties.user_name, self.properties.api_key)
        else:
            session.headers.update({"Authorization": f"Bearer {self.properties.api_key}"})

        if self.properties.headers:
            session.headers.update(self.properties.headers)

        self.session = ConfluenceSession(
            session,
            properties=self.properties,
            api_url=self.properties.api_url,
            domain=self.properties.domain,
            base_path=self.properties.base_path,
            space_key=self.properties.space_key,
        )
        return self.session

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        """
        Closes an open connection.
        """

        if self.session is not None:
            self.session.close()
            self.session = None


class ConfluenceSession:
    """
    Represents an active connection to a Confluence server.
    """

    session: requests.Session
    api_url: str
    api_version: ConfluenceVersion
    site: ConfluenceSiteMetadata

    _space_id_to_key: dict[str, str]
    _space_key_to_id: dict[str, str]

    def __init__(
        self,
        session: requests.Session,
        *,
        properties: ConfluenceConnectionProperties,
        api_url: Optional[str],
        domain: Optional[str],
        base_path: Optional[str],
        space_key: Optional[str],
    ) -> None:
        self.session = session
        self._space_id_to_key = {}
        self._space_key_to_id = {}

        # Detect and set API version based on deployment type
        self.api_version = self._detect_api_version(properties.deployment_type)
        LOGGER.info("Using Confluence REST API %s", self.api_version.value)

        if api_url:
            self.api_url = api_url

            if not domain or not base_path:
                # Use detected API version for domain/base_path inference
                if self.api_version == ConfluenceVersion.VERSION_1:
                    # v1 API: GET /rest/api/space?limit=1
                    data = self._get(ConfluenceVersion.VERSION_1, "/space", dict[str, JsonType], query={"limit": "1"})
                    results = typing.cast(list[JsonType], data.get("results", []))
                    if results:
                        result = typing.cast(dict[str, JsonType], results[0])
                        links = typing.cast(dict[str, JsonType], result.get("_links", {}))
                        base_url = typing.cast(str, links.get("base", ""))
                    else:
                        raise ConfluenceError("Unable to infer domain and base path: no spaces found")
                else:
                    # v2 API: GET /api/v2/spaces?limit=1
                    data = self._get(ConfluenceVersion.VERSION_2, "/spaces", ConfluenceResultSet, query={"limit": "1"})
                    base_url = data._links.base  # pyright: ignore[reportPrivateUsage]

                _, domain, base_path, _, _, _ = urlparse(base_url)
                if not base_path.endswith("/"):
                    base_path = f"{base_path}/"

        if not domain:
            raise ArgumentError("Confluence domain not specified and cannot be inferred")
        if not base_path:
            raise ArgumentError("Confluence base path not specified and cannot be inferred")
        self.site = ConfluenceSiteMetadata(domain, base_path, space_key)

        if not api_url:
            LOGGER.info("Discovering Confluence REST API URL")

            # For Data Center/Server (v1 API), always use classic REST API URL
            if self.api_version == ConfluenceVersion.VERSION_1:
                self.api_url = f"https://{self.site.domain}{self.site.base_path}"
                LOGGER.info("Configured classic Confluence REST API URL for Data Center/Server: %s", self.api_url)
            else:
                # For Cloud (v2 API), try scoped API URL first, then fall back to classic
                try:
                    # obtain cloud ID to build URL for access with scoped token
                    response = self.session.get(f"https://{self.site.domain}/_edge/tenant_info", headers={"Accept": "application/json"}, verify=True)
                    if response.text:
                        LOGGER.debug("Received HTTP payload:\n%s", response.text)
                    response.raise_for_status()
                    cloud_id = response.json()["cloudId"]

                    # try next-generation REST API URL
                    LOGGER.info("Probing scoped Confluence REST API URL")
                    self.api_url = f"https://api.atlassian.com/ex/confluence/{cloud_id}/"
                    url = self._build_url(ConfluenceVersion.VERSION_2, "/spaces", {"limit": "1"})
                    response = self.session.get(url, headers={"Accept": "application/json"}, verify=True)
                    if response.text:
                        LOGGER.debug("Received HTTP payload:\n%s", response.text)
                    response.raise_for_status()

                    LOGGER.info("Configured scoped Confluence REST API URL: %s", self.api_url)
                except requests.exceptions.HTTPError:
                    # fall back to classic REST API URL
                    self.api_url = f"https://{self.site.domain}{self.site.base_path}"
                    LOGGER.info("Configured classic Confluence REST API URL: %s", self.api_url)

    def close(self) -> None:
        self.session.close()
        self.session = requests.Session()

    def _detect_api_version(self, deployment_type: Optional[str]) -> ConfluenceVersion:
        """
        Detects which Confluence REST API version to use based on deployment type.

        The logic is as follows:
        - If deployment_type is "datacenter" or "server": use VERSION_1 (rest/api)
          because these versions may not support v2 endpoints.
        - If deployment_type is "cloud": use VERSION_2 (api/v2)
          as Cloud supports v2 endpoints.
        - If deployment_type is None (not specified): default to VERSION_2 (api/v2)
          for backward compatibility and to prefer the newer API when possible.

        :param deployment_type: The Confluence deployment type (cloud, datacenter, server, or None).
        :returns: The appropriate ConfluenceVersion to use.
        """
        if deployment_type in ("datacenter", "server"):
            return ConfluenceVersion.VERSION_1
        elif deployment_type == "cloud":
            return ConfluenceVersion.VERSION_2
        else:
            # Default to VERSION_2 when deployment_type is None
            return ConfluenceVersion.VERSION_2

    def _build_url(
        self,
        version: ConfluenceVersion,
        path: str,
        query: Optional[dict[str, str]] = None,
    ) -> str:
        """
        Builds a full URL for invoking the Confluence API.

        :param prefix: A URL path prefix that depends on the Confluence API version.
        :param path: Path of API endpoint to invoke.
        :param query: Query parameters to pass to the API endpoint.
        :returns: A full URL.
        """

        base_url = f"{self.api_url}{version.value}{path}"
        return build_url(base_url, query)

    def _get(
        self,
        version: ConfluenceVersion,
        path: str,
        response_type: type[T],
        *,
        query: Optional[dict[str, str]] = None,
    ) -> T:
        "Executes an HTTP request via Confluence API."

        url = self._build_url(version, path, query)
        response = self.session.get(url, headers={"Accept": "application/json"}, verify=True)
        if response.text:
            LOGGER.debug("Received HTTP payload:\n%s", response.text)
        response.raise_for_status()
        return _json_to_object(response_type, response.json())

    def _fetch_v1(self, path: str, query: Optional[dict[str, str]] = None) -> list[JsonType]:
        "Retrieves all results of a REST API v1 paginated result-set."

        items: list[JsonType] = []
        start = 0
        limit = 200

        while True:
            # Add pagination parameters to query
            paginated_query = dict(query) if query else {}
            paginated_query["start"] = str(start)
            paginated_query["limit"] = str(limit)

            data = self._get(ConfluenceVersion.VERSION_1, path, dict[str, JsonType], query=paginated_query)

            results = typing.cast(list[JsonType], data.get("results", []))
            items.extend(results)

            # Check if there are more results
            size = int(data.get("size", 0))
            if size < limit:
                break
            start += limit

        return items

    def _fetch(self, path: str, query: Optional[dict[str, str]] = None) -> list[JsonType]:
        """
        Retrieves all results of a REST API paginated result-set.

        Routes to v1 or v2 pagination based on api_version.
        """
        if self.api_version == ConfluenceVersion.VERSION_1:
            return self._fetch_v1(path, query)
        else:
            return self._fetch_v2(path, query)

    def _fetch_v2(self, path: str, query: Optional[dict[str, str]] = None) -> list[JsonType]:
        "Retrieves all results of a REST API v2 paginated result-set."

        items: list[JsonType] = []
        url = self._build_url(ConfluenceVersion.VERSION_2, path, query)
        while True:
            response = self.session.get(url, headers={"Accept": "application/json"}, verify=True)
            response.raise_for_status()

            payload = typing.cast(dict[str, JsonType], response.json())
            results = typing.cast(list[JsonType], payload["results"])
            items.extend(results)

            links = typing.cast(dict[str, JsonType], payload.get("_links", {}))
            link = typing.cast(str, links.get("next", ""))
            if link:
                url = f"https://{self.site.domain}{link}"
            else:
                break

        return items

    def _build_request(self, version: ConfluenceVersion, path: str, body: Any, response_type: Optional[type[T]]) -> tuple[str, dict[str, str], bytes]:
        "Generates URL, headers and raw payload for a typed request/response."

        url = self._build_url(version, path)
        headers = {"Content-Type": "application/json"}
        if response_type is not None:
            headers["Accept"] = "application/json"
        data = json_dump_string(object_to_json(body)).encode("utf-8")
        return url, headers, data

    @overload
    def _post(self, version: ConfluenceVersion, path: str, body: Any, response_type: None) -> None: ...

    @overload
    def _post(self, version: ConfluenceVersion, path: str, body: Any, response_type: type[T]) -> T: ...

    def _post(self, version: ConfluenceVersion, path: str, body: Any, response_type: Optional[type[T]]) -> Optional[T]:
        "Creates a new object via Confluence REST API."

        url, headers, data = self._build_request(version, path, body, response_type)
        response = self.session.post(url, data=data, headers=headers, verify=True)
        response.raise_for_status()
        return response_cast(response_type, response)

    @overload
    def _put(self, version: ConfluenceVersion, path: str, body: Any, response_type: None) -> None: ...

    @overload
    def _put(self, version: ConfluenceVersion, path: str, body: Any, response_type: type[T]) -> T: ...

    def _put(self, version: ConfluenceVersion, path: str, body: Any, response_type: Optional[type[T]]) -> Optional[T]:
        "Updates an existing object via Confluence REST API."

        url, headers, data = self._build_request(version, path, body, response_type)
        response = self.session.put(url, data=data, headers=headers, verify=True)
        response.raise_for_status()
        return response_cast(response_type, response)

    def _space_id_to_key_v1(self, id: str) -> str:
        """
        Get space key from space ID using v1 API.

        v1 API limitation: No direct endpoint to lookup space by ID.
        This method relies on the reverse cache from space_key_to_id operations.

        Args:
            id: Space ID

        Returns:
            Space key as string

        Raises:
            ConfluenceError: If space ID is not in cache
        """
        key = self._space_id_to_key.get(id)
        if key is None:
            raise ConfluenceError(
                f"Cannot resolve space ID '{id}' to space key with v1 API. "
                f"The space must be accessed by key first to populate the cache. "
                f"v1 API does not support direct space lookup by ID."
            )
        return key

    def space_id_to_key(self, id: str) -> str:
        "Finds the Confluence space key for a space ID."

        # Check cache first (works for both versions)
        key = self._space_id_to_key.get(id)
        if key is None:
            # Route to appropriate API version
            if self.api_version == ConfluenceVersion.VERSION_1:
                key = self._space_id_to_key_v1(id)
            else:
                # v2 implementation
                data = self._get(
                    ConfluenceVersion.VERSION_2,
                    "/spaces",
                    dict[str, JsonType],
                    query={"ids": id, "status": "current"},
                )
                results = typing.cast(list[JsonType], data["results"])
                if len(results) != 1:
                    raise ConfluenceError(f"unique space not found with id: {id}")

                result = typing.cast(dict[str, JsonType], results[0])
                key = typing.cast(str, result["key"])

                self._space_id_to_key[id] = key

        return key

    def _space_key_to_id_v1(self, key: str) -> str:
        """
        Get space ID from space key using v1 API.

        v1 API endpoint: GET /rest/api/space/{spaceKey}

        Args:
            key: Space key (e.g., "SPACE")

        Returns:
            Space ID as string
        """
        from .api_mappers import map_space_v1_to_id

        response = self._get(
            ConfluenceVersion.VERSION_1,
            f"/space/{key}",
            dict[str, JsonType],
        )
        space_id = map_space_v1_to_id(response)
        self._space_key_to_id[key] = space_id
        # Populate reverse cache for v1 API limitation workaround
        self._space_id_to_key[space_id] = key
        return space_id

    def space_key_to_id(self, key: str) -> str:
        "Finds the Confluence space ID for a space key."

        id = self._space_key_to_id.get(key)
        if id is None:
            # Route to appropriate API version
            if self.api_version == ConfluenceVersion.VERSION_1:
                id = self._space_key_to_id_v1(key)
            else:
                # v2 implementation
                data = self._get(
                    ConfluenceVersion.VERSION_2,
                    "/spaces",
                    dict[str, JsonType],
                    query={"keys": key, "status": "current"},
                )
                results = typing.cast(list[JsonType], data["results"])
                if len(results) != 1:
                    raise ConfluenceError(f"unique space not found with key: {key}")

                result = typing.cast(dict[str, JsonType], results[0])
                id = typing.cast(str, result["id"])

                self._space_key_to_id[key] = id
                # Populate reverse cache
                self._space_id_to_key[id] = key

        return id

    def get_space_id(self, *, space_id: Optional[str] = None, space_key: Optional[str] = None) -> Optional[str]:
        """
        Coalesces a space ID or space key into a space ID, accounting for site default.

        :param space_id: A Confluence space ID.
        :param space_key: A Confluence space key.
        """

        if space_id is not None and space_key is not None:
            raise ConfluenceError("either space ID or space key is required; not both")

        if space_id is not None:
            return space_id

        space_key = space_key or self.site.space_key
        if space_key is not None:
            return self.space_key_to_id(space_key)

        # space ID and key are unset, and no default space is configured
        return None

    def _get_attachment_by_name_v1(self, page_id: str, filename: str) -> ConfluenceAttachment:
        """
        Retrieves a Confluence page attachment by an unprefixed file name using v1 API.

        v1 API endpoint: GET /rest/api/content/{pageId}/child/attachment?filename={filename}
        """
        from .api_mappers import map_attachment_v1_to_domain

        path = f"/content/{page_id}/child/attachment"
        data = self._get(ConfluenceVersion.VERSION_1, path, dict[str, JsonType], query={"filename": filename})

        results = typing.cast(list[JsonType], data.get("results", []))
        if len(results) != 1:
            raise ConfluenceError(f"no such attachment on page {page_id}: {filename}")
        result = typing.cast(dict[str, JsonType], results[0])
        return map_attachment_v1_to_domain(result)

    def get_attachment_by_name(self, page_id: str, filename: str) -> ConfluenceAttachment:
        """
        Retrieves a Confluence page attachment by an unprefixed file name.
        """
        if self.api_version == ConfluenceVersion.VERSION_1:
            return self._get_attachment_by_name_v1(page_id, filename)
        else:
            path = f"/pages/{page_id}/attachments"
            data = self._get(ConfluenceVersion.VERSION_2, path, dict[str, JsonType], query={"filename": filename})

            results = typing.cast(list[JsonType], data["results"])
            if len(results) != 1:
                raise ConfluenceError(f"no such attachment on page {page_id}: {filename}")
            result = typing.cast(dict[str, JsonType], results[0])
            return _json_to_object(ConfluenceAttachment, result)

    def upload_attachment(
        self,
        page_id: str,
        attachment_name: str,
        *,
        attachment_path: Optional[Path] = None,
        raw_data: Optional[bytes] = None,
        content_type: Optional[str] = None,
        comment: Optional[str] = None,
        force: bool = False,
    ) -> None:
        """
        Uploads a new attachment to a Confluence page.

        :param page_id: Confluence page ID.
        :param attachment_name: Unprefixed name unique to the page.
        :param attachment_path: Path to the file to upload as an attachment.
        :param raw_data: Raw data to upload as an attachment.
        :param content_type: Attachment MIME type.
        :param comment: Attachment description.
        :param force: Overwrite an existing attachment even if there seem to be no changes.
        """

        if attachment_path is None and raw_data is None:
            raise ArgumentError("required: `attachment_path` or `raw_data`")

        if attachment_path is not None and raw_data is not None:
            raise ArgumentError("expected: either `attachment_path` or `raw_data`")

        if content_type is None:
            if attachment_path is not None:
                name = str(attachment_path)
            else:
                name = attachment_name
            content_type, _ = mimetypes.guess_type(name, strict=True)

            if content_type is None:
                content_type = "application/octet-stream"

        if attachment_path is not None and not attachment_path.is_file():
            raise PageError(f"file not found: {attachment_path}")

        try:
            attachment = self.get_attachment_by_name(page_id, attachment_name)

            if attachment_path is not None:
                if not force and attachment.fileSize == attachment_path.stat().st_size:
                    LOGGER.info("Up-to-date attachment: %s", attachment_name)
                    return
            elif raw_data is not None:
                if not force and attachment.fileSize == len(raw_data):
                    LOGGER.info("Up-to-date embedded file: %s", attachment_name)
                    return
            else:
                raise NotImplementedError("parameter match not exhaustive")

            id = attachment.id.removeprefix("att")
            path = f"/content/{page_id}/child/attachment/{id}/data"

        except ConfluenceError:
            path = f"/content/{page_id}/child/attachment"

        url = self._build_url(ConfluenceVersion.VERSION_1, path)

        if attachment_path is not None:
            with open(attachment_path, "rb") as attachment_file:
                file_to_upload: dict[str, tuple[Optional[str], Any, str, dict[str, str]]] = {
                    "comment": (
                        None,
                        comment,
                        "text/plain; charset=utf-8",
                        {},
                    ),
                    "file": (
                        attachment_name,  # will truncate path component
                        attachment_file,
                        content_type,
                        {"Expires": "0"},
                    ),
                }
                LOGGER.info("Uploading attachment: %s", attachment_name)
                response = self.session.post(
                    url,
                    files=file_to_upload,
                    headers={
                        "X-Atlassian-Token": "no-check",
                        "Accept": "application/json",
                    },
                    verify=True,
                )
        elif raw_data is not None:
            LOGGER.info("Uploading raw data: %s", attachment_name)

            raw_file = io.BytesIO(raw_data)
            raw_file.name = attachment_name
            file_to_upload = {
                "comment": (
                    None,
                    comment,
                    "text/plain; charset=utf-8",
                    {},
                ),
                "file": (
                    attachment_name,  # will truncate path component
                    raw_file,
                    content_type,
                    {"Expires": "0"},
                ),
            }
            response = self.session.post(
                url,
                files=file_to_upload,
                headers={
                    "X-Atlassian-Token": "no-check",
                    "Accept": "application/json",
                },
                verify=True,
            )
        else:
            raise NotImplementedError("parameter match not exhaustive")

        response.raise_for_status()
        data = response.json()

        if "results" in data:
            result = data["results"][0]
        else:
            result = data

        attachment_id = result["id"]
        version = result["version"]["number"] + 1

        # ensure path component is retained in attachment name
        self._update_attachment(page_id, attachment_id, version, attachment_name)

    def _update_attachment(self, page_id: str, attachment_id: str, version: int, attachment_title: str) -> None:
        id = attachment_id.removeprefix("att")
        path = f"/content/{page_id}/child/attachment/{id}"
        request = ConfluenceUpdateAttachmentRequest(
            id=attachment_id,
            type=ConfluenceLegacyType.ATTACHMENT,
            status=ConfluenceStatus.CURRENT,
            title=attachment_title,
            version=ConfluenceContentVersion(number=version, minorEdit=True),
        )

        LOGGER.info("Updating attachment: %s", attachment_id)
        self._put(ConfluenceVersion.VERSION_1, path, request, None)

    def _get_page_properties_by_title_v1(
        self,
        title: str,
        *,
        space_id: Optional[str] = None,
        space_key: Optional[str] = None,
    ) -> ConfluencePageProperties:
        """
        Looks up a Confluence wiki page by title using v1 API.

        v1 API endpoint: GET /rest/api/content?title={title}&spaceKey={spaceKey}&type=page&expand=version,space

        :param title: The page title.
        :param space_id: The Confluence space ID (unless the default space is to be used). Exclusive with space key.
        :param space_key: The Confluence space key (unless the default space is to be used). Exclusive with space ID.
        :returns: Confluence page properties.
        """
        from .api_mappers import map_page_properties_v1_to_domain

        LOGGER.info("Looking up page with title: %s", title)

        # v1 API requires spaceKey, not spaceId
        if space_id is not None and space_key is None:
            space_key = self.space_id_to_key(space_id)
        elif space_key is None:
            # Get default space key
            default_space_id = self.get_space_id(space_id=space_id, space_key=space_key)
            if default_space_id:
                space_key = self.space_id_to_key(default_space_id)

        path = "/content"
        query = {
            "title": title,
            "type": "page",
            "expand": "version,space",
        }
        if space_key is not None:
            query["spaceKey"] = space_key

        data = self._get(ConfluenceVersion.VERSION_1, path, dict[str, JsonType], query=query)
        results = typing.cast(list[JsonType], data.get("results", []))
        if len(results) != 1:
            raise ConfluenceError(f"unique page not found with title: {title}")

        return map_page_properties_v1_to_domain(results[0])

    def get_page_properties_by_title(
        self,
        title: str,
        *,
        space_id: Optional[str] = None,
        space_key: Optional[str] = None,
    ) -> ConfluencePageProperties:
        """
        Looks up a Confluence wiki page ID by title.

        :param title: The page title.
        :param space_id: The Confluence space ID (unless the default space is to be used). Exclusive with space key.
        :param space_key: The Confluence space key (unless the default space is to be used). Exclusive with space ID.
        :returns: Confluence page ID.
        """
        if self.api_version == ConfluenceVersion.VERSION_1:
            return self._get_page_properties_by_title_v1(title, space_id=space_id, space_key=space_key)
        else:
            LOGGER.info("Looking up page with title: %s", title)
            path = "/pages"
            query = {
                "title": title,
            }
            space_id = self.get_space_id(space_id=space_id, space_key=space_key)
            if space_id is not None:
                query["space-id"] = space_id

            data = self._get(ConfluenceVersion.VERSION_2, path, dict[str, JsonType], query=query)
            results = typing.cast(list[JsonType], data["results"])
            if len(results) != 1:
                raise ConfluenceError(f"unique page not found with title: {title}")

            page = _json_to_object(ConfluencePageProperties, results[0])
            return page

    def _get_page_v1(self, page_id: str) -> ConfluencePage:
        """
        Retrieves Confluence wiki page details and content using v1 API.

        v1 API endpoint: GET /rest/api/content/{pageId}?expand=body.storage,version,space

        :param page_id: The Confluence page ID.
        :returns: Confluence page info and content.
        """
        from .api_mappers import map_page_v1_to_domain

        path = f"/content/{page_id}"
        query = {"expand": "body.storage,version,space"}
        response = self._get(ConfluenceVersion.VERSION_1, path, dict[str, JsonType], query=query)
        return map_page_v1_to_domain(response)

    def get_page(self, page_id: str) -> ConfluencePage:
        """
        Retrieves Confluence wiki page details and content.

        :param page_id: The Confluence page ID.
        :returns: Confluence page info and content.
        """
        if self.api_version == ConfluenceVersion.VERSION_1:
            return self._get_page_v1(page_id)
        else:
            path = f"/pages/{page_id}"
            return self._get(ConfluenceVersion.VERSION_2, path, ConfluencePage, query={"body-format": "storage"})

    def _get_page_properties_v1(self, page_id: str) -> ConfluencePageProperties:
        """
        Retrieves Confluence wiki page details using v1 API.

        v1 API endpoint: GET /rest/api/content/{pageId}?expand=version,space

        :param page_id: The Confluence page ID.
        :returns: Confluence page info.
        """
        from .api_mappers import map_page_properties_v1_to_domain

        path = f"/content/{page_id}"
        query = {"expand": "version,space"}
        response = self._get(ConfluenceVersion.VERSION_1, path, dict[str, JsonType], query=query)
        return map_page_properties_v1_to_domain(response)

    def get_page_properties(self, page_id: str) -> ConfluencePageProperties:
        """
        Retrieves Confluence wiki page details.

        :param page_id: The Confluence page ID.
        :returns: Confluence page info.
        """
        if self.api_version == ConfluenceVersion.VERSION_1:
            return self._get_page_properties_v1(page_id)
        else:
            path = f"/pages/{page_id}"
            return self._get(ConfluenceVersion.VERSION_2, path, ConfluencePageProperties)

    def get_page_version(self, page_id: str) -> int:
        """
        Retrieves a Confluence wiki page version.

        :param page_id: The Confluence page ID.
        :returns: Confluence page version.
        """

        return self.get_page_properties(page_id).version.number

    def _update_page_v1(
        self,
        page_id: str,
        content: str,
        *,
        title: str,
        version: int,
    ) -> None:
        """
        Updates a page via the Confluence v1 API.

        v1 API endpoint: PUT /rest/api/content/{pageId}

        :param page_id: The Confluence page ID.
        :param content: Confluence Storage Format XHTML.
        :param title: New title to assign to the page. Needs to be unique within a space.
        :param version: New version to assign to the page.
        """
        from .api_mappers import map_update_page_to_v1

        LOGGER.info("Updating page: %s", page_id)

        # Get current page to get spaceId
        page_properties = self.get_page_properties(page_id)
        space_key = self.space_id_to_key(page_properties.spaceId)

        request = ConfluenceUpdatePageRequest(
            id=page_id,
            status=ConfluenceStatus.CURRENT,
            title=title,
            body=ConfluencePageBody(storage=ConfluencePageStorage(representation=ConfluenceRepresentation.STORAGE, value=content)),
            version=ConfluenceContentVersion(number=version, minorEdit=True),
        )

        # Map to v1 format
        v1_request = map_update_page_to_v1(page_id, request, space_key)

        path = f"/content/{page_id}"
        url = self._build_url(ConfluenceVersion.VERSION_1, path)
        response = self.session.put(
            url,
            data=json_dump_string(v1_request).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            verify=True,
        )
        response.raise_for_status()

    def update_page(
        self,
        page_id: str,
        content: str,
        *,
        title: str,
        version: int,
    ) -> None:
        """
        Updates a page via the Confluence API.

        :param page_id: The Confluence page ID.
        :param content: Confluence Storage Format XHTML.
        :param title: New title to assign to the page. Needs to be unique within a space.
        :param version: New version to assign to the page.
        """
        if self.api_version == ConfluenceVersion.VERSION_1:
            self._update_page_v1(page_id, content, title=title, version=version)
        else:
            path = f"/pages/{page_id}"
            request = ConfluenceUpdatePageRequest(
                id=page_id,
                status=ConfluenceStatus.CURRENT,
                title=title,
                body=ConfluencePageBody(storage=ConfluencePageStorage(representation=ConfluenceRepresentation.STORAGE, value=content)),
                version=ConfluenceContentVersion(number=version, minorEdit=True),
            )
            LOGGER.info("Updating page: %s", page_id)
            self._put(ConfluenceVersion.VERSION_2, path, request, None)

    def _create_page_v1(
        self,
        parent_id: str,
        title: str,
        new_content: str,
    ) -> ConfluencePage:
        """
        Creates a new page via Confluence v1 API.

        v1 API endpoint: POST /rest/api/content
        """
        from .api_mappers import map_create_page_to_v1, map_page_v1_to_domain

        LOGGER.info("Creating page: %s", title)

        parent_page = self.get_page_properties(parent_id)
        space_key = self.space_id_to_key(parent_page.spaceId)

        request = ConfluenceCreatePageRequest(
            spaceId=parent_page.spaceId,
            status=ConfluenceStatus.CURRENT,
            title=title,
            parentId=parent_id,
            body=ConfluencePageBody(
                storage=ConfluencePageStorage(
                    representation=ConfluenceRepresentation.STORAGE,
                    value=new_content,
                )
            ),
        )

        # Map to v1 format
        v1_request = map_create_page_to_v1(request, space_key)

        path = "/content"
        url = self._build_url(ConfluenceVersion.VERSION_1, path)
        response = self.session.post(
            url,
            data=json_dump_string(v1_request).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            verify=True,
        )
        response.raise_for_status()
        return map_page_v1_to_domain(response.json())

    def create_page(
        self,
        parent_id: str,
        title: str,
        new_content: str,
    ) -> ConfluencePage:
        """
        Creates a new page via Confluence API.
        """
        if self.api_version == ConfluenceVersion.VERSION_1:
            return self._create_page_v1(parent_id, title, new_content)
        else:
            LOGGER.info("Creating page: %s", title)

            parent_page = self.get_page_properties(parent_id)

            path = "/pages/"
            request = ConfluenceCreatePageRequest(
                spaceId=parent_page.spaceId,
                status=ConfluenceStatus.CURRENT,
                title=title,
                parentId=parent_id,
                body=ConfluencePageBody(
                    storage=ConfluencePageStorage(
                        representation=ConfluenceRepresentation.STORAGE,
                        value=new_content,
                    )
                ),
            )

            url = self._build_url(ConfluenceVersion.VERSION_2, path)
            response = self.session.post(
                url,
                data=json_dump_string(object_to_json(request)).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                verify=True,
            )
            response.raise_for_status()
            return _json_to_object(ConfluencePage, response.json())

    def _delete_page_v1(self, page_id: str, *, purge: bool = False) -> None:
        """
        Deletes a page via Confluence v1 API.

        v1 API endpoint: DELETE /rest/api/content/{pageId}

        :param page_id: The Confluence page ID.
        :param purge: `True` to completely purge the page, `False` to move to trash only.
        """
        path = f"/content/{page_id}"

        if purge:
            # Permanently delete with purge parameter
            query = {"status": "trashed"}
            url = self._build_url(ConfluenceVersion.VERSION_1, path, query)
            LOGGER.info("Permanently deleting page: %s", page_id)
            response = self.session.delete(url, verify=True)
            response.raise_for_status()
        else:
            # Move to trash
            url = self._build_url(ConfluenceVersion.VERSION_1, path)
            LOGGER.info("Moving page to trash: %s", page_id)
            response = self.session.delete(url, verify=True)
            response.raise_for_status()

    def delete_page(self, page_id: str, *, purge: bool = False) -> None:
        """
        Deletes a page via Confluence API.

        :param page_id: The Confluence page ID.
        :param purge: `True` to completely purge the page, `False` to move to trash only.
        """
        if self.api_version == ConfluenceVersion.VERSION_1:
            self._delete_page_v1(page_id, purge=purge)
        else:
            path = f"/pages/{page_id}"

            # move to trash
            url = self._build_url(ConfluenceVersion.VERSION_2, path)
            LOGGER.info("Moving page to trash: %s", page_id)
            response = self.session.delete(url, verify=True)
            response.raise_for_status()

            if purge:
                # purge from trash
                query = {"purge": "true"}
                url = self._build_url(ConfluenceVersion.VERSION_2, path, query)
                LOGGER.info("Permanently deleting page: %s", page_id)
                response = self.session.delete(url, verify=True)
                response.raise_for_status()

    def _page_exists_v1(
        self,
        title: str,
        *,
        space_id: Optional[str] = None,
        space_key: Optional[str] = None,
    ) -> Optional[str]:
        """
        Checks if a Confluence page exists with the given title using v1 API.

        v1 API endpoint: GET /rest/api/content?title={title}&spaceKey={spaceKey}&type=page

        :param title: Page title. Pages in the same Confluence space must have a unique title.
        :param space_id: Identifies the Confluence space by ID.
        :param space_key: Identifies the Confluence space by key.

        :returns: Confluence page ID of a matching page (if found), or `None`.
        """
        LOGGER.info("Checking if page exists with title: %s", title)

        # v1 API requires spaceKey, not spaceId
        if space_id is not None and space_key is None:
            space_key = self.space_id_to_key(space_id)
        elif space_key is None:
            # Get default space key
            default_space_id = self.get_space_id(space_id=space_id, space_key=space_key)
            if default_space_id:
                space_key = self.space_id_to_key(default_space_id)

        path = "/content"
        query = {
            "title": title,
            "type": "page",
        }
        if space_key is not None:
            query["spaceKey"] = space_key

        url = self._build_url(ConfluenceVersion.VERSION_1, path)
        response = self.session.get(
            url,
            params=query,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            verify=True,
        )
        response.raise_for_status()
        data = typing.cast(dict[str, JsonType], response.json())
        results = typing.cast(list[JsonType], data.get("results", []))

        if len(results) == 1:
            result = typing.cast(dict[str, JsonType], results[0])
            return str(result["id"])
        else:
            return None

    def page_exists(
        self,
        title: str,
        *,
        space_id: Optional[str] = None,
        space_key: Optional[str] = None,
    ) -> Optional[str]:
        """
        Checks if a Confluence page exists with the given title.

        :param title: Page title. Pages in the same Confluence space must have a unique title.
        :param space_key: Identifies the Confluence space.

        :returns: Confluence page ID of a matching page (if found), or `None`.
        """
        if self.api_version == ConfluenceVersion.VERSION_1:
            return self._page_exists_v1(title, space_id=space_id, space_key=space_key)
        else:
            space_id = self.get_space_id(space_id=space_id, space_key=space_key)
            path = "/pages"
            query = {"title": title}
            if space_id is not None:
                query["space-id"] = space_id

            LOGGER.info("Checking if page exists with title: %s", title)

            url = self._build_url(ConfluenceVersion.VERSION_2, path)
            response = self.session.get(
                url,
                params=query,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                verify=True,
            )
            response.raise_for_status()
            data = typing.cast(dict[str, JsonType], response.json())
            results = _json_to_object(list[ConfluencePageProperties], data["results"])

            if len(results) == 1:
                return results[0].id
            else:
                return None

    def get_or_create_page(self, title: str, parent_id: str) -> ConfluencePage:
        """
        Finds a page with the given title, or creates a new page if no such page exists.

        :param title: Page title. Pages in the same Confluence space must have a unique title.
        :param parent_id: Identifies the parent page for a new child page.
        """

        parent_page = self.get_page_properties(parent_id)
        page_id = self.page_exists(title, space_id=parent_page.spaceId)

        if page_id is not None:
            LOGGER.debug("Retrieving existing page: %s", page_id)
            return self.get_page(page_id)
        else:
            LOGGER.debug("Creating new page with title: %s", title)
            return self.create_page(parent_id, title, "")

    def get_labels(self, page_id: str) -> list[ConfluenceIdentifiedLabel]:
        """
        Retrieves labels for a Confluence page.

        :param page_id: The Confluence page ID.
        :returns: A list of page labels.
        """
        if self.api_version == ConfluenceVersion.VERSION_1:
            from .api_mappers import map_label_v1_to_domain

            path = f"/content/{page_id}/label"
            results = self._fetch(path)
            return [map_label_v1_to_domain(typing.cast(dict[str, JsonType], item)) for item in results]
        else:
            path = f"/pages/{page_id}/labels"
            results = self._fetch(path)
            return _json_to_object(list[ConfluenceIdentifiedLabel], results)

    def add_labels(self, page_id: str, labels: list[ConfluenceLabel]) -> None:
        """
        Adds labels to a Confluence page.

        :param page_id: The Confluence page ID.
        :param labels: A list of page labels to add.
        """

        path = f"/content/{page_id}/label"
        self._post(ConfluenceVersion.VERSION_1, path, labels, None)

    def remove_labels(self, page_id: str, labels: list[ConfluenceLabel]) -> None:
        """
        Removes labels from a Confluence page.

        :param page_id: The Confluence page ID.
        :param labels: A list of page labels to remove.
        """

        path = f"/content/{page_id}/label"
        for label in labels:
            query = {"name": label.name}

            url = self._build_url(ConfluenceVersion.VERSION_1, path, query)
            response = self.session.delete(url, verify=True)
            if response.text:
                LOGGER.debug("Received HTTP payload:\n%s", response.text)
            response.raise_for_status()

    def update_labels(self, page_id: str, labels: list[ConfluenceLabel], *, keep_existing: bool = False) -> None:
        """
        Assigns the specified labels to a Confluence page. Existing labels are removed.

        :param page_id: The Confluence page ID.
        :param labels: A list of page labels to assign.
        """

        new_labels = set(labels)
        old_labels = set(ConfluenceLabel(name=label.name, prefix=label.prefix) for label in self.get_labels(page_id))

        add_labels = list(new_labels - old_labels)
        remove_labels = list(old_labels - new_labels)

        if add_labels:
            add_labels.sort()
            self.add_labels(page_id, add_labels)
        if not keep_existing and remove_labels:
            remove_labels.sort()
            self.remove_labels(page_id, remove_labels)

    def _add_content_property_to_page_v1(self, page_id: str, property: ConfluenceContentProperty) -> ConfluenceIdentifiedContentProperty:
        """
        Adds a new content property to a Confluence page using v1 API.

        v1 API endpoint: POST /rest/api/content/{pageId}/property

        :param page_id: The Confluence page ID.
        :param property: Content property to add.
        :returns: The created content property with ID.
        """
        from .api_mappers import map_property_v1_to_domain

        path = f"/content/{page_id}/property"

        # v1 API expects the property object directly
        request_body = {
            "key": property.key,
            "value": property.value
        }

        response_data = self._post(ConfluenceVersion.VERSION_1, path, request_body, dict[str, JsonType])
        return map_property_v1_to_domain(response_data)

    def _remove_content_property_from_page_v1(self, page_id: str, property_id: str) -> None:
        """
        Removes a content property from a Confluence page using v1 API.

        v1 API endpoint: DELETE /rest/api/content/{pageId}/property/{key}

        Note: v1 API uses property key in URL, not property ID. We need to look up the key first.
        This requires an additional API call to fetch all properties and find the matching ID.

        Performance consideration: This adds one extra GET request per delete operation.

        :param page_id: The Confluence page ID.
        :param property_id: Property ID, which uniquely identifies the property.
        """
        # First, get all properties to find the key for this ID
        # Limitation: v1 API requires key not ID, so we must look it up
        properties = self.get_content_properties_for_page(page_id)

        # Find the property with matching ID
        property_key = None
        for prop in properties:
            if prop.id == property_id:
                property_key = prop.key
                break

        if property_key is None:
            raise PageError(f"Property with ID {property_id} not found on page {page_id}")

        # Now delete using the key
        path = f"/content/{page_id}/property/{property_key}"
        url = self._build_url(ConfluenceVersion.VERSION_1, path)
        response = self.session.delete(url, verify=True)
        response.raise_for_status()

    def get_content_properties_for_page(self, page_id: str) -> list[ConfluenceIdentifiedContentProperty]:
        """
        Retrieves content properties for a Confluence page.

        :param page_id: The Confluence page ID.
        :returns: A list of content properties.
        """
        if self.api_version == ConfluenceVersion.VERSION_1:
            from .api_mappers import map_property_v1_to_domain

            path = f"/content/{page_id}/property"
            results = self._fetch(path)
            return [map_property_v1_to_domain(typing.cast(dict[str, JsonType], item)) for item in results]
        else:
            path = f"/pages/{page_id}/properties"
            results = self._fetch(path)
            return _json_to_object(list[ConfluenceIdentifiedContentProperty], results)

    def add_content_property_to_page(self, page_id: str, property: ConfluenceContentProperty) -> ConfluenceIdentifiedContentProperty:
        """
        Adds a new content property to a Confluence page.

        :param page_id: The Confluence page ID.
        :param property: Content property to add.
        """
        if self.api_version == ConfluenceVersion.VERSION_1:
            return self._add_content_property_to_page_v1(page_id, property)
        else:
            path = f"/pages/{page_id}/properties"
            return self._post(ConfluenceVersion.VERSION_2, path, property, ConfluenceIdentifiedContentProperty)

    def remove_content_property_from_page(self, page_id: str, property_id: str) -> None:
        """
        Removes a content property from a Confluence page.

        :param page_id: The Confluence page ID.
        :param property_id: Property ID, which uniquely identifies the property.
        """
        if self.api_version == ConfluenceVersion.VERSION_1:
            self._remove_content_property_from_page_v1(page_id, property_id)
        else:
            path = f"/pages/{page_id}/properties/{property_id}"
            url = self._build_url(ConfluenceVersion.VERSION_2, path)
            response = self.session.delete(url, verify=True)
            response.raise_for_status()

    def _update_content_property_for_page_v1(
        self, page_id: str, property_id: str, version: int, property: ConfluenceContentProperty
    ) -> ConfluenceIdentifiedContentProperty:
        """
        Updates an existing content property associated with a Confluence page using v1 API.

        v1 API endpoint: PUT /rest/api/content/{pageId}/property/{key}

        Note: v1 API uses property key in URL, not property ID. We need to look up the key first.
        This requires an additional API call to fetch all properties and find the matching ID.

        Performance consideration: This adds one extra GET request per update operation.

        :param page_id: The Confluence page ID.
        :param property_id: Property ID, which uniquely identifies the property.
        :param version: Version number to assign.
        :param property: Content property data to assign.
        :returns: Updated content property data.
        """
        from .api_mappers import map_property_v1_to_domain

        # First, get all properties to find the key for this ID
        # Limitation: v1 API requires key not ID, so we must look it up
        properties = self.get_content_properties_for_page(page_id)

        # Find the property with matching ID
        property_key = None
        for prop in properties:
            if prop.id == property_id:
                property_key = prop.key
                break

        if property_key is None:
            raise PageError(f"Property with ID {property_id} not found on page {page_id}")

        # v1 API expects key, value, and version
        request_body = {
            "key": property.key,
            "value": property.value,
            "version": {
                "number": version
            }
        }

        path = f"/content/{page_id}/property/{property_key}"
        response_data = self._put(ConfluenceVersion.VERSION_1, path, request_body, dict[str, JsonType])
        return map_property_v1_to_domain(response_data)

    def update_content_property_for_page(
        self, page_id: str, property_id: str, version: int, property: ConfluenceContentProperty
    ) -> ConfluenceIdentifiedContentProperty:
        """
        Updates an existing content property associated with a Confluence page.

        :param page_id: The Confluence page ID.
        :param property_id: Property ID, which uniquely identifies the property.
        :param version: Version number to assign.
        :param property: Content property data to assign.
        :returns: Updated content property data.
        """
        if self.api_version == ConfluenceVersion.VERSION_1:
            return self._update_content_property_for_page_v1(page_id, property_id, version, property)
        else:
            path = f"/pages/{page_id}/properties/{property_id}"
            return self._put(
                ConfluenceVersion.VERSION_2,
                path,
                ConfluenceVersionedContentProperty(
                    key=property.key,
                    value=property.value,
                    version=ConfluenceContentVersion(number=version),
                ),
                ConfluenceIdentifiedContentProperty,
            )

    def update_content_properties_for_page(self, page_id: str, properties: list[ConfluenceContentProperty], *, keep_existing: bool = False) -> None:
        """
        Updates content properties associated with a Confluence page.

        :param page_id: The Confluence page ID.
        :param properties: A list of content property data to update.
        :param keep_existing: Whether to keep content property data whose key is not included in the list of properties passed as an argument.
        """

        old_mapping = {p.key: p for p in self.get_content_properties_for_page(page_id)}
        new_mapping = {p.key: p for p in properties}

        new_props = set(p.key for p in properties)
        old_props = set(old_mapping.keys())

        add_props = list(new_props - old_props)
        remove_props = list(old_props - new_props)
        update_props = list(old_props & new_props)

        if add_props:
            add_props.sort()
            for key in add_props:
                self.add_content_property_to_page(page_id, new_mapping[key])
        if not keep_existing and remove_props:
            remove_props.sort()
            for key in remove_props:
                self.remove_content_property_from_page(page_id, old_mapping[key].id)
        if update_props:
            update_props.sort()
            for key in update_props:
                old_prop = old_mapping[key]
                new_prop = new_mapping[key]
                if old_prop.value == new_prop.value:
                    continue
                self.update_content_property_for_page(page_id, old_prop.id, old_prop.version.number + 1, new_prop)
