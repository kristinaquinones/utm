# Copyright (C) 2026 Kristina Quinones
# SPDX-License-Identifier: GPL-2.0-only

"""Per-tenant branding: persistence, neutral defaults, injection safety, isolation."""

from fastapi.testclient import TestClient

import app.main as main
from app.branding import (
    _DARK_BG,
    _LIGHT_BG,
    _contrast,
    build_brand_style,
    normalize_hex,
    parse_hex,
)
from app.repository import ensure_user

from tests.conftest import login


def _csrf(client):
    import re

    return re.search(r'name="csrf-token" content="([^"]+)"', client.get("/").text).group(1)


def save_settings(client, workspace_name="", accent_color=""):
    return client.post(
        "/settings",
        data={"csrf_token": _csrf(client), "workspace_name": workspace_name, "accent_color": accent_color},
        follow_redirects=False,
    )


# -- persistence + rendering -------------------------------------------------


def test_branding_persists_and_renders(client, seed_user):
    response = save_settings(client, workspace_name="Acme Campaigns", accent_color="#3366cc")
    assert response.status_code == 200
    assert "Saved." in response.text

    home = client.get("/")
    assert "<h1 class=\"page-title\">Acme Campaigns</h1>" in home.text
    assert "<title>Acme Campaigns</title>" in home.text
    assert "--clay-500: #3366cc;" in home.text


def test_unset_branding_uses_neutral_defaults(client, seed_user):
    home = client.get("/")
    assert "UTM link builder" in home.text
    # No accent set -> no injected style override.
    assert "--clay-500:" not in home.text


# -- injection safety --------------------------------------------------------


def test_malicious_accent_color_cannot_break_out_of_the_style_block(client, seed_user):
    payload = "#fff; } </style><script>alert(1)</script>"
    save_settings(client, accent_color=payload)

    home = client.get("/")
    assert "<script>alert(1)</script>" not in home.text
    assert "</style><script>" not in home.text
    # Invalid color is dropped, so no override block is emitted at all.
    assert "--clay-500:" not in home.text


def test_workspace_name_is_html_escaped(client, seed_user):
    save_settings(client, workspace_name="<script>alert(1)</script>")

    home = client.get("/")
    assert "<script>alert(1)</script>" not in home.text
    assert "&lt;script&gt;" in home.text


# -- tenant isolation --------------------------------------------------------


def test_branding_does_not_leak_across_tenants(client, bound_db, seed_user):
    save_settings(client, workspace_name="Owner Co", accent_color="#3366cc")

    ensure_user(bound_db, "bob@example.com", status="approved")
    bob = TestClient(main.app)
    login(bob, "bob@example.com")

    home = bob.get("/")
    assert "Owner Co" not in home.text
    assert "#3366cc" not in home.text
    assert "UTM link builder" in home.text


# -- color math (unit) -------------------------------------------------------


def test_parse_and_normalize_hex():
    assert parse_hex("#be7350") == (190, 115, 80)
    assert parse_hex("#FFF") == (255, 255, 255)
    assert parse_hex("not-a-color") is None
    assert parse_hex("") is None
    assert normalize_hex("#FFF") == "#ffffff"
    assert normalize_hex("red;}") is None


def test_build_brand_style_is_none_for_invalid_color():
    assert build_brand_style("javascript:alert(1)") is None
    assert build_brand_style(None) is None


def test_text_link_meets_contrast_floor_in_both_modes():
    # A pale accent (yellow) would be unreadable at face value; the derivation
    # must lift it to AA contrast against each background.
    style = build_brand_style("#ffff00")
    light_link = parse_hex(style["light"]["--text-link"])
    dark_link = parse_hex(style["dark"]["--text-link"])

    assert _contrast(light_link, _LIGHT_BG) >= 4.4
    assert _contrast(dark_link, _DARK_BG) >= 4.4
