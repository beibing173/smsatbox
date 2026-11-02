// ============================================================================
//  SMSATBOX · 日志模块实现
// ============================================================================
#include "logger.h"

#include <cstdarg>
#include <cstdio>

namespace {

char s_ring[LOG_RING_SIZE][LOG_LINE_MAX];
int s_head = 0;   // 下一个写入位置
int s_count = 0;  // 已写入条数（最多 LOG_RING_SIZE）

}  // namespace

void logInit() {
  for (int i = 0; i < LOG_RING_SIZE; i++) {
    s_ring[i][0] = '\0';
  }
  s_head = 0;
  s_count = 0;
}

void logPrintf(LogLevel level, const char* fmt, ...) {
  char body[LOG_LINE_MAX];
  va_list args;
  va_start(args, fmt);
  vsnprintf(body, sizeof(body), fmt, args);
  va_end(args);

  const char* tag = (level == LOG_ERROR) ? "E" : (level == LOG_WARN) ? "W" : "I";

  // 运行时长作为简易时间戳（设备未联网时也可靠）
  unsigned long ms = millis();
  unsigned long sec = ms / 1000UL;
  char line[LOG_LINE_MAX];
  snprintf(line, sizeof(line), "[%02lu:%02lu:%02lu][%s] %s",
           sec / 3600UL, (sec / 60UL) % 60UL, sec % 60UL, tag, body);

  Serial.println(line);

  strncpy(s_ring[s_head], line, LOG_LINE_MAX - 1);
  s_ring[s_head][LOG_LINE_MAX - 1] = '\0';
  s_head = (s_head + 1) % LOG_RING_SIZE;
  if (s_count < LOG_RING_SIZE) {
    s_count++;
  }
}

const char* logRingLine(int i) {
  if (i < 0 || i >= s_count) {
    return "";
  }
  int idx = (s_head - 1 - i + LOG_RING_SIZE * 2) % LOG_RING_SIZE;
  return s_ring[idx];
}

int logRingCount() { return s_count; }

String logDump() {
  String out;
  out.reserve(s_count * 100);
  for (int i = 0; i < s_count; i++) {
    out += logRingLine(i);
    out += '\n';
  }
  return out;
}
