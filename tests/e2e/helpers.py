# Copyright (C) 2026 Kristina Quinones
# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import re

from playwright.sync_api import Page, expect

STANDARD_UTM_DEFAULTS = {
    "utm_source": "newsletter",
    "utm_medium": "email",
    "utm_campaign": "baseline",
    "utm_term": "",
    "utm_content": "",
}


def extract_csrf(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    if not match:
        raise AssertionError("CSRF token not found in page HTML")
    return match.group(1)


def switch_tab(page: Page, tab: str) -> None:
    if tab == "builder":
        page.locator("#nav-builder").click()
        expect(page.locator("#view-builder")).to_have_class(re.compile(r"\bactive\b"))
    else:
        page.locator("#nav-links").click()
        expect(page.locator("#view-links")).to_have_class(re.compile(r"\bactive\b"))


def switch_mode(page: Page, mode: str) -> None:
    if mode == "bulk":
        page.locator("#mode-bulk").click()
        expect(page.locator("#generation-mode")).to_have_value("bulk")
        expect(page.locator("#bulk-section")).to_have_class(re.compile(r"\bvisible\b"))
    else:
        page.locator("#mode-single").click()
        expect(page.locator("#generation-mode")).to_have_value("single")


def fill_standard_utms(page: Page, **overrides: str) -> None:
    values = {**STANDARD_UTM_DEFAULTS, **overrides}
    for key, value in values.items():
        field = page.locator(f"#{key.replace('utm_', 'f-utm_')}" if key != "utm_medium" else "#f-utm_medium")
        if key == "utm_medium":
            if value:
                field.select_option(value)
        else:
            field.fill(value)


def fill_builder_single(
    page: Page,
    *,
    name: str,
    base_url: str,
    utm_overrides: dict[str, str] | None = None,
) -> None:
    switch_mode(page, "single")
    page.locator("#link-name-input").fill(name)
    page.locator("#utm-base-url").fill(base_url)
    fill_standard_utms(page, **(utm_overrides or {}))


def fill_builder_bulk(
    page: Page,
    *,
    name_prefix: str,
    base_url: str,
    bulk_values: str,
    bulk_key: str = "utm_campaign",
    utm_overrides: dict[str, str] | None = None,
) -> None:
    page.locator("#link-name-input").fill(name_prefix)
    page.locator("#utm-base-url").fill(base_url)
    fill_standard_utms(page, **(utm_overrides or {}))
    switch_mode(page, "bulk")
    page.locator("#f-bulk-base-urls").fill(base_url)
    page.locator("#f-bulk-param").select_option(bulk_key)
    page.locator("#f-bulk-values").fill(bulk_values)


def expand_custom_params(page: Page) -> None:
    panel = page.locator("#panel-custom-params")
    if not panel.evaluate("el => el.classList.contains('open')"):
        page.locator("#toggle-custom-params").click()
    expect(panel).to_have_class(re.compile(r"\bopen\b"))


def set_custom_param(page: Page, key: str, value: str) -> None:
    expand_custom_params(page)
    rows = page.locator("[data-custom-params] .cp-row")
    if rows.count() == 0:
        page.locator("[data-add-param]").click()
    row = page.locator("[data-custom-params] .cp-row").first
    row.locator('input[name="custom_key"]').fill(key)
    row.locator('input[name="custom_value"]').fill(value)


def expand_save_template(page: Page) -> None:
    panel = page.locator("#panel-save-template")
    if not panel.evaluate("el => el.classList.contains('open')"):
        page.locator("#toggle-save-template").click()
    expect(panel).to_have_class(re.compile(r"\bopen\b"))


def generate_preview(page: Page) -> None:
    page.locator("#generate-preview-btn").click()
    expect(page.locator("#preview-section")).to_be_visible()


def wait_for_save_success(page: Page, text: str) -> None:
    success = page.locator("#save-success")
    expect(success).to_have_class(re.compile(r"\bvisible\b"))
    expect(page.locator("#save-success-text")).to_contain_text(text)


def save_bulk_links(page: Page) -> None:
    page.locator("#save-bulk").click()
    wait_for_save_success(page, "link")


def save_single_link(page: Page) -> None:
    page.locator("#save-single").click()
    wait_for_save_success(page, "Saved")


def seed_link_via_request(
    page: Page,
    *,
    name: str,
    base_url: str = "https://example.com/pricing",
    utm_source: str = "newsletter",
    utm_medium: str = "email",
    utm_campaign: str = "baseline",
) -> None:
    index = page.request.get("/")
    assert index.ok
    token = extract_csrf(index.text())
    response = page.request.post(
        "/links",
        form={
            "csrf_token": token,
            "generation_mode": "single",
            "save_mode": "single",
            "name": name,
            "base_url": base_url,
            "utm_source": utm_source,
            "utm_medium": utm_medium,
            "utm_campaign": utm_campaign,
            "utm_term": "",
            "utm_content": "",
        },
        headers={"X-Requested-With": "fetch"},
    )
    assert response.ok
    payload = response.json()
    assert payload["ok"] is True
    page.reload()


def seed_template_via_request(
    page: Page,
    *,
    template_name: str,
    utm_source: str = "paid",
    utm_medium: str = "social",
    utm_campaign: str = "launch",
) -> None:
    index = page.request.get("/")
    assert index.ok
    token = extract_csrf(index.text())
    response = page.request.post(
        "/templates",
        form={
            "csrf_token": token,
            "template_name": template_name,
            "utm_source": utm_source,
            "utm_medium": utm_medium,
            "utm_campaign": utm_campaign,
            "utm_term": "",
            "utm_content": "",
        },
        headers={"X-Requested-With": "fetch"},
    )
    assert response.ok
    page.reload()
