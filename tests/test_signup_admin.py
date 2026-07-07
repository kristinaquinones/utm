# Copyright (C) 2026 Kristina Quinones
# SPDX-License-Identifier: GPL-2.0-only

"""Approval-gated signup, the admin queue, and the first-admin seed."""

import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

import app.main as main
from app import accounts
from app.models import User
from app.repository import ensure_user

from tests.conftest import login


@pytest.fixture
def mail(monkeypatch):
    box: dict[str, list] = {"signup": [], "approval": [], "login": [], "pending": []}
    monkeypatch.setattr(
        main, "send_signup_notification", lambda s, to, who: box["signup"].append((to, who))
    )
    monkeypatch.setattr(main, "send_approval_email", lambda s, to: box["approval"].append(to))
    monkeypatch.setattr(main, "send_login_email", lambda s, to, link: box["login"].append((to, link)))
    monkeypatch.setattr(main, "send_pending_email", lambda s, to: box["pending"].append(to))
    return box


def _form_csrf(client, path):
    match = re.search(r'name="csrf_token" value="([^"]+)"', client.get(path).text)
    assert match
    return match.group(1)


def do_signup(client, email, workspace=""):
    token = _form_csrf(client, "/signup")
    return client.post(
        "/signup",
        data={"csrf_token": token, "email": email, "workspace_name": workspace},
        follow_redirects=False,
    )


def request_link(client, email):
    token = _form_csrf(client, "/login")
    return client.post(
        "/auth/request-link",
        data={"csrf_token": token, "email": email},
        follow_redirects=False,
    )


def _status(email):
    with main.SessionLocal() as db:
        return db.execute(select(User).where(User.email == email)).scalar_one()


# -- signup ------------------------------------------------------------------


def test_signup_creates_pending_and_notifies_admins(anon_client, seed_user, mail):
    response = do_signup(anon_client, "new@example.com", "Acme")
    assert response.status_code == 200
    assert "Request received" in response.text

    pending = accounts.list_pending_users(main.SessionLocal)
    assert [(u["email"], u["workspace_name"]) for u in pending] == [("new@example.com", "Acme")]
    assert mail["signup"] == [("owner@example.com", "new@example.com")]


def test_signup_for_existing_email_is_silent(anon_client, seed_user, mail):
    # owner already exists (approved admin). Re-signup must not leak that, nor
    # create a pending row, nor re-notify.
    response = do_signup(anon_client, "owner@example.com")
    assert response.status_code == 200
    assert "Request received" in response.text
    assert accounts.list_pending_users(main.SessionLocal) == []
    assert mail["signup"] == []


def test_signup_does_not_resurrect_a_denied_account(anon_client, bound_db, seed_user, mail):
    ensure_user(bound_db, "denied@example.com", status="denied")

    do_signup(anon_client, "denied@example.com")

    assert _status("denied@example.com").status == "denied"
    assert accounts.list_pending_users(main.SessionLocal) == []


# -- pending users can't log in ---------------------------------------------


def test_pending_user_cannot_request_a_login_link(anon_client, seed_user, mail):
    do_signup(anon_client, "new@example.com")

    response = request_link(anon_client, "new@example.com")
    assert response.status_code == 200
    assert mail["login"] == []
    assert mail["pending"] == ["new@example.com"]


# -- admin queue -------------------------------------------------------------


def _csrf(client):
    return re.search(r'name="csrf-token" content="([^"]+)"', client.get("/").text).group(1)


def test_admin_can_approve_which_emails_and_unlocks_login(client, seed_user, mail):
    accounts.signup(main.SessionLocal, "new@example.com")
    user_id = accounts.list_pending_users(main.SessionLocal)[0]["id"]

    approved = client.post(
        f"/admin/users/{user_id}/approve",
        data={"csrf_token": _csrf(client)},
        follow_redirects=False,
    )
    assert approved.status_code == 303

    user = _status("new@example.com")
    assert user.status == "approved"
    assert user.approved_by == seed_user  # the acting admin
    assert mail["approval"] == ["new@example.com"]

    # Now the login path issues a real link.
    request_link(client, "new@example.com")
    assert [to for to, _ in mail["login"]] == ["new@example.com"]


def test_admin_can_deny(client, seed_user):
    accounts.signup(main.SessionLocal, "new@example.com")
    user_id = accounts.list_pending_users(main.SessionLocal)[0]["id"]

    denied = client.post(
        f"/admin/users/{user_id}/deny",
        data={"csrf_token": _csrf(client)},
        follow_redirects=False,
    )
    assert denied.status_code == 303
    assert _status("new@example.com").status == "denied"


def test_admin_mutations_require_csrf(client, seed_user):
    accounts.signup(main.SessionLocal, "new@example.com")
    user_id = accounts.list_pending_users(main.SessionLocal)[0]["id"]

    response = client.post(f"/admin/users/{user_id}/approve")
    assert response.status_code == 403


def test_admin_routes_require_an_admin(anon_client, bound_db, seed_user):
    # Anonymous -> redirected to login.
    assert anon_client.get("/admin", follow_redirects=False).status_code == 303

    # Logged-in non-admin -> 403.
    ensure_user(bound_db, "member@example.com", status="approved")
    member = TestClient(main.app)
    login(member, "member@example.com")
    assert member.get("/admin", follow_redirects=False).status_code == 403


# -- first-admin seed --------------------------------------------------------


def test_seed_promotes_existing_pending_admin_and_is_idempotent(bound_db):
    ensure_user(bound_db, "boss@example.com", status="pending")

    accounts.promote_admins(bound_db, ("boss@example.com",))
    user = _status("boss@example.com")
    assert user.status == "approved"
    assert user.is_admin is True

    # Running again changes nothing and creates no duplicate.
    accounts.promote_admins(bound_db, ("boss@example.com",))
    with bound_db() as db:
        count = db.execute(
            select(User).where(User.email == "boss@example.com")
        ).scalars().all()
    assert len(count) == 1
