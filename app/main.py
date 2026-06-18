from __future__ import annotations

import csv
import io
import os
import secrets
from typing import Any

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.store import JsonStore
from app.utm import STANDARD_UTM_KEYS, build_tracking_url, generate_links, merge_param_lists

app = FastAPI(title="UTM link builder")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

templates = Jinja2Templates(directory="app/templates")
store = JsonStore()
CSRF_TOKEN = secrets.token_urlsafe(32)


def require_csrf(csrf_token: str = Form("")) -> None:
    if not secrets.compare_digest(csrf_token, CSRF_TOKEN):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return render_index(request)


@app.post("/generate", response_class=HTMLResponse)
async def generate(
    request: Request,
    _: None = Depends(require_csrf),
    name: str = Form(""),
    base_url: str = Form(""),
    utm_source: str = Form(""),
    utm_medium: str = Form(""),
    utm_campaign: str = Form(""),
    utm_term: str = Form(""),
    utm_content: str = Form(""),
    custom_key: list[str] = Form(default=[]),
    custom_value: list[str] = Form(default=[]),
    bulk_key: str = Form(""),
    bulk_values: str = Form(""),
) -> HTMLResponse:
    form_state = await collect_form_state(
        name,
        base_url,
        utm_source,
        utm_medium,
        utm_campaign,
        utm_term,
        utm_content,
        custom_key,
        custom_value,
        bulk_key,
        bulk_values,
    )
    preview = generate_links(base_url, form_state["params"], bulk_key, bulk_values)
    return render_index(request, form_state=form_state, preview=preview)


@app.post("/links")
async def create_links(
    _: None = Depends(require_csrf),
    save_mode: str = Form("single"),
    name: str = Form(""),
    base_url: str = Form(""),
    utm_source: str = Form(""),
    utm_medium: str = Form(""),
    utm_campaign: str = Form(""),
    utm_term: str = Form(""),
    utm_content: str = Form(""),
    custom_key: list[str] = Form(default=[]),
    custom_value: list[str] = Form(default=[]),
    bulk_key: str = Form(""),
    bulk_values: str = Form(""),
) -> RedirectResponse:
    params = merge_param_lists(
        {
            "utm_source": utm_source,
            "utm_medium": utm_medium,
            "utm_campaign": utm_campaign,
            "utm_term": utm_term,
            "utm_content": utm_content,
        },
        custom_key,
        custom_value,
    )
    generated = (
        generate_links(base_url, params, bulk_key, bulk_values)
        if save_mode == "bulk"
        else generate_links(base_url, params)
    )

    for index, item in enumerate(generated, start=1):
        suffix = f" {index}" if len(generated) > 1 else ""
        store.create_link(
            {
                "name": (name.strip() or "Untitled link") + suffix,
                "base_url": base_url.strip(),
                "params": item["params"],
                "generated_url": item["url"],
            }
        )

    return redirect_home()


@app.get("/links/{link_id}/edit", response_class=HTMLResponse)
async def edit_link(request: Request, link_id: str) -> HTMLResponse:
    link = store.get_link(link_id)
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    return templates.TemplateResponse(
        request,
        "edit_link.html",
        {
            "link": link,
            "standard_keys": STANDARD_UTM_KEYS,
            "custom_pairs": custom_pairs(link["params"]),
            "csrf_token": CSRF_TOKEN,
        },
    )


