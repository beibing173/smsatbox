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
#include "euicc.h"
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

// eUICC / eSIM 适配（每个卡槽一个实例）
static Euicc s_euicc1;
static Euicc s_euicc2;

static uint32_t s_lastPollMs = 0;
static uint32_t s_lastOtaPollMs = 0;
static uint32_t s_lastModemProbeMs = 0;
static uint32_t s_lastEsimPollMs = 0;
static uint32_t s_lastEuiccRefreshMs = 0;
static uint32_t s_bootMs = 0;
static bool s_lanWebStarted = false;
static bool s_euiccProbed = false;

// modem.cpp 中的注册函数
extern void registerModem(Modem* m);

// ---------------------------------------------------------------------------
// eUICC 探测与状态上报
// ---------------------------------------------------------------------------
static Euicc* euiccForSlot(int slotIndex) {
  if (slotIndex == 1) return &s_euicc1;
  if (slotIndex == 2) return &s_euicc2;
  return nullptr;
}

/**
 * 开机后探测两个卡槽是否为 eUICC 卡。
 * 只探测一次（换卡需重启，符合实际使用习惯），避免频繁占用串口。
 */
static void probeEuiccOnce() {
  if (s_euiccProbed) return;

  s_euicc1.bindSlot(1);
  s_euicc2.bindSlot(2);

  bool allProbed = true;
  for (int i = 1; i <= MODEM_COUNT; i++) {
    Modem* m = modemForSlot(i);
    Euicc* e = euiccForSlot(i);
    if (m == nullptr || e == nullptr) continue;
    if (!m->isReady()) {
      allProbed = false;   // 还有模组没就绪，下次再试
      continue;
    }
    e->probe(false);
  }

  if (allProbed) {
    s_euiccProbed = true;
    LOGI("eUICC probe done: slot1=%s slot2=%s",
         s_euicc1.isEuicc() ? "yes" : "no", s_euicc2.isEuicc() ? "yes" : "no");
    // 探测完成后立即上报一次
    for (int i = 1; i <= MODEM_COUNT; i++) {
      Euicc* e = euiccForSlot(i);
      if (e != nullptr && e->isEuicc()) {
        e->refresh();
        cloud::reportEuicc(i, e);
      }
    }
  }
}

// ---------------------------------------------------------------------------
// 回调：收到短信
// ---------------------------------------------------------------------------
static void onSms(int slotIndex, const String& sender, const String& content,
                  const String& rawAt) {
  LOGI("[SLOT%d] SMS %s: %s", slotIndex, sender.c_str(), content.c_str());
  // 立即上报云端；业务侧（验证码提取等）由 Server 负责，设备不解析业务
  if (!cloud::reportMessage("sms", slotIndex, sender, content)) {
    LOGW("sms report failed");
  }
}

// ---------------------------------------------------------------------------
// 回调：来电
// ---------------------------------------------------------------------------
static void onCall(int slotIndex, const String& number) {
  LOGI("[SLOT%d] incoming call %s", slotIndex, number.c_str());
  cloud::reportMessage("call", slotIndex, number, "未接来电");
}

// ---------------------------------------------------------------------------
// 执行一条下行指令
// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------
// 发短信冷却：供电不足时频繁发射会让模组反复死机，这里做退避保护
// ---------------------------------------------------------------------------
static uint32_t s_smsCooldownUntil = 0;   // 冷却结束时间
static int s_smsFailStreak = 0;           // 连续失败次数

