"""
Publish Markdown files to Confluence wiki.

Copyright 2022-2025, Levente Hunyadi

:see: https://github.com/hunyadi/md2conf
"""

import os
from typing import Literal, Optional, overload


class ArgumentError(ValueError):
    "Raised when wrong arguments are passed to a function call."


class PageError(ValueError):
    "Raised in case there is an issue with a Confluence page."


class ConfluenceError(RuntimeError):
    "Raised when a Confluence API call fails."


@overload
def _validate_domain(domain: str) -> str: ...


@overload
def _validate_domain(domain: Optional[str]) -> Optional[str]: ...


def _validate_domain(domain: Optional[str]) -> Optional[str]:
    if domain is None:
        return None

    if domain.startswith(("http://", "https://")) or domain.endswith("/"):
        raise ArgumentError("Confluence domain looks like a URL; only host name required")

    return domain


@overload
def _validate_base_path(base_path: str) -> str: ...


@overload
def _validate_base_path(base_path: Optional[str]) -> Optional[str]: ...


def _validate_base_path(base_path: Optional[str]) -> Optional[str]:
    if base_path is None:
        return None

    if not base_path.startswith("/") or not base_path.endswith("/"):
        raise ArgumentError("Confluence base path must start and end with a '/'")

    return base_path


@overload
def _validate_deployment_type(deployment_type: str) -> Literal["cloud", "datacenter", "server"]: ...


@overload
def _validate_deployment_type(deployment_type: Optional[str]) -> Optional[Literal["cloud", "datacenter", "server"]]: ...


def _validate_deployment_type(deployment_type: Optional[str]) -> Optional[Literal["cloud", "datacenter", "server"]]:
    if deployment_type is None:
        return None

    deployment_type_lower = deployment_type.lower()
    if deployment_type_lower not in ("cloud", "datacenter", "server"):
        raise ArgumentError(f"Invalid deployment type '{deployment_type}'; must be one of: 'cloud', 'datacenter', 'server'")

    return deployment_type_lower  # type: ignore


class ConfluenceSiteProperties:
    domain: str
    base_path: str
    space_key: Optional[str]

    def __init__(
        self,
        domain: Optional[str] = None,
        base_path: Optional[str] = None,
        space_key: Optional[str] = None,
    ) -> None:
        opt_domain = domain or os.getenv("CONFLUENCE_DOMAIN")
        opt_base_path = base_path or os.getenv("CONFLUENCE_PATH")
        opt_space_key = space_key or os.getenv("CONFLUENCE_SPACE_KEY")

        if not opt_domain:
            raise ArgumentError("Confluence domain not specified")
        if not opt_base_path:
            opt_base_path = "/wiki/"

        self.domain = _validate_domain(opt_domain)
        self.base_path = _validate_base_path(opt_base_path)
        self.space_key = opt_space_key


class ConfluenceConnectionProperties:
    """
    Properties related to connecting to Confluence.

    :param api_url: Confluence API URL. Required for scoped tokens.
    :param user_name: Confluence user name.
    :param api_key: Confluence API key.
    :param deployment_type: Confluence deployment type (cloud, datacenter, or server).
    :param headers: Additional HTTP headers to pass to Confluence REST API calls.
    """

    domain: Optional[str]
    base_path: Optional[str]
    space_key: Optional[str]
    api_url: Optional[str]
    user_name: Optional[str]
    api_key: str
    deployment_type: Optional[Literal["cloud", "datacenter", "server"]]
    headers: Optional[dict[str, str]]

    def __init__(
        self,
        *,
        api_url: Optional[str] = None,
        domain: Optional[str] = None,
        base_path: Optional[str] = None,
        user_name: Optional[str] = None,
        api_key: Optional[str] = None,
        space_key: Optional[str] = None,
        deployment_type: Optional[str] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> None:
        opt_api_url = api_url or os.getenv("CONFLUENCE_API_URL")
        opt_domain = domain or os.getenv("CONFLUENCE_DOMAIN")
        opt_base_path = base_path or os.getenv("CONFLUENCE_PATH")
        opt_space_key = space_key or os.getenv("CONFLUENCE_SPACE_KEY")
        opt_user_name = user_name or os.getenv("CONFLUENCE_USER_NAME")
        opt_api_key = api_key or os.getenv("CONFLUENCE_API_KEY")
        opt_deployment_type = deployment_type or os.getenv("CONFLUENCE_DEPLOYMENT_TYPE")

        if not opt_api_key:
            raise ArgumentError("Confluence API key not specified")
        if not opt_api_url and not opt_domain:
            raise ArgumentError("Confluence API URL or domain required")
        if not opt_api_url and not opt_base_path:
            opt_base_path = "/wiki/"

        self.api_url = opt_api_url
        self.domain = _validate_domain(opt_domain)
        self.base_path = _validate_base_path(opt_base_path)
        self.space_key = opt_space_key
        self.user_name = opt_user_name
        self.api_key = opt_api_key
        self.deployment_type = _validate_deployment_type(opt_deployment_type)
        self.headers = headers
