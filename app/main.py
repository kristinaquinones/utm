# Copyright (C) 2026 Kristina Quinones
# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import csv
import io
import os
import secrets
from datetime import datetime
from typing import Any

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.store import JsonStore
from app.utm import (
    STANDARD_UTM_KEYS,
    UTM_MEDIUM_OPTIONS,
    grouped_utm_medium_choices,
    BulkGenerationError,
    build_tracking_url,
    generate_links,
    merge_param_lists,
    resolve_base_urls,
    standard_utm_error,
    url_label,
)

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
    generation_mode: str = Form("single"),
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
    bulk_base_urls: str = Form(""),
) -> HTMLResponse:
    mode = normalize_generation_mode(generation_mode)
    form_state = await collect_form_state(
        mode,
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
        bulk_base_urls,
    )
    preview, form_error = build_preview(form_state, mode)
    form_state["form_error"] = form_error
    return render_index(request, form_state=form_state, preview=preview)


@app.post("/links", response_model=None)
async def create_links(
    request: Request,
    _: None = Depends(require_csrf),
    generation_mode: str = Form("single"),
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
    bulk_base_urls: str = Form(""),
) -> RedirectResponse:
    mode = normalize_generation_mode(generation_mode)
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

    try:
        validate_standard_utm_or_raise(
            params,
            bulk_key,
            bulk_values,
            bulk_mode=mode == "bulk" and save_mode == "bulk",
        )
        generated = run_generation(
            mode,
            save_mode,
            base_url,
            bulk_base_urls,
            params,
            bulk_key,
            bulk_values,
        )
    except BulkGenerationError as exc:
        if request.headers.get("X-Requested-With") == "fetch":
            return JSONResponse({"ok": False, "error": exc.message}, status_code=400)
        raise HTTPException(status_code=400, detail=exc.message) from exc

    created: list[dict[str, Any]] = []
    for item in generated:
        link_name = name_for_item(name, mode, save_mode, item)
        created.append(
            store.create_link(
                {
                    "name": link_name,
                    "base_url": str(item.get("base_url", base_url)).strip(),
                    "params": item["params"],
                    "generated_url": item["url"],
                }
            )
        )

    if request.headers.get("X-Requested-With") == "fetch":
        return JSONResponse(
            {
                "ok": True,
                "count": len(created),
                "names": [item["name"] for item in created],
            }
        )

    return redirect_home()


@app.post("/links/bulk-delete", response_model=None)
async def bulk_delete_links(
    request: Request,
    _: None = Depends(require_csrf),
    link_ids: list[str] = Form(default=[]),
):
    deleted = 0
    for link_id in link_ids:
        if store.delete_link(link_id):
            deleted += 1

    if request.headers.get("X-Requested-With") == "fetch":
        return JSONResponse({"ok": True, "deleted": deleted})

    return redirect_home()


@app.get("/links/{link_id}/edit", response_class=HTMLResponse)
async def edit_link(request: Request, link_id: str) -> HTMLResponse:
    link = store.get_link(link_id)
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    return render_edit_link(request, link)


@app.post("/links/{link_id}", response_model=None)
async def update_link(
    request: Request,
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
):
    link = store.get_link(link_id)
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")

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

    try:
        validate_standard_utm_or_raise(params)
    except BulkGenerationError as exc:
        draft = {
            **link,
            "name": name.strip() or "Untitled link",
            "base_url": base_url.strip(),
            "params": params,
        }
        return render_edit_link(request, draft, error=exc.message)

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


@app.post("/templates", response_model=None)
async def create_template(
    request: Request,
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

    try:
        validate_standard_utm_or_raise(params)
    except BulkGenerationError as exc:
        if request.headers.get("X-Requested-With") == "fetch":
            return JSONResponse({"ok": False, "error": exc.message}, status_code=400)
        raise HTTPException(status_code=400, detail=exc.message) from exc

    template = store.create_template({"name": template_name.strip() or "Untitled template", "params": params})

    if request.headers.get("X-Requested-With") == "fetch":
        return JSONResponse({"ok": True, "template": template})

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
    links = enrich_links(store.list_links())
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "links": links,
            "links_count": len(links),
            "links_for_js": links_for_client(links),
            "templates": store.list_templates(),
            "standard_keys": STANDARD_UTM_KEYS,
            "utm_medium_options": UTM_MEDIUM_OPTIONS,
            "utm_medium_groups": grouped_utm_medium_choices(),
            "form_state": form_state or empty_form_state(),
            "preview": preview or [],
            "data_path": os.getenv("DATA_PATH", "data/utm-data.json"),
            "csrf_token": CSRF_TOKEN,
        },
    )


def normalize_generation_mode(mode: str) -> str:
    return "bulk" if mode.strip().lower() == "bulk" else "single"


def validate_standard_utm_or_raise(
    params: dict[str, str],
    bulk_key: str = "",
    bulk_values: str = "",
    *,
    bulk_mode: bool = False,
) -> None:
    error = standard_utm_error(params, bulk_key, bulk_values, bulk_mode=bulk_mode)
    if error:
        raise BulkGenerationError(error)


