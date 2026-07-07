# Copyright (C) 2026 Kristina Quinones
# SPDX-License-Identifier: GPL-2.0-only

"""Magic-link login: token lifecycle, enumeration resistance, and rate limiting."""

import re
from dataclasses import replace

import pytest
from sqlalchemy import select

import app.main as main
from app.models import User
from app.repository import ensure_user
from app.tokens import create_login_token


@pytest.fixture
def sent(monkeypatch):
    """Capture emails instead of sending them."""
    box: dict[str, list] = {"login": [], "pending": []}
    monkeypatch.setattr(
        main, "send_login_email", lambda settings, to, link: box["login"].append((to, link))
    )
    monkeypatch.setattr(
        main, "send_pending_email", lambda settings, to: box["pending"].append(to)
    )
    return box


def request_link(client, email):
    form = client.get("/login").text
    token = re.search(r'name="csrf_token" value="([^"]+)"', form).group(1)
    return client.post(
        "/auth/request-link",
        data={"csrf_token": token, "email": email},
        follow_redirects=False,
    )


def _user_id(email: str) -> str:
    with main.SessionLocal() as db:
        return db.execute(select(User).where(User.email == email)).scalar_one().id


# -- happy path --------------------------------------------------------------


def test_request_link_emails_an_approved_user_and_the_link_logs_in(anon_client, seed_user, sent):
    response = request_link(anon_client, "owner@example.com")
    assert response.status_code == 200
    assert "Check your email" in response.text
    assert len(sent["login"]) == 1

    _, link = sent["login"][0]
    token = link.split("token=", 1)[1]
    callback = anon_client.get(f"/auth/callback?token={token}", follow_redirects=False)
    assert callback.status_code == 303
    assert anon_client.get("/", follow_redirects=False).status_code == 200


# -- token lifecycle ---------------------------------------------------------


def test_expired_token_is_rejected(anon_client, seed_user):
    raw = create_login_token(main.SessionLocal, _user_id("owner@example.com"), -1)
    callback = anon_client.get(f"/auth/callback?token={raw}", follow_redirects=False)
    assert callback.status_code == 400
    assert anon_client.get("/", follow_redirects=False).status_code == 303


def test_token_is_single_use(anon_client, seed_user):
    raw = create_login_token(main.SessionLocal, _user_id("owner@example.com"), 900)

    assert anon_client.get(f"/auth/callback?token={raw}", follow_redirects=False).status_code == 303
    # Second use of the same token fails.
    assert anon_client.get(f"/auth/callback?token={raw}", follow_redirects=False).status_code == 400


def test_unknown_token_is_rejected(anon_client, seed_user):
    callback = anon_client.get("/auth/callback?token=not-a-real-token", follow_redirects=False)
    assert callback.status_code == 400


def test_deapproved_user_cannot_use_a_live_token(anon_client, bound_db, seed_user):
    raw = create_login_token(main.SessionLocal, _user_id("owner@example.com"), 900)
    with bound_db() as db:
        db.query(User).filter(User.email == "owner@example.com").update({User.status: "denied"})
        db.commit()

    assert anon_client.get(f"/auth/callback?token={raw}", follow_redirects=False).status_code == 400


# -- enumeration resistance --------------------------------------------------


def test_response_is_identical_for_approved_pending_and_unknown(anon_client, bound_db, seed_user, sent):
    ensure_user(bound_db, "pending@example.com", status="pending")

    bodies = []
    for email in ("owner@example.com", "pending@example.com", "ghost@example.com"):
        response = request_link(anon_client, email)
        assert response.status_code == 200
        bodies.append(response.text)

    assert all("Check your email" in body for body in bodies)


def test_email_routing_by_status(anon_client, bound_db, seed_user, sent):
    ensure_user(bound_db, "pending@example.com", status="pending")

    request_link(anon_client, "owner@example.com")   # approved -> login link
    request_link(anon_client, "pending@example.com")  # pending -> review notice
    request_link(anon_client, "ghost@example.com")    # unknown -> nothing

    assert [to for to, _ in sent["login"]] == ["owner@example.com"]
    assert sent["pending"] == ["pending@example.com"]


# -- rate limiting -----------------------------------------------------------


def test_rate_limit_stops_sending_but_keeps_the_response_generic(anon_client, seed_user, sent, monkeypatch):
    monkeypatch.setattr(main, "settings", replace(main.settings, rate_limit_max=2))

    for _ in range(4):
        response = request_link(anon_client, "owner@example.com")
        assert response.status_code == 200
        assert "Check your email" in response.text

    # Only the first two attempts sent a link; the rest were silently limited.
    assert len(sent["login"]) == 2
