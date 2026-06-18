from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


STANDARD_UTM_KEYS = [
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
]


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


def build_tracking_url(base_url: str, params: dict[str, str]) -> str:
    clean_base = base_url.strip()
    clean = clean_params(params)
    if not clean_base or not clean:
        return clean_base

    parts = urlsplit(clean_base)
    existing = dict(parse_qsl(parts.query, keep_blank_values=True))
    existing.update(clean)
    query = urlencode(existing, doseq=True)

    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def bulk_values(raw_values: str) -> list[str]:
    return [line.strip() for line in raw_values.splitlines() if line.strip()]


def generate_links(
    base_url: str,
    params: dict[str, str],
    bulk_key: str = "",
    raw_bulk_values: str = "",
) -> list[dict[str, object]]:
    values = bulk_values(raw_bulk_values)
    clean_bulk_key = bulk_key.strip()

    if not clean_bulk_key or not values:
        return [{"params": clean_params(params), "url": build_tracking_url(base_url, params)}]

    generated = []
    for value in values:
        next_params = {**clean_params(params), clean_bulk_key: value}
        generated.append({"params": next_params, "url": build_tracking_url(base_url, next_params)})

    return generated
