# Copyright (C) 2026 Kristina Quinones
# SPDX-License-Identifier: GPL-2.0-only

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.helpers import (
    expand_save_template,
    fill_builder_single,
    seed_template_via_request,
    set_custom_param,
)

pytestmark = pytest.mark.e2e


def test_apply_template_fills_form(page: Page) -> None:
    seed_template_via_request(
        page,
        template_name="Paid social baseline",
        utm_source="paid",
        utm_medium="social",
        utm_campaign="launch",
    )
    page.reload()

    page.locator('[data-apply-template]').click()
    expect(page.locator("#f-utm_source")).to_have_value("paid")
    expect(page.locator("#f-utm_medium")).to_have_value("social")
    expect(page.locator("#f-utm_campaign")).to_have_value("launch")


def test_delete_template(page: Page) -> None:
    fill_builder_single(
        page,
        name="Template source",
        base_url="https://example.com",
        utm_overrides={"utm_source": "email", "utm_medium": "email", "utm_campaign": "spring"},
    )
    expand_save_template(page)
    page.locator("#f-template-name").fill("Delete me")
    page.locator("#save-template-btn").click()
    page.wait_for_load_state("networkidle")

    expect(page.locator('[data-apply-template]')).to_have_count(1)
    page.locator('button[aria-label="Delete template: Delete me"]').click()
    page.wait_for_load_state("networkidle")
    expect(page.locator('[data-apply-template]')).to_have_count(0)
    expect(page.locator(".empty-italic")).to_contain_text("No templates yet")
