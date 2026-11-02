// ============================================================================
//  SMSATBOX · 局域网调试 Web 服务实现
// ============================================================================
#include "lanweb.h"

#include <ArduinoJson.h>
#include <WebServer.h>

#include "cloud.h"
#include "config_store.h"
#include "logger.h"
#include "modem.h"
#include "network.h"
#include "webpage.h"

namespace lanweb {

namespace {

WebServer s_server(LAN_WEB_PORT);
bool s_active = false;

String esc(const String& in) {
  String out = in;
  out.replace("&", "&amp;");
  out.replace("<", "&lt;");
  out.replace(">", "&gt;");
  return out;
}

String modemStateName(ModemState s) {
  switch (s) {
    case MODEM_OFF:
      return "未上电";
    case MODEM_BOOTING:
      return "启动中";
    case MODEM_READY:
      return "就绪";
    case MODEM_ERROR:
      return "故障";
  }
  return "未知";
}

String renderStatus() {
  String html = FPSTR(PAGE_COMMON_HEAD);

  bool wifiUp = WiFi.status() == WL_CONNECTED;
  html += "<h2>设备状态</h2><div class=\"kv\">";
  html += "<div><b>固件版本</b><span>v" + String(SMSATBOX_VERSION) + "</span></div>";
  html += "<div><b>网络模式</b><span><span class=\"dot " +
          String(net::online() ? "on" : "off") + "\"></span>" +
          String(net::modeName()) + "</span></div>";
  html += "<div><b>局域网 IP</b><span>" +
          (wifiUp ? WiFi.localIP().toString() : String("4G 模式")) + "</span></div>";
  html += "<div><b>WiFi 信号</b><span>" +
          (wifiUp ? String(WiFi.RSSI()) + " dBm" : String("-")) + "</span></div>";
  html += "<div><b>运行时长</b><span>" + String(millis() / 1000UL) + " 秒</span></div>";
  html += "<div><b>空闲内存</b><span>" + String(ESP.getFreeHeap() / 1024) + " KB</span></div>";
  html += "</div>";

  html += "<h2>4G 卡槽</h2><div class=\"kv\">";
  for (int i = 1; i <= MODEM_COUNT; i++) {
    Modem* m = modemForSlot(i);
    if (m == nullptr) continue;
    String sig = (m->signalDbm() == 99) ? String("未知")
                                        : String(m->signalDbm()) + " dBm";
    html += "<div><b>卡槽 " + String(i) + " · " + modemStateName(m->state()) +
            "</b><span>" + sig + "</span></div>";
    String num = m->phoneNumber().length() ? m->phoneNumber() : String("未写入");
    html += "<div><b>卡槽 " + String(i) + " 号码</b><span>" + esc(num) +
            "</span></div>";
  }
  html += "</div>";

  // 日志
  html += "<h2>最近日志</h2><pre>";
  int n = logRingCount();
  if (n == 0) {
    html += "（暂无日志）";
  } else {
    for (int i = 0; i < n; i++) {
      html += esc(String(logRingLine(i)));
      html += "\n";
    }
  }
  html += "</pre>";

  html += FPSTR(PAGE_STATUS_FOOT);
  return html;
}

void handleRoot() {
  s_server.send(200, "text/html; charset=utf-8", renderStatus());
}

void handleApiStatus() {
  JsonDocument doc;
  doc["version"] = SMSATBOX_VERSION;
  doc["uptime_s"] = millis() / 1000UL;
  doc["net_mode"] = net::modeName();
  doc["online"] = net::online();
  doc["local_ip"] = WiFi.status() == WL_CONNECTED ? WiFi.localIP().toString() : "";
  doc["wifi_rssi"] = net::wifiRssi();
  doc["heap_kb"] = ESP.getFreeHeap() / 1024;

  JsonArray arr = doc["slots"].to<JsonArray>();
  for (int i = 1; i <= MODEM_COUNT; i++) {
    Modem* m = modemForSlot(i);
    if (m == nullptr) continue;
    JsonObject s = arr.add<JsonObject>();
    s["slot_index"] = i;
    s["state"] = modemStateName(m->state());
    s["csq"] = m->signalCsq();
    s["dbm"] = m->signalDbm();
    s["number"] = m->phoneNumber();
    s["carrier"] = m->carrier();
  }

  String out;
  serializeJson(doc, out);
  s_server.send(200, "application/json; charset=utf-8", out);
}

void handleApiLogs() {
  JsonDocument doc;
  JsonArray arr = doc["logs"].to<JsonArray>();
  int n = logRingCount();
  for (int i = 0; i < n; i++) {
    arr.add(String(logRingLine(i)));
  }
  doc["count"] = n;
  String out;
  serializeJson(doc, out);
  s_server.send(200, "application/json; charset=utf-8", out);
}

void handleNotFound() {
  s_server.send(404, "text/plain; charset=utf-8", "404 Not Found");
}

}  // namespace

void begin() {
  if (s_active) return;
  s_server.on("/", HTTP_GET, handleRoot);
  s_server.on("/api/status", HTTP_GET, handleApiStatus);
  s_server.on("/api/logs", HTTP_GET, handleApiLogs);
  s_server.onNotFound(handleNotFound);
  s_server.begin();
  s_active = true;
  LOGI("局域网调试服务已启动 http://%s/",
       WiFi.localIP().toString().c_str());
}

void loop() {
  if (!s_active) return;
  s_server.handleClient();
}

bool active() { return s_active; }

void stop() {
  if (!s_active) return;
  s_server.stop();
  s_active = false;
  LOGI("局域网调试服务已停止");
}

}  // namespace lanweb

// webpage.h 声明的动态页构建函数（供 portal 复用同一套样式）
String buildStatusPage() { return String(); }
