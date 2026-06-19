# Copyright (C) 2026 Kristina Quinones
# SPDX-License-Identifier: GPL-2.0-only

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def test_dark_mode_toggle_and_persist(page: Page) -> None:
    toggle = page.locator("#theme-toggle")
    expect(toggle).to_have_attribute("aria-pressed", "false")

    toggle.click()
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    expect(toggle).to_have_attribute("aria-pressed", "true")
    expect(toggle).to_have_attribute("aria-label", "Switch to light mode")

    page.reload()
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    expect(page.locator("#theme-toggle")).to_have_attribute("aria-pressed", "true")
