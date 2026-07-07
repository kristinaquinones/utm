# Copyright (C) 2026 Kristina Quinones
# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import csv
import io
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, text
from starlette.middleware.sessions import SessionMiddleware

from app.auth import (
    ensure_csrf,
    is_exempt_path,
    load_session_user,
    login_user,
    logout_user,
    verify_csrf,
)
from app import accounts, branding, ratelimit
from app.config import load_settings
from app.db import Base, make_session_factory
from app.mailer import (
    send_approval_email,
    send_login_email,
    send_pending_email,
    send_signup_notification,
)
from app.models import User
from app.repository import Store, normalize_email
from app.tokens import consume_login_token, create_login_token
from app.utm import (
    BASE_URL_REQUIRED_MSG,
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

settings = load_settings()
engine, SessionLocal = make_session_factory(settings)


def seed_admin() -> str:
    """Ensure the configured admins exist as approved admins; return the first id.

    Additive: promotes each ADMIN_EMAILS address to admin + approved (including
    someone who signed up first and is still pending) and never demotes anyone.
    """
    return accounts.promote_admins(SessionLocal, settings.seed_admin_emails)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Postgres schema is managed by Alembic; SQLite dev/CI creates it inline.
    if settings.is_sqlite:
        Base.metadata.create_all(engine)
    app.state.seed_user_id = seed_admin()
    yield


app = FastAPI(title="UTM link builder", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

def branding_context(request: Request) -> dict[str, Any]:
    """Make the current tenant's brand available to every template.

    Reads the user validated by the auth gate; on exempt pages (login, signup)
    there is no user, so the neutral defaults apply.
    """
    user = getattr(request.state, "user", None)
    accent = user.get("accent_color") if user else None
    return {
        "brand_name": branding.brand_name(user),
        "brand_style": branding.build_brand_style(accent),
    }


templates = Jinja2Templates(directory="app/templates", context_processors=[branding_context])


@app.middleware("http")
async def auth_gate(request: Request, call_next):
    """Redirect unauthenticated requests to /login, except for exempt paths.

    Validated once here and stashed on ``request.state.user`` so downstream
    dependencies reuse it without a second query.
    """
    if is_exempt_path(request.url.path):
        return await call_next(request)

    user = load_session_user(SessionLocal, request, settings.session_absolute_max_age)
    if user is None:
        request.session.clear()
        if request.headers.get("X-Requested-With") == "fetch":
            return JSONResponse(
                {"ok": False, "error": "Session expired. Reload the page and sign in."},
                status_code=401,
            )
        return RedirectResponse("/login", status_code=303)

    request.state.user = user
    return await call_next(request)


# SessionMiddleware is added last so it wraps auth_gate: the session cookie is
# decoded before the gate reads it, and re-encoded after any gate/route changes.
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    session_cookie="utm_session",
    max_age=settings.session_idle_max_age,
    same_site="lax",
    https_only=settings.session_https_only,
)


def require_user(request: Request) -> dict[str, Any]:
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def require_admin(request: Request) -> dict[str, Any]:
    user = require_user(request)
    if not user["is_admin"]:
        raise HTTPException(status_code=403, detail="Admins only")
    return user


def get_store(user: dict[str, Any] = Depends(require_user)) -> Store:
    """The current tenant's repository, scoped to the authenticated user."""
    return Store(SessionLocal, user["id"])


def require_csrf(request: Request, csrf_token: str = Form("")) -> None:
    if not verify_csrf(request, csrf_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")


@app.get("/healthz")
async def healthz() -> JSONResponse:
    # Liveness + database connectivity, for the platform's health checks.
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse({"status": "degraded", "database": "unreachable"}, status_code=503)
    return JSONResponse({"status": "ok", "database": "ok"})


@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request) -> HTMLResponse:
    return render_login(request)


@app.get("/signup", response_class=HTMLResponse)
async def signup_form(request: Request) -> HTMLResponse:
    return render_signup(request)


@app.post("/signup", response_class=HTMLResponse)
async def signup_submit(
    request: Request,
    _: None = Depends(require_csrf),
    email: str = Form(""),
    workspace_name: str = Form(""),
) -> HTMLResponse:
    normalized = normalize_email(email)
    client_ip = request.client.host if request.client else "unknown"

    within_limits = ratelimit.allow(
        SessionLocal, f"signup:email:{normalized}", settings.rate_limit_max, settings.rate_limit_window
    ) and ratelimit.allow(
        SessionLocal, f"signup:ip:{client_ip}", settings.rate_limit_max, settings.rate_limit_window
    )

    if within_limits and normalized:
        created = accounts.signup(SessionLocal, normalized, workspace_name)
        if created:
            for admin_email in accounts.admin_emails(SessionLocal):
                send_signup_notification(settings, admin_email, normalized)

    # Identical response whether or not the account is new, so signup can't be
    # used to probe which emails already have accounts.
    return render_signup(request, submitted=True)


@app.post("/auth/request-link", response_class=HTMLResponse)
async def request_link(
    request: Request,
    _: None = Depends(require_csrf),
    email: str = Form(""),
) -> HTMLResponse:
    normalized = normalize_email(email)
    client_ip = request.client.host if request.client else "unknown"

    # Rate-limit per email and per IP (shared Postgres-backed limiter).
    within_limits = ratelimit.allow(
        SessionLocal, f"reqlink:email:{normalized}", settings.rate_limit_max, settings.rate_limit_window
    ) and ratelimit.allow(
        SessionLocal, f"reqlink:ip:{client_ip}", settings.rate_limit_max, settings.rate_limit_window
    )

    if within_limits and normalized:
        with SessionLocal() as db:
            user = db.execute(
                select(User).where(User.email == normalized)
            ).scalar_one_or_none()
            status = user.status if user else None
            user_id = user.id if user else None

        if status == "approved":
            raw_token = create_login_token(SessionLocal, user_id, settings.login_token_ttl)
            link = f"{settings.base_url}/auth/callback?token={raw_token}"
            send_login_email(settings, normalized, link)
        elif status == "pending":
            # Truthful "still under review" note keeps the response non-enumerable
            # without leaving a pending applicant in silence.
            send_pending_email(settings, normalized)

    # Identical response whether the email is approved, pending, unknown, or
    # rate-limited: no account-enumeration signal.
    return render_check_email(request)


@app.get("/auth/callback", response_class=HTMLResponse)
async def auth_callback(request: Request, token: str = "") -> HTMLResponse:
    user_id = consume_login_token(SessionLocal, token)
    if user_id is not None:
        with SessionLocal() as db:
            user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
            if user is not None and user.status == "approved":
                login_user(request, user.id, user.session_epoch)
                return redirect_home()

    return render_login(
        request,
        error="That sign-in link is invalid or has expired. Request a new one below.",
        status_code=400,
    )


@app.post("/logout", response_model=None)
async def logout(request: Request, _: None = Depends(require_csrf)) -> RedirectResponse:
    logout_user(request)
    return RedirectResponse("/login", status_code=303)


@app.get("/admin", response_class=HTMLResponse)
async def admin_queue(
    request: Request, admin: dict[str, Any] = Depends(require_admin)
) -> HTMLResponse:
    return render_admin(request)


@app.post("/admin/users/{user_id}/approve", response_model=None)
async def admin_approve(
    request: Request,
    user_id: str,
    admin: dict[str, Any] = Depends(require_admin),
    _: None = Depends(require_csrf),
) -> RedirectResponse:
    user = accounts.set_status(SessionLocal, user_id, "approved", approved_by=admin["id"])
    if user is not None:
        send_approval_email(settings, user["email"])
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/users/{user_id}/deny", response_model=None)
async def admin_deny(
    request: Request,
    user_id: str,
    admin: dict[str, Any] = Depends(require_admin),
    _: None = Depends(require_csrf),
) -> RedirectResponse:
    accounts.set_status(SessionLocal, user_id, "denied")
    return RedirectResponse("/admin", status_code=303)


@app.get("/settings", response_class=HTMLResponse)
async def settings_form(
    request: Request, user: dict[str, Any] = Depends(require_user)
) -> HTMLResponse:
    return render_settings(request, user)


@app.post("/settings", response_model=None)
async def settings_save(
    request: Request,
    user: dict[str, Any] = Depends(require_user),
    _: None = Depends(require_csrf),
    workspace_name: str = Form(""),
    accent_color: str = Form(""),
) -> HTMLResponse:
    accounts.update_branding(SessionLocal, user["id"], workspace_name, accent_color)
    # Reflect the saved values on request.state.user so the branding context
    # processor applies the new name/accent to this very response.
    request.state.user = {
        **user,
        "workspace_name": workspace_name.strip()[:120] or None,
        "accent_color": branding.normalize_hex(accent_color),
    }
    return render_settings(request, request.state.user, saved=True)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, store: Store = Depends(get_store)) -> HTMLResponse:
    return render_index(request, store)


