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

**启动服务端**（二选一）：

```bash
# 方式 A：直接拉 Docker Hub 上的现成镜像（推荐）
docker pull beibing173/smsatbox-server:latest
docker run -d --name smsatbox-server --restart unless-stopped \
  -p 8080:8080 \
  -e ADMIN_PASSWORD='换成你的强密码' \
  -e SECRET_KEY="$(openssl rand -base64 48)" \
  -v smsatbox-data:/data \
  beibing173/smsatbox-server:latest

# 方式 B：用 docker compose（自动拉镜像，配置集中管理）
cd server
cp .env.example .env       # 修改 ADMIN_PASSWORD / SECRET_KEY
docker compose up -d
```

浏览器打开 `http://<服务器IP>:8080`，默认 `admin / Admin@123456`。

**镜像标签说明**：

| 标签 | 含义 |
| --- | --- |
| `latest` | 最新构建（跟随 main 分支） |
| `1.0.0` | 精确版本 |
| `1.0` | 主.次版本 |
| `sha-fd312bc` | 对应 commit |

拉最新版升级：
```bash
docker pull beibing173/smsatbox-server:latest
docker compose up -d          # 或 docker restart smsatbox-server
```

不想用 Docker 也行：

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

## 版本号管理（分平台独立）

**三个平台各自一套版本号**，互不强制一致：

```
versions/server.txt    → 1.0.0   服务端 / 固件
versions/android.txt   → 1.0.0   APK
versions/windows.txt   → 1.0.0   EXE
```

```bash
./scripts/version.sh all              # 查看三端版本 + 快照号
./scripts/version.sh android name     # 1.0.0
./scripts/version.sh android code     # 10000
./scripts/version.sh windows name     # 1.0.0
./scripts/version.sh sync             # 写进各端源码
./scripts/version.sh snapshot         # 2026.11.02-r1（Release tag）
```

### 一个 Release 承载两端，但各端独立升级

Release 的 **tag 是日期快照号**（`v2026.11.02-r1`），只作归档标识，**不代表任何一端的版本**。

真正的平台版本写在**附件文件名**里：

```
smsatbox-android-1.2.0.apk
smsatbox-windows-1.0.5.exe
```

客户端升级时只解析**自己那个附件**的版本：

| 客户端 | 只认这个文件名 | 用它比对 |
| --- | --- | --- |
| Android | `smsatbox-android-*.apk` | 与本机 `versionName` 比 |
| Windows | `smsatbox-windows-*.exe` | 与本机 `AppInfo.Version` 比 |

所以 Android 发 `1.2.0` 时，Windows 端（`1.0.5`）**不会**被误触发升级，反之亦然。
两端可以同一天发版共用一个 Release，也可以只发其中一端。

> ESP32 固件版本跟随 Server，走 Docker Hub + OTA 通道，不进 GitHub Release。

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
| GitHub Release | [v2026.11.02-r1 已发布](https://github.com/beibing173/smsatbox/releases/tag/v2026.11.02-r1) |
| 分平台版本解析 | ✅ 两端各读自己附件，互不干扰 |
| APK 签名校验 | SHA-256 `24bcd123…` |
| Release 产物 SHA256 | 与 SHA256SUMS.txt 一致 |

---

## 主题（三端统一）

**默认全部跟随系统**，可手动切换，选择记忆到本地。

| 端 | 默认 | 切换入口 |
| --- | --- | --- |
| Web | 跟随系统（`prefers-color-scheme`） | 侧栏底部 / 顶栏图标 / 设置页三选一 |
| Android | 跟随系统（`AppCompatDelegate.MODE_NIGHT_FOLLOW_SYSTEM`） | 设置页三档单选 |
| Windows | 跟随系统（读注册表，**只读不写**） | 登录窗按钮 / 设置页三档开关 |

> 三端都**不会修改操作系统的外观设置**。Windows 端早期版本曾写入
> `HKCU\...\Themes\Personalize\AppsUseLightTheme`，该行为已彻底移除。

---

## 已知限制

- **ESP32 未实机联调**：AT 驱动、短信解析、OTA 逻辑已编译通过，协议经 36 项离线验证；
  但 4G 数据链路（PPP 拨号/模组 TCP 栈）需实机调通。
- **docker-build 需配置 Secrets**：需在仓库 Settings → Secrets 添加
  `DOCKERHUB_USERNAME` 和 `DOCKERHUB_TOKEN` 才能推送镜像。
- **APK 签名**：CI 每次动态生成密钥（无泄漏风险），代价是覆盖安装需先卸载。
  长期发布建议改用固定 keystore。
- **旧命名兼容**：升级逻辑仍能识别旧的 `smsatbox-v1.0.0.apk` / `.exe`，
  但新构建一律用带平台的新命名。
