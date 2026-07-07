# Copyright (C) 2026 Kristina Quinones
# SPDX-License-Identifier: GPL-2.0-only

"""Deploy-facing behavior: health check and DATABASE_URL normalization."""

import app.main as main
from app.config import load_settings, normalize_database_url


# -- /healthz ----------------------------------------------------------------


def test_healthz_reports_ok_when_the_database_is_reachable(anon_client):
    response = anon_client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_healthz_reports_degraded_when_the_database_is_down(anon_client, monkeypatch):
    def boom():
        raise RuntimeError("database unreachable")

    monkeypatch.setattr(main, "SessionLocal", boom)

    response = anon_client.get("/healthz")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"


# -- DATABASE_URL normalization ---------------------------------------------


def test_normalize_database_url_forces_the_psycopg_driver():
    assert normalize_database_url("postgres://u:p@h:5432/db") == "postgresql+psycopg://u:p@h:5432/db"
    assert normalize_database_url("postgresql://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    # Already explicit -> unchanged.
    assert normalize_database_url("postgresql+psycopg://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    # Non-Postgres URLs pass through.
    assert normalize_database_url("sqlite:///./data/utm.db") == "sqlite:///./data/utm.db"


def test_load_settings_normalizes_the_database_url():
    settings = load_settings({"DATABASE_URL": "postgres://a:b@host/db"})
    assert settings.database_url == "postgresql+psycopg://a:b@host/db"
