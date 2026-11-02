// ============================================================================
//  SMSATBOX · ML307A-DSLN 驱动实现
//  ---------------------------------------------------------------------------
//  设计要点：
//   1) 全非阻塞：AT 等待带超时，绝不死等，避免拖垮主循环
//   2) 双模组独立状态机：任意一路故障不影响另一路
//   3) URC（+CMTI / +CLIP / +CREG 等）随时可能插入，故逐行解析
//   4) 短信按 +CMTI 索引逐条 +CMGR 读取后立即 +CMGD 删除，避免 SIM 塞满
// ============================================================================
#include "modem.h"

#include "logger.h"

SmsCallback Modem::smsCb_ = nullptr;
CallCallback Modem::callCb_ = nullptr;

namespace {
// 统一把 CR/LF 清干净
String trimCrlf(const String& s) {
  String out = s;
  out.trim();
  return out;
}

// 从 "+CMGR: \"REC UNREAD\",\"+8613800138000\",,\"24/01/01,10:00:00+32\"" 里取号码
String extractQuoted(const String& line, int index) {
  int q = -1;
  for (int i = 0, seen = 0; i <= index; i++) {
    q = line.indexOf('"', q + 1);
    if (q < 0) return String();
  }
  int end = line.indexOf('"', q + 1);
  if (end < 0) return String();
  return line.substring(q + 1, end);
}
}  // namespace

// 两个静态实例，定义在 smsatbox.ino 之外的独立翻译单元
static Modem* g_modems[MODEM_COUNT] = {nullptr, nullptr};

void registerModem(Modem* m) {
  if (m == nullptr) return;
  int idx = m->slot() - 1;
  if (idx >= 0 && idx < MODEM_COUNT) {
    g_modems[idx] = m;
  }
}

Modem* modemForSlot(int slotIndex) {
  int idx = slotIndex - 1;
  if (idx < 0 || idx >= MODEM_COUNT) return nullptr;
  return g_modems[idx];
}

Modem::Modem(uint8_t slotIndex, uint8_t uartNum, int8_t txPin, int8_t rxPin,
             int8_t enPin, int8_t rstPin)
    : slotIndex_(slotIndex),
      uartNum_(uartNum),
      txPin_(txPin),
      rxPin_(rxPin),
      enPin_(enPin),
      rstPin_(rstPin) {}

void Modem::begin() {
  if (enPin_ >= 0) {
    pinMode(enPin_, OUTPUT);
    digitalWrite(enPin_, LOW);
  }
  if (rstPin_ >= 0) {
    pinMode(rstPin_, OUTPUT);
    digitalWrite(rstPin_, HIGH);
  }

  switch (uartNum_) {
    case 1:
      serial_ = &Serial1;
      Serial1.begin(SMSATBOX_SERIAL_BAUD, SERIAL_8N1, rxPin_, txPin_);
      break;
    case 2:
      serial_ = &Serial2;
      Serial2.begin(SMSATBOX_SERIAL_BAUD, SERIAL_8N1, rxPin_, txPin_);
      break;
    default:
      LOGE("卡槽%d: 不支持的 UART 编号 %u", slotIndex_, uartNum_);
      state_ = MODEM_ERROR;
      return;
  }
  lineBuf_.reserve(MODEM_LINE_BUFFER);
  state_ = MODEM_OFF;
  bootStartMs_ = millis();
  lastActionMs_ = 0;
  LOGI("卡槽%d: 模组初始化 (UART%u TX=%d RX=%d)", slotIndex_, uartNum_, txPin_,
       rxPin_);
  powerOn();
}

void Modem::powerOn() {
  if (enPin_ >= 0) {
    // ML307A PWRKEY：拉高约 800ms 触发开机
    digitalWrite(enPin_, HIGH);
    delay(800);
    digitalWrite(enPin_, LOW);
  }
  state_ = MODEM_BOOTING;
  bootStartMs_ = millis();
  simReady_ = false;
  registered_ = false;
  csq_ = 99;
  LOGI("卡槽%d: 上电脉冲完成，等待 AT 响应", slotIndex_);
}

void Modem::hardReset() {
  LOGW("卡槽%d: 硬复位模组", slotIndex_);
  if (rstPin_ >= 0) {
    digitalWrite(rstPin_, LOW);
    delay(200);
    digitalWrite(rstPin_, HIGH);
  }
  lineBuf_ = "";
  powerOn();
}

void Modem::restart() {
  hardReset();
  lastActionMs_ = 0;
}

bool Modem::sendAt(const String& cmd, const String& expect, uint32_t timeoutMs,
                   String* response) {
  if (serial_ == nullptr) return false;
  while (serial_->available()) {
    serial_->read();  // 清掉积压，避免旧回显干扰
  }
  serial_->println(cmd);

  String acc;
  uint32_t start = millis();
  while (millis() - start < timeoutMs) {
    while (serial_->available()) {
      char c = static_cast<char>(serial_->read());
      if (c == '\n') {
        String line = trimCrlf(acc);
        acc = "";
        if (line.isEmpty()) continue;
        if (response) {
          response->concat(line);
          response->concat('\n');
        }
        // 命令回显，跳过
        if (line == cmd) continue;
        if (expect.length() && line.indexOf(expect) >= 0) return true;
        if (line == "ERROR" || line.startsWith("+CME ERROR")) return false;
        // 顺手处理插入的 URC
        handleUrc(line);
      } else if (c != '\r') {
        if (acc.length() < MODEM_LINE_BUFFER) acc.concat(c);
      }
    }
    delay(2);
  }
  return false;
}

