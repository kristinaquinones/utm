# Copyright (C) 2026 Kristina Quinones
# SPDX-License-Identifier: GPL-2.0-only

"""Sessions, the auth gate, per-session CSRF, and session revocation."""

import re
from dataclasses import replace

from fastapi.testclient import TestClient

import app.main as main
from app.models import User
from app.repository import ensure_user

from tests.conftest import login


def _csrf(client: TestClient) -> str:
    match = re.search(r'name="csrf-token" content="([^"]+)"', client.get("/").text)
    assert match
    return match.group(1)


# -- the gate ----------------------------------------------------------------


def test_gate_redirects_anonymous_to_login(anon_client) -> None:
    response = anon_client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_login_page_is_reachable_anonymously(anon_client) -> None:
    response = anon_client.get("/login")
    assert response.status_code == 200
    assert "Sign in" in response.text


def test_healthz_is_public(anon_client) -> None:
    response = anon_client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_gate_returns_401_json_for_fetch_requests(anon_client) -> None:
    response = anon_client.post(
        "/links",
        data={"base_url": "https://example.com"},
        headers={"X-Requested-With": "fetch"},
        follow_redirects=False,
    )
    assert response.status_code == 401
    assert response.json()["ok"] is False


# -- login / logout ----------------------------------------------------------


def test_login_then_logout(anon_client, seed_user) -> None:
    login(anon_client, "owner@example.com")

    home = anon_client.get("/")
    assert home.status_code == 200
    assert "Log out" in home.text

    token = _csrf(anon_client)
    out = anon_client.post("/logout", data={"csrf_token": token}, follow_redirects=False)
    assert out.status_code == 303
    assert out.headers["location"] == "/login"

    # Session is gone: protected routes redirect again.
    assert anon_client.get("/", follow_redirects=False).status_code == 303


def test_login_rejects_unapproved_email(anon_client, bound_db) -> None:
    ensure_user(bound_db, "pending@example.com", status="pending")

    token = re.search(
        r'name="csrf_token" value="([^"]+)"', anon_client.get("/login").text
    ).group(1)
    response = anon_client.post(
        "/login",
        data={"csrf_token": token, "email": "pending@example.com"},
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "No approved account" in response.text
    # No session was established.
    assert anon_client.get("/", follow_redirects=False).status_code == 303


# -- CSRF --------------------------------------------------------------------


def test_login_post_requires_anonymous_csrf(anon_client, seed_user) -> None:
    # No CSRF token issued to this request -> rejected before any session exists.
    response = anon_client.post("/login", data={"email": "owner@example.com"})
    assert response.status_code == 403


def test_csrf_token_is_not_valid_across_sessions(anon_client, seed_user) -> None:
    login(anon_client, "owner@example.com")
    stolen = _csrf(anon_client)

    other = TestClient(main.app)
    login(other, "owner@example.com")

    # A token minted for `anon_client`'s session is rejected on `other`'s.
    forged = other.post(
        "/templates",
        data={"csrf_token": stolen, "template_name": "x", "utm_source": "s"},
        headers={"X-Requested-With": "fetch"},
    )
    assert forged.status_code == 403

    # `other`'s own token works.
    ok = other.post(
        "/templates",
        data={"csrf_token": _csrf(other), "template_name": "x", "utm_source": "s"},
        headers={"X-Requested-With": "fetch"},
    )
    assert ok.status_code == 200


# -- session hardening (revocation + absolute lifetime) ----------------------


def test_bumping_session_epoch_revokes_the_session(client, bound_db, seed_user) -> None:
    assert client.get("/", follow_redirects=False).status_code == 200

    with bound_db() as db:
        db.query(User).filter(User.id == seed_user).update(
            {User.session_epoch: User.session_epoch + 1}
        )
        db.commit()

    # The cookie still validates its signature but its epoch is now stale.
    assert client.get("/", follow_redirects=False).status_code == 303


def test_absolute_lifetime_expires_the_session(client, monkeypatch) -> None:
    assert client.get("/", follow_redirects=False).status_code == 200

    monkeypatch.setattr(
        main, "settings", replace(main.settings, session_absolute_max_age=-1)
    )
    assert client.get("/", follow_redirects=False).status_code == 303


# -- tenant isolation through the HTTP stack --------------------------------


def test_tenants_only_see_their_own_links(anon_client, bound_db, seed_user) -> None:
    ensure_user(bound_db, "bob@example.com", status="approved")

    login(anon_client, "owner@example.com")
    owner_token = _csrf(anon_client)
    anon_client.post(
        "/links",
        data={
            "csrf_token": owner_token,
            "name": "Owner link",
            "base_url": "https://example.com",
            "utm_source": "email",
        },
        headers={"X-Requested-With": "fetch"},
    )

    bob = TestClient(main.app)
    login(bob, "bob@example.com")
    assert "Owner link" not in bob.get("/").text
