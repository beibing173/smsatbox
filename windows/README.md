# SMSATBOX · windows

SMSATBOX —— 短信 / 未接来电 多卡提醒盒子的 **Windows 桌面客户端**（WPF / .NET 8）。

三端一致的客户端之一：Web 管理端、Android APK、**Windows EXE**。硬件（ESP32）收到短信与来电后上报中转平台，Windows 端常驻系统托盘，第一时间弹原生通知，验证码一键复制。

> 全局版本：**v1.0.0**

---

## 一、功能

| 需求 | 实现 |
| --- | --- |
| **常驻系统托盘** | 关闭窗口 / 最小化 → 收缩到托盘。托盘图标左键单击或双击唤出主窗口；右键菜单：**显示主窗口 / 检查更新 / 退出**。单实例运行，重复启动会唤醒已有窗口。 |
| **三页布局** | 左侧导航：**消息列表 / 设备状态 / 设置**。底部与侧栏均标注版本号 **v1.0.0**（三端一致）。 |
| **消息通知** | Windows 原生 Toast（`Microsoft.Toolkit.Uwp.Notifications` 7.1.3）。新短信 / 未接来电弹出通知，**验证码消息使用 Reminder 场景突出显示**。通知不可用时自动降级为托盘气泡。 |
| **一键复制验证码** | 消息卡片中的验证码是一个可点击「芯片」，点一下即复制到剪贴板并标记已读。右键菜单另可复制全文。 |
| **登录** | 手动填写「公网中转平台地址」+ Token，验证通过后保存到 `%APPDATA%\SMSATBOX\config.json`。 |
| **独立升级** | 直接查 **GitHub Release API**，只与 GitHub 通信，**绝不经过 SMSATBOX 中转平台**。下载 `.exe` 后用 `Process.Start` 启动新版本并退出自身。 |
| **黑白双主题** | 深色 / 浅色即时切换，记忆到配置。切换时同步系统 App 主题键，让原生窗口边框跟随。 |
| **版本号 v1.0.0** | 项目属性、UI 展示、发布产物版本信息三者一致。 |

### 消息列表
- 统计卡片：总消息 / 未读 / 今日 / 验证码
- 卡片展示：发送者、类型（短信 / 未接来电 / 系统）、卡槽号、正文、本地时间与相对时间
- 点击卡片标记已读，「全部标为已读」一键处理
- 右键菜单：标记已读 / 复制验证码 / 复制全文

### 设备状态
- 设备卡：名称、在线状态、网络模式（Wi-Fi / 4G / 未连接）、IP、固件版本、最后在线
- 卡槽明细：槽位号、号码、运营商、套餐、信号强度（dBm + 格数可视化）

### 设置
- 中转平台：地址、当前用户、Token（脱敏显示）、重新登录、测试连接、打开配置文件夹
- 外观：深色 / 浅色主题
- 通知：开关、轮询间隔（5–600 秒）、发送测试通知
- 窗口与托盘：启动时最小化到托盘
- 独立升级：当前版本、更新源、检查更新（显示下载进度）
- 关于：版本信息、配置文件路径、打开日志文件夹

---

## 二、与服务端的对接

所有请求：

```
Base:   {serverUrl}/api/v1
Header: X-Client-Version: 1.0.0
Header: X-Client-Platform: windows
Header: Authorization: Bearer {token}
```

平台地址允许用户**只填域名/IP**（例如 `http://1.2.3.4:8000`），客户端会自动补全 `/api/v1`；填成 `/api` 也能纠正，填 `.../api/v1` 则原样使用。

| 接口 | 用途 |
| --- | --- |
| `GET /auth/verify` | 登录校验、探测平台连通性、取用户信息 |
| `GET /messages?limit=100&offset=0&slot_id=` | 消息列表 |
| `GET /messages/stats` | 总消息 / 未读 / 今日 / 验证码数量 |
| `PATCH /messages/{id}` body `{"is_read":true}` | 标记已读 |
| `GET /devices` | 设备与卡槽状态 |
| `GET /version` | 平台版本（登录时附带展示，失败不影响登录） |

JSON 解析使用 **System.Text.Json**，属性名用 `[JsonPropertyName("slot_index")]` 映射 snake_case。

字段按服务端 `message_to_client()` / `device_detail()` 的真实输出对齐：

