FROM python:3.12-slim

ENV TZ=Asia/Taipei \
    PYTHONUNBUFFERED=1

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000

# 單 worker：Phase 3 STT 模型常駐後避免多份模型佔滿 RAM（SPEC §2.2）
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
