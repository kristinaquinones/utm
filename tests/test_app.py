# Copyright (C) 2026 Kristina Quinones
# SPDX-License-Identifier: GPL-2.0-only

import re

from fastapi.testclient import TestClient

from app.utm import BASE_URL_REQUIRED_MSG, STANDARD_UTM_REQUIRED_MSG


def csrf_token(client: TestClient) -> str:
    response = client.get("/")
    match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
    assert match
    return match.group(1)


def test_form_workflow_bulk_template_edit_delete_and_export(client, store) -> None:
    token = csrf_token(client)

    response = client.get("/")
    assert response.status_code == 200
    assert "UTM link builder" in response.text
    assert "Skip to main content" in response.text
    assert 'id="nav-builder"' in response.text
    assert 'id="theme-toggle"' in response.text
    assert "Generate a link" in response.text

    form_data = {
        "csrf_token": token,
        "name": "Launch",
        "base_url": "https://example.com/pricing",
        "utm_source": "newsletter",
        "utm_medium": "email",
        "utm_campaign": "baseline",
        "utm_term": "",
        "utm_content": "",
        "custom_key": ["audience"],
        "custom_value": ["founders"],
        "bulk_key": "utm_campaign",
        "bulk_values": "alpha\nbeta",
    }

    preview = client.post(
        "/generate",
        data={**form_data, "generation_mode": "bulk"},
    )
    assert preview.status_code == 200
    assert "utm_campaign=alpha" in preview.text
    assert "utm_campaign=beta" in preview.text
    assert "Launch · alpha" in preview.text

    saved = client.post(
        "/links",
        data={**form_data, "generation_mode": "bulk", "save_mode": "bulk"},
        follow_redirects=False,
    )
    assert saved.status_code == 303
    assert len(store.list_links()) == 2
    names = [link["name"] for link in store.list_links()]
    assert names == ["Launch · alpha", "Launch · beta"]

    template = client.post(
        "/templates",
        data={**form_data, "template_name": "Email baseline"},
        follow_redirects=False,
    )
    assert template.status_code == 303
    assert store.list_templates()[0]["name"] == "Email baseline"

    first_link = store.list_links()[0]
    edited = client.post(
        f"/links/{first_link['id']}",
        data={**form_data, "name": "Launch edited", "utm_campaign": "gamma"},
        follow_redirects=False,
    )
    assert edited.status_code == 303
    assert store.get_link(first_link["id"])["name"] == "Launch edited"
    assert "utm_campaign=gamma" in store.get_link(first_link["id"])["generated_url"]

    export = client.get("/export/links.csv")
    assert export.status_code == 200
    assert "Launch edited" in export.text
    assert "audience" in export.text

    index = client.get("/")
    assert f'/links/{first_link["id"]}/edit' in index.text
    assert 'aria-label="Edit: Launch edited"' in index.text

    deleted = client.post(f"/links/{first_link['id']}/delete", follow_redirects=False)
    assert deleted.status_code == 403

    deleted = client.post(
        f"/links/{first_link['id']}/delete",
        data={"csrf_token": token},
        follow_redirects=False,
    )
    assert deleted.status_code == 303
    assert store.get_link(first_link["id"]) is None


def test_get_edit_link_page(client, store) -> None:
    token = csrf_token(client)

    saved = client.post(
        "/links",
        data={
            "csrf_token": token,
            "name": "June newsletter",
            "base_url": "https://example.com/pricing",
            "utm_source": "newsletter",
            "utm_medium": "email",
            "utm_campaign": "spring",
        },
        follow_redirects=False,
    )
    assert saved.status_code == 303
    link = store.list_links()[0]

    response = client.get(f"/links/{link['id']}/edit")

    assert response.status_code == 200
    assert "June newsletter" in response.text
    assert 'name="base_url"' in response.text


def test_mutating_routes_reject_missing_csrf_token(client) -> None:
    response = client.post("/links", data={"base_url": "https://example.com"})

    assert response.status_code == 403


def test_template_json_escapes_script_breakouts(client) -> None:
    token = csrf_token(client)

    client.post(
        "/templates",
        data={
            "csrf_token": token,
            "template_name": "</script><script>alert(1)</script>",
            "utm_source": "</script><script>alert(2)</script>",
        },
    )
    response = client.get("/")

    assert response.status_code == 200
    assert "</script><script>alert" not in response.text
    assert "\\u003c/script\\u003e" in response.text


def test_csv_export_neutralizes_formula_values(client, store) -> None:
    store.create_link(
        {
            "name": "=IMPORTDATA(\"https://example.com\")",
            "base_url": "https://example.com",
            "params": {"=custom_header": "+SUM(1,1)"},
            "generated_url": "https://example.com?utm_source=%2BSUM%281%2C1%29",
        }
    )

    response = client.get("/export/links.csv")

    assert response.status_code == 200
    assert "'=IMPORTDATA" in response.text
    assert "'=custom_header" in response.text
    assert "'+SUM(1,1)" in response.text


