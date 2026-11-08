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
      LOGE("[SLOT%d] unsupported UART num %u", slotIndex_, uartNum_);
      state_ = MODEM_ERROR;
      return;
  }
  lineBuf_.reserve(MODEM_LINE_BUFFER);
  state_ = MODEM_OFF;
  bootStartMs_ = millis();
  lastActionMs_ = 0;
  LOGI("[SLOT%d] modem init (UART%u TX=%d RX=%d)", slotIndex_, uartNum_, txPin_,
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
  LOGI("[SLOT%d] power-on pulse done, waiting for AT", slotIndex_);
}

void Modem::hardReset() {
  LOGW("[SLOT%d] hard reset modem", slotIndex_);
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
  bool gotExpect = false;
  uint32_t expectAt = 0;

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
        if (expect.length() && line.indexOf(expect) >= 0) {
          gotExpect = true;
          expectAt = millis();
          // 不再立即返回：多读 60ms，把 OK 之前/之后可能还在缓冲区里的行收全
          // （+CREG: 这类响应有时分多行/延迟到达）
          continue;
        }
        if (line == "ERROR" || line.startsWith("+CME ERROR")) return false;
        // 顺手处理插入的 URC
        handleUrc(line);
      } else if (c != '\r') {
        if (acc.length() < MODEM_LINE_BUFFER) acc.concat(c);
      }
    }

    // 已经拿到期望响应，且安静了 60ms → 认为响应收全
    if (gotExpect && millis() - expectAt > 60) {
      return true;
    }
    delay(2);
  }
  return gotExpect;
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
      if (now - lastActionMs_ < retryInterval()) break;
      lastActionMs_ = now;

      if (sendAt("AT", "OK", 1000)) {
        LOGI("[SLOT%d] AT handshake OK, modem present", slotIndex_);
        present_ = true;   // 标记模组被检测到
        everConnected_ = true;
        absentRounds_ = 0; // 清零缺席计数
        sendAt("ATE0", "OK", 1000);   // 关回显，减轻串口压力
        sendAt("AT+CMEE=1", "OK", 1000);
        sendAt("AT+CMGF=1", "OK", 1000);  // 文本模式
        sendAt("AT+CNMI=2,1,0,0,0", "OK", 1500);  // +CMTI 提示
        sendAt("AT+CLIP=1", "OK", 1500);          // 来电显示
        sendAt("AT+CPMS=\"SM\",\"SM\",\"SM\"", "OK", 2000);
        state_ = MODEM_READY;
        // 完整探测：SIM 状态、网络注册、身份标识
        querySimState();
        queryRegistration();
        queryIdentity();
        querySignal();
      } else {
        // 握手失败：模组可能没插/没接线
        present_ = false;
        absentRounds_++;

        if (absentRounds_ == 1) {
          // 第一次失败就提示，方便排查
          LOGW("[SLOT%d] no response yet (modem may be absent). retrying...", slotIndex_);
        } else if (absentRounds_ <= 3) {
          LOGI("[SLOT%d] still absent (%u/3)", slotIndex_, absentRounds_);
        } else if (absentRounds_ == 4) {
          // 连续失败多次后降低日志噪音，改为低频重试（不彻底放弃）
          LOGW("[SLOT%d] slot appears unused. Will keep probing every %us in background.",
               slotIndex_, RETRY_SLOW_MS / 1000);
        }
        // 不进入 ERROR 状态，保持可恢复：
        // 用户随时插上模组，下一轮探测就能自动接上
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
            LOGW("[SLOT%d] not registered, re-attach", slotIndex_);
            sendAt("AT+CFUN=1", "OK", 5000);
          }
          // 顺便刷新注册详情
          queryRegistration();
        } else {
          // AT 有响应但 CREG 查询失败，可能刚掉线，先不动
        }
      }

      // ★ 防呆：定期做活跃性检查，模组被拔掉能自动发现并退回探测态
      static uint32_t lastAlive = 0;
      if (now - lastAlive > 45000) {
        lastAlive = now;
        if (!sendAt("AT", "OK", 800)) {
          LOGW("[SLOT%d] modem stopped responding, back to probing", slotIndex_);
          present_ = false;
          state_ = MODEM_BOOTING;
          bootStartMs_ = now;
          lastActionMs_ = 0;
          absentRounds_ = 1;
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
    LOGI("[SLOT%d] modem reported RDY", slotIndex_);
  }
}

void Modem::handleUrc(const String& line) { handleLine(line); }

