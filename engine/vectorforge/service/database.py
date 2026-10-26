"""Registry of open collections under one data directory."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from vectorforge.collection import Collection
from vectorforge.storage.metadata import Manifest


class CollectionNotFoundError(KeyError):
    pass


class Database:
    def __init__(self, root: Path) -> None:
        self.root = root
        self._collections: dict[str, Collection] = {}
        # Guards the name -> collection map only; each collection has its own lock for data.
        self._lock = threading.Lock()
        self.ready = False

    def load_all(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        for child in sorted(self.root.iterdir()):
            if (child / Manifest.FILENAME).exists():
                self._collections[child.name] = Collection.open(child)
        self.ready = True

    def close_all(self) -> None:
        self.ready = False
        with self._lock:
            for c in self._collections.values():
                c.close()
            self._collections.clear()

    def names(self) -> list[str]:
        with self._lock:
            return sorted(self._collections)

    def get(self, name: str) -> Collection:
        with self._lock:
            c = self._collections.get(name)
        if c is None:
            raise CollectionNotFoundError(name)
        return c

    def create(self, name: str, **kwargs: Any) -> Collection:
        with self._lock:
            if name in self._collections:
                raise FileExistsError(name)
            c = Collection.create(self.root, name, **kwargs)
            self._collections[name] = c
            return c

    def drop(self, name: str) -> None:
        with self._lock:
            c = self._collections.pop(name, None)
        if c is None:
            raise CollectionNotFoundError(name)
        c.drop()

    def sizes(self) -> dict[str, tuple[int, int]]:
        with self._lock:
            return {n: (c.count, c.deleted_count) for n, c in self._collections.items()}
