# Copyright (C) 2026 Kristina Quinones
# SPDX-License-Identifier: GPL-2.0-only

"""Centralized environment configuration.

Every environment read for the app lives here instead of scattered ``os.getenv``
calls, so the web deploy has one place to audit for required secrets. Local dev
gets friendly defaults (a SQLite file, an ephemeral session secret); production
supplies real values through the platform secret store.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass


DEFAULT_DATABASE_URL = "sqlite:///./data/utm.db"
DEFAULT_ADMIN_EMAIL = "admin@localhost"


def _split_emails(raw: str) -> tuple[str, ...]:
    seen: list[str] = []
    for part in raw.split(","):
        email = part.strip().lower()
        if email and email not in seen:
            seen.append(email)
    return tuple(seen)


@dataclass(frozen=True)
class Settings:
    database_url: str
    session_secret: str
    admin_emails: tuple[str, ...]
    base_url: str
    postmark_token: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def storage_label(self) -> str:
        return "SQLite (local)" if self.is_sqlite else "Postgres"

    @property
    def seed_admin_emails(self) -> tuple[str, ...]:
        # There must always be at least one admin so the app is usable on a
        # fresh database; fall back to a local placeholder in dev.
        return self.admin_emails or (DEFAULT_ADMIN_EMAIL,)


def load_settings(environ: dict[str, str] | None = None) -> Settings:
    env = environ if environ is not None else os.environ
    database_url = env.get("DATABASE_URL", DEFAULT_DATABASE_URL)

    # SESSION_SECRET is not consumed until Phase 1 (sessions). In dev we mint an
    # ephemeral one so nothing crashes; production must set a stable value or
    # sessions won't survive a restart. Enforcement lands with the session work.
    session_secret = env.get("SESSION_SECRET") or secrets.token_urlsafe(32)

    return Settings(
        database_url=database_url,
        session_secret=session_secret,
        admin_emails=_split_emails(env.get("ADMIN_EMAILS", "")),
        base_url=env.get("BASE_URL", "http://localhost:8000").rstrip("/"),
        postmark_token=env.get("POSTMARK_TOKEN", ""),
        smtp_host=env.get("SMTP_HOST", ""),
        smtp_port=int(env.get("SMTP_PORT", "587") or "587"),
        smtp_user=env.get("SMTP_USER", ""),
        smtp_password=env.get("SMTP_PASSWORD", ""),
    )
