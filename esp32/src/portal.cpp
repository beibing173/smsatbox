// ============================================================================
//  SMSATBOX · 配网实现（AP + Captive Portal + DNS 劫持）
// ============================================================================
#include "portal.h"

#include <DNSServer.h>
#include <WebServer.h>
#include <WiFi.h>

#include "config_store.h"
#include "logger.h"
#include "network.h"
#include "webpage.h"

namespace portal {

namespace {
WebServer s_server(80);
DNSServer s_dns;
bool s_active = false;
String s_lastError;

/** 极简 HTML 转义 */
String esc(const String& in) {
  String out = in;
  out.replace("&", "&amp;");
  out.replace("<", "&lt;");
  out.replace(">", "&gt;");
  out.replace("\"", "&quot;");
  return out;
}

/** 渲染配置页（带错误提示与已填值） */
String renderPage(const String& error, const String& ssid,
                  const String& serverUrl, const String& token) {
  String html = FPSTR(PAGE_PORTAL_HEAD);
  if (error.length() > 0) {
    html += "<div class=\"err\">" + esc(error) + "</div>";
  }
  html += "<form method=\"POST\" action=\"/save\">";
  html += "<div class=\"field\"><label>1. WiFi 账号</label>";
  html += "<input name=\"ssid\" maxlength=\"32\" required value=\"" + esc(ssid) +
          "\" placeholder=\"家里的 WiFi 名称\"></div>";
  html += "<div class=\"field\"><label>WiFi 密码</label>";
  html += "<input name=\"pass\" type=\"password\" maxlength=\"64\" "
          "placeholder=\"开放网络可留空\"></div>";
  html += "<div class=\"field\"><label>2. 云端中转平台地址</label>";
  html += "<input name=\"server\" maxlength=\"200\" required value=\"" +
          esc(serverUrl) + "\" placeholder=\"https://sms.example.com\"></div>";
  html += "<div class=\"field\"><label>3. 设备绑定码 Device_Token</label>";
  html += "<input name=\"token\" maxlength=\"120\" required value=\"" +
          esc(token) + "\" placeholder=\"在管理端创建设备后复制\"></div>";
  html += "<button type=\"submit\">保存并连接</button>";
  html += "</form>";
  html += FPSTR(PAGE_PORTAL_FOOT);
  return html;
}

void handleRoot() {
  const DeviceConfig& c = cfg::get();
  s_server.send(200, "text/html; charset=utf-8",
                renderPage(s_lastError, c.wifiSsid, c.serverUrl, ""));
  s_lastError = "";
}

void handleSave() {
  String ssid = s_server.arg("ssid");
  String pass = s_server.arg("pass");
  String server = s_server.arg("server");
  String token = s_server.arg("token");
  ssid.trim();
  server.trim();
  token.trim();

  String error;
  if (!cfg::validate(ssid, pass, server, token, &error)) {
    s_lastError = error;
    s_server.sendHeader("Location", "/", true);
    s_server.send(302, "text/plain", "");
    return;
  }

  DeviceConfig next;
  next.wifiSsid = ssid;
  next.wifiPass = pass;
  next.serverUrl = cfg::normalizeServerUrl(server);
  next.deviceToken = token;
  next.configured = true;
  cfg::save(next);

  LOGI("setup saved, rebooting");
  s_server.send(
      200, "text/html; charset=utf-8",
      String(FPSTR(PAGE_PORTAL_HEAD)) +
          "<div class=\"ok\">✓ 配置已保存</div>"
          "<p>设备将以 WiFi 模式连接网络，随后重启。</p>"
          "<p style=\"opacity:.6;font-size:13px\">若 10 秒内未重启，请手动断电重上。</p>" +
          String(FPSTR(PAGE_PORTAL_FOOT)));

  delay(1200);
  ESP.restart();
}

// 任意未匹配路径都重定向到配置页，实现 Captive Portal 体验
void handleNotFound() {
  s_server.sendHeader("Location", "/", true);
  s_server.send(302, "text/plain", "");
}

}  // namespace

void begin() {
  if (s_active) return;

  WiFi.mode(WIFI_AP);
  IPAddress apIp(192, 168, 4, 1);
  WiFi.softAPConfig(apIp, apIp, IPAddress(255, 255, 255, 0));
  bool ok = WiFi.softAP(AP_SSID, (strlen(AP_PASSWORD) ? AP_PASSWORD : nullptr),
                        AP_CHANNEL, 0, AP_MAX_CLIENTS);
  if (!ok) {
    LOGE("AP start failed");
    return;
  }

  net::setApMode(true);

  // DNS 劫持：把所有域名解析到本机，触发系统 Captive Portal 弹窗
  s_dns.start(DNS_PORT, "*", apIp);

  s_server.on("/", HTTP_GET, handleRoot);
  s_server.on("/save", HTTP_POST, handleSave);
  s_server.on("/generate_204", HTTP_GET, handleRoot);  // Android 探测
  s_server.on("/hotspot-detect.html", HTTP_GET, handleRoot);  // iOS/macOS
  s_server.on("/connecttest.txt", HTTP_GET, handleRoot);      // Windows
  s_server.onNotFound(handleNotFound);
  s_server.begin();

  s_active = true;
  LOGI("AP started: SSID=%s IP=%s", AP_SSID,
       WiFi.softAPIP().toString().c_str());
}

void loop() {
  if (!s_active) return;
  s_dns.processNextRequest();
  s_server.handleClient();
}

bool active() { return s_active; }

void stop() {
  if (!s_active) return;
  s_server.stop();
  s_dns.stop();
  WiFi.softAPdisconnect(true);
  net::setApMode(false);
  s_active = false;
  LOGI("setup mode closed");
}

}  // namespace portal
