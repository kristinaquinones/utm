from app.utm import build_tracking_url, generate_links, merge_param_lists


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
        "https://example.com",
        {"utm_source": "linkedin", "utm_campaign": "base"},
        "utm_campaign",
        "alpha\nbeta\n",
    )

    assert [item["url"] for item in links] == [
        "https://example.com?utm_source=linkedin&utm_campaign=alpha",
        "https://example.com?utm_source=linkedin&utm_campaign=beta",
    ]
