# ---------- SMSATBOX Server ----------
# 构建：docker build -t beibing173/smsatbox-server:1.0.0 .
# 多阶段构建：第一阶段装依赖，第二阶段仅保留运行时，镜像更小

# ----------------------------- 依赖层 -----------------------------
FROM python:3.12-slim AS deps

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build
COPY requirements.txt .
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r requirements.txt

# ----------------------------- 运行层 -----------------------------
FROM python:3.12-slim AS runtime

ARG VERSION=1.0.0
ARG BUILD_DATE=unknown
ARG VCS_REF=unknown

LABEL org.opencontainers.image.title="SMSATBOX Server" \
      org.opencontainers.image.description="短信/未接来电多卡提醒盒子 · 云端中转平台" \
      org.opencontainers.image.source="https://github.com/beibing173/smsatbox" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}"

ENV SMSATBOX_IMAGE_VERSION=${VERSION}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    DATA_DIR=/data \
    TZ=Asia/Shanghai

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# 非 root 运行
RUN groupadd -g 10001 smsatbox \
    && useradd -u 10001 -g smsatbox -m -s /usr/sbin/nologin smsatbox

WORKDIR /app

COPY --from=deps /opt/venv /opt/venv
COPY --chown=smsatbox:smsatbox app ./app
COPY --chown=smsatbox:smsatbox requirements.txt ./

RUN mkdir -p /data/firmware && chown -R smsatbox:smsatbox /data

USER smsatbox

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8080/api/v1/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips", "*"]