- Message：`id, device_id, device_name, slot_id, slot_index, slot_number, kind("sms"|"call"|"system"), sender, content, code, received_at(UTC ISO), is_read`
- Device：`id, device_name, online, firmware_version, net_mode("wifi"|"4g"|"none"), local_ip, wifi_rssi, last_seen_at, slots[]`
- Slot：`id, slot_index, phone_number, carrier, signal_dbm, plan_name, plan_expire_at`

时间统一按 UTC 解析后转本地时间显示。

---

## 三、构建

### 环境要求
- **.NET SDK 8.0**（已在 8.0.425 上验证）
- Windows 10 1809 (build 17763) 或更高

### 编译

```powershell
cd windows
dotnet restore SmsatBox.sln
dotnet build SmsatBox.sln -c Release
```

### 发布单文件 EXE（CI 使用的正是这条命令）

```powershell
cd windows
dotnet restore SmsatBox.sln
dotnet publish SmsatBox.Desktop/SmsatBox.Desktop.csproj -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -p:EnableCompressionInSingleFile=true -p:Version=1.0.0 -p:AssemblyVersion="1.0.0.0" -p:FileVersion="1.0.0.0" -o ../dist/exe
```

产物：**`dist/exe/SmsatBox.exe`**（自包含单文件，约 72 MB，目标机器无需安装 .NET 运行时）。

### 项目结构

```
windows/
├─ SmsatBox.sln
├─ README.md
└─ SmsatBox.Desktop/
   ├─ SmsatBox.Desktop.csproj      # net8.0-windows10.0.17763.0, UseWPF
   ├─ app.manifest                 # asInvoker，Win10/11 兼容声明
   ├─ GlobalUsings.cs
   ├─ App.xaml / App.xaml.cs       # 入口：单实例、托盘、登录、轮询、通知
   ├─ MainWindow.xaml(.cs)         # 三页外壳、左侧导航、底部版本号
   ├─ Themes/Theme.xaml            # 深浅双主题资源与控件样式
   ├─ Core/
   │  ├─ AppInfo.cs                # 全局常量、版本号、GitHub 仓库
   │  ├─ AppConfig.cs              # 配置模型（snake_case）
   │  ├─ ConfigStore.cs            # %APPDATA%\SMSATBOX\config.json 读写
   │  ├─ AppState.cs               # 消息/设备/统计仓库，轮询与差异合并
   │  ├─ ApiClient.cs              # HTTP 客户端（X-Client-* / Bearer）
   │  ├─ NotificationService.cs    # Toast + 托盘气泡降级
   │  ├─ UpdateService.cs          # GitHub Release 独立升级
   │  ├─ ThemeManager.cs           # 主题切换与调色板
   │  ├─ TrayIconFactory.cs        # 代码动态生成托盘图标（无 .ico 依赖）
   │  ├─ AppInstance.cs            # 单实例 Mutex + 唤出事件
   │  ├─ Converters.cs             # 值转换器
   │  ├─ ObservableObject.cs
   │  └─ Log.cs                    # 文件日志
   ├─ Models/                      # MessageItem / DeviceItem / SimSlot 等
   └─ Views/
      ├─ LoginWindow.xaml(.cs)     # 平台地址 + Token 登录
      └─ Pages/                    # MessagesPage / DevicesPage / SettingsPage
```

---

## 四、独立升级机制

**完全绕开 Server**，客户端自己访问 GitHub：

```
GET https://api.github.com/repos/beibing173/smsatbox/releases/latest
Accept: application/vnd.github+json
User-Agent: SMSATBOX-Windows/1.0.0
```

流程：