// 根据缺席轮次决定重试间隔：
//   刚开机 / 刚失败   → 3 秒（快速检测）
//   连续失败 1-3 次    → 10 秒
//   连续失败 4 次以上  → 60 秒（降低噪音，但永不放弃）
uint32_t Modem::retryInterval() const {
  if (absentRounds_ <= 0) return 3000;
  if (absentRounds_ <= 3) return 10000;
  return RETRY_SLOW_MS;
}

// ---------------------------------------------------------------------------
// 状态查询实现
// ---------------------------------------------------------------------------

const char* Modem::stateName() const {
  switch (state_) {
    case MODEM_OFF:
      return "off";
    case MODEM_BOOTING:
      // 长期探测不到就报 absent，前端可以显示「槽位未使用」
      return absentRounds_ >= 2 ? "absent" : "booting";
    case MODEM_READY:
      return "ready";
    case MODEM_ERROR:
      return "error";
  }
  return "error";
}

String Modem::regText() const {
  switch (regStatus_) {
    case 0:
      return "未注册·未搜索";
    case 1:
      return "已注册·本地网络";
    case 2:
      return "搜索中";
    case 3:
      return "注册被拒绝";
    case 4:
      return "未知";
    case 5:
      return "已注册·漫游";
    default:
      return "未知";
  }
}

int Modem::signalLevel() const {
  if (csq_ < 0 || csq_ > 31) return 0;
  // 0-31 映射到 0-4 格
  if (csq_ >= 25) return 4;
  if (csq_ >= 18) return 3;
  if (csq_ >= 11) return 2;
  if (csq_ >= 5) return 1;
  return 0;
}

// AT+CREG?  -> 常见几种格式：
//   +CREG: 0,1                 （n=0, stat=1 已注册）
//   +CREG: 0,1,"1A2B","1C2D3E4F"
//   +CREG: 1,1                 （有时 n 位丢失/粘连）
//   +CREG: 11                  （n 与 stat 粘连成一个数）
void Modem::queryRegistration() {
  String resp;
  if (!sendAt("AT+CREG?", "OK", 3000, &resp)) {
    return;
  }

  // ★ 关键：响应里可能同时有 +CREG: 和 +CGREG:（甚至被粘在同一行）
  //   必须只取 "+CREG:" 开头的那一行，不能整段搜 indexOf
  String body;
  int from = 0;
  while (from < (int)resp.length()) {
    int nl = resp.indexOf('\n', from);
    String line = (nl < 0) ? resp.substring(from) : resp.substring(from, nl);
    line.trim();
    from = (nl < 0) ? resp.length() : nl + 1;

    if (!line.startsWith("+CREG:")) continue;

    body = line.substring(6);
    body.trim();

    // 若这一行里意外粘了 "+CGREG"，截断掉
    int cut = body.indexOf("+CG");
    if (cut > 0) body = body.substring(0, cut);
    body.trim();
    break;
  }

  if (body.isEmpty()) {
    // 没有 +CREG 行，可能模组没开 CREG 上报
    LOGW("[SLOT%d] no +CREG line in response", slotIndex_);
    return;
  }

  // —— 提取所有逗号分隔的数字字段 ——
  int nums[4] = {-1, -1, -1, -1};
  int numCount = 0;
  int i = 0;
  while (i < (int)body.length() && numCount < 4) {
    // 跳过非数字
    while (i < (int)body.length() && (body[i] < '0' || body[i] > '9')) i++;
    if (i >= (int)body.length()) break;
    int start = i;
    while (i < (int)body.length() && body[i] >= '0' && body[i] <= '9') i++;
    long v = body.substring(start, i).toInt();
    if (v >= 0 && v < 100000) {
      nums[numCount++] = (int)v;
    }
  }

  // —— 判定 stat ——
  // 正常两字段：nums[0]=n, nums[1]=stat
  // 只有一字段：那个数可能是 stat，也可能是 n*10+stat 的粘连值
  int stat = -1;
  if (numCount >= 2) {
    stat = nums[1];
    // 兜底：某些模组（如 ML307A）会把 +CGREG 的状态码粘进来，
    // 变成 "0,11" 这种。此时取个位数即为真实 stat。
    if (stat > 5) {
      int alt = stat % 10;
      if (alt >= 0 && alt <= 5) {
        stat = alt;
      }
    }
  } else if (numCount == 1) {
    int v = nums[0];
    if (v >= 0 && v <= 5) {
      stat = v;              // 直接就是 stat
    } else if (v >= 10 && v <= 59) {
      stat = v % 10;         // 粘连：n*10 + stat
    }
  }

  // 极端兜底：若仍无法解析，用 +CGREG 的信息或直接看原始串
  if (stat < 0 || stat > 5) {
    // 原始串里含 "1" 或 "5" 且不含 "0,"/2/3 时，倾向于已注册
    if (body.indexOf(",1") >= 0 || body.indexOf(",5") >= 0) {
      stat = body.indexOf(",5") >= 0 ? 5 : 1;
    }
  }

  // 校验范围，异常时按未注册处理
  if (stat < 0 || stat > 5) {
    LOGW("[SLOT%d] cannot parse CREG, raw='%s'", slotIndex_, body.c_str());
    regStatus_ = 0;
    registered_ = false;
    return;
  }

  regStatus_ = stat;
  registered_ = (stat == 1 || stat == 5);

  // —— 解析 LAC / CellID（可能存在）——
  int q1 = body.indexOf('"');
  if (q1 >= 0) {
    int q2 = body.indexOf('"', q1 + 1);
    if (q2 > q1) lac_ = body.substring(q1 + 1, q2);
    int q3 = body.indexOf('"', q2 + 1);
    if (q3 >= 0) {
      int q4 = body.indexOf('"', q3 + 1);
      if (q4 > q3) cellId_ = body.substring(q3 + 1, q4);
    }
  }

  // 串口日志只用 ASCII，中文由前端自行映射（避免 USB 串口工具乱码）
  LOGI("[SLOT%d] reg raw='%s' -> stat=%d registered=%d lac=%s cell=%s",
       slotIndex_, body.c_str(), regStatus_, registered_ ? 1 : 0,
       lac_.c_str(), cellId_.c_str());
}

