// ============================================================================
//  SMSATBOX · 网络管理（WiFi 优先，断开切 4G）
// ============================================================================
#pragma once

#include <Arduino.h>

#include "config.h"

namespace net {

/** 初始化（不阻塞连接） */
void begin();

/** 推进 WiFi 重连 / 模式切换状态机 */
void loop();

/** 当前回传模式 */
NetMode mode();

/** 是否具备可用网络（WiFi 或 4G） */
bool online();

/** 人类可读的模式名 */
const char* modeName();

/** WiFi 信号强度（未连接返回 0） */
int wifiRssi();

/** 局域网 IP（4G 模式或未连接返回空串） */
String localIp();

/** 连接 WiFi（内部调用，也可用于配网后立即连接） */
void connectWifi();

/** 强制重连 */
void reconnect();

/** 配网 AP 模式开关：开启时暂停 STA 重连，避免与热点冲突 */
void setApMode(bool enabled);

}  // namespace net
