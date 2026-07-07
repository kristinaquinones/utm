# Copyright (C) 2026 Kristina Quinones
# SPDX-License-Identifier: GPL-2.0-only

import pytest

from app.utm import (
    BASE_URL_REQUIRED_MSG,
    MAX_BULK_LINKS,
    STANDARD_UTM_REQUIRED_MSG,
    BulkGenerationError,
    build_tracking_url,
    generate_links,
    merge_param_lists,
    resolve_base_urls,
    standard_utm_error,
    url_label,
)


def test_build_tracking_url_adds_https_when_scheme_missing() -> None:
    url = build_tracking_url("example.com/pricing", {"utm_source": "newsletter"})

    assert url == "https://example.com/pricing?utm_source=newsletter"


def test_build_tracking_url_rejects_unparseable_url() -> None:
    with pytest.raises(BulkGenerationError, match="valid URL"):
        build_tracking_url("http://[", {"utm_source": "newsletter"})


def test_url_label_degrades_to_empty_on_unparseable_url() -> None:
    assert url_label("http://[") == ""


def test_build_tracking_url_adds_params_and_preserves_existing_query() -> None:
    url = build_tracking_url(
        "https://example.com/pricing?ref=nav",
        {"utm_source": "newsletter", "utm_campaign": "june launch"},
    )

    assert url == "https://example.com/pricing?ref=nav&utm_source=newsletter&utm_campaign=june+launch"


def test_merge_param_lists_drops_empty_values_and_adds_custom_pairs() -> None:
    params = merge_param_lists(
        {"utm_source": "email", "utm_medium": ""},
        ["audience", ""],
        ["founders", "ignored"],
    )

    assert params == {"utm_source": "email", "audience": "founders"}


def test_generate_links_uses_bulk_key_when_values_are_present() -> None:
    links = generate_links(
        ["https://example.com"],
        {"utm_source": "linkedin", "utm_campaign": "base"},
        "utm_campaign",
        "alpha\nbeta\n",
    )

    assert [item["url"] for item in links] == [
        "https://example.com?utm_source=linkedin&utm_campaign=alpha",
        "https://example.com?utm_source=linkedin&utm_campaign=beta",
    ]
    assert [item["varied_value"] for item in links] == ["alpha", "beta"]


def test_generate_links_supports_multiple_base_urls() -> None:
    links = generate_links(
        [
            "https://example.com/pricing",
            "https://example.com/signup",
        ],
        {"utm_source": "newsletter"},
    )

    assert len(links) == 2
    assert links[0]["url"] == "https://example.com/pricing?utm_source=newsletter"
    assert links[1]["url"] == "https://example.com/signup?utm_source=newsletter"


def test_generate_links_pairs_urls_and_values() -> None:
    links = generate_links(
        [
            "https://example.com/pricing",
            "https://example.com/signup",
        ],
        {"utm_source": "newsletter"},
        "utm_campaign",
        "alpha\nbeta",
    )

    assert links[0]["url"] == "https://example.com/pricing?utm_source=newsletter&utm_campaign=alpha"
    assert links[1]["url"] == "https://example.com/signup?utm_source=newsletter&utm_campaign=beta"


def test_generate_links_rejects_mismatched_url_and_value_counts() -> None:
    with pytest.raises(BulkGenerationError, match="must match"):
        generate_links(
            ["https://example.com/a", "https://example.com/b"],
            {"utm_source": "newsletter"},
            "utm_campaign",
            "alpha",
        )


def test_generate_links_enforces_max_bulk_links() -> None:
    values = "\n".join(f"value-{index}" for index in range(MAX_BULK_LINKS + 1))
    with pytest.raises(BulkGenerationError, match=str(MAX_BULK_LINKS)):
        generate_links(["https://example.com"], {"utm_source": "email"}, "utm_campaign", values)


def test_generate_links_rejects_missing_base_url() -> None:
    with pytest.raises(BulkGenerationError, match=BASE_URL_REQUIRED_MSG):
        generate_links([""], {"utm_source": "email"})


def test_generate_links_rejects_blank_base_urls_in_bulk() -> None:
    with pytest.raises(BulkGenerationError, match=BASE_URL_REQUIRED_MSG):
        generate_links(["", "   "], {"utm_source": "email"})


def test_url_label_uses_last_path_segment() -> None:
    assert url_label("https://example.com/pricing/plans") == "plans"


def test_url_label_falls_back_to_hostname() -> None:
    assert url_label("https://example.com") == "example.com"


def test_resolve_base_urls_uses_bulk_textarea_in_bulk_mode() -> None:
    urls = resolve_base_urls(
        "bulk",
        "https://ignored.example",
        "https://example.com/a\nhttps://example.com/b\n",
    )

    assert urls == ["https://example.com/a", "https://example.com/b"]


def test_standard_utm_error_accepts_one_standard_field() -> None:
    assert standard_utm_error({"utm_source": "email", "audience": "founders"}) is None


def test_standard_utm_error_rejects_custom_only() -> None:
    assert standard_utm_error({"audience": "founders"}) == STANDARD_UTM_REQUIRED_MSG


def test_standard_utm_error_accepts_bulk_vary_on_standard_key() -> None:
    assert (
        standard_utm_error({}, bulk_key="utm_campaign", raw_bulk_values="alpha\n", bulk_mode=True)
        is None
    )


def test_standard_utm_error_rejects_bulk_vary_on_custom_key_only() -> None:
    assert (
        standard_utm_error({}, bulk_key="audience", raw_bulk_values="founders\n", bulk_mode=True)
        == STANDARD_UTM_REQUIRED_MSG
    )


def test_utm_medium_options_are_stable_lowercase_values() -> None:
    from app.utm import UTM_MEDIUM_CHOICES, UTM_MEDIUM_OPTIONS, grouped_utm_medium_choices

    assert "email" in UTM_MEDIUM_OPTIONS
    assert "social" in UTM_MEDIUM_OPTIONS
    assert all(choice["value"] == choice["value"].lower() for choice in UTM_MEDIUM_CHOICES)
    assert sum(len(group["choices"]) for group in grouped_utm_medium_choices()) == len(UTM_MEDIUM_OPTIONS)
