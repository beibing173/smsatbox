// ============================================================================
//  SMSATBOX · 配置存储实现（Preferences / NVS）
// ============================================================================
#include "config_store.h"

#include <Preferences.h>

#include "logger.h"

namespace {

DeviceConfig s_cfg;
Preferences s_prefs;
bool s_loaded = false;

/** 读取字符串，缺失返回空串 */
String readStr(const char* key, const char* fallback = "") {
  return s_prefs.isKey(key) ? s_prefs.getString(key, fallback) : String(fallback);
}

}  // namespace

namespace cfg {

void ensureLoaded() {
  s_prefs.begin(NVS_NAMESPACE, /*readOnly=*/true);
  s_cfg.wifiSsid = readStr(NVS_KEY_WIFI_SSID);
  s_cfg.wifiPass = readStr(NVS_KEY_WIFI_PASS);
  s_cfg.serverUrl = readStr(NVS_KEY_SERVER_URL);
  s_cfg.deviceToken = readStr(NVS_KEY_DEVICE_TOKEN);
  s_cfg.configured = s_prefs.getBool(NVS_KEY_CONFIGURED, false);
  s_prefs.end();
  s_loaded = true;
}

const DeviceConfig& get() {
  if (!s_loaded) {
    ensureLoaded();
  }
  return s_cfg;
}

bool save(const DeviceConfig& incoming) {
  if (s_loaded) {
    // 再次调用时比较一下，避免每次开机都写 NVS（NVS 有擦写寿命）
    const DeviceConfig& cur = s_cfg;
    bool same = (cur.wifiSsid == incoming.wifiSsid) &&
                (cur.wifiPass == incoming.wifiPass) &&
                (cur.serverUrl == incoming.serverUrl) &&
                (cur.deviceToken == incoming.deviceToken);
    if (same && cur.configured) {
      return true;
    }
  }

  s_prefs.begin(NVS_NAMESPACE, /*readOnly=*/false);
  s_prefs.putString(NVS_KEY_WIFI_SSID, incoming.wifiSsid);
  s_prefs.putString(NVS_KEY_WIFI_PASS, incoming.wifiPass);
  s_prefs.putString(NVS_KEY_SERVER_URL, incoming.serverUrl);
  s_prefs.putString(NVS_KEY_DEVICE_TOKEN, incoming.deviceToken);
  s_prefs.putBool(NVS_KEY_CONFIGURED, incoming.configured);
  s_prefs.end();

  s_cfg = incoming;
  s_loaded = true;
  String tokenPreview = s_cfg.deviceToken.length() > 12
                            ? s_cfg.deviceToken.substring(0, 8) + "..."
                            : String("(short)");
  LOGI("config saved: ssid=%s server=%s token=%s", s_cfg.wifiSsid.c_str(),
       s_cfg.serverUrl.c_str(), tokenPreview.c_str());
  return true;
}

void clear() {
  s_prefs.begin(NVS_NAMESPACE, /*readOnly=*/false);
  s_prefs.clear();
  s_prefs.end();
  s_cfg = DeviceConfig();
  s_loaded = true;
  LOGW("config cleared, back to setup mode");
}

String normalizeServerUrl(const String& raw) {
  String url = raw;
  url.trim();
  if (url.isEmpty()) {
    return url;
  }
  if (!url.startsWith("http://") && !url.startsWith("https://")) {
    url = "http://" + url;
  }
  while (url.endsWith("/")) {
    url.remove(url.length() - 1);
  }
  return url;
}

bool validate(const String& ssid, const String& pass, const String& serverUrl,
              const String& token, String* error) {
  if (ssid.length() == 0) {
    if (error) *error = "WiFi 账号不能为空";
    return false;
  }
  if (ssid.length() > 32) {
    if (error) *error = "WiFi 账号过长（最多 32 字符）";
    return false;
  }
  if (pass.length() > 0 && pass.length() < 8) {
    if (error) *error = "WiFi 密码至少 8 位（开放网络请留空）";
    return false;
  }
  if (serverUrl.length() == 0) {
    if (error) *error = "云端平台地址不能为空";
    return false;
  }
  if (token.length() < 8) {
    if (error) *error = "设备绑定码过短，请从管理端复制完整 Device_Token";
    return false;
  }
  return true;
}

}  // namespace cfg
