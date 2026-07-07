# Copyright (C) 2026 Kristina Quinones
# SPDX-License-Identifier: GPL-2.0-only

"""Shared fixtures for the route, repository, and auth tests.

Each test gets a throwaway SQLite database that the *whole* app uses: the auth
middleware, the login route, and the tenant store all read through the module's
``SessionLocal``, which is repointed at the test database here. The ``client``
fixture then signs in via the dev-login bridge so protected routes are reachable.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.main as main
from app.db import Base
from app.repository import Store, ensure_user


@pytest.fixture
def session_factory(tmp_path) -> sessionmaker:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


@pytest.fixture
def bound_db(session_factory: sessionmaker, monkeypatch) -> sessionmaker:
    # Point every DB touchpoint in the app (middleware, login, store) at the
    # test database for the duration of the test.
    monkeypatch.setattr(main, "SessionLocal", session_factory)
    return session_factory


@pytest.fixture
def seed_user(bound_db: sessionmaker) -> str:
    return ensure_user(bound_db, "owner@example.com", is_admin=True, status="approved")


@pytest.fixture
def store(bound_db: sessionmaker, seed_user: str) -> Store:
    return Store(bound_db, seed_user)


@pytest.fixture
def anon_client(bound_db: sessionmaker) -> TestClient:
    return TestClient(main.app)


@pytest.fixture
def client(anon_client: TestClient, seed_user: str) -> TestClient:
    login(anon_client, "owner@example.com")
    return anon_client


def login(client: TestClient, email: str) -> None:
    """Sign a client in through the dev-login bridge."""
    token = _login_csrf(client)
    response = client.post(
        "/login",
        data={"csrf_token": token, "email": email},
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text


def _login_csrf(client: TestClient) -> str:
    page = client.get("/login")
    match = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
    assert match, "no CSRF token on the login form"
    return match.group(1)
