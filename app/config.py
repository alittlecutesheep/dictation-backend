"""讀取環境變數。所有設定集中於此，啟動時載入一次。"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    dictation_token: str
    polish_provider: str  # gemini | openai | claude | ollama | none
    gemini_api_key: str
    openai_api_key: str
    anthropic_api_key: str
    ollama_base_url: str
    ollama_model: str
    stt_model: str  # Phase 3 使用


def _load() -> Settings:
    token = os.environ.get("DICTATION_TOKEN", "")
    if not token or token == "change-me":
        raise RuntimeError("DICTATION_TOKEN 必須設定為非預設值（.env）")

    provider = os.environ.get("POLISH_PROVIDER", "gemini").lower()
    if provider not in ("gemini", "openai", "claude", "ollama", "none"):
        raise RuntimeError(f"POLISH_PROVIDER 不合法: {provider}")

    return Settings(
        dictation_token=token,
        polish_provider=provider,
        gemini_api_key=os.environ.get("GEMINI_API_KEY", ""),
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        ollama_base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/"),
        ollama_model=os.environ.get("OLLAMA_MODEL", "qwen2.5:7b"),
        stt_model=os.environ.get("STT_MODEL", "small"),
    )


settings = _load()
