# SMSATBOX · ESP32 固件

> 硬件端 · ESP32-S3 (N16R8) + 双 ML307A-DSLN 4G 模组
> 当前版本 **v1.0.0** · 编译验证通过

---

## 一、设计原则（严格遵守）

| 原则 | 落地方式 |
| --- | --- |
| **边缘极简** | 设备不存任何用户密码、成员列表、权限逻辑。业务判断（谁能看哪个卡槽、验证码提取）全部在 Server |
| **鉴权隔离** | 仅持有一个 `Device_Token`，所有请求走 `X-Device-Token` 头 |
| **双轨服务** | 既是局域网的 Web 服务器（本地调试），又是公网平台的客户端（数据回传） |

设备 NVS 里**只有三项**（加一个配网完成标志）：

```
w_ssid   WiFi 账号
w_pass   WiFi 密码
srv_url  云端中转平台地址
dev_tok  设备唯一绑定码 Device_Token
cfg_ok   配网完成标志
```

---

## 二、编译与烧录

```bash
cd esp32
pio run                 # 编译
pio run -t upload       # 烧录
pio device monitor -b 115200
```

首次会自动下载 ESP32 平台与依赖库（约 300MB）。

**当前编译结果**（已验证）：

```
RAM:   17.3%  (56852 / 327680 bytes)
Flash: 23.4%  (982605 / 4194304 bytes)
产物  .pio/build/smsatbox/firmware.bin ≈ 960 KB
```

> `firmware.bin` 就是上传到 Server 管理端做 OTA 的文件。

---

## 三、硬件接线

### ESP32-S3 (N16R8) ↔ 双 ML307A-DSLN

| 信号 | 卡槽 1（UART1） | 卡槽 2（UART2） |
| --- | --- | --- |
| TX（ESP32 → 模组 RX） | GPIO 17 | GPIO 9 |
| RX（模组 TX → ESP32） | GPIO 18 | GPIO 10 |
| PWRKEY / EN | GPIO 16 | GPIO 8 |
| RST | GPIO 15 | GPIO 7 |
| VCC | 5V（模组峰值电流 2A） | 5V |
| GND | 共地 | 共地 |

状态指示灯：GPIO 48（板载 RGB）

> ⚠️ 两个模组同时发射时峰值电流可达 4A，务必用独立 5V/3A 以上电源，别从开发板 USB 取电。

引脚定义集中在 [`include/config.h`](include/config.h)，改硬件只改这一处。

---

## 四、目录结构

```
esp32/
├── platformio.ini          # 构建配置（N16R8 / 16MB Flash / 8MB PSRAM）
├── partitions.csv          # 双 OTA 分区表
├── include/
│   └── config.h            # 引脚、常量、NVS 键名、版本号
├── src/
│   ├── main.cpp            # 主循环：串起所有模块 + 指令派发
│   ├── config_store.h/cpp  # NVS 配置读写（仅三项）
│   ├── modem.h/cpp         # ML307A AT 驱动（+CMTI / +CLIP 解析）
│   ├── network.h/cpp       # WiFi 优先 / 4G 兜底切换
│   ├── cloud.h/cpp         # 云端通信（上报 / 轮询 / OTA / 升级请求）
│   ├── ota.h/cpp           # 双分区升级 + MD5 校验
│   ├── portal.h/cpp        # AP 配网 + Captive Portal + DNS 劫持
│   ├── lanweb.h/cpp        # 局域网调试 Web
│   ├── webpage.h           # 内置网页模板（PROGMEM）
│   └── logger.h/cpp        # 环形日志缓冲
└── scripts/
    └── protocol_check.py   # 固件↔Server 协议一致性验证
```

---

## 五、运行流程

### 首次开机（未配网）

```
上电
 └─ NVS 无配置
     └─ 开 AP 热点 SMSWIFI（192.168.4.1）
         └─ 手机连上 → 自动弹出配置页（DNS 劫持）
             └─ 只填三项：WiFi / 云端地址 / Device_Token
                 └─ 保存 → 重启 → 进入正常工作模式
```

Captive Portal 覆盖了各系统的探测地址，能自动弹窗：

| 系统 | 探测路径 |
| --- | --- |
| Android | `/generate_204` |
| iOS / macOS | `/hotspot-detect.html` |
| Windows | `/connecttest.txt` |

### 正常工作模式

