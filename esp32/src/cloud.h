// ============================================================================
//  SMSATBOX · 云端通信（ESP32 作为客户端连公网中转平台）
//  ---------------------------------------------------------------------------
//  上行：设备状态心跳、短信、来电
//  下行：发送短信指令、OTA 固件任务、Server 升级指令
//  鉴权：仅凭 Device_Token（X-Device-Token 头），不携带任何用户凭据
// ============================================================================
#pragma once

#include <Arduino.h>

#include "config.h"

// 下行指令类型
enum CloudCommandType {
  CMD_NONE = 0,
  CMD_SEND_SMS,
  CMD_OTA,
  CMD_SERVER_UPGRADE,
};

struct CloudCommand {
  CloudCommandType type = CMD_NONE;
  int commandId = 0;
  int slotIndex = 1;
  String targetNumber;
  String content;
  // OTA
  int taskId = 0;
  String otaVersion;
  String otaUrl;
  String otaMd5;
  int otaSize = 0;
};

namespace cloud {

/** 初始化（读取配置，准备 HTTP 客户端） */
void begin();

/** 推进：心跳上报、指令轮询 */
void loop();

/** 上报设备状态（心跳） */
bool reportStatus();

/** 上报一条短信 */
bool reportMessage(const char* kind, int slotIndex, const String& sender,
                   const String& content);

/** 拉取待执行指令（HTTP 兜底轮询） */
bool pollCommands(CloudCommand* out, int maxCount, int* outCount);

/** 回写指令执行结果 */
bool reportCommandResult(int commandId, const char* status,
                         const String& error = "");

/** 拉取待执行 OTA 任务 */
bool pollOta(CloudCommand* out);

/** 回写 OTA 进度 */
bool reportOta(int taskId, const char* status, const String& error = "");

/** 请求 Server 升级（设备发现版本落后时） */
bool requestServerUpgrade(const String& targetVersion);

/** 构造带鉴权的完整 URL */
String apiUrl(const char* path);

}  // namespace cloud