// 查询 SIM 状态与卡内标识
void Modem::querySimState() {
  // SIM 就绪检测：模组刚开机时 SIM 需要 3~10 秒初始化，
  // 不能只查一次就判定 ABSENT，这里最多等 12 秒。
  String resp;
  bool ok = false;
  simReady_ = false;

  for (int attempt = 0; attempt < 6; attempt++) {
    resp = "";
    ok = sendAt("AT+CPIN?", "OK", 3000, &resp);
    if (ok && resp.indexOf("READY") >= 0) {
      simReady_ = true;
      break;
    }
    // 没就绪：等 2 秒再试（模组可能需要时间读卡）
    if (attempt < 5) {
      delay(2000);
      pumpBytes(*serial_);
    }
  }

  if (!simReady_) {
    // 等完仍不就绪，把原始响应打出来，方便判断是「没插卡」还是「需要 PIN」
    String raw = resp;
    raw.replace("\r", "");
    raw.replace("\n", " | ");
    raw.trim();
    if (raw.length() > 80) raw = raw.substring(0, 80);
    LOGW("[SLOT%d] SIM not ready after retries (cpin_ok=%d raw='%s')",
         slotIndex_, ok ? 1 : 0, raw.c_str());
  }

  // IMSI
  String imsiResp;
  if (sendAt("AT+CIMI", "OK", 3000, &imsiResp)) {
    String v;
    for (size_t i = 0; i < imsiResp.length(); i++) {
      char ch = imsiResp[i];
      if (ch >= '0' && ch <= '9') v += ch;
    }
    if (v.length() >= 10) imsi_ = v;
  }

  // ICCID
  String iccidResp;
  if (sendAt("AT+CCID", "OK", 3000, &iccidResp)) {
    String v;
    for (size_t i = 0; i < iccidResp.length(); i++) {
      char ch = iccidResp[i];
      if (ch >= '0' && ch <= '9') v += ch;
    }
    if (v.length() >= 10) iccid_ = v;
  }

  // IMEI
  String imeiResp;
  if (sendAt("AT+GSN", "OK", 3000, &imeiResp)) {
    String v;
    for (size_t i = 0; i < imeiResp.length(); i++) {
      char ch = imeiResp[i];
      if (ch >= '0' && ch <= '9') v += ch;
    }
    if (v.length() >= 10) imei_ = v;
  }

  LOGI("[SLOT%d] SIM=%s imsi=%s iccid=%s imei=%s", slotIndex_,
       simReady_ ? "READY" : "ABSENT", imsi_.c_str(), iccid_.c_str(),
       imei_.c_str());
}

// 一次性刷新全部状态（只在主循环低频调用，避免占用串口）
void Modem::refreshAll() {
  if (state_ != MODEM_READY) return;
  querySignal();
  queryRegistration();
  queryIdentity();
  querySimState();
}

// "+CMTI: \"SM\",4"  -> 读第 4 条
void Modem::parseCmti(const String& line) {
  int comma = line.lastIndexOf(',');
  if (comma < 0) return;
  int index = line.substring(comma + 1).toInt();
  LOGI("[SLOT%d] new SMS +CMTI index=%d", slotIndex_, index);
  readSmsAt(index);
}