1. 取 `tag_name`，去掉 `v` / `V` 前缀（兼容 `vV1.2.0` 这类脏数据与 `-beta` 后缀）。
2. 与当前版本 `1.0.0` 做 `System.Version` 比较（补齐到 4 段，`1.10.0 > 1.9.9` 正确）。
3. 在 `assets[]` 中找到以 `.exe` 结尾的资产（不区分大小写）。
4. 有新版本则下载到 `%TEMP%\SMSATBOX-update\`，带进度条。
5. 用户确认后 `Process.Start(newExe, "--upgraded")` 启动新版本，并退出自身。
6. 新版本以 `--upgraded` 启动时会**等待旧进程释放单实例 Mutex（最多 20 秒）**，避免被自己的单实例保护挡掉。

入口有三处：托盘右键「检查更新」、设置页「检查更新」按钮、设置页「打开发布页」。

版本比较逻辑已通过 12 条用例（含 `v1.0.0` vs `1.0.0`、`v1.0.0.1`、`1.10.0` vs `1.9.9`、脏 tag 等）。

---

## 五、本地数据

| 内容 | 路径 |
| --- | --- |
| 配置（平台地址 / Token / 主题 / 通知设置） | `%APPDATA%\SMSATBOX\config.json` |
| 日志 | `%APPDATA%\SMSATBOX\logs\app.log`（超过 512 KB 自动截断） |
| 升级临时文件 | `%TEMP%\SMSATBOX-update\` |

配置写入采用「先写临时文件再替换」，避免掉电写坏。Token 在设置页脱敏显示（前 6 后 4）。

> 注意：Token 以明文保存在 config.json 中（与 Web/APK 端一致的取舍），请确保本机账户安全。

---

## 六、已知限制

1. **Toast 依赖 WinRT**。使用 `Microsoft.Toolkit.Uwp.Notifications` 发原生通知。若系统通知服务异常、或精简版系统移除了 WinRT 通知组件，首次发送可能失败（`0x80040111`）。此时会**自动降级为托盘气泡通知**并记录一次日志；后续消息会继续尝试 Toast，成功即自动恢复，不会一直卡在降级状态。
2. **通知与前台激活**：Windows 通知中心对未关联 AppUserModelID 的进程有节流，通过托盘直接启动时通知可能延迟出现，属于系统行为。
3. **托盘图标为代码动态生成**（GDI+ 绘制蓝色圆角信封 + 信号弧），不依赖 `.ico` 资源文件，规避单文件发布的资源定位问题。未读数 > 0 时切换为带红点的变体；托盘提示文本会显示未读数。
4. **轮询而非推送**：默认每 20 秒轮询一次（可在设置中调 5–600 秒），非 WebSocket 实时推送。新消息取第一页 100 条做差异比对。
5. **升级仅支持 x64 自包含单文件**：`assets` 中必须存在 `.exe`；若 Release 只发压缩包，会提示到发布页手动下载。
6. **单实例**：同一用户会话只允许一个实例。第二次启动会唤醒已有窗口（不创建新进程）。
7. **退出方式**：关闭窗口只是缩到托盘；真正退出请用托盘右键「退出」。
8. **Win10 1809 以下**不支持原生 Toast，自动走托盘气泡分支。
9. **托盘图标可见性**：Win11「通知区域全部收起」布局下需要展开折叠区才能看到图标。

---

## 七、验证记录

本机（Windows 11 26200 / .NET SDK 8.0.425）实测：

- `dotnet restore SmsatBox.sln` ✅
- `dotnet build SmsatBox.sln -c Release` → **0 错误 0 警告** ✅
- 完整 `dotnet publish` 命令 → 产出 `dist/exe/SmsatBox.exe`，文件版本 `1.0.0.0` / 产品版本 `1.0.0` ✅
- 对接本机真实 FastAPI 服务端端到端：
  - 登录校验（`/auth/verify`）✅
  - 消息列表 / 统计 / 设备列表渲染 ✅
  - 点击验证码芯片 → 剪贴板取得验证码，`PATCH` 已读回写服务端 ✅
  - 轮询期间注入新验证码短信 → 触发通知（日志记录验证码内容）✅
  - 单实例：第二次启动自动退出，进程数保持 1 ✅
  - 关闭窗口 → 窗口隐藏、进程存活（缩到托盘）✅
  - 启动最小化到托盘 ✅
  - 主题切换 → config.json 持久化为 `light`，重启后保持 ✅
  - 版本号 `v1.0.0` 在多处一致 ✅
- 版本比较逻辑单元验证 12/12 通过 ✅
- GitHub Release JSON 解析（`.exe` 资产选取）验证通过 ✅

> 说明：本机环境下对 WPF 窗口（含官方最简 WPF 探针）的屏幕截图均为空白（WPF 走硬件加速，`PrintWindow` / `CopyFromScreen` 抓不到内容），因此 UI 验证改用 **UI Automation 读取真实控件树、坐标与尺寸**，全部元素布局正常、零尺寸元素仅为隐藏占位符，可判定渲染链路与布局正确。