def test_template_custom_utm_keys_are_not_dropped_by_prefix_filter() -> None:
    script = open("app/static/app.js", encoding="utf-8").read()

    assert 'startsWith("utm_")' not in script
    assert "!standardKeys.has(key)" in script


def test_bulk_delete_links(client, store) -> None:
    token = csrf_token(client)

    first = store.create_link(
        {
            "name": "One",
            "base_url": "https://example.com",
            "params": {"utm_source": "a"},
            "generated_url": "https://example.com?utm_source=a",
        }
    )
    second = store.create_link(
        {
            "name": "Two",
            "base_url": "https://example.com",
            "params": {"utm_source": "b"},
            "generated_url": "https://example.com?utm_source=b",
        }
    )

    response = client.post(
        "/links/bulk-delete",
        data={"csrf_token": token, "link_ids": [first["id"], second["id"]]},
        headers={"X-Requested-With": "fetch"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "deleted": 2}
    assert store.list_links() == []


def test_fetch_save_links_returns_json(client) -> None:
    token = csrf_token(client)

    response = client.post(
        "/links",
        data={
            "csrf_token": token,
            "save_mode": "single",
            "name": "Newsletter",
            "base_url": "https://example.com",
            "utm_source": "email",
        },
        headers={"X-Requested-With": "fetch"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["count"] == 1
    assert payload["names"] == ["Newsletter"]


def test_single_mode_ignores_bulk_fields_on_generate(client) -> None:
    token = csrf_token(client)

    response = client.post(
        "/generate",
        data={
            "csrf_token": token,
            "generation_mode": "single",
            "name": "Solo",
            "base_url": "https://example.com",
            "utm_source": "email",
            "bulk_key": "utm_campaign",
            "bulk_values": "alpha\nbeta",
        },
    )

    assert response.status_code == 200
    assert "1 link(s)" in response.text
    assert "utm_campaign=alpha" not in response.text


def test_bulk_generate_reports_mismatched_counts(client) -> None:
    token = csrf_token(client)

    response = client.post(
        "/generate",
        data={
            "csrf_token": token,
            "generation_mode": "bulk",
            "name": "Launch",
            "utm_source": "email",
            "bulk_base_urls": "https://example.com/a\nhttps://example.com/b",
            "bulk_key": "utm_campaign",
            "bulk_values": "alpha",
        },
    )

    assert response.status_code == 200
    assert "URL count and value count must match" in response.text


def test_bulk_save_rejects_over_limit(client, store) -> None:
    from app.utm import MAX_BULK_LINKS

    token = csrf_token(client)
    values = "\n".join(f"value-{index}" for index in range(MAX_BULK_LINKS + 1))

    response = client.post(
        "/links",
        data={
            "csrf_token": token,
            "generation_mode": "bulk",
            "save_mode": "bulk",
            "name": "Launch",
            "base_url": "https://example.com",
            "utm_source": "email",
            "bulk_key": "utm_campaign",
            "bulk_values": values,
        },
        headers={"X-Requested-With": "fetch"},
    )

    assert response.status_code == 400
    assert response.json()["error"] == f"Maximum {MAX_BULK_LINKS} links allowed."


def test_bulk_multi_url_naming_uses_url_label(client, store) -> None:
    token = csrf_token(client)

    response = client.post(
        "/links",
        data={
            "csrf_token": token,
            "generation_mode": "bulk",
            "save_mode": "bulk",
            "name": "Campaign",
            "utm_source": "email",
            "bulk_base_urls": "https://example.com/pricing\nhttps://example.com/signup",
        },
        headers={"X-Requested-With": "fetch"},
    )

    assert response.status_code == 200
    names = [link["name"] for link in store.list_links()]
    assert names == ["Campaign · pricing", "Campaign · signup"]


def test_save_rejects_unparseable_base_url(client, store) -> None:
    token = csrf_token(client)

    response = client.post(
        "/links",
        data={
            "csrf_token": token,
            "generation_mode": "single",
            "save_mode": "single",
            "name": "Broken",
            "base_url": "http://[",
            "utm_source": "email",
        },
        headers={"X-Requested-With": "fetch"},
    )

    assert response.status_code == 400
    assert "valid URL" in response.json()["error"]
    assert store.list_links() == []


def test_update_link_rejects_unparseable_base_url(client, store) -> None:
    token = csrf_token(client)

    created = store.create_link(
        {
            "name": "Original",
            "base_url": "https://example.com",
            "params": {"utm_source": "email"},
            "generated_url": "https://example.com?utm_source=email",
        }
    )

    response = client.post(
        f"/links/{created['id']}",
        data={
            "csrf_token": token,
            "name": "Original",
            "base_url": "http://[",
            "utm_source": "email",
        },
    )

    assert response.status_code == 200
    assert "valid URL" in response.text
    # The stored link must be untouched after a failed update.
    assert store.get_link(created["id"])["base_url"] == "https://example.com"


def test_save_rejects_missing_base_url(client, store) -> None:
    token = csrf_token(client)

    response = client.post(
        "/links",
        data={
            "csrf_token": token,
            "generation_mode": "single",
            "save_mode": "single",
            "name": "No URL",
            "base_url": "",
            "utm_source": "tumblr",
        },
        headers={"X-Requested-With": "fetch"},
    )

    assert response.status_code == 400
    assert response.json()["error"] == BASE_URL_REQUIRED_MSG
    assert store.list_links() == []


def test_bulk_save_rejects_missing_base_urls(client, store) -> None:
    token = csrf_token(client)

    response = client.post(
        "/links",
        data={
            "csrf_token": token,
            "generation_mode": "bulk",
            "save_mode": "bulk",
            "name": "No URLs",
            "bulk_base_urls": "",
            "utm_source": "tumblr",
        },
        headers={"X-Requested-With": "fetch"},
    )

    assert response.status_code == 400
    assert response.json()["error"] == BASE_URL_REQUIRED_MSG
    assert store.list_links() == []


def test_generate_preview_requires_base_url(client) -> None:
    token = csrf_token(client)

    response = client.post(
        "/generate",
        data={
            "csrf_token": token,
            "generation_mode": "single",
            "base_url": "",
            "utm_source": "tumblr",
        },
    )

    assert response.status_code == 200
    assert BASE_URL_REQUIRED_MSG in response.text
    assert "preview-section" not in response.text


def test_update_link_rejects_missing_base_url(client, store) -> None:
    token = csrf_token(client)

    created = store.create_link(
        {
            "name": "Original",
            "base_url": "https://example.com",
            "params": {"utm_source": "email"},
            "generated_url": "https://example.com?utm_source=email",
        }
    )

    response = client.post(
        f"/links/{created['id']}",
        data={
            "csrf_token": token,
            "name": "Original",
            "base_url": "",
            "utm_source": "email",
        },
    )

    assert response.status_code == 200
    assert BASE_URL_REQUIRED_MSG in response.text
    # The stored link must be untouched after a failed update.
    assert store.get_link(created["id"])["base_url"] == "https://example.com"


def test_generate_requires_standard_utm(client) -> None:
    token = csrf_token(client)

    response = client.post(
        "/generate",
        data={
            "csrf_token": token,
            "generation_mode": "single",
            "base_url": "https://example.com",
        },
    )

    assert response.status_code == 200
    assert STANDARD_UTM_REQUIRED_MSG in response.text
    assert "preview-section" not in response.text


def test_save_rejects_custom_param_without_standard_utm(client) -> None:
    token = csrf_token(client)

    response = client.post(
        "/links",
        data={
            "csrf_token": token,
            "generation_mode": "single",
            "save_mode": "single",
            "base_url": "https://example.com",
            "custom_key": ["audience"],
            "custom_value": ["founders"],
        },
        headers={"X-Requested-With": "fetch"},
    )

    assert response.status_code == 400
    assert response.json()["error"] == STANDARD_UTM_REQUIRED_MSG


def test_bulk_vary_standard_utm_without_base_fields(client) -> None:
    token = csrf_token(client)

    response = client.post(
        "/generate",
        data={
            "csrf_token": token,
            "generation_mode": "bulk",
            "bulk_base_urls": "https://example.com",
            "bulk_key": "utm_campaign",
            "bulk_values": "alpha",
        },
    )

    assert response.status_code == 200
    assert "utm_campaign=alpha" in response.text
    assert STANDARD_UTM_REQUIRED_MSG not in response.text


def test_bulk_vary_custom_key_without_standard_utm_fails(client) -> None:
    token = csrf_token(client)

    response = client.post(
        "/generate",
        data={
            "csrf_token": token,
            "generation_mode": "bulk",
            "bulk_base_urls": "https://example.com",
            "bulk_key": "audience",
            "bulk_values": "founders",
            "custom_key": ["audience"],
            "custom_value": ["baseline"],
        },
    )

    assert response.status_code == 200
    assert STANDARD_UTM_REQUIRED_MSG in response.text


def test_template_save_requires_standard_utm(client) -> None:
    token = csrf_token(client)

    response = client.post(
        "/templates",
        data={
            "csrf_token": token,
            "template_name": "Custom only",
            "custom_key": ["audience"],
            "custom_value": ["founders"],
        },
        headers={"X-Requested-With": "fetch"},
    )

    assert response.status_code == 400
    assert response.json()["error"] == STANDARD_UTM_REQUIRED_MSG


def test_delete_template(client, store) -> None:
    token = csrf_token(client)

    created = client.post(
        "/templates",
        data={
            "csrf_token": token,
            "template_name": "Email baseline",
            "utm_source": "newsletter",
            "utm_medium": "email",
            "utm_campaign": "baseline",
        },
        follow_redirects=False,
    )
    assert created.status_code == 303
    template = store.list_templates()[0]

    deleted = client.post(f"/templates/{template['id']}/delete", follow_redirects=False)
    assert deleted.status_code == 403

    deleted = client.post(
        f"/templates/{template['id']}/delete",
        data={"csrf_token": token},
        follow_redirects=False,
    )
    assert deleted.status_code == 303
    assert store.list_templates() == []
