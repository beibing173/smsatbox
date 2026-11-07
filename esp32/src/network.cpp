// ============================================================================
//  SMSATBOX · 网络管理实现
//  ---------------------------------------------------------------------------
//  "双轨服务机制" 的网络侧：
//   - 对 Server 是客户端：优先 WiFi 上网回传，WiFi 断开时切 4G 流量
//   - 对局域网是服务端：WiFi 模式下开启 Web 服务器供本地调试
// ============================================================================
#include "network.h"

#include <WiFi.h>

#include "config_store.h"
#include "logger.h"

namespace net {

namespace {
NetMode s_mode = NET_NONE;
uint32_t s_lastCheck = 0;
uint32_t s_connectStart = 0;
bool s_wifiConnecting = false;
bool s_apMode = false;  // 配网热点模式下不尝试 STA 连接

}  // namespace

void begin() {
  WiFi.persistent(false);
  WiFi.setAutoReconnect(true);
  WiFi.mode(WIFI_STA);
  const DeviceConfig& cfg = cfg::get();
  if (cfg.configured && cfg.wifiSsid.length() > 0) {
    connectWifi();
  } else {
    LOGI("not configured yet");
  }
  s_lastCheck = millis();
}

void connectWifi() {
  const DeviceConfig& cfg = cfg::get();
  if (cfg.wifiSsid.isEmpty()) return;
  LOGI("connecting wifi: %s", cfg.wifiSsid.c_str());
  WiFi.begin(cfg.wifiSsid.c_str(), cfg.wifiPass.c_str());
  s_wifiConnecting = true;
  s_connectStart = millis();
}

void loop() {
  uint32_t now = millis();

  // WiFi 连接超时判定（15 秒连不上就切 4G）
  if (s_wifiConnecting) {
    if (WiFi.status() == WL_CONNECTED) {
      s_wifiConnecting = false;
      s_mode = NET_WIFI;
      LOGI("wifi connected ip=%s rssi=%d", WiFi.localIP().toString().c_str(),
           WiFi.RSSI());
      return;
    }
    if (now - s_connectStart > 15000) {
      s_wifiConnecting = false;
      LOGW("wifi timeout, fallback 4G");
      if (s_mode == NET_NONE) s_mode = NET_4G;
      return;
    }
  }

  // 周期性检查
  if (now - s_lastCheck > WIFI_RECHECK_MS) {
    s_lastCheck = now;

    if (WiFi.status() == WL_CONNECTED) {
      if (s_mode != NET_WIFI) {
        LOGI("switch to wifi");
        s_mode = NET_WIFI;
      }
    } else {
      if (s_mode == NET_WIFI) {
        LOGW("wifi lost, switch to 4G");
        s_mode = NET_4G;
      }
      // 未配网 / AP 模式时不主动重连，避免与热点冲突
      if (!s_apMode && !s_wifiConnecting) {
        const DeviceConfig& cfg = cfg::get();
        if (cfg.configured && cfg.wifiSsid.length() > 0 &&
            WiFi.getMode() == WIFI_STA) {
          connectWifi();
        }
      }
    }
  }
}

NetMode mode() { return s_mode; }

bool online() {
  if (WiFi.status() == WL_CONNECTED) return true;
  // 4G 模式：只要任一模组已注册网络即视为在线
  return s_mode == NET_4G;
}

const char* modeName() {
  switch (s_mode) {
    case NET_WIFI:
      return "wifi";
    case NET_4G:
      return "4g";
    default:
      return "none";
  }
}

int wifiRssi() {
  return (WiFi.status() == WL_CONNECTED) ? WiFi.RSSI() : 0;
}

String localIp() {
  if (WiFi.status() == WL_CONNECTED) {
    return WiFi.localIP().toString();
  }
  return String();
}

void reconnect() {
  s_wifiConnecting = false;
  WiFi.disconnect(false, false);
  connectWifi();
}

// 供配网模块使用：进入 AP 模式时禁止 STA 重连
void setApMode(bool enabled) {
  s_apMode = enabled;
  if (enabled) {
    s_wifiConnecting = false;
    s_mode = NET_NONE;
  }
}

}  // namespace net
