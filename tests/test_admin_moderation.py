# Copyright (C) 2026 Kristina Quinones
# SPDX-License-Identifier: GPL-2.0-only

"""Admin moderation: cross-tenant audit, content takedown, suspend, audit log.

The trust model here is deliberate: an admin can view and remove *any* tenant's
content and suspend accounts. The isolation invariant still holds — every query
targets a single user_id; the admin route just chooses whose.
"""

import re

from fastapi.testclient import TestClient
from sqlalchemy import select

import app.main as main
from app import accounts
from app.models import AdminAction, User
from app.repository import Store, ensure_user

from tests.conftest import login


def _csrf(client):
    return re.search(r'name="csrf-token" content="([^"]+)"', client.get("/").text).group(1)


def _make_user_with_link(bound_db, email, status="approved"):
    user_id = ensure_user(bound_db, email, status=status)
    link = Store(bound_db, user_id).create_link(
        {
            "name": "Spammy Link",
            "base_url": "https://evil.example",
            "params": {"utm_source": "spam"},
            "generated_url": "https://evil.example?utm_source=spam",
        }
    )
    return user_id, link


def _user_id(bound_db, email):
    with bound_db() as db:
        return db.execute(select(User).where(User.email == email)).scalar_one().id


# -- admin listing + audit view ---------------------------------------------


def test_admin_page_lists_all_users(client, bound_db, seed_user):
    ensure_user(bound_db, "bob@example.com", status="approved")

    response = client.get("/admin")
    assert response.status_code == 200
    assert "All users" in response.text
    assert "bob@example.com" in response.text


def test_admin_can_view_another_tenants_content(client, bound_db, seed_user):
    bob_id, _ = _make_user_with_link(bound_db, "bob@example.com")

    response = client.get(f"/admin/users/{bob_id}")
    assert response.status_code == 200
    assert "bob@example.com" in response.text
    assert "Spammy Link" in response.text


# -- content takedown --------------------------------------------------------


def test_admin_can_take_down_a_link_and_it_is_logged(client, bound_db, seed_user):
    bob_id, link = _make_user_with_link(bound_db, "bob@example.com")

    response = client.post(
        f"/admin/users/{bob_id}/links/{link['id']}/delete",
        data={"csrf_token": _csrf(client)},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert Store(bound_db, bob_id).get_link(link["id"]) is None

    with bound_db() as db:
        actions = db.execute(
            select(AdminAction).where(AdminAction.action == "delete_link")
        ).scalars().all()
    assert len(actions) == 1
    assert actions[0].admin_id == seed_user
    assert actions[0].target_user_id == bob_id
    assert actions[0].detail == link["id"]


def test_takedown_stays_single_tenant_scoped(client, bound_db, seed_user):
    bob_id, _ = _make_user_with_link(bound_db, "bob@example.com")
    alice_id, alice_link = _make_user_with_link(bound_db, "alice@example.com")

    # Alice's link id under Bob's path must not delete Alice's link.
    client.post(
        f"/admin/users/{bob_id}/links/{alice_link['id']}/delete",
        data={"csrf_token": _csrf(client)},
        follow_redirects=False,
    )
    assert Store(bound_db, alice_id).get_link(alice_link["id"]) is not None


# -- suspend / reinstate -----------------------------------------------------


def test_admin_can_suspend_and_reinstate_an_approved_user(client, bound_db, seed_user):
    bob_id = ensure_user(bound_db, "bob@example.com", status="approved")

    client.post(f"/admin/users/{bob_id}/deny", data={"csrf_token": _csrf(client)}, follow_redirects=False)
    assert accounts.get_user(bound_db, bob_id)["status"] == "denied"

    client.post(f"/admin/users/{bob_id}/approve", data={"csrf_token": _csrf(client)}, follow_redirects=False)
    assert accounts.get_user(bound_db, bob_id)["status"] == "approved"

    with bound_db() as db:
        actions = {a.action for a in db.execute(select(AdminAction)).scalars().all()}
    assert {"suspend", "approve"} <= actions


def test_suspended_user_is_locked_out(client, bound_db, seed_user):
    bob_id = ensure_user(bound_db, "bob@example.com", status="approved")
    bob = TestClient(main.app)
    login(bob, "bob@example.com")
    assert bob.get("/", follow_redirects=False).status_code == 200

    client.post(f"/admin/users/{bob_id}/deny", data={"csrf_token": _csrf(client)}, follow_redirects=False)

    # Bob's still-signed cookie no longer validates (status != approved).
    assert bob.get("/", follow_redirects=False).status_code == 303


def test_admin_cannot_suspend_another_admin(client, bound_db, seed_user):
    accounts.promote_admins(bound_db, ("carol@example.com",))
    carol_id = _user_id(bound_db, "carol@example.com")

    client.post(f"/admin/users/{carol_id}/deny", data={"csrf_token": _csrf(client)}, follow_redirects=False)

    assert accounts.get_user(bound_db, carol_id)["status"] == "approved"


# -- authorization -----------------------------------------------------------


def test_non_admin_and_anon_cannot_moderate(anon_client, bound_db, seed_user):
    bob_id, link = _make_user_with_link(bound_db, "bob@example.com")

    # Anonymous -> redirected to login.
    assert anon_client.get(f"/admin/users/{bob_id}", follow_redirects=False).status_code == 303

    # Logged-in non-admin -> 403 on both view and takedown.
    ensure_user(bound_db, "member@example.com", status="approved")
    member = TestClient(main.app)
    login(member, "member@example.com")
    assert member.get(f"/admin/users/{bob_id}", follow_redirects=False).status_code == 403
    assert member.post(
        f"/admin/users/{bob_id}/links/{link['id']}/delete",
        data={"csrf_token": _csrf(member)},
        follow_redirects=False,
    ).status_code == 403
    # The link survived the blocked attempt.
    assert Store(bound_db, bob_id).get_link(link["id"]) is not None
