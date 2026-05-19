from cognix.providers.resolver import normalize_openai_base_url


def test_normalize_openai_base_url_appends_v1_for_gateway_root() -> None:
    assert normalize_openai_base_url("https://ai.xiuxian.info") == "https://ai.xiuxian.info/v1"


def test_normalize_openai_base_url_keeps_existing_path() -> None:
    assert normalize_openai_base_url("https://ai.xiuxian.info/v1") == "https://ai.xiuxian.info/v1"


def test_normalize_openai_base_url_handles_empty_values() -> None:
    assert normalize_openai_base_url("") is None
    assert normalize_openai_base_url(None) is None
