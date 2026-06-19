# Copyright (C) 2026 Kristina Quinones
# SPDX-License-Identifier: GPL-2.0-only

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.helpers import extract_csrf, seed_link_via_request, switch_tab

pytestmark = pytest.mark.e2e


def test_filter_shows_empty_state(page: Page) -> None:
    seed_link_via_request(page, name="June newsletter")
    switch_tab(page, "links")

    page.locator("#f-links-filter").fill("no-such-link")
    expect(page.locator("#links-empty-filter")).to_be_visible()
    expect(page.locator("#filter-query-display")).to_have_text('"no-such-link"')
    expect(page.locator("#links-list")).to_be_hidden()


def test_select_all_visible_and_bulk_delete(page: Page) -> None:
    seed_link_via_request(page, name="Alpha link")
    seed_link_via_request(page, name="Beta link")
    switch_tab(page, "links")

    page.locator("#cb-select-all").check()
    expect(page.locator("#select-all-label")).to_contain_text("2 of 2 selected")
    expect(page.locator("#delete-selected-btn")).to_be_visible()

    page.locator("#delete-selected-btn").click()
    page.wait_for_load_state("networkidle")
    expect(page.locator("#links-empty-all")).to_be_visible()


def test_export_selected_csv_neutralizes_formulas(page: Page) -> None:
    index = page.request.get("/")
    token = extract_csrf(index.text())
    response = page.request.post(
        "/links",
        form={
            "csrf_token": token,
            "generation_mode": "single",
            "save_mode": "single",
            "name": "=evil",
            "base_url": "https://example.com",
            "utm_source": "email",
            "utm_medium": "email",
            "utm_campaign": "test",
            "utm_term": "",
            "utm_content": "",
        },
        headers={"X-Requested-With": "fetch"},
    )
    assert response.ok
    page.reload()

    switch_tab(page, "links")
    page.locator(".link-cb").first.check()

    with page.expect_download() as download_info:
        page.locator("#export-selected-btn").click()
    download = download_info.value
    content = download.path().read_text(encoding="utf-8")
    assert '"Name","URL","Created"' in content.replace("\n", "")
    assert "'=evil" in content


def test_export_all_csv_columns(page: Page) -> None:
    seed_link_via_request(page, name="Export me")
    switch_tab(page, "links")

    with page.expect_download() as download_info:
        page.locator("#export-all-btn").click()
    download = download_info.value
    content = download.path().read_text(encoding="utf-8")
    assert content.startswith('"Name","URL","Created"')
    assert "Export me" in content
