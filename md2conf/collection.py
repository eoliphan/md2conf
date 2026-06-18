"""
Publish Markdown files to Confluence wiki.

Copyright 2022-2025, Levente Hunyadi

:see: https://github.com/hunyadi/md2conf
"""

from pathlib import Path
from typing import Generic, Iterable, Optional, TypeVar

from .metadata import ConfluencePageMetadata

K = TypeVar("K")
V = TypeVar("V")


class KeyValueCollection(Generic[K, V]):
    _collection: dict[K, V]

    def __init__(self) -> None:
        self._collection = {}

    def __len__(self) -> int:
        return len(self._collection)

    def __contains__(self, key: object) -> bool:
        return key in self._collection

    def add(self, key: K, data: V) -> None:
        self._collection[key] = data

    def get(self, key: K) -> Optional[V]:
        return self._collection.get(key)

    def items(self) -> Iterable[tuple[K, V]]:
        return self._collection.items()


class ConfluencePageCollection(KeyValueCollection[Path, ConfluencePageMetadata]): ...


class ConfluenceUserCollection(KeyValueCollection[str, tuple[str, str]]):
    """
    Maps Confluence user email addresses to their CSF mention attribute.

    Stored as ``(ri_attribute_name, ri_attribute_value)``, e.g.:
    - Cloud/v2: ``("ri:account-id", "557058:abc-def")``
    - Data Center/v1: ``("ri:username", "jsmith")``
    """

    ...
