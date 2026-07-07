# Copyright (C) 2026 Kristina Quinones
# SPDX-License-Identifier: GPL-2.0-only

"""Repository behavior and the tenant-isolation invariant.

Isolation is the #1 new security guarantee: a ``Store`` bound to one tenant must
never read or mutate another tenant's rows, even when handed a valid id that
belongs to someone else.
"""

import pytest

from app.repository import Store, ensure_user, normalize_email


@pytest.fixture
def alice(session_factory) -> Store:
    return Store(session_factory, ensure_user(session_factory, "alice@example.com", status="approved"))


@pytest.fixture
def bob(session_factory) -> Store:
    return Store(session_factory, ensure_user(session_factory, "bob@example.com", status="approved"))


def _link_payload(name: str = "Newsletter") -> dict:
    return {
        "name": name,
        "base_url": "https://example.com",
        "params": {"utm_source": "email"},
        "generated_url": "https://example.com?utm_source=email",
    }


# -- basic CRUD (ported from the JSON store) --------------------------------


def test_create_get_update_and_delete_link(store: Store) -> None:
    link = store.create_link(_link_payload())

    assert store.get_link(link["id"])["name"] == "Newsletter"

    store.update_link(link["id"], {"name": "Updated"})
    assert store.get_link(link["id"])["name"] == "Updated"

    assert store.delete_link(link["id"]) is True
    assert store.get_link(link["id"]) is None


def test_list_links_orders_by_updated_at_desc(store: Store) -> None:
    first = store.create_link(_link_payload("First"))
    second = store.create_link(_link_payload("Second"))
    # Touch the first so it becomes the most recently updated.
    store.update_link(first["id"], {"name": "First again"})

    names = [link["name"] for link in store.list_links()]
    assert names == ["First again", "Second"]


def test_templates_sorted_case_insensitively(store: Store) -> None:
    store.create_template({"name": "beta", "params": {}})
    store.create_template({"name": "Alpha", "params": {}})

    names = [template["name"] for template in store.list_templates()]
    assert names == ["Alpha", "beta"]

    template_id = store.list_templates()[0]["id"]
    assert store.delete_template(template_id) is True
    assert [t["name"] for t in store.list_templates()] == ["beta"]


# -- tenant isolation (the #1 invariant) ------------------------------------


def test_list_is_scoped_to_the_tenant(alice: Store, bob: Store) -> None:
    alice.create_link(_link_payload("Alice link"))
    bob.create_link(_link_payload("Bob link"))

    assert [link["name"] for link in alice.list_links()] == ["Alice link"]
    assert [link["name"] for link in bob.list_links()] == ["Bob link"]


def test_cannot_read_another_tenants_link(alice: Store, bob: Store) -> None:
    alice_link = alice.create_link(_link_payload("Alice link"))

    assert bob.get_link(alice_link["id"]) is None


def test_cannot_update_another_tenants_link(alice: Store, bob: Store) -> None:
    alice_link = alice.create_link(_link_payload("Alice link"))

    assert bob.update_link(alice_link["id"], {"name": "hijacked"}) is None
    # Alice's data is untouched.
    assert alice.get_link(alice_link["id"])["name"] == "Alice link"


def test_cannot_delete_another_tenants_link(alice: Store, bob: Store) -> None:
    alice_link = alice.create_link(_link_payload("Alice link"))

    assert bob.delete_link(alice_link["id"]) is False
    assert alice.get_link(alice_link["id"]) is not None


def test_template_isolation(alice: Store, bob: Store) -> None:
    alice_template = alice.create_template({"name": "Alice template", "params": {}})

    assert bob.get_template(alice_template["id"]) is None
    assert bob.delete_template(alice_template["id"]) is False
    assert alice.list_templates()[0]["name"] == "Alice template"


# -- user provisioning ------------------------------------------------------


def test_ensure_user_is_idempotent_and_normalizes_email(session_factory) -> None:
    first = ensure_user(session_factory, "Casey@Example.com ", status="approved")
    second = ensure_user(session_factory, "casey@example.com", status="approved")

    assert first == second
    assert normalize_email("  MixedCase@Example.COM ") == "mixedcase@example.com"
