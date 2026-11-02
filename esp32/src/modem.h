// ============================================================================
//  SMSATBOX · ML307A-DSLN 4G 模组驱动（AT 指令）
//  ---------------------------------------------------------------------------
//  职责：串口 AT 交互、上电/复位、SIM 就绪检测、信号查询、
//        短信收发（+CMTI / +CMGR / +CMGS）、来电监听（+CLIP）、
//        掉线重连。不含任何业务逻辑，消息通过回调交给上层。
//
//  两个模组各占一路 UART，互不干扰：
//    slot 1 -> UART1 (TX17 / RX18)
//    slot 2 -> UART2 (TX9  / RX10)
// ============================================================================
#pragma once

#include <Arduino.h>

#include "config.h"

// 回调：一条完整短信（由 URC +CMTI 触发，内部再 +CMGR 取回内容）
typedef void (*SmsCallback)(int slotIndex, const String& sender,
                            const String& content, const String& rawAt);
// 回调：来电（+CLIP）
typedef void (*CallCallback)(int slotIndex, const String& number);

class Modem {
 public:
  Modem(uint8_t slotIndex, uint8_t uartNum, int8_t txPin, int8_t rxPin,
        int8_t enPin, int8_t rstPin);

  /** 初始化串口与引脚（不等待模组就绪） */
  void begin();

  /** 推进状态机：AT 握手、SIM 检测、注册网络。非阻塞 */
  void loop();

  /** 是否已就绪可用 */
  bool isReady() const { return state_ == MODEM_READY; }
  ModemState state() const { return state_; }
  uint8_t slot() const { return slotIndex_; }

  /** 信号强度 CSQ（0-31），未知返回 99 */
  int signalCsq() const { return csq_; }
  /** 转 dBm 估算值 */
  int signalDbm() const;

  /** SIM 卡号（+CNUM / +CIMI 尽力而为，可能为空） */
  const String& phoneNumber() const { return phoneNumber_; }
  /** 运营商名（+COPS） */
  const String& carrier() const { return carrier_; }

  /** 发送短信（异步投递，结果通过返回值表示是否成功入队） */
  bool sendSms(const String& number, const String& content, String* error);

  /** 设置回调 */
  static void setSmsCallback(SmsCallback cb) { smsCb_ = cb; }
  static void setCallCallback(CallCallback cb) { callCb_ = cb; }

  /** 统一处理各路串口来的字节（由 UartPump 调用） */
  void pumpBytes(HardwareSerial& port);

  /** 立即重新初始化模组（掉线恢复用） */
  void restart();

 private:
  void handleLine(const String& line);
  void handleUrc(const String& line);
  bool sendAt(const String& cmd, const String& expect, uint32_t timeoutMs,
              String* response = nullptr);
  void powerOn();
  void hardReset();
  void readSmsAt(int index);
  void querySignal();
  void queryIdentity();
  void parseClip(const String& line);
  void parseCmti(const String& line);

  uint8_t slotIndex_;
  uint8_t uartNum_;
  int8_t txPin_;
  int8_t rxPin_;
  int8_t enPin_;
  int8_t rstPin_;

  HardwareSerial* serial_ = nullptr;
  String lineBuf_;
  ModemState state_ = MODEM_OFF;
  uint32_t lastActionMs_ = 0;
  uint32_t bootStartMs_ = 0;
  int csq_ = 99;
  String phoneNumber_;
  String carrier_;
  bool simReady_ = false;
  bool registered_ = false;

  static SmsCallback smsCb_;
  static CallCallback callCb_;
};

/** 全局：按卡槽号取模组实例（1 或 2），越界返回 nullptr */
Modem* modemForSlot(int slotIndex);
