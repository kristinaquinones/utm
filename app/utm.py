# Copyright (C) 2026 Kristina Quinones
# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


STANDARD_UTM_KEYS = [
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
]

UTM_MEDIUM_CHOICES: list[dict[str, str]] = [
    {"value": "cpc", "label": "CPC (paid search)", "group": "Paid"},
    {"value": "paid-social", "label": "Paid social", "group": "Paid"},
    {"value": "display", "label": "Display", "group": "Paid"},
    {"value": "affiliate", "label": "Affiliate", "group": "Paid"},
    {"value": "email", "label": "Email", "group": "Owned"},
    {"value": "sms", "label": "SMS", "group": "Owned"},
    {"value": "push", "label": "Push notification", "group": "Owned"},
    {"value": "podcast", "label": "Podcast", "group": "Owned"},
    {"value": "social", "label": "Social", "group": "Organic and social"},
    {"value": "organic", "label": "Organic", "group": "Organic and social"},
    {"value": "referral", "label": "Referral", "group": "Organic and social"},
    {"value": "video", "label": "Video", "group": "Organic and social"},
    {"value": "qr", "label": "QR code", "group": "Organic and social"},
]

UTM_MEDIUM_OPTIONS = [choice["value"] for choice in UTM_MEDIUM_CHOICES]


def grouped_utm_medium_choices() -> list[dict[str, object]]:
    groups: dict[str, list[dict[str, str]]] = {}
    order: list[str] = []
    for choice in UTM_MEDIUM_CHOICES:
        group_name = choice["group"]
        if group_name not in groups:
            groups[group_name] = []
            order.append(group_name)
        groups[group_name].append(choice)
    return [{"group": name, "choices": groups[name]} for name in order]

MAX_BULK_LINKS = 50

STANDARD_UTM_REQUIRED_MSG = (
    "Add at least one standard UTM parameter "
    "(utm_source, utm_medium, utm_campaign, utm_term, or utm_content)."
)

BASE_URL_REQUIRED_MSG = "Add a destination URL."


class BulkGenerationError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def clean_params(params: dict[str, str]) -> dict[str, str]:
    cleaned: dict[str, str] = {}
    for key, value in params.items():
        clean_key = key.strip()
        clean_value = value.strip()
        if clean_key and clean_value:
            cleaned[clean_key] = clean_value
    return cleaned


def merge_param_lists(
    standard: dict[str, str],
    custom_keys: list[str] | None,
    custom_values: list[str] | None,
) -> dict[str, str]:
    params = clean_params(standard)
    keys = custom_keys or []
    values = custom_values or []

    for key, value in zip(keys, values, strict=False):
        params.update(clean_params({key: value}))

    return params


def normalize_base_url(base_url: str) -> str:
    clean_base = base_url.strip()
    if not clean_base:
        return clean_base
    if not clean_base.startswith(("http://", "https://")):
        return f"https://{clean_base}"
    return clean_base


def _split_url(clean_url: str):
    """Split a normalized URL, turning a parse failure into a user-facing error.

    urlsplit raises ValueError on a few malformed authorities (notably an
    unbalanced IPv6 bracket like "http://["). Callers treat that as invalid
    user input rather than letting it surface as an unhandled 500.
    """
    try:
        return urlsplit(clean_url)
    except ValueError as exc:
        raise BulkGenerationError(
            f'"{clean_url}" is not a valid URL. '
            "Remove stray characters or unbalanced brackets, and try again."
        ) from exc


def url_label(base_url: str) -> str:
    clean = normalize_base_url(base_url)
    if not clean:
        return ""

    try:
        parts = urlsplit(clean)
    except ValueError:
        return ""
    path = parts.path.strip("/")
    if path:
        return path.split("/")[-1] or parts.netloc
    return parts.netloc


def build_tracking_url(base_url: str, params: dict[str, str]) -> str:
    clean_base = normalize_base_url(base_url)
    clean = clean_params(params)
    if not clean_base or not clean:
        return clean_base

    parts = _split_url(clean_base)
    existing = dict(parse_qsl(parts.query, keep_blank_values=True))
    existing.update(clean)
    query = urlencode(existing, doseq=True)

    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def bulk_values(raw_values: str) -> list[str]:
    return [line.strip() for line in raw_values.splitlines() if line.strip()]


def standard_utm_error(
    params: dict[str, str],
    bulk_key: str = "",
    raw_bulk_values: str = "",
    *,
    bulk_mode: bool = False,
) -> str | None:
    clean = clean_params(params)
    if any(key in STANDARD_UTM_KEYS for key in clean):
        return None

    clean_bulk_key = bulk_key.strip()
    if bulk_mode and clean_bulk_key in STANDARD_UTM_KEYS and bulk_values(raw_bulk_values):
        return None

    return STANDARD_UTM_REQUIRED_MSG


def resolve_base_urls(generation_mode: str, base_url: str, bulk_base_urls: str) -> list[str]:
    if generation_mode != "bulk":
        return [base_url.strip()]

    lines = bulk_values(bulk_base_urls)
    if lines:
        return lines
    return [base_url.strip()]


def _link_item(
    base_url: str,
    params: dict[str, str],
    varied_value: str = "",
) -> dict[str, object]:
    return {
        "params": params,
        "url": build_tracking_url(base_url, params),
        "base_url": base_url,
        "varied_value": varied_value,
    }


def generate_links(
    base_urls: list[str],
    params: dict[str, str],
    bulk_key: str = "",
    raw_bulk_values: str = "",
) -> list[dict[str, object]]:
    values = bulk_values(raw_bulk_values)
    clean_bulk_key = bulk_key.strip()
    clean = clean_params(params)

    urls = [url.strip() for url in base_urls if url.strip()]
    if not urls:
        raise BulkGenerationError(BASE_URL_REQUIRED_MSG)

    has_vary = bool(clean_bulk_key and values)

    if has_vary and len(urls) > 1 and len(values) != len(urls):
        raise BulkGenerationError("URL count and value count must match when both are provided.")

    link_count = len(values) if has_vary and len(urls) <= 1 else len(urls)

    if link_count > MAX_BULK_LINKS:
        raise BulkGenerationError(f"Maximum {MAX_BULK_LINKS} links allowed.")

    if not has_vary:
        return [_link_item(url, clean) for url in urls]

    if len(urls) == 1:
        generated = []
        for value in values:
            next_params = {**clean, clean_bulk_key: value}
            generated.append(_link_item(urls[0], next_params, value))
        return generated

    generated = []
    for url, value in zip(urls, values, strict=True):
        next_params = {**clean, clean_bulk_key: value}
        generated.append(_link_item(url, next_params, value))
    return generated
