# SMSATBOX · Android 客户端

> 底部导航（消息 / 设备 / 设置） · 系统通知 · 验证码一键复制 · GitHub 独立升级
> 当前版本 **v1.0.0**

---

## 一、打包方式：由 GitHub Actions 完成

**本地不打包。** APK 由 `.github/workflows/release-build.yml` 在 GitHub Runner 上构建并发布到 Release。

### 触发方式

```bash
# 推送代码即触发（版本号取自仓库根目录 VERSION 文件）
git push origin main

# 或手动触发
gh workflow run release-build.yml
```

### 流水线做了什么

1. **prepare** —— 读 `VERSION`，算出 `versionName` / `versionCode` / `tag`；
   用 `gh release view` 检查该 Tag 的 Release 是否已存在，决定 `create` 还是 `overwrite`。
2. **build-apk** —— ubuntu-latest 上装 JDK 17 + Android SDK，
   动态生成签名密钥，`gradle :app:assembleRelease`，产物重命名为
   `smsatbox-v{version}.apk`。
3. **build-exe** —— windows-latest 上 `dotnet publish` 出单文件 EXE。
4. **release** —— 汇总两个平台产物 + 生成 SHA256 校验和，
   按策略 **新建** 或 **覆盖** GitHub Release。

### 版本覆盖规则

| 情况 | 行为 |
| --- | --- |
| Release 已有同版本 Tag | 删掉旧资产 → 更新说明 → 上传新资产（覆盖） |
| Release 无该 Tag | 新建 Release |

---

## 二、为什么用 GitHub Actions 而不是本地打包

| 维度 | 本地打包 | GitHub Actions |
| --- | --- | --- |
| 环境一致性 | 依赖本机 JDK/SDK 版本，换台机器就崩 | Runner 环境固定，可复现 |
| 签名密钥 | 得手工管，容易泄漏 | CI 动态生成，不进仓库 |
| 发布链路 | 打完了还得手动传 Release | 打包 + 发布一条龙 |
| 审计 | 说不清哪个包对应哪次提交 | 每次构建都可追溯到 commit |

---

## 三、目录结构

```
android/
├── build.gradle.kts              # Project 级插件声明
├── settings.gradle.kts           # 仓库与模块
├── gradle.properties             # JVM 参数、AndroidX 开关
├── version.properties            # 版本号（CI 按 VERSION 覆盖生成）
├── .gitignore                    # 忽略 keystore / build / local.properties
└── app/
    ├── build.gradle.kts          # App 模块：SDK 版本、依赖、签名
    ├── proguard-rules.pro
    └── src/main/
        ├── AndroidManifest.xml   # 权限、Activity、FileProvider、通知接收器
        ├── java/com/smsatbox/app/
        │   ├── SmsatApp.kt       # Application：通知渠道
        │   ├── Prefs.kt          # 本地配置（地址/Token/主题/通知开关）
        │   ├── data/
        │   │   ├── Models.kt     # 数据模型
        │   │   └── ApiClient.kt  # OkHttp API 客户端
        │   ├── notify/
        │   │   ├── Notifier.kt        # 系统通知
        │   │   └── CopyReceiver.kt    # 通知栏复制验证码
        │   ├── update/
        │   │   ├── UpdateChecker.kt   # GitHub Release API
        │   │   └── ApkInstaller.kt    # 下载 + 安装
        │   └── ui/
        │       ├── LoginActivity.kt
        │       ├── MainActivity.kt
        │       ├── MessagesFragment.kt
        │       ├── MessageAdapter.kt
        │       ├── DevicesFragment.kt
        │       └── SettingsFragment.kt
        └── res/                  # 布局、颜色（深/浅双主题）、图标
```

---

## 四、功能说明

### 登录
手动填写两项：
- **公网中转平台地址**（如 `https://sms.example.com`）
- **访问 Token**（管理端「设置 → 客户端令牌」生成）

登录时调 `GET /auth/verify` 验证有效性，成功后存入 SharedPreferences。

### 消息页
- 顶部四个统计卡片：总数 / 未读 / 今日 / 验证码
- 消息卡片显示：类型标签（短信/来电）、卡槽号、发送者、时间、未读圆点
- **验证码独立成块**，点一下直接进剪贴板
- 下拉刷新

### 设备页
显示每台设备的在线状态、固件版本、网络模式（WiFi/4G）、局域网 IP、WiFi 信号，
以及每个卡槽的号码、运营商、信号强度、套餐到期日。

### 设置页
- 连接信息（地址 / Token / 账号）
- **外观主题**：跟随系统 / 深色 / 浅色
- 消息通知开关
- **检查更新**（直连 GitHub）
- 退出登录

### 系统通知
新短信 / 未接来电推送系统通知：
- 标题带类型与卡槽：`💬 新短信 · 卡槽 1`
- 验证码消息额外显示 `验证码 483920`，并附**「复制验证码」按钮**（不用打开 App）

### 独立升级
```
设置 → 检查更新
  └─ GET https://api.github.com/repos/beibing173/smsatbox/releases/latest
      └─ 比较 tag_name 与当前 BuildConfig.APP_VERSION
          └─ 有新版本 → 弹窗 → 下载 APK（带进度条）
              └─ FileProvider 交给系统安装器
```

**绝不经过 Server 中转**，与云端平台完全解耦。

---

## 五、版本号

全平台唯一来源：仓库根目录 `VERSION` 文件。

```bash
./scripts/version.sh name          # 1.0.0
./scripts/version.sh code          # 10000
./scripts/version.sh write-gradle android   # 生成 version.properties
```

CI 在构建前自动执行 `write-gradle`，所以**不要手改** `android/version.properties`。

---

## 六、本地调试（仅开发用，不产出发布包）

```bash
cd android
../scripts/version.sh write-gradle .
echo "sdk.dir=$ANDROID_HOME" > local.properties
gradle :app:assembleDebug
```

> 需要 JDK 17+ 与 Android SDK（platform 34 / build-tools 34.0.0）。
> 调试包 applicationId 带 `.debug` 后缀，可与正式版共存。

---

## 七、已知限制

- **无 release keystore**：仓库不提交密钥，CI 每次动态生成。
  好处是绝无泄漏风险；代价是**每次构建签名指纹不同**，
  覆盖安装旧版本时需要先卸载。若要做长期正式发布，
  应在仓库 Secrets 里配置固定 keystore（`KEYSTORE_BASE64` 等）并改流水线读取。
- **未做 Doze 白名单引导**：后台实时性依赖前台轮询，
  极端省电模式下通知可能延迟。
- **未做 ABI 拆分**：打包为通用包，APK 体积偏大。