def render_edit_link(request: Request, link: dict[str, Any], error: str = "") -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "edit_link.html",
        {
            "link": link,
            "standard_keys": STANDARD_UTM_KEYS,
            "utm_medium_options": UTM_MEDIUM_OPTIONS,
            "utm_medium_groups": grouped_utm_medium_choices(),
            "custom_pairs": custom_pairs(link["params"]),
            "csrf_token": CSRF_TOKEN,
            "links_count": len(store.list_links()),
            "error": error,
        },
    )


def run_generation(
    generation_mode: str,
    save_mode: str,
    base_url: str,
    bulk_base_urls: str,
    params: dict[str, str],
    bulk_key: str,
    bulk_values: str,
) -> list[dict[str, object]]:
    base_urls = resolve_base_urls(generation_mode, base_url, bulk_base_urls)
    if generation_mode == "bulk" and save_mode == "bulk":
        return generate_links(base_urls, params, bulk_key, bulk_values)
    return generate_links(base_urls, params)


def build_preview(
    form_state: dict[str, Any],
    mode: str,
) -> tuple[list[dict[str, Any]], str]:
    try:
        validate_standard_utm_or_raise(
            form_state["params"],
            form_state["bulk_key"] if mode == "bulk" else "",
            form_state["bulk_values"] if mode == "bulk" else "",
            bulk_mode=mode == "bulk",
        )
        generated = run_generation(
            mode,
            "bulk" if mode == "bulk" else "single",
            form_state["base_url"],
            form_state["bulk_base_urls"],
            form_state["params"],
            form_state["bulk_key"] if mode == "bulk" else "",
            form_state["bulk_values"] if mode == "bulk" else "",
        )
    except BulkGenerationError as exc:
        return [], exc.message
    return with_preview_names(generated, form_state["name"], mode), ""


async def collect_form_state(
    generation_mode: str,
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
    bulk_base_urls: str,
) -> dict[str, Any]:
    standard = {
        "utm_source": utm_source,
        "utm_medium": utm_medium,
        "utm_campaign": utm_campaign,
        "utm_term": utm_term,
        "utm_content": utm_content,
    }
    params = merge_param_lists(standard, custom_key, custom_value)
    mode = normalize_generation_mode(generation_mode)
    return {
        "generation_mode": mode,
        "name": name,
        "base_url": base_url,
        "bulk_base_urls": bulk_base_urls if mode == "bulk" else "",
        "standard": standard,
        "params": params,
        "custom_pairs": paired_custom(custom_key, custom_value),
        "bulk_key": bulk_key if mode == "bulk" else "",
        "bulk_values": bulk_values if mode == "bulk" else "",
        "form_error": "",
    }


def empty_form_state() -> dict[str, Any]:
    return {
        "generation_mode": "single",
        "name": "",
        "base_url": "",
        "bulk_base_urls": "",
        "standard": {key: "" for key in STANDARD_UTM_KEYS},
        "params": {},
        "custom_pairs": [],
        "bulk_key": "utm_campaign",
        "bulk_values": "",
        "form_error": "",
    }


def custom_pairs(params: dict[str, str]) -> list[dict[str, str]]:
    return [{"key": key, "value": value} for key, value in params.items() if key not in STANDARD_UTM_KEYS]


def paired_custom(keys: list[str], values: list[str]) -> list[dict[str, str]]:
    return [{"key": key, "value": value} for key, value in zip(keys, values, strict=False) if key or value]


def enrich_links(links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**link, "display_date": format_link_date(link["created_at"])} for link in links]


def links_for_client(links: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "id": link["id"],
            "name": link["name"],
            "url": link["generated_url"],
            "created": link["display_date"],
        }
        for link in links
    ]


def format_link_date(iso_str: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return f"{dt.strftime('%b')} {dt.day}, {dt.year}"
    except ValueError:
        return iso_str


def bulk_link_name(prefix: str, varied_value: str, base_url: str) -> str:
    clean_prefix = prefix.strip()
    suffix = varied_value.strip() or url_label(base_url)
    if not suffix:
        return clean_prefix or "Untitled link"
    if not clean_prefix:
        return suffix
    return f"{clean_prefix} · {suffix}"


def name_for_item(
    name: str,
    generation_mode: str,
    save_mode: str,
    item: dict[str, object],
) -> str:
    if generation_mode == "bulk" and save_mode == "bulk":
        return bulk_link_name(
            name,
            str(item.get("varied_value", "")),
            str(item.get("base_url", "")),
        )
    return name.strip() or "Untitled link"


def with_preview_names(
    preview: list[dict[str, object]],
    name: str,
    generation_mode: str,
) -> list[dict[str, Any]]:
    if generation_mode != "bulk":
        display_name = name.strip() or "Link"
        return [{**item, "name": display_name} for item in preview]

    return [
        {
            **item,
            "name": bulk_link_name(
                name,
                str(item.get("varied_value", "")),
                str(item.get("base_url", "")),
            ),
        }
        for item in preview
    ]


def redirect_home() -> RedirectResponse:
    return RedirectResponse("/", status_code=303)


def csv_cell(value: Any) -> str:
    text = str(value)
    if text.startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
        return f"'{text}"
    return text
