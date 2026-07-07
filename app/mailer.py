# Copyright (C) 2026 Kristina Quinones
# SPDX-License-Identifier: GPL-2.0-only

"""Outbound email.

Backend is chosen by configuration: Postmark when ``POSTMARK_TOKEN`` is set, a
generic SMTP server when ``SMTP_HOST`` is set, otherwise a console fallback that
logs the message (so local dev can copy the sign-in link out of the logs without
any provider). Send failures are logged, never raised, so a delivery hiccup can't
turn into an account-enumeration signal in the login response.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

import httpx

from app.config import Settings

logger = logging.getLogger("app.mailer")

POSTMARK_URL = "https://api.postmarkapp.com/email"


def send_login_email(settings: Settings, to: str, link: str) -> None:
    subject = "Your sign-in link"
    body = (
        "Use the link below to sign in to the UTM link builder:\n\n"
        f"{link}\n\n"
        "It can be used once and expires shortly. "
        "If you didn't request this, you can ignore this email."
    )
    _send(settings, to, subject, body)


def send_signup_notification(settings: Settings, to: str, applicant_email: str) -> None:
    subject = "New access request"
    body = (
        f"{applicant_email} has requested access to the UTM link builder.\n\n"
        f"Review pending requests at {settings.base_url}/admin"
    )
    _send(settings, to, subject, body)


def send_approval_email(settings: Settings, to: str) -> None:
    subject = "Your access request was approved"
    body = (
        "Good news: your account has been approved.\n\n"
        f"Sign in at {settings.base_url}/login and we'll email you a link."
    )
    _send(settings, to, subject, body)


def send_pending_email(settings: Settings, to: str) -> None:
    subject = "Your access request is under review"
    body = (
        "Thanks for requesting access to the UTM link builder.\n\n"
        "Your account is still awaiting approval. Once an admin approves it, "
        "you'll be able to request a sign-in link."
    )
    _send(settings, to, subject, body)


def _send(settings: Settings, to: str, subject: str, body: str) -> None:
    try:
        backend = settings.email_backend
        if backend == "postmark":
            _send_postmark(settings, to, subject, body)
        elif backend == "smtp":
            _send_smtp(settings, to, subject, body)
        else:
            logger.info("[email:console] To=%s Subject=%s\n%s", to, subject, body)
    except Exception:
        logger.exception("Failed to send email to %s", to)


def _send_postmark(settings: Settings, to: str, subject: str, body: str) -> None:
    response = httpx.post(
        POSTMARK_URL,
        headers={
            "X-Postmark-Server-Token": settings.postmark_token,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        json={
            "From": settings.email_from,
            "To": to,
            "Subject": subject,
            "TextBody": body,
            "MessageStream": "outbound",
        },
        timeout=10.0,
    )
    response.raise_for_status()


def _send_smtp(settings: Settings, to: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["From"] = settings.email_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
        server.starttls()
        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(message)
