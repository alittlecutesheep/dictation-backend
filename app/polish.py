"""Polish provider 抽象（SPEC §4）。

介面固定：polish(text, app_context) -> str
依 POLISH_PROVIDER 決定實作；system prompt 所有 provider 共用，
並附上 dictionary.txt 詞庫做同音錯字校正。
"""

from pathlib import Path

import httpx

from .config import settings

GEMINI_MODEL = "gemini-3.1-flash-lite"
OPENAI_MODEL = "gpt-5-nano"
CLAUDE_MODEL = "claude-haiku-4-5"

_DICT_PATH = Path(__file__).with_name("dictionary.txt")

SYSTEM_PROMPT = """你是聽寫後處理引擎。將原始語音逐字稿轉為乾淨、可直接送出的文字。
- 移除填充詞（嗯、呃、就是、um、uh）與口吃重複。
- 修正標點、大小寫、換行；使用者不口說標點。
- 處理口誤自我修正：「三點，不對，改四點」→ 只輸出「四點」。
- 保留繁體中文；醫學/技術英文原樣保留（SOAP、CRP、osteomyelitis 等）。
- 依 app_context 調語氣：Slack 口語、Gmail 正式、程式碼編輯器保留 camelCase/snake_case。
- 套用詞庫做同音錯字校正。
- 只輸出最終文字本身。無前言、無解釋、無引號、無 markdown。"""

# Command Mode（SPEC §8 Phase 5）：選取文字 + 語音指令 → 改寫
REWRITE_SYSTEM_PROMPT = """你是文字改寫引擎。使用者提供一段「原文」與一句口述的「指令」（來自語音辨識，可能有雜訊），依指令改寫原文。
- 常見指令例：「改成條列」「翻成英文」「更正式一點」「縮短成兩句」。
- 指令若有語音辨識雜訊，理解其意圖即可。
- 除指令要求外，保留原文的語言、事實與專有名詞；醫學/技術英文原樣保留。
- 套用詞庫做同音錯字校正。
- 只輸出改寫後的文字本身。無前言、無解釋、無引號、無 markdown 圍欄。"""


def _load_dictionary() -> str:
    try:
        lines = _DICT_PATH.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return ""
    words = [w.strip() for w in lines if w.strip() and not w.strip().startswith("#")]
    if not words:
        return ""
    return "\n\n詞庫（同音/專有名詞校正優先參照）：\n" + "、".join(words)


def _system_prompt() -> str:
    return SYSTEM_PROMPT + _load_dictionary()


def _user_message(text: str, app_context: str | None) -> str:
    if app_context:
        return f"[app_context: {app_context}]\n{text}"
    return text


async def _gemini(client: httpx.AsyncClient, system: str, user: str) -> str:
    r = await client.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
        headers={"x-goog-api-key": settings.gemini_api_key},
        json={
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": 0.2},
        },
    )
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


async def _openai(client: httpx.AsyncClient, system: str, user: str) -> str:
    r = await client.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {settings.openai_api_key}"},
        json={
            "model": OPENAI_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


async def _claude(client: httpx.AsyncClient, system: str, user: str) -> str:
    r = await client.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
        },
        json={
            "model": CLAUDE_MODEL,
            "max_tokens": 2048,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        },
    )
    r.raise_for_status()
    return r.json()["content"][0]["text"]


async def _ollama(client: httpx.AsyncClient, system: str, user: str) -> str:
    r = await client.post(
        f"{settings.ollama_base_url}/api/chat",
        json={
            "model": settings.ollama_model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
    )
    r.raise_for_status()
    return r.json()["message"]["content"]


_PROVIDERS = {
    "gemini": _gemini,
    "openai": _openai,
    "claude": _claude,
    "ollama": _ollama,
}


async def polish(text: str, app_context: str | None) -> str:
    """依 POLISH_PROVIDER 潤飾逐字稿；provider=none 時原樣回傳。"""
    if settings.polish_provider == "none":
        return text
    fn = _PROVIDERS[settings.polish_provider]
    async with httpx.AsyncClient(timeout=30.0) as client:
        result = await fn(client, _system_prompt(), _user_message(text, app_context))
    return result.strip()


async def rewrite(text: str, command: str, app_context: str | None) -> str:
    """Command Mode：依語音指令改寫選取文字；provider=none 時原樣回傳。"""
    if settings.polish_provider == "none":
        return text
    fn = _PROVIDERS[settings.polish_provider]
    user = f"指令：{command}\n\n原文：\n{text}"
    if app_context:
        user = f"[app_context: {app_context}]\n{user}"
    system = REWRITE_SYSTEM_PROMPT + _load_dictionary()
    async with httpx.AsyncClient(timeout=30.0) as client:
        result = await fn(client, system, user)
    return result.strip()