```
主循环 loop()
 ├─ 配网模式？→ 只跑配网服务
 ├─ 模组1.loop()  ← 非阻塞状态机
 ├─ 模组2.loop()
 ├─ network.loop()     WiFi 断开 15s 后切 4G
 ├─ cloud.loop()       60s 心跳上报
 ├─ lanweb.loop()      WiFi 下提供局域网调试页
 ├─ 15s 轮询指令 → 执行
 ├─ 60s 轮询 OTA  → 执行
 └─ 每 500ms 刷指示灯
```

**没有任何 `delay()` 阻塞主循环**（除模组上电脉冲等必要时序），保证双模组 URC 不丢。

---

## 六、AT 指令与消息解析

### 初始化序列

```
AT                      握手
ATE0                    关回显
AT+CMEE=1               详细错误码
AT+CMGF=1               短信文本模式
AT+CNMI=2,1,0,0,0       新短信走 +CMTI 提示
AT+CLIP=1               开启来电显示
AT+CPMS="SM","SM","SM"  短信存 SIM
```

### 短信接收（+CMTI）

```
模组主动上报:  +CMTI: "SM",4
设备读取:      AT+CMGR=4
返回:          +CMGR: "REC UNREAD","+8613800138000",,"24/01/01,10:00:00+32"
               短信正文
               OK
设备删除:      AT+CMGD=4        ← 读完立即删，防止 SIM 塞满
上报云端:      POST /api/v1/device/messages
```

### 来电提醒（+CLIP）

```
模组主动上报:  +CLIP: "+8613700137000",145
设备解析号码 → 直接上报云端
```

### 发送短信（反向控制）

```
AT+CMGS="13800138000"   → 等提示符 ">"
正文 + 0x1A (Ctrl-Z)    → 提交
+CMGS: 23 / OK          → 成功
```

---

## 七、OTA 双分区升级

```
分区布局（16MB Flash）:
  nvs       0x009000  20KB
  otadata   0x00E000   8KB    ← 记录当前从哪个分区启动
  app0      0x010000   4MB    ← OTA 分区 A（当前运行）
  app1      0x410000   4MB    ← OTA 分区 B（升级写入）
  spiffs    0x810000   7MB
  coredump  0xF10000  64KB

总占用 15.12 MB / 16 MB，无重叠（已验证）
```

升级流程：

```
1. 管理端上传 .bin → Server 计算 MD5，入库，下发任务
2. 设备拉取任务（HTTP 轮询 或 WebSocket）
3. 回写 status=downloading
4. 静默下载 → 边下边算 MD5
5. ★ MD5 比对：不一致则 Update.abort()，保持当前固件运行
6. 一致 → Update.end(true) 写入完成
7. 回写 status=success → 3 秒后重启进入新分区
```

**安全闸门**：MD5 不通过绝不切换分区，设备不会变砖。

---

## 八、局域网调试

WiFi 连接成功后自动开启，同一网段浏览器访问 `http://<设备IP>/`：

| 路径 | 内容 |
| --- | --- |
| `/` | 状态页（固件版本 / 网络模式 / 各卡槽信号 / 最近日志） |
| `/api/status` | JSON 状态 |
| `/api/logs` | JSON 日志 |

页面**只读**，不提供任何写操作，避免本地被滥用。风格与 Web 管理端一致，同样支持黑白双主题。

> 4G 模式下不开启（无固定 IP 可访问）。

---

## 九、协议一致性验证

固件烧在硬件上才能跑，但**协议对接可以离线验证**：

```bash
# 先启动 Server
cd server && uvicorn app.main:app --port 8080

# 用与固件完全相同的请求头/路径/报文去打真实 Server
cd esp32
python scripts/protocol_check.py http://127.0.0.1:8080
```

覆盖 36 项检查：Device_Token 鉴权、心跳报文、短信/来电上报、指令轮询与回写、OTA 上传下载与 MD5、协同升级请求。

**这能提前发现"固件编译过了，一上机就 404/401"的经典事故。**

---

## 十、已知限制

- **WebSocket 未启用**：固件目前走 HTTP 轮询（15s）拉指令。`platformio.ini` 已引入 WebSockets 库，但为保证首次编译稳定性，长连接在下一版接入。轮询兜底功能完整，只是指令延迟最多 15 秒。
- **4G 数据链路未打通**：ML307A 的 AT 收发、短信、来电已实现并编译验证；但「4G 模式下作为 HTTP 客户端上网」还需要额外的 PPP 拨号或模组内置 TCP 栈支持，这部分依赖具体模组固件版本，需实机调试。
- **证书不做校验**：HTTPS 请求用 `setInsecure()`，靠 Device_Token 鉴权。若要严格校验，需在固件里烧 CA 证书。

以上三项都需要实机联调，属于下一阶段工作。
