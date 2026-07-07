# dictation-backend

Voice Flow 的 VPS 聽寫後端（FastAPI）。規格見專案 SPEC.md（單一真相來源）。

## 端點

| Method | Path | 用途 |
|--------|------|------|
| POST | `/polish` | 逐字稿 LLM 潤飾（桌面端用；已本地 STT） |
| GET | `/health` | 健康檢查 |
| POST | `/dictate` | 音訊（wav/webm）→ faster-whisper STT + 潤飾（Android 用） |

全部端點需 `Authorization: Bearer <DICTATION_TOKEN>`。
`privacy_mode=true` 強制回傳原始逐字稿、不呼叫雲端。

## 部署（VPS：/docker/dictation-backend/）

```bash
cp .env.example .env   # 填 DICTATION_TOKEN 與 provider API key
docker compose up -d --build
```

## 驗證

```bash
TOKEN=$(grep ^DICTATION_TOKEN .env | cut -d= -f2)
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8010/health
curl -s -X POST http://127.0.0.1:8010/polish \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"text":"嗯就是那個病人今天 CRP 有點高，呃，開三天，不對，開五天的抗生素"}'
```
