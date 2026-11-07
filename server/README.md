# SMSATBOX Server · 云端中转平台

> 短信 / 未接来电 多卡提醒盒子 —— 云端核心中枢
> 当前版本 **v1.0.0**

基于 **FastAPI + SQLite + WebSocket**，单进程即可跑通全部功能；容器化后一条命令上线。

---

## 一、能力概览

| 模块 | 说明 |
| --- | --- |
| 设备接入 | ESP32 仅凭唯一 `Device_Token` 鉴权，上行心跳 / 短信 / 来电，下行指令与 OTA |
| 实时推送 | WebSocket 双通道：`/ws`（人）、`/ws/device`（设备） |
| RBAC | 超级管理员（全权） / 普通成员（仅授权卡槽可见、受控发短信） |
| 消息中心 | 短信 + 来电 + 系统消息，自动提取验证码，支持搜索 / 筛选 / 已读 |
| 反向控制 | Web 下发“发送短信”，WebSocket 实时推送设备，离线自动排队补发 |
| OTA | 上传 `.bin` → MD5 校验值入库 → 设备静默下载 → 回写结果 → 固件版本自更新 |
| 协同升级 | 设备可请求 Server 拉取 Docker Hub 最新镜像并重启（默认关闭，安全开关） |
| 审计 | 登录、改密、授权、下发、OTA 全量落库 |
| Web 管理端 | 暗黑科技风单页应用，响应式 + PWA（可添加到主屏幕） |

---

## 二、本地运行（三种方式）

### 方式 A：直接 Python 运行（最快，调试用）

```bash
cd server
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements-dev.txt
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

打开 <http://127.0.0.1:8080> ，默认账号：

```
用户名：admin
密码：  Admin@123456
```

### 方式 B：Docker 直接拉镜像（推荐）

镜像已发布在 Docker Hub：**[beibing173/smsatbox-server](https://hub.docker.com/r/beibing173/smsatbox-server)**

```bash
# 最简：一条命令跑起来
docker pull beibing173/smsatbox-server:latest

docker run -d --name smsatbox-server \
  --restart unless-stopped \
  -p 8080:8080 \
  -e ADMIN_PASSWORD='请改成强密码' \
  -e SECRET_KEY="$(openssl rand -base64 48)" \
  -v smsatbox-data:/data \
  beibing173/smsatbox-server:latest
```

或者用 compose（配置集中管理，推荐生产）：

```bash
cd server
cp .env.example .env          # Windows: copy .env.example .env
# 编辑 .env，务必修改 ADMIN_PASSWORD 与 SECRET_KEY

docker compose pull           # 拉取最新镜像
docker compose up -d
docker compose logs -f
```

**可用标签**：

| 标签 | 含义 |
| --- | --- |
| `latest` | 最新构建 |
| `1.0.0` | 精确版本 |
| `1.0` | 主.次版本 |
| `sha-xxxxxxx` | 对应 commit |

**升级**：
```bash
docker compose pull && docker compose up -d
# 或单容器：
docker pull beibing173/smsatbox-server:latest
docker stop smsatbox-server && docker rm smsatbox-server && \
  docker run -d ...（同上）