@app.post("/links/{link_id}")
async def update_link(
    link_id: str,
    _: None = Depends(require_csrf),
    name: str = Form(""),
    base_url: str = Form(""),
    utm_source: str = Form(""),
    utm_medium: str = Form(""),
    utm_campaign: str = Form(""),
    utm_term: str = Form(""),
    utm_content: str = Form(""),
    custom_key: list[str] = Form(default=[]),
    custom_value: list[str] = Form(default=[]),
) -> RedirectResponse:
    params = merge_param_lists(
        {
            "utm_source": utm_source,
            "utm_medium": utm_medium,
            "utm_campaign": utm_campaign,
            "utm_term": utm_term,
            "utm_content": utm_content,
        },
        custom_key,
        custom_value,
    )
    updated = store.update_link(
        link_id,
        {
            "name": name.strip() or "Untitled link",
            "base_url": base_url.strip(),
            "params": params,
            "generated_url": build_tracking_url(base_url, params),
        },
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Link not found")
    return redirect_home()


@app.post("/links/{link_id}/delete")
async def delete_link(link_id: str, _: None = Depends(require_csrf)) -> RedirectResponse:
    store.delete_link(link_id)
    return redirect_home()


@app.post("/templates")
async def create_template(
    _: None = Depends(require_csrf),
    template_name: str = Form(""),
    utm_source: str = Form(""),
    utm_medium: str = Form(""),
    utm_campaign: str = Form(""),
    utm_term: str = Form(""),
    utm_content: str = Form(""),
    custom_key: list[str] = Form(default=[]),
    custom_value: list[str] = Form(default=[]),
) -> RedirectResponse:
    params = merge_param_lists(
        {
            "utm_source": utm_source,
            "utm_medium": utm_medium,
            "utm_campaign": utm_campaign,
            "utm_term": utm_term,
            "utm_content": utm_content,
        },
        custom_key,
        custom_value,
    )
    store.create_template({"name": template_name.strip() or "Untitled template", "params": params})
    return redirect_home()


@app.post("/templates/{template_id}/delete")
async def delete_template(template_id: str, _: None = Depends(require_csrf)) -> RedirectResponse:
    store.delete_template(template_id)
    return redirect_home()


@app.get("/export/links.csv")
async def export_links() -> StreamingResponse:
    links = store.list_links()
    param_keys = sorted({key for link in links for key in link.get("params", {}).keys()})
    param_headers = {key: csv_cell(key) for key in param_keys}
    fieldnames = ["id", "name", "base_url", "generated_url", *param_headers.values(), "created_at", "updated_at"]

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for link in links:
        row = {
            "id": csv_cell(link["id"]),
            "name": csv_cell(link["name"]),
            "base_url": csv_cell(link["base_url"]),
            "generated_url": csv_cell(link["generated_url"]),
            "created_at": csv_cell(link["created_at"]),
            "updated_at": csv_cell(link["updated_at"]),
        }
        row.update({param_headers[key]: csv_cell(value) for key, value in link.get("params", {}).items()})
        writer.writerow(row)

    response = StreamingResponse(iter([output.getvalue()]), media_type="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=utm-links.csv"
    return response


def render_index(
    request: Request,
    form_state: dict[str, Any] | None = None,
    preview: list[dict[str, Any]] | None = None,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "links": store.list_links(),
            "templates": store.list_templates(),
            "standard_keys": STANDARD_UTM_KEYS,
            "form_state": form_state or empty_form_state(),
            "preview": preview or [],
            "data_path": os.getenv("DATA_PATH", "data/utm-data.json"),
            "csrf_token": CSRF_TOKEN,
        },
    )


async def collect_form_state(
    name: str,
    base_url: str,
    utm_source: str,
    utm_medium: str,
    utm_campaign: str,
    utm_term: str,
    utm_content: str,
    custom_key: list[str],
    custom_value: list[str],
    bulk_key: str,
    bulk_values: str,
) -> dict[str, Any]:
    standard = {
        "utm_source": utm_source,
        "utm_medium": utm_medium,
        "utm_campaign": utm_campaign,
        "utm_term": utm_term,
        "utm_content": utm_content,
    }
    params = merge_param_lists(standard, custom_key, custom_value)
    return {
        "name": name,
        "base_url": base_url,
        "standard": standard,
        "params": params,
        "custom_pairs": paired_custom(custom_key, custom_value),
        "bulk_key": bulk_key,
        "bulk_values": bulk_values,
    }


def empty_form_state() -> dict[str, Any]:
    return {
        "name": "",
        "base_url": "",
        "standard": {key: "" for key in STANDARD_UTM_KEYS},
        "params": {},
        "custom_pairs": [],
        "bulk_key": "utm_campaign",
        "bulk_values": "",
    }


def custom_pairs(params: dict[str, str]) -> list[dict[str, str]]:
    return [{"key": key, "value": value} for key, value in params.items() if key not in STANDARD_UTM_KEYS]


def paired_custom(keys: list[str], values: list[str]) -> list[dict[str, str]]:
    return [{"key": key, "value": value} for key, value in zip(keys, values, strict=False) if key or value]


def redirect_home() -> RedirectResponse:
    return RedirectResponse("/", status_code=303)


def csv_cell(value: Any) -> str:
    text = str(value)
    if text.startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
        return f"'{text}"
    return text