void Modem::loop() {
  if (serial_ == nullptr || state_ == MODEM_ERROR) return;

  // 1) 先泵串口，URC 随时会来
  pumpBytes(*serial_);

  uint32_t now = millis();

  switch (state_) {
    case MODEM_OFF:
      powerOn();
      break;

    case MODEM_BOOTING: {
      // 开机后给模组 3 秒缓冲，再试 AT
      if (now - bootStartMs_ < 3000) break;
      if (now - lastActionMs_ < 3000) break;
      lastActionMs_ = now;
      if (sendAt("AT", "OK", 1000)) {
        LOGI("卡槽%d: AT 握手成功", slotIndex_);
        sendAt("ATE0", "OK", 1000);   // 关回显，减轻串口压力
        sendAt("AT+CMEE=1", "OK", 1000);
        sendAt("AT+CMGF=1", "OK", 1000);  // 文本模式
        sendAt("AT+CNMI=2,1,0,0,0", "OK", 1500);  // +CMTI 提示
        sendAt("AT+CLIP=1", "OK", 1500);          // 来电显示
        sendAt("AT+CPMS=\"SM\",\"SM\",\"SM\"", "OK", 2000);
        simReady_ = true;
        state_ = MODEM_READY;
        queryIdentity();
        querySignal();
      }
      break;
    }

    case MODEM_READY: {
      // 每 30 秒刷一次信号
      static uint32_t lastSignal = 0;
      if (now - lastSignal > 30000) {
        lastSignal = now;
        querySignal();
      }
      // 每 5 分钟确认一次网络注册
      static uint32_t lastReg = 0;
      if (now - lastReg > 300000) {
        lastReg = now;
        String resp;
        if (sendAt("AT+CREG?", "OK", 2000, &resp)) {
          registered_ = (resp.indexOf(",1") >= 0 || resp.indexOf(",5") >= 0);
          if (!registered_) {
            LOGW("卡槽%d: 网络未注册，尝试重新附着", slotIndex_);
            sendAt("AT+CFUN=1", "OK", 5000);
          }
        }
      }
      break;
    }

    case MODEM_ERROR:
      break;
  }
}

void Modem::pumpBytes(HardwareSerial& port) {
  while (port.available()) {
    char c = static_cast<char>(port.read());
    if (c == '\n') {
      String line = trimCrlf(lineBuf_);
      lineBuf_ = "";
      if (!line.isEmpty()) handleLine(line);
    } else if (c != '\r') {
      if (lineBuf_.length() < MODEM_LINE_BUFFER) {
        lineBuf_.concat(c);
      } else {
        lineBuf_ = "";  // 溢出丢弃，防止内存碎片
      }
    }
  }
}

void Modem::handleLine(const String& line) {
  if (line.startsWith("+CMTI")) {
    parseCmti(line);
  } else if (line.startsWith("+CLIP")) {
    parseClip(line);
  } else if (line.startsWith("+CREG") || line.startsWith("+CGREG")) {
    registered_ = (line.indexOf(",1") >= 0 || line.indexOf(",5") >= 0);
  } else if (line == "RDY" && state_ == MODEM_BOOTING) {
    LOGI("卡槽%d: 模组上报 RDY", slotIndex_);
  }
}

void Modem::handleUrc(const String& line) { handleLine(line); }

// "+CMTI: \"SM\",4"  -> 读第 4 条
void Modem::parseCmti(const String& line) {
  int comma = line.lastIndexOf(',');
  if (comma < 0) return;
  int index = line.substring(comma + 1).toInt();
  LOGI("卡槽%d: 新短信提示 +CMTI index=%d", slotIndex_, index);
  readSmsAt(index);
}

