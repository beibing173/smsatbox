// ============================================================================
//  SMSATBOX · ESP32-S3 固件主程序
//  ---------------------------------------------------------------------------
//  硬件：ESP32-S3 (N16R8) + 双 ML307A-DSLN 4G 模组
//
//  架构原则（严格遵守）：
//    1. 边缘极简：设备不存用户密码、成员列表、权限逻辑
//    2. 鉴权隔离：仅凭唯一 Device_Token 向 Server 验明身份
//    3. 双轨服务：既做局域网 Web 服务器（本地调试），
//                  又做公网中转平台的客户端（数据回传）
//
//  主循环职责：驱动各模块状态机 + 派发下行指令
// ============================================================================
#include <Arduino.h>
#include <WiFi.h>
#include <esp_system.h>

#include "cloud.h"
#include "config.h"
#include "config_store.h"
#include "lanweb.h"
#include "logger.h"
#include "modem.h"
#include "network.h"
#include "ota.h"
#include "portal.h"

// ---------------------------------------------------------------------------
// 全局对象
// ---------------------------------------------------------------------------
static Modem s_modem1(1, MODEM1_UART_NUM, MODEM1_TX_PIN, MODEM1_RX_PIN,
                      MODEM1_EN_PIN, MODEM1_RST_PIN);
static Modem s_modem2(2, MODEM2_UART_NUM, MODEM2_TX_PIN, MODEM2_RX_PIN,
                      MODEM2_EN_PIN, MODEM2_RST_PIN);

static uint32_t s_lastPollMs = 0;
static uint32_t s_lastOtaPollMs = 0;
static uint32_t s_bootMs = 0;
static bool s_lanWebStarted = false;

// modem.cpp 中的注册函数
extern void registerModem(Modem* m);

// ---------------------------------------------------------------------------
// 回调：收到短信
// ---------------------------------------------------------------------------
static void onSms(int slotIndex, const String& sender, const String& content,
                  const String& rawAt) {
  LOGI("[卡槽%d] 短信 %s: %s", slotIndex, sender.c_str(), content.c_str());
  // 立即上报云端；业务侧（验证码提取等）由 Server 负责，设备不解析业务
  if (!cloud::reportMessage("sms", slotIndex, sender, content)) {
    LOGW("短信上报失败，本条丢失（设备端不缓存业务数据）");
  }
}

// ---------------------------------------------------------------------------
// 回调：来电
// ---------------------------------------------------------------------------
static void onCall(int slotIndex, const String& number) {
  LOGI("[卡槽%d] 来电 %s", slotIndex, number.c_str());
  cloud::reportMessage("call", slotIndex, number, "未接来电");
}

// ---------------------------------------------------------------------------
// 执行一条下行指令
// ---------------------------------------------------------------------------
static void executeCommand(const CloudCommand& cmd) {
  switch (cmd.type) {
    case CMD_SEND_SMS: {
      LOGI("执行指令 #%d: 卡槽%d 发短信 -> %s", cmd.commandId, cmd.slotIndex,
           cmd.targetNumber.c_str());
      Modem* m = modemForSlot(cmd.slotIndex);
      String err;
      if (m == nullptr) {
        cloud::reportCommandResult(cmd.commandId, "failed", "卡槽不存在");
        return;
      }
      bool ok = m->sendSms(cmd.targetNumber, cmd.content, &err);
      cloud::reportCommandResult(cmd.commandId, ok ? "sent" : "failed", err);
      break;
    }

    case CMD_OTA: {
      LOGI("执行 OTA 任务 #%d -> v%s", cmd.taskId, cmd.otaVersion.c_str());
      cloud::reportOta(cmd.taskId, "downloading");
      String err;
      bool ok = ota::performUpdate(cmd.otaUrl, cmd.otaMd5, cmd.otaVersion, &err);
      if (ok) {
        cloud::reportOta(cmd.taskId, "success");
        LOGI("OTA 成功，3 秒后重启进入新固件");
        delay(3000);
        ESP.restart();
      } else {
        cloud::reportOta(cmd.taskId, "failed", err);
        LOGE("OTA 失败: %s", err.c_str());
      }
      break;
    }

    case CMD_SERVER_UPGRADE: {
      LOGI("设备请求 Server 升级到 v%s", cmd.otaVersion.c_str());
      // 设备只发请求，实际拉取镜像并重启由 Server 侧受控执行
      cloud::requestServerUpgrade(cmd.otaVersion);
      break;
    }

    default:
      break;
  }
}