static void executeCommand(const CloudCommand& cmd) {
  switch (cmd.type) {
    case CMD_SEND_SMS: {
      Modem* m = modemForSlot(cmd.slotIndex);
      if (m == nullptr) {
        cloud::reportCommandResult(cmd.commandId, "failed", "slot not found");
        return;
      }

      // ★ 模组未就绪时不执行、也不回写失败：
      //   保持 pending，等模组初始化完成后下次轮询再执行。
      //   （设备刚开机时模组需要 20~30 秒启动，不能把指令白白判死）
      if (!m->isReady()) {
        LOGW("cmd #%d deferred: slot%d modem not ready yet", cmd.commandId,
             cmd.slotIndex);
        return;
      }

      // ★ 冷却保护：连续发送失败说明供电撑不住，退避 2 分钟再试，
      //   避免每条指令都把模组打死一次。
      uint32_t now = millis();
      if (s_smsCooldownUntil != 0 && (int32_t)(now - s_smsCooldownUntil) < 0) {
        LOGW("cmd #%d deferred: sms cooldown %lds left", cmd.commandId,
             (long)((s_smsCooldownUntil - now) / 1000));
        return;
      }

      LOGI("exec cmd #%d: slot%d send sms -> %s", cmd.commandId, cmd.slotIndex,
           cmd.targetNumber.c_str());

      // 发射前给电源 300ms 稳定时间
      delay(300);

      String err;
      bool ok = m->sendSms(cmd.targetNumber, cmd.content, &err);
      cloud::reportCommandResult(cmd.commandId, ok ? "sent" : "failed", err);

      if (ok) {
        s_smsFailStreak = 0;
      } else {
        s_smsFailStreak++;
        // 连续失败 2 次以上进入冷却，且失败越多冷却越久（最多 10 分钟）
        if (s_smsFailStreak >= 2) {
          uint32_t cooldownMs = 120000UL * (s_smsFailStreak - 1);
          if (cooldownMs > 600000UL) cooldownMs = 600000UL;
          s_smsCooldownUntil = millis() + cooldownMs;
          LOGW("sms failed %d times in a row, cooldown %lus (check power supply!)",
               s_smsFailStreak, cooldownMs / 1000);
        }
      }
      break;
    }

    case CMD_OTA: {
      LOGI("exec OTA #%d -> v%s", cmd.taskId, cmd.otaVersion.c_str());
      cloud::reportOta(cmd.taskId, "downloading");
      String err;
      bool ok = ota::performUpdate(cmd.otaUrl, cmd.otaMd5, cmd.otaVersion, &err);
      if (ok) {
        cloud::reportOta(cmd.taskId, "success");
        LOGI("OTA ok, reboot in 3s");
        delay(3000);
        ESP.restart();
      } else {
        cloud::reportOta(cmd.taskId, "failed", err);
        LOGE("OTA failed: %s", err.c_str());
      }
      break;
    }

    case CMD_SERVER_UPGRADE: {
      LOGI("request server upgrade to v%s", cmd.otaVersion.c_str());
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
  // ★ 所有模组都未就绪时不要拉取指令：
  //   否则刚开机会把排队中的短信指令拉下来又判死。
  bool anyReady = false;
  for (int i = 1; i <= MODEM_COUNT; i++) {
    Modem* m = modemForSlot(i);
    if (m != nullptr && m->isReady()) {
      anyReady = true;
      break;
    }
  }
  if (!anyReady) {
    return;
  }

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
// eSIM：执行一条 eSIM 指令
// ---------------------------------------------------------------------------
static void executeEsimCommand(const CloudCommand& cmd) {
  Euicc* e = euiccForSlot(cmd.slotIndex);
  if (e == nullptr) {
    cloud::reportEsimResult(cmd.commandId, false, "slot not found");
    return;
  }
  if (!e->isEuicc()) {
    cloud::reportEsimResult(cmd.commandId, false, "not an eUICC card");
    return;
  }
  if (!e->userEnabled()) {
    cloud::reportEsimResult(cmd.commandId, false, "eSIM 管理已被用户关闭");
    return;
  }

  const char* opName = "?";
  bool ok = false;
  String err;

  switch (cmd.esimOp) {
    case ESIM_OP_REFRESH:
      opName = "refresh";
      ok = e->refresh();
      if (!ok) err = e->lastError();
      break;

    case ESIM_OP_ENABLE:
      opName = "enable";
      ok = e->enableProfile(cmd.esimIccid);
      if (!ok) err = e->lastError();
      break;

    case ESIM_OP_DISABLE:
      opName = "disable";
      ok = e->disableProfile(cmd.esimIccid);
      if (!ok) err = e->lastError();
      break;

    case ESIM_OP_DELETE:
      opName = "delete";
      ok = e->deleteProfile(cmd.esimIccid);
      if (!ok) err = e->lastError();
      break;

    case ESIM_OP_NICKNAME:
      opName = "nickname";
      ok = e->setNickname(cmd.esimIccid, cmd.esimNickname);
      if (!ok) err = e->lastError();
      break;

    default:
      cloud::reportEsimResult(cmd.commandId, false, "unknown eSIM operation");
      return;
  }

  LOGI("esim cmd #%d %s -> %s", cmd.commandId, opName, ok ? "ok" : err.c_str());
  cloud::reportEsimResult(cmd.commandId, ok, ok ? "" : err);

  // 操作完刷新一次缓存并上报（切卡/删卡后 profile 列表会变）
  if (ok && cmd.esimOp != ESIM_OP_NICKNAME) {
    delay(1500);  // 给卡片一点时间处理 REFRESH
    e->refresh();
  }
  cloud::reportEuicc(cmd.slotIndex, e);
}

// ---------------------------------------------------------------------------
// 轮询 eSIM 指令
// ---------------------------------------------------------------------------
static void pollEsim() {
  // eUICC 功能必须真实可用才轮询，避免空转
  bool anyAvailable = false;
  for (int i = 1; i <= MODEM_COUNT; i++) {
    Euicc* e = euiccForSlot(i);
    if (e != nullptr && e->available()) {
      anyAvailable = true;
      break;
    }
  }
  if (!anyAvailable) return;

  CloudCommand cmd;
  if (!cloud::pollEsimCommand(&cmd)) return;
  executeEsimCommand(cmd);
}

// ---------------------------------------------------------------------------
// 定期刷新并上报 eUICC 状态（每 5 分钟）
// ---------------------------------------------------------------------------
static void refreshEuiccStatus() {
  for (int i = 1; i <= MODEM_COUNT; i++) {
    Euicc* e = euiccForSlot(i);
    if (e == nullptr) continue;
    if (!e->isEuicc()) continue;
    if (!e->userEnabled()) continue;
    e->refresh();
    cloud::reportEuicc(i, e);
  }
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
  LOGI(" SMSATBOX firmware v%s boot", SMSATBOX_VERSION);
  LOGI(" HW: ESP32-S3 N16R8 + 2x ML307A");
  LOGI(" Flash: %u KB  PSRAM: %u KB",
       ESP.getFlashChipSize() / 1024, ESP.getPsramSize() / 1024);
  LOGI(" reset reason: %d", (int)esp_reset_reason());
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

  // eUICC 实例绑定卡槽（真正探测在 loop 中等模组就绪后执行）
  s_euicc1.bindSlot(1);
  s_euicc2.bindSlot(2);

  s_modem1.begin();
  s_modem2.begin();

  if (!c.configured) {
    // 3a) 未配网 -> 只开 AP 热点
    LOGI("not configured, entering setup mode");
    portal::begin();
  } else {
    // 3b) 已配网 -> 连接 WiFi + 初始化云端通信
    LOGI("configured, connecting: %s", c.wifiSsid.c_str());
    net::begin();
    cloud::begin();
  }

  LOGI("setup done in %lu ms", millis() - s_bootMs);
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

  // 7) 定期刷新模组完整状态（SIM/注册/信号/运营商），供云端设备详情展示
  if (now - s_lastModemProbeMs > 60000UL) {
    s_lastModemProbeMs = now;
    s_modem1.refreshAll();
    s_modem2.refreshAll();
    // 模组就绪后探测一次 eUICC（只探一次，换卡需重启）
    probeEuiccOnce();
  }

  // 8) eSIM 指令轮询（15 秒一次，比短信指令稍慢：切卡是低频重操作）
  if (now - s_lastEsimPollMs > 15000UL) {
    s_lastEsimPollMs = now;
    pollEsim();
  }

  // 9) 定期刷新并上报 eUICC 状态（5 分钟）
  if (now - s_lastEuiccRefreshMs > 300000UL) {
    s_lastEuiccRefreshMs = now;
    refreshEuiccStatus();
  }

  // 10) 指示灯
  updateLed();

  delay(2);
}
