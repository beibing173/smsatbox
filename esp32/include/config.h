// ============================================================================
//  SMSATBOX · 全局配置与引脚定义
//  ESP32-S3 (N16R8) + 双 ML307A-DSLN 4G 模组
// ============================================================================
#pragma once

#include <Arduino.h>

// ---------------------------------------------------------------------------
// 版本（与 Server / APK / EXE 全平台一致）
// ---------------------------------------------------------------------------
#define SMSATBOX_VERSION "1.0.1"

// ---------------------------------------------------------------------------
// 编译期开关（可用 platformio.ini 的 build_flags 覆盖）
// ---------------------------------------------------------------------------
#ifndef SMSATBOX_SERIAL_BAUD
#define SMSATBOX_SERIAL_BAUD 115200
#endif

// 心跳间隔（毫秒）
#define HEARTBEAT_INTERVAL_MS (30 * 1000)
// 状态上报间隔（毫秒）
#define REPORT_INTERVAL_MS (60 * 1000)
// 指令轮询兜底间隔（WebSocket 断开时启用）
#define COMMAND_POLL_INTERVAL_MS (15 * 1000)
// WiFi 重连检查间隔
#define WIFI_RECHECK_MS (15 * 1000)
// 4G 模组初始化重试间隔
#define MODEM_RETRY_MS (20 * 1000)
// 模组长期缺席后的慢速重试间隔（防呆：槽位空着也不刷屏，但永不放弃）
#define RETRY_SLOW_MS (60 * 1000)
// 串口行缓冲长度
#define MODEM_LINE_BUFFER 320
// 单条短信最大长度
#define SMS_MAX_LEN 320
// 本地 Web 日志环形缓冲行数
#define LOG_RING_SIZE 48
// 日志单行最大长度
#define LOG_LINE_MAX 190

// ---------------------------------------------------------------------------
// 双 ML307A 模组引脚（ESP32-S3 三组可用 UART：UART1 / UART2）
//  模组 A —— 卡槽 1
//  模组 B —— 卡槽 2
// ---------------------------------------------------------------------------
#define MODEM_COUNT 2

// --- 卡槽 1：UART1（GPIO 15/16/17/18）---
// 实测验证：TX=17 / RX=18 @115200 可正常收发 AT，收到 "OK"
#define MODEM1_UART_NUM 1
#define MODEM1_TX_PIN 17
#define MODEM1_RX_PIN 18
#define MODEM1_EN_PIN 16   // 模组电源使能（PWRKEY）
#define MODEM1_RST_PIN 15  // 复位

// --- 卡槽 2：UART2（改用 UART2 的经典引脚 9/10）---
// 说明：-1 表示该引脚未接线，固件会跳过对应的电平控制。
//       若模组 BAT 与 EN 已硬件短接（常开机），EN 也应设为 -1。
#define MODEM2_UART_NUM 2
#define MODEM2_TX_PIN 9
#define MODEM2_RX_PIN 10
#define MODEM2_EN_PIN -1   // BAT-EN 已短接，无需 GPIO 控制
#define MODEM2_RST_PIN -1  // 未接复位脚

// 状态指示灯（板载 RGB，共阴）
#define LED_PIN 48
#define LED_COUNT 1

// ---------------------------------------------------------------------------
// 网络与配网
// ---------------------------------------------------------------------------
// 首次配网热点
#define AP_SSID "SMSWIFI"
#define AP_PASSWORD ""  // 开放热点，便于手机直连后打开 Captive Portal
#define AP_CHANNEL 6
#define AP_MAX_CLIENTS 4

// 局域网调试 Web 端口
#define LAN_WEB_PORT 80
// Captive Portal 端口（与 80 复用同一 WebServer 实例）
#define DNS_PORT 53

// 设备默认上报间隔内 Server 版本比较
#define SERVER_VERSION_CHECK_INTERVAL_MS (6 * 60 * 60 * 1000L)

// ---------------------------------------------------------------------------
// NVS 键名（仅存 WiFi / 云端地址 / Device_Token —— 绝不含用户密码）
// ---------------------------------------------------------------------------
#define NVS_NAMESPACE "smsatbox"
#define NVS_KEY_WIFI_SSID "w_ssid"
#define NVS_KEY_WIFI_PASS "w_pass"
#define NVS_KEY_SERVER_URL "srv_url"
#define NVS_KEY_DEVICE_TOKEN "dev_tok"
#define NVS_KEY_CONFIGURED "cfg_ok"

// ---------------------------------------------------------------------------
// 模组状态机
// ---------------------------------------------------------------------------
enum ModemState {
  MODEM_OFF = 0,
  MODEM_BOOTING,
  MODEM_READY,
  MODEM_ERROR
};

// 网络回传优先级
enum NetMode {
  NET_NONE = 0,
  NET_WIFI = 1,
  NET_4G = 2
};