```

> 数据（SQLite + 固件）持久化在 `/data`，挂载 volume 后重建容器不丢数据。

### 方式 C：从源码构建镜像

改了代码想自己编译时用：

```bash
cd server
docker compose up -d --build
# 或
docker build -t beibing173/smsatbox-server:1.0.0 .
```

### 一键验收

```bash
# 服务跑起来后，另开一个终端
python scripts/smoke.py http://127.0.0.1:8080
# 或跑单元/集成测试
pytest tests -q
```

冒烟脚本会真实走完：登录 → 建卡 → 设备上报 → 验证码提取 → 成员授权 → 反向控制 → OTA 上传下载 → 静态资源。

---

## 三、目录结构

```
server/
├── app/
│   ├── main.py              # FastAPI 入口、中间件、路由注册、静态托管
│   ├── config.py            # 环境变量配置（含 SECRET_KEY 自动生成持久化）
│   ├── db.py                # SQLite 连接、建表 SQL、种子数据
│   ├── security.py          # 密码哈希、JWT、设备令牌、RBAC 依赖
│   ├── schemas.py           # Pydantic 请求/响应模型
│   ├── realtime.py          # WebSocket 连接管理器
│   ├── utils.py             # 时间/验证码提取/审计等工具
│   ├── routers/
│   │   ├── auth.py          # 登录、当前用户、客户端令牌、改密
│   │   ├── users.py         # 用户管理 + 卡槽权限分配
│   │   ├── devices.py       # 设备、卡槽、OTA 上传下发
│   │   ├── messages.py      # 消息总览、验证码、已读、反向控制
│   │   ├── device_api.py    # ESP32 专用 API（Device_Token 鉴权）
│   │   ├── ota.py           # 固件下载通道
│   │   ├── system.py        # 健康检查、版本、总览、审计
│   │   └── ws.py            # WebSocket 双通道
│   ├── services/            # 业务逻辑（设备/消息/指令/升级）
│   └── static/              # Web 管理端（index.html / app.js / styles.css / PWA）
├── tests/                   # pytest：API、RBAC、OTA、WebSocket
├── scripts/smoke.py         # 真实进程冒烟脚本
├── Dockerfile               # 多阶段构建，非 root 运行，内置 HEALTHCHECK
├── docker-compose.yml       # 一键编排（数据卷 + 健康检查 + 日志轮转）
├── requirements.txt         # 运行依赖
├── requirements-dev.txt     # 含 pytest / httpx
└── .env.example             # 环境变量模板
```

---

## 四、数据库表结构

| 表 | 作用 | 关键字段 |
| --- | --- | --- |
| `users` | 用户 | `username` 唯一、`password_hash`(PBKDF2-SHA256 26 万轮)、`role` = superadmin/member、`is_active` |
| `devices` | 设备 | `device_token` 唯一、`firmware_version`、`local_ip`、`wifi_rssi`、`net_mode`、`online`、`last_seen_at` |
| `sim_cards` | SIM 卡槽 | `device_id + slot_index` 唯一、`phone_number`、`carrier`、`plan_name`、`plan_expire_at`、`signal_dbm` |
| `permissions` | 成员→卡槽 授权 | 主键 `(user_id, slot_id)`、`can_read`、`can_send_sms`、`granted_by` |
| `messages` | 短信/来电 | `kind` = sms/call/system、`sender`、`content`、`code`(自动提取)、`received_at`、`is_read`、`raw` |
| `sms_commands` | 下行指令 | `target_number`、`content`、`status` = pending/sent/delivered/failed、`created_by` |
| `ota_tasks` | 固件任务 | `version`、`filename`、`md5`、`size`、`status` |
| `user_tokens` | 客户端长效令牌 | `token_hash`（只存哈希）、`last_used_at` |
| `audit_logs` | 审计 | `action`、`target`、`detail`、`ip` |
| `app_settings` | 全局配置 | `key` / `value` |

---

## 五、环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `ADMIN_USERNAME` | `admin` | 首启创建的管理员账号 |
| `ADMIN_PASSWORD` | `Admin@123456` | **务必修改**，否则启动日志会告警 |
| `SECRET_KEY` | 自动生成 | JWT 签名密钥，留空则写入 `/data/.secret_key` |
| `TOKEN_TTL_MINUTES` | `720` | 登录令牌有效期 |
| `HTTP_PORT` | `8080` | compose 映射的宿主端口 |
| `DATA_DIR` | `/data` | 数据目录（数据库 + 固件） |
| `CORS_ORIGINS` | `*` | 跨域白名单，生产建议写死 |
| `DEVICE_OFFLINE_SECONDS` | `90` | 设备离线判定阈值 |
| `MAX_FIRMWARE_MB` | `16` | 固件上传大小上限 |
| `SERVER_IMAGE` | `beibing173/smsatbox-server` | 协同升级用的镜像名 |
| `SERVER_UPGRADE_ENABLED` | `false` | 是否允许 ESP32 触发 Server 自升级 |
| `SERVER_UPGRADE_COMMAND` | 空 | 具体升级命令（需挂载 docker.sock） |

---

## 六、CI/CD（维度二）

`.github/workflows/docker-build.yml`：

1. **test** —— 用 Python 3.12 跑 `pytest`，不过不进下一步；
2. **build** —— Buildx 多架构（amd64 + arm64）构建并推送 Docker Hub：
   `beibing173/smsatbox-server:{版本} / {主.次} / latest / sha-{短哈希}`；
3. **smoke** —— 真把镜像拉起来，`curl` 健康检查 + 版本比对 + 登录冒烟。

标签规则：**同版本覆盖同名 tag，不同版本新建 tag**（`docker push` 天然覆盖）。

需要在仓库 Settings → Secrets 配置：

| Secret | 说明 |
| --- | --- |
| `DOCKERHUB_USERNAME` | Docker Hub 用户名 |
| `DOCKERHUB_TOKEN` | Docker Hub Access Token（不要用密码） |

---

## 七、安全设计要点

- ESP32 **不保存**任何用户密码、成员列表或权限逻辑，只持有一个 `Device_Token`；
- 用户权限、卡槽可见性、套餐到期日全部由 Server 数据库裁决；
- 密码 PBKDF2-SHA256（260k 轮 + 随机盐），令牌存哈希不存明文；
- 固件下载通道需 `Device_Token`，文件名做路径穿越校验，扩展名白名单 `.bin`；
- 设备触发 Server 自升级默认关闭，开启需同时配置受控命令，且需挂载 docker.sock；
- 所有响应头附 `X-API-Version`，全平台版本一致性可被外部校验。

---

## 八、下一步

- [ ] `esp32/`：ESP32-S3 固件（ML307A 双模组、`+CMTI`/`+CLIP` 解析、AP 配网、LAN Web、OTA 双分区）
- [ ] `android/`：APK（底部导航、通知、验证码复制、GitHub API 自更新）
- [ ] `windows/`：EXE（托盘常驻、原生通知、GitHub API 自更新）
- [ ] `.github/workflows/release-build.yml`：APK/EXE 打包发布（维度一）
