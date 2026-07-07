# Copyright (C) 2026 Kristina Quinones
# SPDX-License-Identifier: GPL-2.0-only

"""Shared fixtures for the route and repository tests.

Each test gets a throwaway SQLite database, a seeded tenant, and a ``Store``
bound to that tenant. The FastAPI app resolves the current tenant through the
``get_store`` dependency, so tests inject their store via ``dependency_overrides``
rather than reaching into a module global.
"""

from __future__ import annotations

from collections.abc import Iterator

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
def seed_user(session_factory: sessionmaker) -> str:
    return ensure_user(session_factory, "owner@example.com", is_admin=True, status="approved")


@pytest.fixture
def store(session_factory: sessionmaker, seed_user: str) -> Store:
    return Store(session_factory, seed_user)


@pytest.fixture
def client(store: Store) -> Iterator[TestClient]:
    main.app.dependency_overrides[main.get_store] = lambda: store
    try:
        yield TestClient(main.app)
    finally:
        main.app.dependency_overrides.pop(main.get_store, None)
