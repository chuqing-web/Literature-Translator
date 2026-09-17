from app.services.openai_url import openai_chat_completions_url


def test_bare_host_appends_v1_chat():
    assert (
        openai_chat_completions_url("https://apihub.agnes-ai.com")
        == "https://apihub.agnes-ai.com/v1/chat/completions"
    )


def test_v1_suffix_appends_chat_only():
    assert (
        openai_chat_completions_url("https://apihub.agnes-ai.com/v1/")
        == "https://apihub.agnes-ai.com/v1/chat/completions"
    )


def test_custom_prefix_path():
    assert (
        openai_chat_completions_url("https://openrouter.ai/api/v1")
        == "https://openrouter.ai/api/v1/chat/completions"
    )


def test_full_url_mode_passthrough():
    full = "https://gateway.example.com/custom/openai/chat"
    assert openai_chat_completions_url(full, is_full_url=True) == full


def test_already_complete_path():
    url = "https://host.example/v1/chat/completions"
    assert openai_chat_completions_url(url) == url
