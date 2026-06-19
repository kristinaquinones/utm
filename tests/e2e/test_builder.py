# Copyright (C) 2026 Kristina Quinones
# SPDX-License-Identifier: GPL-2.0-only

import re

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.helpers import (
    fill_builder_single,
    generate_preview,
    save_single_link,
    switch_mode,
    switch_tab,
)

pytestmark = pytest.mark.e2e


def test_single_mode_generate_and_fetch_save(page: Page) -> None:
    fill_builder_single(
        page,
        name="June newsletter",
        base_url="https://example.com/pricing",
    )
    generate_preview(page)
    expect(page.locator("#preview-section")).to_contain_text("June newsletter")

    save_single_link(page)
    expect(page.locator("#links-count-badge")).to_have_text("1")
    expect(page.locator("#save-success-text")).to_contain_text('Saved "June newsletter"')


def test_mode_toggle_persists_in_local_storage(page: Page) -> None:
    switch_mode(page, "bulk")
    expect(page.locator("#generation-mode")).to_have_value("bulk")

    page.reload()
    expect(page.locator("#generation-mode")).to_have_value("bulk")
    expect(page.locator("#bulk-section")).to_have_class(re.compile(r"\bvisible\b"))


def test_generate_disabled_without_standard_utm(page: Page) -> None:
    page.locator("#utm-base-url").fill("https://example.com")
    for field_id in ("#f-utm_source", "#f-utm_campaign", "#f-utm_term", "#f-utm_content"):
        page.locator(field_id).fill("")
    page.locator("#f-utm_medium").select_option("")

    expect(page.locator("#generate-preview-btn")).to_be_disabled()
    expect(page.locator("#save-single")).to_be_disabled()
    expect(page.locator("#utm-validity-hint")).to_be_visible()
    expect(page.locator("#utm-validity-hint")).to_contain_text("Add at least one standard UTM parameter")


def test_bulk_over_50_lines_shows_limit(page: Page) -> None:
    page.locator("#f-utm_source").fill("email")
    switch_mode(page, "bulk")
    page.locator("#f-bulk-base-urls").fill("https://example.com")
    page.locator("#f-bulk-values").fill("\n".join(f"value-{index}" for index in range(51)))

    expect(page.locator("#generate-preview-btn")).to_be_disabled()
    expect(page.locator("#save-bulk")).to_be_disabled()
    expect(page.locator("#bulk-url-line-count")).to_contain_text("Maximum 50 links allowed")
