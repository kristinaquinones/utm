# Copyright (C) 2026 Kristina Quinones
# SPDX-License-Identifier: GPL-2.0-only

from app.store import JsonStore


def test_json_store_creates_updates_and_deletes_links(tmp_path) -> None:
    store = JsonStore(str(tmp_path / "utm-data.json"))
    link = store.create_link(
        {
            "name": "Newsletter",
            "base_url": "https://example.com",
            "params": {"utm_source": "email"},
            "generated_url": "https://example.com?utm_source=email",
        }
    )

    assert store.get_link(link["id"])["name"] == "Newsletter"

    store.update_link(link["id"], {"name": "Updated"})
    assert store.get_link(link["id"])["name"] == "Updated"

    assert store.delete_link(link["id"]) is True
    assert store.get_link(link["id"]) is None
