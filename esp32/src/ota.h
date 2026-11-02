// ============================================================================
//  SMSATBOX · OTA 双分区升级
//  ---------------------------------------------------------------------------
//  流程：Server 上传 .bin -> WebSocket/轮询下发任务 -> 设备静默下载
//        -> MD5 校验 -> 写入备用分区 -> 切换启动 -> 重启
//  安全：校验不通过绝不切换分区，保持当前固件可运行
// ============================================================================
#pragma once

#include <Arduino.h>

namespace ota {

/**
 * 执行一次 OTA 升级。
 * @param url     固件下载地址（相对路径会自动拼上 Server 基地址）
 * @param md5     期望的 MD5（32 位小写十六进制），为空则跳过校验
 * @param version 目标版本号，仅用于日志
 * @param error   失败原因输出
 * @return true 表示已成功写入并即将重启
 */
bool performUpdate(const String& url, const String& md5, const String& version,
                   String* error);

/** 当前运行分区版本信息 */
String runningVersion();

}  // namespace ota
