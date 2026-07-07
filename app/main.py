"""dictation-backend — VPS 聽寫後端（SPEC §2）。

端點：POST /dictate（音訊 → STT + 潤飾）、POST /polish、GET /health。
"""

import asyncio
import logging
import secrets
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from . import stt
from .config import settings
from .polish import polish, rewrite

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("dictation")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # STT 模型啟動時載入一次並常駐（SPEC §2.2）
    stt.load_model()
    yield


app = FastAPI(title="dictation-backend", docs_url=None, redoc_url=None, lifespan=lifespan)


def require_token(request: Request) -> None:
    auth = request.headers.get("authorization", "")
    scheme, _, token = auth.partition(" ")
    if scheme.lower() != "bearer" or not secrets.compare_digest(
        token.strip(), settings.dictation_token
    ):
        raise HTTPException(status_code=401, detail="invalid or missing token")


class PolishRequest(BaseModel):
    text: str
    app_context: str | None = None
    privacy_mode: bool = False
    # Command Mode（Phase 5）：有值時 text 視為「原文」、command 為口述改寫指令
    command: str | None = None


@app.get("/health", dependencies=[Depends(require_token)])
async def health() -> dict:
    return {"status": "ok", "stt": "loaded" if stt.is_loaded() else "not_loaded"}


@app.post("/polish", dependencies=[Depends(require_token)])
async def polish_endpoint(req: PolishRequest) -> dict:
    # privacy_mode=true → 強制不呼叫雲端，回原始逐字稿（SPEC §2.1）
    if req.privacy_mode or settings.polish_provider == "none":
        return {"text": req.text}
    try:
        if req.command and req.command.strip():
            cleaned = await rewrite(req.text, req.command.strip(), req.app_context)
        else:
            cleaned = await polish(req.text, req.app_context)
    except Exception as e:
        log.warning("polish provider (%s) failed: %s", settings.polish_provider, e)
        raise HTTPException(status_code=502, detail=f"polish provider error: {e}")
    return {"text": cleaned}


@app.post("/dictate", dependencies=[Depends(require_token)])
async def dictate_endpoint(
    audio: UploadFile = File(...),
    app_context: str | None = Form(None),
    privacy_mode: bool = Form(False),
) -> dict:
    data = await audio.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty audio")

    t0 = time.perf_counter()
    try:
        # CPU-bound，丟 thread 避免卡住事件圈（單 worker）
        raw = await asyncio.to_thread(stt.transcribe, data)
    except Exception as e:
        log.error("STT failed: %s", e)
        raise HTTPException(status_code=500, detail=f"stt error: {e}")
    stt_secs = time.perf_counter() - t0

    if privacy_mode or settings.polish_provider == "none" or not raw:
        log.info("dictate: stt %.2fs, polish skipped", stt_secs)
        return {"text": raw}

    t1 = time.perf_counter()
    try:
        cleaned = await polish(raw, app_context)
    except Exception as e:
        # fail-open：潤飾掛了就回原始逐字稿，鍵盤端不至於什麼都拿不到
        log.warning("dictate: polish failed, returning raw transcript: %s", e)
        log.info("dictate: stt %.2fs, polish failed", stt_secs)
        return {"text": raw}
    log.info("dictate: stt %.2fs, polish %.2fs", stt_secs, time.perf_counter() - t1)
    return {"text": cleaned}
