"""faster-whisper 封裝（SPEC §2.2）。

模型於服務啟動時載入一次並常駐，禁止每請求重載。
設定：int8、cpu_threads=2、beam_size=1、vad_filter=True、
language=None（自動偵測 zh/en 混用）、initial_prompt=醫學詞庫。
"""

import logging
import time
from io import BytesIO
from pathlib import Path

from faster_whisper import WhisperModel

from .config import settings

log = logging.getLogger("dictation.stt")

_DICT_PATH = Path(__file__).with_name("dictionary.txt")

_model: WhisperModel | None = None
_initial_prompt_cache: str | None = None


# Whisper 的 initial_prompt 上限約 224 tokens，超過會被截斷；
# 保守以字元數截斷（詞庫檔內重要詞放前面）。
_INITIAL_PROMPT_MAX_CHARS = 400


def _initial_prompt() -> str | None:
    global _initial_prompt_cache
    if _initial_prompt_cache is not None:
        return _initial_prompt_cache or None
    try:
        lines = _DICT_PATH.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        _initial_prompt_cache = ""
        return None
    words = [w.strip() for w in lines if w.strip() and not w.strip().startswith("#")]
    if not words:
        _initial_prompt_cache = ""
        return None
    prompt = "醫療聽寫，繁體中文與英文醫學名詞混用。常用詞："
    for word in words:
        if len(prompt) + len(word) + 1 > _INITIAL_PROMPT_MAX_CHARS:
            break
        prompt += word + "、"
    _initial_prompt_cache = prompt.rstrip("、")
    return _initial_prompt_cache


def load_model() -> None:
    """服務啟動時呼叫一次；重複呼叫為 no-op。"""
    global _model
    if _model is not None:
        return
    t0 = time.perf_counter()
    _model = WhisperModel(
        settings.stt_model,
        device="cpu",
        compute_type="int8",
        cpu_threads=2,
    )
    log.info(
        "STT model '%s' (int8) loaded in %.1fs",
        settings.stt_model,
        time.perf_counter() - t0,
    )


def is_loaded() -> bool:
    return _model is not None


def transcribe(audio: bytes) -> str:
    """音訊 bytes（wav/webm 等，PyAV 自動解碼）→ 逐字稿。CPU-bound，呼叫端請丟 thread。"""
    if _model is None:
        raise RuntimeError("STT model not loaded")
    t0 = time.perf_counter()
    segments, info = _model.transcribe(
        BytesIO(audio),
        beam_size=1,
        vad_filter=True,
        language=None,
        initial_prompt=_initial_prompt(),
    )
    text = "".join(segment.text for segment in segments).strip()
    log.info(
        "STT %.2fs (audio %.1fs, lang=%s p=%.2f)",
        time.perf_counter() - t0,
        info.duration,
        info.language,
        info.language_probability,
    )
    return text
