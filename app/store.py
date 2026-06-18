from __future__ import annotations

import json
import os
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_DATA = {"links": [], "templates": []}


class JsonStore:
    def __init__(self, path: str | None = None) -> None:
        self.path = Path(path or os.getenv("DATA_PATH", "data/utm-data.json"))
        self._lock = threading.Lock()

    def all(self) -> dict[str, list[dict[str, Any]]]:
        with self._lock:
            return self._read()

    def list_links(self) -> list[dict[str, Any]]:
        return sorted(self.all()["links"], key=lambda item: item["updated_at"], reverse=True)

    def list_templates(self) -> list[dict[str, Any]]:
        return sorted(self.all()["templates"], key=lambda item: item["name"].lower())

    def get_link(self, link_id: str) -> dict[str, Any] | None:
        return self._find("links", link_id)

    def get_template(self, template_id: str) -> dict[str, Any] | None:
        return self._find("templates", template_id)

    def create_link(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._create("links", payload)

    def create_template(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._create("templates", payload)

    def update_link(self, link_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        return self._update("links", link_id, payload)

    def delete_link(self, link_id: str) -> bool:
        return self._delete("links", link_id)

    def delete_template(self, template_id: str) -> bool:
        return self._delete("templates", template_id)

    def _find(self, collection: str, item_id: str) -> dict[str, Any] | None:
        for item in self.all()[collection]:
            if item["id"] == item_id:
                return item
        return None

    def _create(self, collection: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = _now()
        item = {
            "id": uuid.uuid4().hex,
            "created_at": now,
            "updated_at": now,
            **payload,
        }

        with self._lock:
            data = self._read()
            data[collection].append(item)
            self._write(data)

        return item

    def _update(self, collection: str, item_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        with self._lock:
            data = self._read()
            for index, item in enumerate(data[collection]):
                if item["id"] == item_id:
                    updated = {**item, **payload, "updated_at": _now()}
                    data[collection][index] = updated
                    self._write(data)
                    return updated
        return None

    def _delete(self, collection: str, item_id: str) -> bool:
        with self._lock:
            data = self._read()
            original_count = len(data[collection])
            data[collection] = [item for item in data[collection] if item["id"] != item_id]
            deleted = len(data[collection]) != original_count
            if deleted:
                self._write(data)
            return deleted

    def _read(self) -> dict[str, list[dict[str, Any]]]:
        if not self.path.exists():
            return deepcopy(DEFAULT_DATA)

        with self.path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        return {
            "links": data.get("links", []),
            "templates": data.get("templates", []),
        }

    def _write(self, data: dict[str, list[dict[str, Any]]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(".tmp")
        with temp_path.open("w", encoding="utf-8") as file:
            json.dump(data, file, indent=2)
            file.write("\n")
        temp_path.replace(self.path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
