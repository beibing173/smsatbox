// ============================================================================
//  SMSATBOX · 配置存储（NVS）
//  ---------------------------------------------------------------------------
//  核心安全原则：设备端只存三项——WiFi 账号密码、云端地址、Device_Token。
//  绝不存储任何用户密码、成员列表或权限逻辑（那属于 Server 数据库职责）。
// ============================================================================
#pragma once

#include <Arduino.h>

#include "config.h"

struct DeviceConfig {
  String wifiSsid;
  String wifiPass;
  String serverUrl;   // 例如 https://sms.example.com 或 http://1.2.3.4:8080
  String deviceToken; // 唯一设备绑定码
  bool configured;    // 配网是否完成
};

namespace cfg {

/** 从 NVS 载入配置（幂等）；未配网时 configured=false */
void ensureLoaded();

/** 取当前配置（首次调用会自动载入） */
const DeviceConfig& get();

/** 写入并持久化配置，返回是否成功 */
bool save(const DeviceConfig& incoming);

/** 清空配置（恢复出厂，重新进入配网页） */
void clear();

/** 规范化云端地址：去掉尾部斜杠；缺协议时补 http:// */
String normalizeServerUrl(const String& raw);

/** 三项必填是否都齐全且合法 */
bool validate(const String& ssid, const String& pass, const String& serverUrl,
              const String& token, String* error);

}  // namespace cfg
