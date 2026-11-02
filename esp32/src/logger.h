// ============================================================================
//  SMSATBOX · 日志模块（环形缓冲，供本地 Web 调试查看）
// ============================================================================
#pragma once

#include <Arduino.h>

#include "config.h"

enum LogLevel : uint8_t {
  LOG_INFO = 0,
  LOG_WARN = 1,
  LOG_ERROR = 2,
};

void logInit();

/** printf 风格写日志：串口 + 环形缓冲 */
void logPrintf(LogLevel level, const char* fmt, ...)
    __attribute__((format(printf, 2, 3)));

/** 取第 i 条日志（0 = 最新），越界返回空串 */
const char* logRingLine(int i);

/** 环形缓冲当前条数 */
int logRingCount();

/** 全部日志拼成一段文本（最新在前） */
String logDump();

#define LOGI(...) logPrintf(LOG_INFO, __VA_ARGS__)
#define LOGW(...) logPrintf(LOG_WARN, __VA_ARGS__)
#define LOGE(...) logPrintf(LOG_ERROR, __VA_ARGS__)
