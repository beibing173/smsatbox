// ============================================================================
//  SMSATBOX · 云端通信实现
//  ---------------------------------------------------------------------------
//  【安全原则】本文件只发送 Device_Token。用户密码、成员列表、权限逻辑
//  完全不在设备侧存在，全部由 Server 数据库裁决。
// ============================================================================
#include "cloud.h"

#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>

#include "config_store.h"
#include "logger.h"
#include "modem.h"
#include "network.h"

namespace cloud {

namespace {
uint32_t s_lastReport = 0;
uint32_t s_lastPoll = 0;
uint32_t s_lastOtaPoll = 0;
bool s_hasToken = false;

/** 统一发起 HTTP 请求；https 时跳过证书校验（设备侧无 CA 存储） */
int httpRequest(const String& url, const char* method, const String& body,
                String* response, uint32_t timeoutMs = 12000) {
  if (url.isEmpty()) return -1;

  HTTPClient http;
  http.setTimeout(timeoutMs);
  http.setReuse(false);
  http.setConnectTimeout(8000);

  bool isHttps = url.startsWith("https://");
  WiFiClientSecure secureClient;
  WiFiClient plainClient;

  if (isHttps) {
    secureClient.setInsecure();  // 设备端不做证书校验，靠 Token 鉴权
    if (!http.begin(secureClient, url)) return -1;
  } else {
    if (!http.begin(plainClient, url)) return -1;
  }

  http.addHeader("X-Device-Token", cfg::get().deviceToken);
  http.addHeader("X-Client-Version", SMSATBOX_VERSION);
  http.addHeader("X-Client-Platform", "esp32");
  http.addHeader("X-Client-Hardware", "ESP32-S3-N16R8");

  int code = -1;
  if (body.length() > 0) {
    http.addHeader("Content-Type", "application/json");
    code = http.sendRequest(method, reinterpret_cast<uint8_t*>(
                                        const_cast<char*>(body.c_str())),
                            body.length());
  } else {
    code = http.sendRequest(method);
  }

  if (response != nullptr) {
    *response = (code > 0) ? http.getString() : String();
  }
  http.end();
  return code;
}

/** 解析 Server 下发的指令 JSON */
bool parseCommand(JsonObjectConst obj, CloudCommand* out) {
  String type = obj["type"] | "";
  if (type == "send_sms") {
    out->type = CMD_SEND_SMS;
    out->commandId = obj["command_id"] | 0;
    out->slotIndex = obj["slot_index"] | 1;
    out->targetNumber = String(obj["target_number"] | "");
    out->content = String(obj["content"] | "");
    return true;
  }
  if (type == "ota") {
    out->type = CMD_OTA;
    out->taskId = obj["task_id"] | 0;
    out->otaVersion = String(obj["version"] | "");
    out->otaUrl = String(obj["url"] | "");
    out->otaMd5 = String(obj["md5"] | "");
    out->otaSize = obj["size"] | 0;
    return true;
  }
  if (type == "server_upgrade") {
    out->type = CMD_SERVER_UPGRADE;
    out->otaVersion = String(obj["version"] | "");
    return true;
  }
  return false;
}

}  // namespace

void begin() {
  const DeviceConfig& c = cfg::get();
  s_hasToken = c.deviceToken.length() > 0 && c.serverUrl.length() > 0;
  if (s_hasToken) {
    LOGI("cloud ready: %s", c.serverUrl.c_str());
  } else {
    LOGW("cloud config incomplete");
  }
}

String apiUrl(const char* path) {
  const DeviceConfig& c = cfg::get();
  String base = c.serverUrl;
  if (base.isEmpty()) return String();
  String url = base;
  if (!url.endsWith("/api/v1")) {
    if (!url.endsWith("/")) url += "/";
    url += "api/v1";
  }
  if (path[0] != '/') url += "/";
  url += path;
  return url;
}

bool reportStatus() {
  if (!s_hasToken || !net::online()) return false;

  JsonDocument doc;
  doc["firmware_version"] = SMSATBOX_VERSION;
  doc["local_ip"] = net::localIp();
  doc["wifi_rssi"] = net::wifiRssi();
  doc["net_mode"] = net::modeName();

  JsonArray slots = doc["slots"].to<JsonArray>();
  for (int i = 1; i <= MODEM_COUNT; i++) {
    Modem* m = modemForSlot(i);
    if (m == nullptr) continue;
    JsonObject s = slots.add<JsonObject>();

    s["slot_index"] = i;

    // ---- 模组与 SIM ----
    s["present"] = m->present();
    s["module_state"] = m->stateName();
    s["sim_state"] = m->simReady() ? "ready" : "absent";

    // ---- 网络注册 ----
    s["registered"] = m->registered();
    s["reg_status"] = m->regStatus();
    s["reg_text"] = m->regText();
    if (m->lac().length() > 0) s["lac"] = m->lac();
    if (m->cellId().length() > 0) s["cell_id"] = m->cellId();

    // ---- 信号 ----
    s["rssi_csq"] = m->csq();
    s["signal_dbm"] = m->signalDbm();
    s["signal_level"] = m->signalLevel();

    // ---- 身份 ----
    if (m->phoneNumber().length() > 0) s["phone_number"] = m->phoneNumber();
    if (m->carrier().length() > 0) s["carrier"] = m->carrier();
    if (m->imsi().length() > 0) s["imsi"] = m->imsi();
    if (m->iccid().length() > 0) s["iccid"] = m->iccid();
    if (m->imei().length() > 0) s["imei"] = m->imei();
  }

  String body;
  serializeJson(doc, body);

  String resp;
  int code = httpRequest(apiUrl("/device/report"), "POST", body, &resp);
  if (code == 200) {
    s_lastReport = millis();
    // Server 通过响应带回自己的版本，用于协同升级判断
    JsonDocument in;
    if (deserializeJson(in, resp) == DeserializationError::Ok) {
      const char* serverVer = in["server_version"] | "";
      if (strlen(serverVer) > 0 && strcmp(serverVer, SMSATBOX_VERSION) != 0) {
        LOGW("server %s != fw %s", serverVer, SMSATBOX_VERSION);
      }
    }
    return true;
  }
  LOGW("report failed code=%d", code);
  return false;
}

bool reportMessage(const char* kind, int slotIndex, const String& sender,
                   const String& content) {
  if (!s_hasToken || !net::online()) {
    LOGW("network down");
    return false;
  }

  JsonDocument doc;
  doc["kind"] = kind;
  doc["slot_index"] = slotIndex;
  doc["sender"] = sender;
  doc["content"] = content;

  String body;
  serializeJson(doc, body);

  String resp;
  int code = httpRequest(apiUrl("/device/messages"), "POST", body, &resp);
  if (code == 201 || code == 200) {
    JsonDocument in;
    String codeStr;
    if (deserializeJson(in, resp) == DeserializationError::Ok) {
      const char* v = in["code"] | "";
      codeStr = v;
    }
    LOGI("report ok slot=%d code=%s", slotIndex,
         codeStr.length() ? codeStr.c_str() : "-");
    return true;
  }
  LOGE("report failed code=%d", code);
  return false;
}

bool pollCommands(CloudCommand* out, int maxCount, int* outCount) {
  *outCount = 0;
  if (!s_hasToken || !net::online()) return false;

  String resp;
  int code = httpRequest(apiUrl("/device/commands"), "GET", "", &resp);
  if (code != 200) return false;

  JsonDocument doc;
  if (deserializeJson(doc, resp) != DeserializationError::Ok) return false;

  JsonArrayConst items = doc["items"].as<JsonArrayConst>();
  for (JsonObjectConst obj : items) {
    if (*outCount >= maxCount) break;
    if (parseCommand(obj, &out[*outCount])) {
      (*outCount)++;
    }
  }
  s_lastPoll = millis();
  return *outCount > 0;
}

bool reportCommandResult(int commandId, const char* status, const String& error) {
  if (!s_hasToken || !net::online()) return false;

  JsonDocument doc;
  doc["status"] = status;
  if (error.length() > 0) doc["error"] = error;

  String body;
  serializeJson(doc, body);

  String path = String("/device/commands/") + commandId;
  String resp;
  int code = httpRequest(apiUrl(path.c_str()), "POST", body, &resp);
  LOGI("cmd %d result %s -> %d", commandId, status, code);
  return code == 200;
}

bool pollOta(CloudCommand* out) {
  if (!s_hasToken || !net::online()) return false;

  String resp;
  int code = httpRequest(apiUrl("/device/ota"), "GET", "", &resp);
  if (code != 200) return false;

  JsonDocument doc;
  if (deserializeJson(doc, resp) != DeserializationError::Ok) return false;

  JsonObjectConst task = doc["task"].as<JsonObjectConst>();
  if (task.isNull()) {
    s_lastOtaPoll = millis();
    return false;
  }
  out->type = CMD_OTA;
  out->taskId = task["id"] | 0;
  out->otaVersion = String(task["version"] | "");
  out->otaUrl = String(task["url"] | "");
  out->otaMd5 = String(task["md5"] | "");
  out->otaSize = task["size"] | 0;
  s_lastOtaPoll = millis();
  return out->otaUrl.length() > 0;
}

bool reportOta(int taskId, const char* status, const String& error) {
  if (!s_hasToken) return false;

  JsonDocument doc;
  doc["status"] = status;
  if (error.length() > 0) doc["error"] = error;

  String body;
  serializeJson(doc, body);

  String path = String("/device/ota/") + taskId;
  String resp;
  int code = httpRequest(apiUrl(path.c_str()), "POST", body, &resp);
  return code == 200;
}

bool requestServerUpgrade(const String& targetVersion) {
  JsonDocument doc;
  doc["target_version"] = targetVersion;
  doc["reason"] = "device-detected-version-lag";

  String body;
  serializeJson(doc, body);

  String resp;
  int code = httpRequest(apiUrl("/device/server-upgrade"), "POST", body, &resp);
  LOGI("server upgrade req -> %d", code);
  return code == 200;
}

void loop() {
  if (!s_hasToken) return;
  uint32_t now = millis();

  // 心跳 / 状态上报
  if (now - s_lastReport > REPORT_INTERVAL_MS) {
    s_lastReport = now;
    reportStatus();
  }
}

}  // namespace cloud
