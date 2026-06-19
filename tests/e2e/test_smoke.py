# Copyright (C) 2026 Kristina Quinones
# SPDX-License-Identifier: GPL-2.0-only

import re

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.helpers import (
    expand_save_template,
    fill_builder_bulk,
    generate_preview,
    save_bulk_links,
    set_custom_param,
    switch_tab,
)

pytestmark = pytest.mark.e2e


def test_smoke_bulk_save_edit_export_delete(page: Page, live_server: str) -> None:
    page.goto("/")
    expect(page.locator("h1")).to_contain_text("UTM link builder")
    expect(page.locator("#nav-builder")).to_be_visible()
    expect(page.locator('input[name="csrf_token"]')).to_have_count(1)

    fill_builder_bulk(
        page,
        name_prefix="Launch",
        base_url="https://example.com/pricing",
        bulk_values="alpha\nbeta",
    )
    set_custom_param(page, "audience", "founders")

    generate_preview(page)
    expect(page.locator("#preview-section")).to_contain_text("Launch · alpha")
    expect(page.locator("#preview-section")).to_contain_text("Launch · beta")
    expect(page.locator("#preview-section")).to_contain_text("utm_campaign=alpha")
    expect(page.locator("#preview-section")).to_contain_text("utm_campaign=beta")

    save_bulk_links(page)
    expect(page.locator("#links-count-badge")).to_have_text("2")

    expand_save_template(page)
    page.locator("#f-template-name").fill("Email baseline")
    page.locator("#save-template-btn").click()
    page.wait_for_load_state("networkidle")
    expect(page.locator('[data-apply-template]')).to_contain_text("Email baseline")

    switch_tab(page, "links")
    expect(page.locator(".links-row")).to_have_count(2)

    edit_link = page.locator(".links-row").first.locator('a[href*="/edit"]')
    edit_link.click()
    expect(page).to_have_url(re.compile(r"/links/.+/edit"))
    page.locator("#edit-link-name").fill("Launch edited")
    page.locator("#edit-utm_campaign").fill("gamma")
    page.locator('button[type="submit"]').click()
    page.wait_for_load_state("networkidle")

    switch_tab(page, "links")
    expect(page.locator(".links-row").first).to_contain_text("Launch edited")

    export = page.request.get("/export/links.csv")
    assert export.ok
    assert "Launch edited" in export.text()
    assert "audience" in export.text()
    assert "utm_campaign=gamma" in export.text()

    page.locator(".links-row").first.locator('button[aria-label^="Delete:"]').click()
    page.wait_for_load_state("networkidle")
    expect(page.locator(".links-row")).to_have_count(1)
