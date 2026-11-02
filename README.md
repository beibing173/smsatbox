# SMSATBOX

> 短信 / 未接来电 多卡提醒盒子 —— ESP32 硬件端 + 云端中转 + 三端客户端
> 全局版本：**v1.0.0** · [已发布](https://github.com/beibing173/smsatbox/releases/tag/v1.0.0)

---

## 四大模块（全部完成）

| 目录 | 内容 | 状态 |
| --- | --- | --- |
| [`server/`](server/README.md) | 云端中转平台：FastAPI + SQLite + WebSocket + RBAC + OTA + PWA 管理端 | ✅ 已交付 |
| [`esp32/`](esp32/README.md) | ESP32-S3(N16R8) 固件：双 ML307A 驱动、AP 配网、局域网 Web、双分区 OTA | ✅ 已交付 · 编译通过 |
| [`android/`](android/README.md) | APK：底部导航、系统通知、验证码复制、GitHub 独立升级 | ✅ 已交付 · CI 打包 |
| [`windows/`](windows/README.md) | EXE：托盘常驻、原生 Toast、GitHub 独立升级 | ✅ 已交付 · CI 打包 |

---

## 立即使用

**下载客户端**（v1.0.0）：

| 平台 | 文件 | 说明 |
| --- | --- | --- |
| 📱 Android | [smsatbox-v1.0.0.apk](https://github.com/beibing173/smsatbox/releases/download/v1.0.0/smsatbox-v1.0.0.apk) | 5.1 MB |
| 🖥️ Windows | [smsatbox-v1.0.0.exe](https://github.com/beibing173/smsatbox/releases/download/v1.0.0/smsatbox-v1.0.0.exe) | 69 MB 单文件 |

**启动服务端**：

```bash
cd server
cp .env.example .env       # 修改 ADMIN_PASSWORD / SECRET_KEY
docker compose up -d --build
```

浏览器打开 `http://<服务器IP>:8080`，默认 `admin / Admin@123456`。

不用 Docker 也行：

```bash
cd server
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements-dev.txt
uvicorn app.main:app --port 8080
pytest tests -q                                  # 15 项测试
python scripts/smoke.py http://127.0.0.1:8080    # 46 项端到端冒烟
```

---

## 核心架构原则

| 原则 | 落地 |
| --- | --- |
| **边缘极简** | ESP32 只存 WiFi / 云端地址 / Device_Token 三项。**零**用户密码、成员列表、权限逻辑 |
| **鉴权隔离** | 设备仅凭唯一 `Device_Token` 验明身份；用户、权限、卡槽可见性全部由 Server 数据库裁决 |
| **双轨服务** | ESP32 既是局域网 Web 服务器（本地调试），又是公网平台客户端（数据回传） |

---

## 两条互相隔离的发布维度

### 维度一：外部用户端（APK & EXE）→ GitHub Release

`.github/workflows/release-build.yml`

```
prepare  → 读 VERSION，判断 Release 已存在否（create / overwrite）
build-apk→ ubuntu-latest + JDK17 + Android SDK，动态生成签名 → assembleRelease
build-exe→ windows-latest + .NET 8 → 单文件自包含 EXE
release  → 汇总产物 + SHA256 → 新建或覆盖 GitHub Release
```

- 客户端**直连 GitHub Release API** 检查更新，**绝不经过 Server 中转**
- 同版本 Tag → 覆盖附件；不同版本 → 新建 Release

### 维度二：底层协同（ESP32 & Server）→ Docker Hub + OTA

`.github/workflows/docker-build.yml`

```
test  → pytest 门禁
build → Buildx 多架构(amd64+arm64) → beibing173/smsatbox-server
smoke → 拉起镜像真跑，健康检查 + 版本比对 + 登录冒烟
```

- **ESP32 固件不参与 GitHub Release**
- Server → ESP32：上传 `.bin` → 下发 → 静默下载 → **MD5 校验** → 双分区切换
- ESP32 → Server：请求拉取最新镜像并重启（默认关闭的安全开关）

---

## 版本号管理

全平台唯一来源：仓库根目录 [`VERSION`](VERSION) 文件。

```bash
./scripts/version.sh name          # 1.0.0
./scripts/version.sh code          # 10000
./scripts/version.sh write-gradle android
```

改版本只需改这一个文件，CI 自动同步到 Android `versionName/versionCode`、
Windows 程序集版本、Docker 镜像 tag、Release tag。

---

## 代码规模

| 模块 | 文件 | 行数 |
| --- | --- | --- |
| Python（服务端） | 27 | 3,227 |
| C#（Windows） | 22 | 2,980 |
| C++（ESP32） | 19 | 2,093 |
| HTML/CSS/JS（Web 管理端） | 4 | 1,858 |
| Kotlin（Android） | 14 | 1,324 |
| XAML（Windows 界面） | 7 | 1,077 |
| XML（Android 布局） | 29 | 1,206 |
| **合计** | **122** | **13,765** |

---

## 验证记录

| 项目 | 结果 |
| --- | --- |
| 服务端 pytest | 15 passed |
| 服务端端到端冒烟 | 46 项全通过 |
| ESP32 固件编译 | ✅ Flash 23.4% / RAM 17.3% |
| ESP32 ↔ Server 协议 | 36 项全通过 |
| Android release 构建 | ✅ CI 产包 |
| Windows EXE 构建 | ✅ CI 产包 |
| GitHub Release | [v1.0.0 已发布](https://github.com/beibing173/smsatbox/releases/tag/v1.0.0) |
| APK 签名校验 | SHA-256 `24bcd123…` |
| Release 产物 SHA256 | 与 SHA256SUMS.txt 一致 |

---

## 已知限制

- **ESP32 未实机联调**：AT 驱动、短信解析、OTA 逻辑已编译通过，协议经 36 项离线验证；
  但 4G 数据链路（PPP 拨号/模组 TCP 栈）需实机调通。
- **docker-build 需配置 Secrets**：需在仓库 Settings → Secrets 添加
  `DOCKERHUB_USERNAME` 和 `DOCKERHUB_TOKEN` 才能推送镜像。
- **APK 签名**：CI 每次动态生成密钥（无泄漏风险），代价是覆盖安装需先卸载。
  长期发布建议改用固定 keystore。
