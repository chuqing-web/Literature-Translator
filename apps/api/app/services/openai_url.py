from __future__ import annotations

from urllib.parse import urlparse


def normalize_base_url(base_url: str) -> str:
    """Strip whitespace and trailing slashes (CC Switch FAQ)."""
    return (base_url or "").strip().rstrip("/")


def openai_chat_completions_url(base_url: str, *, is_full_url: bool = False) -> str:
    """Resolve chat-completions URL the way CC Switch does.

    - **Default (prefix mode):** treat ``base_url`` as a prefix.
      - ``https://host`` → ``https://host/v1/chat/completions``
      - ``https://host/v1`` → ``https://host/v1/chat/completions``
      - ``https://host/custom/v1`` → ``https://host/custom/v1/chat/completions``
    - **Full URL mode:** use ``base_url`` as the exact endpoint (no path append).
    """
    base = normalize_base_url(base_url)
    if not base:
        raise ValueError("Base URL is empty")

    if is_full_url:
        return base

    if base.endswith("/chat/completions"):
        return base

    parsed = urlparse(base)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid Base URL: {base_url!r}")

    path = (parsed.path or "").rstrip("/")
    # Bare origin → append /v1/chat/completions (CC Switch default table)
    if path in ("", "/"):
        return f"{parsed.scheme}://{parsed.netloc}/v1/chat/completions"

    # Already ends with /v1 (or .../v1) → append /chat/completions only
    if path == "/v1" or path.endswith("/v1"):
        return f"{base}/chat/completions"

    # Custom prefix path → append /chat/completions
    return f"{base}/chat/completions"


# Common OpenAI-compatible vendor presets (inspired by CC Switch provider list)
PROVIDER_PRESETS: list[dict[str, str]] = [
    {
        "id": "openai",
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
    },
    {
        "id": "agnes",
        "name": "Agnes",
        "base_url": "https://apihub.agnes-ai.com/v1",
        "model": "agnes-2.5-flash",
    },
    {
        "id": "deepseek",
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    },
    {
        "id": "openrouter",
        "name": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "model": "openai/gpt-4o-mini",
    },
    {
        "id": "siliconflow",
        "name": "SiliconFlow",
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "deepseek-ai/DeepSeek-V3",
    },
    {
        "id": "moonshot",
        "name": "Moonshot (Kimi)",
        "base_url": "https://api.moonshot.cn/v1",
        "model": "moonshot-v1-8k",
    },
    {
        "id": "zhipu",
        "name": "Zhipu GLM",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4-flash",
    },
    {
        "id": "ollama",
        "name": "Ollama (local)",
        "base_url": "http://127.0.0.1:11434/v1",
        "model": "llama3.2",
    },
    {
        "id": "custom",
        "name": "Custom / OpenAI Compatible",
        "base_url": "",
        "model": "",
    },
]