void Modem::readSmsAt(int index) {
  String resp;
  String cmd = "AT+CMGR=" + String(index);
  if (!sendAt(cmd, "OK", 5000, &resp)) {
    LOGE("卡槽%d: 读取短信 %d 失败", slotIndex_, index);
    return;
  }

  // resp 结构：
  //   +CMGR: "REC UNREAD","+8613800138000",,"24/01/01,10:00:00+32"
  //   短信正文
  //   OK
  int headerPos = resp.indexOf("+CMGR:");
  String sender;
  String content;
  if (headerPos >= 0) {
    int eol = resp.indexOf('\n', headerPos);
    String header = resp.substring(headerPos, eol < 0 ? resp.length() : eol);
    // 头部形如 +CMGR: "REC UNREAD","+8613800138000",,"24/01/01,10:00:00+32"
    // 第 1 对引号是状态，第 2 对是号码
    sender = extractQuoted(header, 1);
    if (sender.isEmpty()) {
      sender = extractQuoted(header, 0);
    }
    if (eol >= 0) {
      content = resp.substring(eol + 1);
      int okPos = content.lastIndexOf("OK");
      if (okPos >= 0) {
        content = content.substring(0, okPos);
      }
      content.trim();
    }
  } else {
    LOGE("卡槽%d: +CMGR 响应格式异常", slotIndex_);
  }

  // 无论成败都删除，防止 SIM 卡被塞满
  sendAt("AT+CMGD=" + String(index), "OK", 3000);

  if (content.isEmpty()) {
    LOGW("卡槽%d: 短信 %d 内容为空，已忽略", slotIndex_, index);
    return;
  }
  LOGI("卡槽%d: 收到短信 来自 %s (%u 字节)", slotIndex_, sender.c_str(),
       content.length());
  if (smsCb_ != nullptr) {
    smsCb_(slotIndex_, sender, content, resp);
  }
}

// "+CLIP: \"+8613800138000\",145" -> 来电
void Modem::parseClip(const String& line) {
  int q1 = line.indexOf('"');
  if (q1 < 0) return;
  int q2 = line.indexOf('"', q1 + 1);
  if (q2 < 0) return;
  String number = line.substring(q1 + 1, q2);
  LOGI("卡槽%d: 来电 %s", slotIndex_, number.c_str());
  if (callCb_ != nullptr) {
    callCb_(slotIndex_, number);
  }
}

void Modem::querySignal() {
  String resp;
  if (!sendAt("AT+CSQ", "OK", 2000, &resp)) return;
  int pos = resp.indexOf("+CSQ:");
  if (pos < 0) return;
  int comma = resp.indexOf(',', pos);
  if (comma < 0) return;
  int val = resp.substring(pos + 5, comma).toInt();
  // 99 = 未知；0-31 有效
  csq_ = (val >= 0 && val <= 31) ? val : 99;
}

int Modem::signalDbm() const {
  if (csq_ < 0 || csq_ > 31) return 99;  // 未知
  // 3GPP 换算：dBm = -113 + 2 * csq
  return -113 + 2 * csq_;
}

void Modem::queryIdentity() {
  // 运营商
  String resp;
  if (sendAt("AT+COPS?", "OK", 3000, &resp)) {
    int q1 = resp.indexOf('"');
    int q2 = resp.indexOf('"', q1 + 1);
    if (q1 >= 0 && q2 > q1) {
      carrier_ = resp.substring(q1 + 1, q2);
    }
  }
  // 本机号码（部分卡未写入，允许为空）
  String resp2;
  if (sendAt("AT+CNUM", "OK", 3000, &resp2)) {
    int q1 = resp2.indexOf("\",\"");
    if (q1 >= 0) {
      int start = q1 + 3;
      int end = resp2.indexOf('"', start);
      if (end > start) {
        phoneNumber_ = resp2.substring(start, end);
      }
    }
  }
  LOGI("卡槽%d: 仿真信息 carrier=%s number=%s", slotIndex_, carrier_.c_str(),
       phoneNumber_.length() ? phoneNumber_.c_str() : "(未写入)");
}

bool Modem::sendSms(const String& number, const String& content, String* error) {
  if (state_ != MODEM_READY) {
    if (error) *error = "模组未就绪";
    return false;
  }
  if (number.length() < 3) {
    if (error) *error = "号码无效";
    return false;
  }
  if (content.length() == 0) {
    if (error) *error = "内容为空";
    return false;
  }
  if (serial_ == nullptr) {
    if (error) *error = "串口未初始化";
    return false;
  }

  // 1) 设置目标号码
  if (!sendAt("AT+CMGS=\"" + number + "\"", ">", 5000)) {
    if (error) *error = "号码被模组拒绝";
    LOGE("卡槽%d: CMGS 未返回提示符", slotIndex_);
    return false;
  }

  // 2) 写入正文 + Ctrl-Z 提交
  serial_->print(content);
  serial_->write(0x1A);

  // 3) 等 +CMGS: <mr> 与 OK
  String acc;
  uint32_t start = millis();
  bool ok = false;
  while (millis() - start < 30000) {
    while (serial_->available()) {
      char c = static_cast<char>(serial_->read());
      if (c == '\n') {
        String line = trimCrlf(acc);
        acc = "";
        if (line.startsWith("+CMGS")) {
          LOGI("卡槽%d: 短信已提交 %s", slotIndex_, line.c_str());
        } else if (line == "OK") {
          ok = true;
        } else if (line == "ERROR" || line.startsWith("+CMS ERROR")) {
          if (error) *error = line;
          LOGE("卡槽%d: 发送失败 %s", slotIndex_, line.c_str());
          return false;
        }
      } else if (c != '\r') {
        if (acc.length() < MODEM_LINE_BUFFER) acc.concat(c);
      }
    }
    if (ok) break;
    delay(5);
  }

  if (!ok && error) *error = "发送超时";
  if (ok) LOGI("卡槽%d: 短信发送成功 -> %s", slotIndex_, number.c_str());
  return ok;
}
