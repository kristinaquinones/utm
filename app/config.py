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


def _as_bool(raw: str, default: bool = False) -> bool:
    if raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


# Session lifetimes (seconds). Idle is the rolling cookie max-age; absolute is the
# hard ceiling regardless of activity.
DEFAULT_SESSION_IDLE_MAX_AGE = 60 * 60 * 24 * 14   # 14 days
DEFAULT_SESSION_ABSOLUTE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days


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
    session_https_only: bool
    session_idle_max_age: int
    session_absolute_max_age: int
    dev_login_enabled: bool

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

    # The dev-login bridge is a passwordless "sign in as an approved user" shim.
    # It is OFF by default (secure by default): local dev opts in with DEV_LOGIN=1,
    # and it can never be enabled in production, so a forgotten flag on deploy
    # cannot become an auth bypass. Removed entirely once magic-link lands.
    dev_login_enabled = _as_bool(env.get("DEV_LOGIN", ""), default=False)
    if dev_login_enabled and env.get("APP_ENV", "").strip().lower() == "production":
        raise RuntimeError("DEV_LOGIN must not be enabled when APP_ENV=production")

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
        # Secure cookies require HTTPS; default off so local http dev and the test
        # client work. Production must set SESSION_HTTPS_ONLY=1 (Phase 5 deploy).
        session_https_only=_as_bool(env.get("SESSION_HTTPS_ONLY", "")),
        session_idle_max_age=int(
            env.get("SESSION_IDLE_MAX_AGE", "") or DEFAULT_SESSION_IDLE_MAX_AGE
        ),
        session_absolute_max_age=int(
            env.get("SESSION_ABSOLUTE_MAX_AGE", "") or DEFAULT_SESSION_ABSOLUTE_MAX_AGE
        ),
        dev_login_enabled=dev_login_enabled,
    )
