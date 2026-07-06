"""dictation-backend — VPS 聽寫後端（SPEC §2）。

Phase 1 端點：POST /polish、GET /health。
Phase 3 將加入 POST /dictate（faster-whisper STT）。
"""

import logging
import secrets

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel

from .config import settings
from .polish import polish

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("dictation")

app = FastAPI(title="dictation-backend", docs_url=None, redoc_url=None)


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


@app.get("/health", dependencies=[Depends(require_token)])
async def health() -> dict:
    # stt 於 Phase 3 常駐載入後改回報 "loaded"
    return {"status": "ok", "stt": "not_loaded"}


@app.post("/polish", dependencies=[Depends(require_token)])
async def polish_endpoint(req: PolishRequest) -> dict:
    # privacy_mode=true → 強制不呼叫雲端，回原始逐字稿（SPEC §2.1）
    if req.privacy_mode or settings.polish_provider == "none":
        return {"text": req.text}
    try:
        cleaned = await polish(req.text, req.app_context)
    except Exception as e:
        log.warning("polish provider (%s) failed: %s", settings.polish_provider, e)
        raise HTTPException(status_code=502, detail=f"polish provider error: {e}")
    return {"text": cleaned}
