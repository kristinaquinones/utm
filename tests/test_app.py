import re

from fastapi.testclient import TestClient

import app.main as main
from app.store import JsonStore


def csrf_token(client: TestClient) -> str:
    response = client.get("/")
    match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
    assert match
    return match.group(1)


def test_form_workflow_bulk_template_edit_delete_and_export(tmp_path) -> None:
    main.store = JsonStore(str(tmp_path / "utm-data.json"))
    client = TestClient(main.app)
    token = csrf_token(client)

    response = client.get("/")
    assert response.status_code == 200
    assert "UTM link builder" in response.text
    assert "formnovalidate" in response.text

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

    preview = client.post("/generate", data=form_data)
    assert preview.status_code == 200
    assert "utm_campaign=alpha" in preview.text
    assert "utm_campaign=beta" in preview.text

    saved = client.post("/links", data={**form_data, "save_mode": "bulk"}, follow_redirects=False)
    assert saved.status_code == 303
    assert len(main.store.list_links()) == 2

    template = client.post(
        "/templates",
        data={**form_data, "template_name": "Email baseline"},
        follow_redirects=False,
    )
    assert template.status_code == 303
    assert main.store.list_templates()[0]["name"] == "Email baseline"

    first_link = main.store.list_links()[0]
    edited = client.post(
        f"/links/{first_link['id']}",
        data={**form_data, "name": "Launch edited", "utm_campaign": "gamma"},
        follow_redirects=False,
    )
    assert edited.status_code == 303
    assert main.store.get_link(first_link["id"])["name"] == "Launch edited"
    assert "utm_campaign=gamma" in main.store.get_link(first_link["id"])["generated_url"]

    export = client.get("/export/links.csv")
    assert export.status_code == 200
    assert "Launch edited" in export.text
    assert "audience" in export.text

    deleted = client.post(f"/links/{first_link['id']}/delete", follow_redirects=False)
    assert deleted.status_code == 403

    deleted = client.post(
        f"/links/{first_link['id']}/delete",
        data={"csrf_token": token},
        follow_redirects=False,
    )
    assert deleted.status_code == 303
    assert main.store.get_link(first_link["id"]) is None


def test_mutating_routes_reject_missing_csrf_token(tmp_path) -> None:
    main.store = JsonStore(str(tmp_path / "utm-data.json"))
    client = TestClient(main.app)

    response = client.post("/links", data={"base_url": "https://example.com"})

    assert response.status_code == 403


def test_template_json_escapes_script_breakouts(tmp_path) -> None:
    main.store = JsonStore(str(tmp_path / "utm-data.json"))
    client = TestClient(main.app)
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


def test_csv_export_neutralizes_formula_values(tmp_path) -> None:
    main.store = JsonStore(str(tmp_path / "utm-data.json"))
    client = TestClient(main.app)
    main.store.create_link(
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
