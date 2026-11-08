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

  // -------------------------------------------------------------------
  // 状态查询（供上报云端 / 本地调试页展示）
  // -------------------------------------------------------------------

  /** 模组是否被物理检测到（上电后能 AT 握手成功） */
  bool present() const { return present_; }
  /** SIM 卡是否就绪 */
  bool simReady() const { return simReady_; }
  /** 是否已注册网络 */
  bool registered() const { return registered_; }
  /** AT+CREG 原始状态码：0未注册 1本地注册 2搜索中 3被拒 4未知 5漫游 */
  int regStatus() const { return regStatus_; }
  /** 注册状态的中文描述 */
  String regText() const;
  /** 位置区码 LAC */
  const String& lac() const { return lac_; }
  /** 小区 ID */
  const String& cellId() const { return cellId_; }
  /** CSQ 原始值 0-31，99=未知 */
  int csq() const { return csq_; }
  /** 信号格数 0-4 */
  int signalLevel() const;
  /** IMSI */
  const String& imsi() const { return imsi_; }
  /** ICCID */
  const String& iccid() const { return iccid_; }
  /** IMEI */
  const String& imei() const { return imei_; }
  /** 模组状态名（off/booting/ready/error） */
  const char* stateName() const;

  /** 主动刷新一次完整状态（会占用串口，约 1-2 秒） */
  void refreshAll();

  /** 成功握手次数（用于判断是否曾经工作过） */
  bool everConnected() const { return everConnected_; }

 private:
  /** 根据缺席次数决定重试间隔：刚失败时快，久失败后慢 */
  uint32_t retryInterval() const;

  /** PDU 模式发送（中文短信专用） */
  bool sendSmsPdu(const String& number, const String& content, String* error);

  /** PDU 单次发送（调用前需先 AT+CMGF=0） */
  bool sendSmsPduOnce(const String& number, const String& ucs2,
                      const String& smscNumber, bool forceIntl, String* error);

  void handleLine(const String& line);
  void handleUrc(const String& line);
  bool sendAt(const String& cmd, const String& expect, uint32_t timeoutMs,
              String* response = nullptr);
  void powerOn();
  void hardReset();
  void readSmsAt(int index);
  void querySignal();
  void queryIdentity();
  void queryRegistration();
  void querySimState();
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

  // ---- v1.1 新增：完整状态 ----
  bool present_ = false;      // 模组存在（AT 有响应）
  int regStatus_ = 4;         // CREG 状态码
  String lac_;                // 位置区码
  String cellId_;             // 小区 ID
  String imsi_;               // SIM 卡 IMSI
  String iccid_;              // SIM 卡 ICCID
  String imei_;               // 模组 IMEI

  // ---- v1.2 新增：防呆（模组可选插拔）----
  int absentRounds_ = 0;      // 连续未检测到模组的轮次
  bool everConnected_ = false; // 是否曾经成功握手过

  // ---- v1.3 新增：失联自恢复 + 计时器（不能用 static，否则两个模组会串）----
  bool needHardReset_ = false; // 下次进入探测前先拉 RST 硬复位
  uint32_t lastSignalMs_ = 0;
  uint32_t lastRegMs_ = 0;
  uint32_t lastAliveMs_ = 0;

  static SmsCallback smsCb_;
  static CallCallback callCb_;
};

/** 全局：按卡槽号取模组实例（1 或 2），越界返回 nullptr */
Modem* modemForSlot(int slotIndex);
