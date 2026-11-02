# SMSATBOX

> 短信 / 未接来电 多卡提醒盒子 —— ESP32 + 云端中转 + 多端客户端
> 全局版本：**v1.0.0**

## 四大模块

| 目录 | 内容 | 状态 |
| --- | --- | --- |
| [`server/`](server/README.md) | 云端中转平台（FastAPI + SQLite + WebSocket + PWA 管理端 + Docker + CI） | ✅ 第一阶段已完成 |
| `esp32/` | ESP32-S3(N16R8) 固件：双 ML307A-DSLN 4G 模组、AP 配网、本地 Web、OTA 双分区 | ⏳ 阶段二 |
| `android/` | APK：底部导航、系统通知、验证码复制、GitHub 独立升级 | ⏳ 阶段三 |
| `windows/` | EXE：托盘常驻、原生通知、GitHub 独立升级 | ⏳ 阶段三 |

## 两条互相隔离的发布维度

### 维度一：外部用户端（APK & EXE）—— 走 GitHub Release
- `.github/workflows/release-build.yml`，推送 Tag（如 `v1.0.0`）触发
- 自动打包 APK + EXE，发布到 GitHub Release
- 客户端**直连 GitHub Release API** 检查更新，绝不经过 Server 中转
- 同版本 Tag 覆盖附件，不同版本新建

### 维度二：底层协同（ESP32 & Server）—— 走 Docker Hub + OTA
- `.github/workflows/docker-build.yml`，push 或 Tag 触发
- GitHub Runner 构建多架构镜像 → 推送 `beibing173/smsatbox-server`
- 同版本 Tag 覆盖，不同版本新建
- **ESP32 固件不参与 GitHub Release**
- Server → ESP32：上传 `.bin`，WebSocket 下发，静默下载 + MD5 校验 + 双分区升级
- ESP32 → Server：检测到版本落后时可请求拉取最新镜像并重启（默认关闭的安全开关）

## 快速开始（当前可用）

```bash
cd server
cp .env.example .env       # 修改 ADMIN_PASSWORD / SECRET_KEY
docker compose up -d --build
```

浏览器打开 <http://127.0.0.1:8080>，默认 `admin / Admin@123456`。

不想用 Docker？直接 Python 跑：

```bash
cd server
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements-dev.txt
uvicorn app.main:app --port 8080
pytest tests -q            # 15 项测试
python scripts/smoke.py http://127.0.0.1:8080   # 46 项端到端冒烟
```

详细文档见 [server/README.md](server/README.md)。