@app.post("/generate", response_class=HTMLResponse)
async def generate(
    request: Request,
    _: None = Depends(require_csrf),
    store: Store = Depends(get_store),
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
    return render_index(request, store, form_state=form_state, preview=preview)


@app.post("/links", response_model=None)
async def create_links(
    request: Request,
    _: None = Depends(require_csrf),
    store: Store = Depends(get_store),
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
    store: Store = Depends(get_store),
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
async def edit_link(
    request: Request, link_id: str, store: Store = Depends(get_store)
) -> HTMLResponse:
    link = store.get_link(link_id)
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    return render_edit_link(request, store, link)


@app.post("/links/{link_id}", response_model=None)
async def update_link(
    request: Request,
    link_id: str,
    _: None = Depends(require_csrf),
    store: Store = Depends(get_store),
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
        validate_base_url_or_raise(base_url)
        generated_url = build_tracking_url(base_url, params)
    except BulkGenerationError as exc:
        draft = {
            **link,
            "name": name.strip() or "Untitled link",
            "base_url": base_url.strip(),
            "params": params,
        }
        return render_edit_link(request, store, draft, error=exc.message)

    updated = store.update_link(
        link_id,
        {
            "name": name.strip() or "Untitled link",
            "base_url": base_url.strip(),
            "params": params,
            "generated_url": generated_url,
        },
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Link not found")
    return redirect_home()


@app.post("/links/{link_id}/delete")
async def delete_link(
    link_id: str,
    _: None = Depends(require_csrf),
    store: Store = Depends(get_store),
) -> RedirectResponse:
    store.delete_link(link_id)
    return redirect_home()


@app.post("/templates", response_model=None)
async def create_template(
    request: Request,
    _: None = Depends(require_csrf),
    store: Store = Depends(get_store),
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
async def delete_template(
    template_id: str,
    _: None = Depends(require_csrf),
    store: Store = Depends(get_store),
) -> RedirectResponse:
    store.delete_template(template_id)
    return redirect_home()


@app.get("/export/links.csv")
async def export_links(store: Store = Depends(get_store)) -> StreamingResponse:
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
    store: Store,
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
            "storage_label": settings.storage_label,
            "csrf_token": ensure_csrf(request),
            "current_user": getattr(request.state, "user", None),
        },
    )


def render_login(
    request: Request, error: str | None = None, status_code: int = 200
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "csrf_token": ensure_csrf(request),
            "error": error,
            "current_user": None,
        },
        status_code=status_code,
    )


def render_check_email(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "check_email.html",
        {"current_user": None},
    )


def render_signup(
    request: Request, submitted: bool = False, error: str | None = None, status_code: int = 200
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "signup.html",
        {
            "csrf_token": ensure_csrf(request),
            "submitted": submitted,
            "error": error,
            "current_user": None,
        },
        status_code=status_code,
    )


def render_admin(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            "csrf_token": ensure_csrf(request),
            "current_user": getattr(request.state, "user", None),
            "pending_users": accounts.list_pending_users(SessionLocal),
        },
    )


def render_settings(
    request: Request, user: dict[str, Any], saved: bool = False
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "csrf_token": ensure_csrf(request),
            "current_user": user,
            "workspace_name": user.get("workspace_name") or "",
            "accent_color": user.get("accent_color") or "",
            "saved": saved,
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


def validate_base_url_or_raise(base_url: str) -> None:
    if not base_url.strip():
        raise BulkGenerationError(BASE_URL_REQUIRED_MSG)


def render_edit_link(
    request: Request, store: Store, link: dict[str, Any], error: str = ""
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "edit_link.html",
        {
            "link": link,
            "standard_keys": STANDARD_UTM_KEYS,
            "utm_medium_options": UTM_MEDIUM_OPTIONS,
            "utm_medium_groups": grouped_utm_medium_choices(),
            "custom_pairs": custom_pairs(link["params"]),
            "csrf_token": ensure_csrf(request),
            "current_user": getattr(request.state, "user", None),
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