void Modem::readSmsAt(int index) {
  String resp;
  String cmd = "AT+CMGR=" + String(index);
  if (!sendAt(cmd, "OK", 5000, &resp)) {
    LOGE("[SLOT%d] read SMS %d failed", slotIndex_, index);
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
    LOGE("[SLOT%d] bad +CMGR response", slotIndex_);
  }

  // 无论成败都删除，防止 SIM 卡被塞满
  sendAt("AT+CMGD=" + String(index), "OK", 3000);

  if (content.isEmpty()) {
    LOGW("[SLOT%d] SMS %d empty, ignored", slotIndex_, index);
    return;
  }
  LOGI("[SLOT%d] SMS from %s (%u bytes)", slotIndex_, sender.c_str(),
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
  LOGI("[SLOT%d] incoming call %s", slotIndex_, number.c_str());
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
  LOGI("[SLOT%d] identity carrier=%s number=%s", slotIndex_, carrier_.c_str(),
       phoneNumber_.length() ? phoneNumber_.c_str() : "(not set)");
}

bool Modem::sendSms(const String& number, const String& content, String* error) {
  if (state_ != MODEM_READY) {
    if (error) *error = "modem not ready";
    return false;
  }
  if (number.length() < 3) {
    if (error) *error = "invalid number";
    return false;
  }
  if (content.length() == 0) {
    if (error) *error = "empty content";
    return false;
  }
  if (serial_ == nullptr) {
    if (error) *error = "serial not ready";
    return false;
  }

  // ---- 1) 清空串口缓冲 ----
  while (serial_->available()) serial_->read();

  // ---- 2) 发送 AT+CMGS="number" ----
  String cmd = "AT+CMGS=\"" + number + "\"";
  serial_->println(cmd);

  // ---- 3) 逐字节等 '>' 提示符 ----
  // ★ 关键：CMGS 的 ">" 后面没有换行符，不能按行解析，
  //   否则永远等不到 '\n'，会误判超时。
  bool gotPrompt = false;
  bool gotError = false;
  String errLine;
  String acc;
  uint32_t start = millis();

  while (millis() - start < 8000) {
    while (serial_->available()) {
      char c = static_cast<char>(serial_->read());
      if (c == '>') {
        gotPrompt = true;
        break;
      }
      if (c == '\n') {
        String line = trimCrlf(acc);
        acc = "";
        if (line.isEmpty() || line == cmd) continue;
        if (line == "ERROR" || line.startsWith("+CME ERROR") ||
            line.startsWith("+CMS ERROR")) {
          gotError = true;
          errLine = line;
          break;
        }
      } else if (c != '\r') {
        if (acc.length() < MODEM_LINE_BUFFER) acc.concat(c);
      }
    }
    if (gotPrompt || gotError) break;
    delay(2);
  }

  if (gotError) {
    if (error) *error = errLine;
    LOGE("[SLOT%d] CMGS rejected: %s", slotIndex_, errLine.c_str());
    return false;
  }
  if (!gotPrompt) {
    if (error) *error = "no prompt from modem";
    LOGE("[SLOT%d] CMGS no prompt (modem did not reply '>')", slotIndex_);
    return false;
  }

  // ---- 4) 写入正文 + Ctrl-Z 提交 ----
  serial_->print(content);
  serial_->write(0x1A);
  serial_->flush();

  // ---- 5) 等 +CMGS: <mr> 与 OK ----
  acc = "";
  start = millis();
  bool ok = false;
  String finalErr;

  while (millis() - start < 30000) {
    while (serial_->available()) {
      char c = static_cast<char>(serial_->read());
      if (c == '\n') {
        String line = trimCrlf(acc);
        acc = "";
        if (line.startsWith("+CMGS")) {
          LOGI("[SLOT%d] SMS submitted %s", slotIndex_, line.c_str());
        } else if (line == "OK") {
          ok = true;
        } else if (line == "ERROR" || line.startsWith("+CMS ERROR") ||
                   line.startsWith("+CME ERROR")) {
          finalErr = line;
        }
      } else if (c != '\r') {
        if (acc.length() < MODEM_LINE_BUFFER) acc.concat(c);
      }
    }
    if (ok || finalErr.length() > 0) break;
    delay(5);
  }

  if (finalErr.length() > 0) {
    if (error) *error = finalErr;
    LOGE("[SLOT%d] send failed %s", slotIndex_, finalErr.c_str());
    return false;
  }
  if (!ok && error) *error = "send timeout";
  if (ok) LOGI("[SLOT%d] SMS sent -> %s", slotIndex_, number.c_str());
  return ok;
}
