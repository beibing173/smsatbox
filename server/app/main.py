"""SMSATBOX Server 入口。

启动： uvicorn app.main:app --host 0.0.0.0 --port 8080
文档： /docs   (OpenAPI)
面板： /       (Web 管理端 PWA)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import settings
from .db import init_db
from .version import VERSION

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("smsatbox")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("SMSATBOX Server v%s 启动完成 | db=%s", VERSION, settings.db_path)
    if settings.admin_password == "Admin@123456":
        logger.warning("检测到默认管理员密码，请尽快通过环境变量 ADMIN_PASSWORD 修改！")
    yield
    logger.info("SMSATBOX Server 已停止")


app = FastAPI(
    title="SMSATBOX Server",
    version=VERSION,
    description="短信 / 未接来电多卡提醒盒子 —— 云端中转平台",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins or ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-API-Version"],
)


@app.middleware("http")
async def add_version_header(request: Request, call_next):
    """全平台约定：所有响应都带版本标识。"""
    response = await call_next(request)
    response.headers["X-API-Version"] = VERSION
    response.headers["X-Service-Name"] = settings.app_name
    return response


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "status": exc.status_code,
            "version": VERSION,
            "path": request.url.path,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "detail": "请求参数校验失败",
            "errors": exc.errors(),
            "version": VERSION,
            "path": request.url.path,
        },
    )


# --------------------------------------------------------------------------- #
# 路由注册
# --------------------------------------------------------------------------- #
from .routers import (  # noqa: E402
    auth,
    device_api,
    devices,
    esim,
    messages,
    ota,
    system,
    users,
    ws,
)

api = settings.api_prefix
app.include_router(system.router, prefix=api)
app.include_router(auth.router, prefix=api)
app.include_router(users.router, prefix=api)
app.include_router(devices.router, prefix=api)
app.include_router(messages.router, prefix=api)
app.include_router(device_api.router, prefix=api)
app.include_router(esim.router, prefix=api)
app.include_router(ota.router, prefix=api)
app.include_router(ws.router, prefix=api)


# --------------------------------------------------------------------------- #
# Web 管理端（PWA 静态资源）
# --------------------------------------------------------------------------- #
STATIC_DIR = settings.static_dir
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR)), name="assets")


@app.get("/", include_in_schema=False)
def index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return JSONResponse(
        {
            "product": settings.app_name,
            "version": VERSION,
            "message": "Web 管理端静态资源缺失，请检查 app/static 目录",
        }
    )


@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest():
    path = STATIC_DIR / "manifest.webmanifest"
    if path.exists():
        return FileResponse(path, media_type="application/manifest+json")
    return JSONResponse({"error": "manifest 缺失"}, status_code=404)


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    path = STATIC_DIR / "sw.js"
    if path.exists():
        return FileResponse(path, media_type="application/javascript")
    return JSONResponse({"error": "sw.js 缺失"}, status_code=404)


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    path = STATIC_DIR / "favicon.svg"
    if path.exists():
        return FileResponse(path, media_type="image/svg+xml")
    return RedirectResponse("/assets/favicon.svg")