// ---------------------------------------------------------------------------
// 轮询下行指令（HTTP 兜底通道）
// ---------------------------------------------------------------------------
static void pollCommands() {
  CloudCommand cmds[4];
  int count = 0;
  if (!cloud::pollCommands(cmds, 4, &count)) {
    return;
  }
  for (int i = 0; i < count; i++) {
    executeCommand(cmds[i]);
    // 指令之间有间隔，避免模组 AT 指令挤在一起
    delay(200);
  }
}

// ---------------------------------------------------------------------------
// 轮询 OTA 任务
// ---------------------------------------------------------------------------
static void pollOta() {
  CloudCommand task;
  if (!cloud::pollOta(&task)) {
    return;
  }
  executeCommand(task);
}

// ---------------------------------------------------------------------------
// 状态指示灯
// ---------------------------------------------------------------------------
static void updateLed() {
  static uint32_t last = 0;
  uint32_t now = millis();
  if (now - last < 500) return;
  last = now;
  if (net::online()) {
    digitalWrite(LED_PIN, HIGH);  // 常亮：在线
  } else {
    digitalWrite(LED_PIN, (now / 500) % 2 ? HIGH : LOW);  // 慢闪：离线
  }
}

// ---------------------------------------------------------------------------
// setup
// ---------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  delay(300);
  logInit();

  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  LOGI("==============================================");
  LOGI(" SMSATBOX 固件 v%s 启动", SMSATBOX_VERSION);
  LOGI(" 硬件: ESP32-S3 N16R8 + 双 ML307A-DSLN");
  LOGI(" Flash: %u KB  PSRAM: %u KB",
       ESP.getFlashChipSize() / 1024, ESP.getPsramSize() / 1024);
  LOGI(" 上次重启原因: %d", (int)esp_reset_reason());
  LOGI("==============================================");

  s_bootMs = millis();

  // 1) 载入配置
  cfg::ensureLoaded();
  const DeviceConfig& c = cfg::get();

  // 2) 注册模组并初始化（双卡独立）
  registerModem(&s_modem1);
  registerModem(&s_modem2);
  Modem::setSmsCallback(onSms);
  Modem::setCallCallback(onCall);
  s_modem1.begin();
  s_modem2.begin();

  if (!c.configured) {
    // 3a) 未配网 -> 只开 AP 热点
    LOGI("设备未配网，进入配网模式");
    portal::begin();
  } else {
    // 3b) 已配网 -> 连接 WiFi + 初始化云端通信
    LOGI("设备已配网，连接网络: %s", c.wifiSsid.c_str());
    net::begin();
    cloud::begin();
  }

  LOGI("setup 完成，耗时 %lu ms", millis() - s_bootMs);
}

// ---------------------------------------------------------------------------
// loop
// ---------------------------------------------------------------------------
void loop() {
  uint32_t now = millis();

  // 配网模式：只跑配网服务
  if (portal::active()) {
    portal::loop();
    updateLed();
    delay(2);
    return;
  }

  // 1) 驱动两个模组状态机
  s_modem1.loop();
  s_modem2.loop();

  // 2) 网络状态机
  net::loop();

  // 3) 云端心跳
  cloud::loop();

  // 4) WiFi 就绪后启动局域网调试服务（双轨服务机制）
  if (!s_lanWebStarted && WiFi.status() == WL_CONNECTED) {
    lanweb::begin();
    s_lanWebStarted = true;
  }
  if (s_lanWebStarted) {
    lanweb::loop();
  }

  // 5) 指令轮询兜底（WebSocket 未启用时的主通道）
  if (now - s_lastPollMs > COMMAND_POLL_INTERVAL_MS) {
    s_lastPollMs = now;
    pollCommands();
  }

  // 6) OTA 任务轮询（比指令低频，避免频繁请求）
  if (now - s_lastOtaPollMs > 60000UL) {
    s_lastOtaPollMs = now;
    pollOta();
  }

  // 7) 指示灯
  updateLed();

  delay(2);
}
