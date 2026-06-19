# Copyright (C) 2026 Kristina Quinones
# SPDX-License-Identifier: GPL-2.0-only

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.helpers import seed_link_via_request, switch_tab

pytestmark = pytest.mark.e2e


def test_nav_tabs_aria_current(page: Page) -> None:
    expect(page.locator("#nav-builder")).to_have_attribute("aria-current", "page")
    expect(page.locator("#nav-links")).to_have_attribute("aria-current", "false")

    switch_tab(page, "links")
    expect(page.locator("#nav-links")).to_have_attribute("aria-current", "page")
    expect(page.locator("#nav-builder")).to_have_attribute("aria-current", "false")


def test_copy_announces_to_screen_reader(page: Page) -> None:
    seed_link_via_request(page, name="Copy target")
    switch_tab(page, "links")

    page.locator('[data-copy]').first.click()
    expect(page.locator("#copy-announce")).to_have_text("Copied to clipboard")
