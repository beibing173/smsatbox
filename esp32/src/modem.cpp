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

// 从 "+CMGR: \"REC UNREAD\",\"+8613800138000\",,\"24/01/01,10:00:00+32\"" 里取第 index 对引号内容
// index=0 -> REC UNREAD，index=1 -> +8613800138000，index=2 -> 时间戳
String extractQuoted(const String& line, int index) {
  int pos = -1;
  for (int i = 0; i <= index; i++) {
    int begin = line.indexOf('"', pos + 1);
    if (begin < 0) return String();
    int end = line.indexOf('"', begin + 1);
    if (end < 0) return String();
    if (i == index) return line.substring(begin + 1, end);
    pos = end;  // 跳到这一对的结束引号，下次从这里继续找
  }
  return String();
}

// ---- UCS2 解码：中文短信通常以 4 位十六进制/字符 传输 ----
// 例如 "8FD4" -> "返"，"4F60597D" -> "你好"
static bool looksLikeUcs2(const String& s) {
  if (s.length() < 4 || (s.length() % 4) != 0) return false;
  for (size_t i = 0; i < s.length(); i++) {
    char c = s[i];
    bool hex = (c >= '0' && c <= '9') || (c >= 'A' && c <= 'F') ||
               (c >= 'a' && c <= 'f');
    if (!hex) return false;
  }
  return true;
}

static String ucs2ToUtf8(const String& hex) {  String out;
  out.reserve(hex.length() / 2);
  for (size_t i = 0; i + 3 < hex.length(); i += 4) {
    uint32_t cp = 0;
    for (size_t j = i; j < i + 4; j++) {
      char c = hex[j];
      uint32_t v = (c >= '0' && c <= '9') ? (c - '0')
                 : (c >= 'A' && c <= 'F') ? (c - 'A' + 10)
                 : (c - 'a' + 10);
      cp = (cp << 4) | v;
    }
    if (cp == 0) continue;
    // 跳过 BOM / 控制字符
    if (cp == 0xFEFF) continue;
    if (cp < 0x20 && cp != '\n' && cp != '\r') continue;

    if (cp < 0x80) {
      out += (char)cp;
    } else if (cp < 0x800) {
      out += (char)(0xC0 | (cp >> 6));
      out += (char)(0x80 | (cp & 0x3F));
    } else if (cp < 0x10000) {
      out += (char)(0xE0 | (cp >> 12));
      out += (char)(0x80 | ((cp >> 6) & 0x3F));
      out += (char)(0x80 | (cp & 0x3F));
    } else {
      out += (char)(0xF0 | (cp >> 18));
      out += (char)(0x80 | ((cp >> 12) & 0x3F));
      out += (char)(0x80 | ((cp >> 6) & 0x3F));
      out += (char)(0x80 | (cp & 0x3F));
    }
  }
  return out;
}

// ---- 反向：UTF-8 -> UCS2 十六进制（发中文短信用）----
static bool hasNonAscii(const String& s) {
  for (size_t i = 0; i < s.length(); i++) {
    if ((uint8_t)s[i] > 0x7F) return true;
  }
  return false;
}

static String utf8ToUcs2(const String& s) {
  String out;
  out.reserve(s.length() * 2);
  size_t i = 0;
  while (i < s.length()) {
    uint8_t c = (uint8_t)s[i];
    uint32_t cp = 0;
    size_t len = 1;
    if (c < 0x80) {
      cp = c;
    } else if ((c & 0xE0) == 0xC0 && i + 1 < s.length()) {
      cp = ((c & 0x1F) << 6) | ((uint8_t)s[i + 1] & 0x3F);
      len = 2;
    } else if ((c & 0xF0) == 0xE0 && i + 2 < s.length()) {
      cp = ((c & 0x0F) << 12) | (((uint8_t)s[i + 1] & 0x3F) << 6) |
           ((uint8_t)s[i + 2] & 0x3F);
      len = 3;
    } else if ((c & 0xF8) == 0xF0 && i + 3 < s.length()) {
      cp = ((c & 0x07) << 18) | (((uint8_t)s[i + 1] & 0x3F) << 12) |
           (((uint8_t)s[i + 2] & 0x3F) << 6) | ((uint8_t)s[i + 3] & 0x3F);
      len = 4;
    } else {
      cp = '?';
    }
    i += len;

    // BMP 内的码点直接转 4 位十六进制；超出 BMP 用代理对
    if (cp < 0x10000) {
      char buf[8];
      snprintf(buf, sizeof(buf), "%04X", (unsigned)cp);
      out += buf;
    } else {
      uint32_t v = cp - 0x10000;
      uint32_t hi = 0xD800 + (v >> 10);
      uint32_t lo = 0xDC00 + (v & 0x3FF);
      char buf[16];
      snprintf(buf, sizeof(buf), "%04X%04X", (unsigned)hi, (unsigned)lo);
      out += buf;
    }
  }
  return out;
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

bool Modem::restartSimStack() {
  if (!present_) return false;

  LOGI("[SLOT%d] restarting SIM stack (CFUN cycle)", slotIndex_);

  // 关协议栈：让模组放开 SIM
  atRaw("AT+CFUN=0", "OK", 8000, nullptr);
  delay(8000);

  // 开协议栈：模组重新初始化 USIM
  atRaw("AT+CFUN=1", "OK", 15000, nullptr);

  delay(10000);
  LOGI("[SLOT%d] SIM stack restarted", slotIndex_);
  return true;
}

void Modem::restart() {
  hardReset();
  lastActionMs_ = 0;
}

// ---------------------------------------------------------------------------
// 扩展模块独占接口（eUICC APDU 会话用）
// ---------------------------------------------------------------------------
bool Modem::lockExtension() {
  if (serial_ == nullptr) return false;
  if (state_ != MODEM_READY) return false;
  if (extLocked_) return false;
  extLocked_ = true;
  return true;
}

void Modem::unlockExtension() {
  extLocked_ = false;
  // 解锁后把各类计时器推到当前，避免立刻触发一堆周期性查询
  uint32_t now = millis();
  lastAliveMs_ = now;
  lastSignalMs_ = now;
}

bool Modem::atRaw(const String& cmd, const String& expect, uint32_t timeoutMs,
                  String* response) {
  if (serial_ == nullptr) return false;

  while (serial_->available()) serial_->read();
  serial_->println(cmd);

  String acc;
  String collected;
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
        collected += line;
        collected += '\n';
        if (line == cmd) continue;  // 回显
        if (expect.length() && line.indexOf(expect) >= 0) {
          gotExpect = true;
          expectAt = millis();
          continue;
        }
        if (line == "ERROR" || line.startsWith("+CME ERROR")) {
          if (response) *response = collected;
          return false;
        }
      } else if (c != '\r') {
        // 扩展模块用大缓冲：AT+CGLA 的 APDU 响应可能长达数 KB
        if (acc.length() < MODEM_RAW_LINE_BUFFER) acc.concat(c);
      }
    }
    if (gotExpect && millis() - expectAt > 60) break;
    delay(2);
  }

  if (response) *response = collected;
  return gotExpect;
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

  // 被 eUICC 等扩展模块独占时，状态机暂停（串口归它们使用）
  if (extLocked_) return;

  // 1) 先泵串口，URC 随时会来
  pumpBytes(*serial_);

  uint32_t now = millis();

  switch (state_) {
    case MODEM_OFF:
      powerOn();
      break;

    case MODEM_BOOTING: {
      // ★ 失联后的硬复位：模组死机时软 AT 无效，必须拉 RST 重新上电
      if (needHardReset_) {
        needHardReset_ = false;
        LOGW("[SLOT%d] hard-resetting modem (RST low 300ms) to recover", slotIndex_);
        if (rstPin_ >= 0) {
          pinMode(rstPin_, OUTPUT);
          digitalWrite(rstPin_, LOW);
          delay(300);
          digitalWrite(rstPin_, HIGH);
          delay(100);
        }
        powerOn();
        lastActionMs_ = 0;
        bootStartMs_ = millis();
        break;
      }

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

        // ★ 每 5 次失败尝试一次硬复位：
        //   模组可能因供电跌落死机，仅靠 AT 无法唤醒，需要 RST/PWRKEY 重启
        if (absentRounds_ > 0 && absentRounds_ % 5 == 0) {
          LOGW("[SLOT%d] retry %d times failed, attempting hard reset",
               slotIndex_, absentRounds_);
          needHardReset_ = true;
        }
        // 不进入 ERROR 状态，保持可恢复：
        // 用户随时插上模组，下一轮探测就能自动接上
      }
      break;
    }

    case MODEM_READY: {
      // 每 30 秒刷一次信号
      if (now - lastSignalMs_ > 30000) {
        lastSignalMs_ = now;
        querySignal();
      }
      // 每 5 分钟确认一次网络注册
      if (now - lastRegMs_ > 300000) {
        lastRegMs_ = now;
        String resp;
        if (sendAt("AT+CREG?", "OK", 2000, &resp)) {
          registered_ = (resp.indexOf(",1") >= 0 || resp.indexOf(",5") >= 0 ||
                          resp.indexOf(",6") >= 0 || resp.indexOf(",7") >= 0);
          if (!registered_) {
            LOGW("[SLOT%d] not registered, re-attach", slotIndex_);
            sendAt("AT+CFUN=1", "OK", 5000);
          }
          // 顺便刷新注册详情
          queryRegistration();
        }
      }

      // ★ 活跃性检查：模组失联（尤其发射短信后电压跌落死机）自动恢复
      if (now - lastAliveMs_ > 45000) {
        lastAliveMs_ = now;
        if (!sendAt("AT", "OK", 800)) {
          LOGW("[SLOT%d] modem stopped responding (power dip?). will recover",
               slotIndex_);
          present_ = false;
          state_ = MODEM_BOOTING;
          bootStartMs_ = now;
          lastActionMs_ = 0;
          absentRounds_ = 1;
          needHardReset_ = true;   // 标记：下次探测前先拉 RST
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
    registered_ = (line.indexOf(",1") >= 0 || line.indexOf(",5") >= 0 ||
                           line.indexOf(",6") >= 0 || line.indexOf(",7") >= 0);
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
    case 6:
      return "已注册·仅短信";
    case 7:
      return "已注册·漫游（仅短信）";
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
  //
  // 合法 stat（3GPP 27.007）：
  //   0 未注册且未搜索   1 已注册本地网   2 搜索中   3 注册被拒
  //   4 未知             5 已注册漫游
  //   6 已注册（仅短信） 7 已注册漫游（仅短信）  ← 国际漫游数据卡常见
  constexpr int kStatMax = 7;
  int stat = -1;
  if (numCount >= 2) {
    stat = nums[1];
    // 兜底：某些模组（如 ML307A）会把 +CGREG 的状态码粘进来，
    // 变成 "0,11" 这种。此时取个位数即为真实 stat。
    if (stat > kStatMax) {
      int alt = stat % 10;
      if (alt >= 0 && alt <= kStatMax) {
        stat = alt;
      }
    }
  } else if (numCount == 1) {
    int v = nums[0];
    if (v >= 0 && v <= kStatMax) {
      stat = v;              // 直接就是 stat
    } else if (v >= 10 && v <= 79) {
      stat = v % 10;         // 粘连：n*10 + stat
    }
  }

  // 极端兜底：若仍无法解析，看原始串里有没有已注册的状态码
  if (stat < 0 || stat > kStatMax) {
    static const char* kRegisteredCodes[] = {",1", ",5", ",6", ",7"};
    for (const char* code : kRegisteredCodes) {
      if (body.indexOf(code) >= 0) {
        stat = code[1] - '0';
        break;
      }
    }
  }

  // 校验范围，异常时按未注册处理
  if (stat < 0 || stat > kStatMax) {
    LOGW("[SLOT%d] cannot parse CREG, raw='%s'", slotIndex_, body.c_str());
    regStatus_ = 0;
    registered_ = false;
    return;
  }

  regStatus_ = stat;
  // 1/5 = 正常注册；6/7 = 已注册但仅支持短信（国际漫游数据卡常见）
  registered_ = (stat == 1 || stat == 5 || stat == 6 || stat == 7);

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

  // ★ SIM 卡热插拔自恢复：
  //   模组一旦判定「无卡」会一直返回 +CME ERROR: 10，即使之后插好卡，
  //   它也不会主动重新读卡。必须重启协议栈（AT+CFUN=1,1）才会重新初始化 SIM。
  //   这里连续数次检测不到卡就自动重启一次协议栈，让用户插卡后无需重启设备。
  if (!simReady_ && present_) {
    simAbsentRounds_++;
    if (simAbsentRounds_ >= 3) {
      simAbsentRounds_ = 0;
      LOGW("[SLOT%d] SIM absent %d rounds, restarting protocol stack (CFUN=1,1)",
           slotIndex_, 3);
      // 关射频再开，强制重新初始化 SIM
      sendAt("AT+CFUN=0", "OK", 5000);
      delay(1500);
      sendAt("AT+CFUN=1", "OK", 15000);
      delay(3000);
      querySimState();
    }
  } else if (simReady_) {
    simAbsentRounds_ = 0;
  }
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

  // 调试用：把原始响应打出来（换行替换成 |，截断 200 字符）
  {
    String raw = resp;
    raw.replace("\r", "");
    raw.replace("\n", "|");
    raw.trim();
    if (raw.length() > 200) raw = raw.substring(0, 200);
    LOGI("[SLOT%d] CMGR raw: %s", slotIndex_, raw.c_str());
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

  // ★ 中文短信（UCS2 编码）解码：模组在文本模式下对非 GSM 字符
  //   会返回 4 位十六进制/字符的 UCS2 串，需要转成 UTF-8 才能正常显示。
  if (content.length() > 0 && looksLikeUcs2(content)) {
    String decoded = ucs2ToUtf8(content);
    if (decoded.length() > 0) {
      LOGI("[SLOT%d] UCS2 decoded: %s -> %s", slotIndex_, content.c_str(),
           decoded.c_str());
      content = decoded;
    }
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

// ---------------------------------------------------------------------------
// 国际区号推断
// ---------------------------------------------------------------------------
//  为什么优先用本机号码而不是 IMSI？
//    IMSI 的 MCC 只表示「卡归属的运营商国家」，和号码归属可能不一致。
//    例如国际漫游 eSIM：IMSI 是香港(454)，但号码是 +1 美国号。
//    本机号码自己写的前缀才是这个号真正该用的国际码。
// ---------------------------------------------------------------------------
String Modem::countryCode() const {
  // ---- 1) 本机号码前缀（最准）----
  if (phoneNumber_.startsWith("+") && phoneNumber_.length() >= 4) {
    String d = phoneNumber_.substring(1);

    // 1 位区号：+1 北美、+7 俄罗斯
    if (d[0] == '1' || d[0] == '7') return String("+") + d[0];

    // 3 位区号：香港 852 / 澳门 853 / 台湾 886 / 柬埔寨 855 / 老挝 856
    if (d.length() >= 3) {
      String t = d.substring(0, 3);
      if (t == "852" || t == "853" || t == "886" || t == "855" || t == "856") {
        return "+" + t;
      }
    }

    // 其余按 2 位区号（86/81/82/91/44/49/33/39/61/65/60... 都是 2 位）
    if (d.length() >= 2) return "+" + d.substring(0, 2);
  }

  // ---- 2) IMSI 的 MCC 兜底（卡没写号码时）----
  if (imsi_.length() >= 3) {
    String mcc = imsi_.substring(0, 3);
    if (mcc == "460" || mcc == "461") return "+86";   // 中国
    if (mcc == "454" || mcc == "455") return "+852";  // 香港
    if (mcc == "466") return "+886";                  // 台湾
    if (mcc == "440" || mcc == "441") return "+81";   // 日本
    if (mcc == "450") return "+82";                   // 韩国
    if (mcc.startsWith("31") || mcc == "302") return "+1";  // 北美
    if (mcc == "234" || mcc == "235") return "+44";   // 英国
    if (mcc == "262") return "+49";                   // 德国
    if (mcc == "208") return "+33";                   // 法国
    if (mcc == "222") return "+39";                   // 意大利
    if (mcc == "505") return "+61";                   // 澳大利亚
    if (mcc == "525") return "+65";                   // 新加坡
    if (mcc == "502") return "+60";                   // 马来西亚
    if (mcc == "520") return "+66";                   // 泰国
    if (mcc == "404" || mcc == "405") return "+91";   // 印度
    if (mcc == "724") return "+55";                   // 巴西
  }

  return String();
}

namespace {

// 判断号码是否已经是「本国号码」形态（不需要再补国际区号）
bool looksDomestic(const String& n, const String& cc) {
  if (cc == "+86") return n.length() == 11 && n[0] == '1';
  if (cc == "+1") return n.length() == 10;
  if (cc == "+852" || cc == "+853") return n.length() == 8;
  if (cc == "+886") return n.length() == 9 || n.length() == 10;
  if (cc == "+81") return n.length() == 10 || n.length() == 11;
  if (cc == "+82") return n.length() == 9 || n.length() == 10;
  if (cc == "+65") return n.length() == 8;
  if (cc == "+60") return n.length() == 9 || n.length() == 10;
  if (cc == "+44") return n.length() == 10 || n.length() == 11;
  return false;
}

}  // namespace

String Modem::normalizeNumber(const String& number) const {
  String n = number;
  n.trim();
  n.replace(" ", "");
  n.replace("-", "");
  if (n.isEmpty()) return n;

  // 已带 "+"：用户显式指定国际格式，原样用（最可靠）
  if (n.startsWith("+")) return n;

  String cc = countryCode();
  if (cc.isEmpty()) return n;  // 判断不出国家，保持原样

  // 像本国号码 → 按国内格式发
  if (looksDomestic(n, cc)) return n;

  // 否则补本机国家区号
  return cc + n;
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

// 电话号数字串 -> PDU BCD（两位交换，奇数位补 F）
static String digitsToBcd(const String& digits) {
  String out;
  for (size_t i = 0; i < digits.length(); i += 2) {
    if (i + 1 < digits.length()) {
      out += digits[i + 1];
      out += digits[i];
    } else {
      out += 'F';
      out += digits[i];
    }
  }
  return out;
}

// 构造 SMSC 部分。smscNumber 为空时返回 "00"（依赖 SIM 卡内置短信中心）
// 格式：信息长度(1字节) + 号码类型(91) + BCD 号码
static String buildSmscPart(const String& smscNumber) {
  String s = smscNumber;
  s.replace("+", "");
  s.replace(" ", "");
  s.replace("-", "");
  if (s.length() < 5) return String("00");

  int bcdBytes = (int)((s.length() + 1) / 2);
  int infoLen = 1 + bcdBytes;  // 类型字节 + BCD
  char buf[8];
  snprintf(buf, sizeof(buf), "%02X", infoLen);

  String out = buf;
  out += "91";  // 国际号码
  out += digitsToBcd(s);
  return out;
}

// ---- 构造 UCS2 短信的 PDU（CMGF=0 模式），用于可靠地发送中文 ----
// 参考 3GPP 23.040：SMSC + 地址 + PID + DCS + VP + UDL + UD
//   smscNumber : 为空则 PDU 里 SMSC 长度写 0（用 SIM 内置）
//   forceIntl  : 目标号码按 91 国际格式编码（自动补 +86）
//   tpduLenOut : 输出 TPDU 字节数（不含 SMSC，供 AT+CMGS=<len> 使用）
static String buildSmsPdu(const String& number, const String& ucs2Hex,
                          const String& smscNumber, bool forceIntl,
                          int* tpduLenOut) {
  String smsc = buildSmscPart(smscNumber);

  // 目标号码：去符号
  String n = number;
  n.replace("+", "");
  n.replace(" ", "");
  n.replace("-", "");
  if (n.length() == 0) return String();

  // 记住原始号码是否带 "+"：带了就说明已经是完整国际格式，
  // 绝对不能再擅自补 86（否则 +1 的美国号会被拼成 86 1606...）
  const bool hadPlus = number.indexOf('+') >= 0;

  // 转国际格式需要补中国区号 86 —— 仅限「用户没写 +」的国内号码场景
  bool intl = forceIntl || hadPlus || n.length() > 11;
  if (forceIntl && !hadPlus && n.length() == 11) {
    n = "86" + n;
  }

  String tpdu;
  char buf[8];

  // ★★★ 关键：SMS-SUBMIT 的第一个字节（TPDU 类型）和 message reference ★★★
  // 标准 3GPP 23.040 SMS-SUBMIT 结构：
  //   [SCA] [PDU-Type=01] [MR=00] [DA-Len] [DA-Type] [DA-BCD] [PID] [DCS] [VP] [UDL] [UD]
  // 之前漏掉了 PDU-Type 和 MR，导致模组能接受 PDU（返回 +CMGS）
  // 但网络侧解析失败，报 CMS ERROR 41 (Temporary failure)。
  tpdu += "01";  // SMS-SUBMIT 类型（bit0=1 提交，bit6=0 无 UDH）
  tpdu += "00";  // Message Reference（0=模组自动分配）

  // 号码位数（十进制数字个数）
  snprintf(buf, sizeof(buf), "%02X", n.length());
  tpdu += buf;

  // 号码类型：91=国际号码，81=国内号码
  tpdu += intl ? "91" : "81";

  // BCD 编码
  tpdu += digitsToBcd(n);

  tpdu += "00";  // PID：普通点对点短信
  tpdu += "08";  // DCS：UCS2 编码
  // ★ 注意：PDU-Type=0x01 表示 VPF=0（无有效期字段），
  //   这里不能再写 VP 字节，否则整个 PDU 错位，
  //   表现为模组接受 PDU（返回 +CMGS）但网络侧报 CMS ERROR 41。
  //   参考 pdulib 的 PDU_SMS_SUBMIT 实现：DCS 之后直接是 UDL。

  // UDL：用户数据字节数
  int byteLen = ucs2Hex.length() / 2;
  snprintf(buf, sizeof(buf), "%02X", byteLen);
  tpdu += buf;
  tpdu += ucs2Hex;

  if (tpduLenOut != nullptr) *tpduLenOut = (int)(tpdu.length() / 2);
  return smsc + tpdu;
}

bool Modem::sendSms(const String& rawNumber, const String& content, String* error) {
  if (state_ != MODEM_READY) {
    if (error) *error = "modem not ready";
    return false;
  }
  if (rawNumber.length() < 3) {
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

  // 按本机国家区号规范化号码
  const String number = normalizeNumber(rawNumber);
  if (number != rawNumber) {
    LOGI("[SLOT%d] number normalized: %s -> %s (cc=%s)", slotIndex_,
         rawNumber.c_str(), number.c_str(), countryCode().c_str());
  }

  // ---- 1) 清空串口缓冲 ----
  while (serial_->available()) serial_->read();

  const bool sendAsUcs2 = hasNonAscii(content);

  // ---- 含中文等非 ASCII 字符：走 PDU 模式（ML307A 官方推荐，最可靠）----
  if (sendAsUcs2) {
    return sendSmsPdu(number, content, error);
  }

  // ---- 1.5) 确保处于文本模式（CMGF=1）----
  // ★ CMS ERROR 304 = "Invalid PDU mode parameter"
  //   说明模组当前在 PDU 模式（CMGF=0），但我们是按文本模式发的。
  //   模组掉线重启后可能恢复默认 PDU 模式，所以每次发送前都确认一次。
  {
    String cmgfResp;
    bool cmgfOk = sendAt("AT+CMGF?", "OK", 2000, &cmgfResp);
    if (!cmgfOk || cmgfResp.indexOf("+CMGF: 1") < 0) {
      LOGW("[SLOT%d] not in text mode, switching CMGF=1", slotIndex_);
      sendAt("AT+CMGF=1", "OK", 3000);
    }
  }

  // ---- 1.6) 纯 ASCII 内容用 GSM 字符集 ----
  {
    sendAt("AT+CSCS=\"GSM\"", "OK", 2000);
  }

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


// ---------------------------------------------------------------------------
// PDU 模式发送（中文短信），带「国内格式 -> 国际格式」自动重试
//   CMS ERROR 41（Temporary failure）常见于地址类型不被网络接受，
//   先按 81（国内）发，失败再按 91（国际 +86）重发一次。
// ---------------------------------------------------------------------------
bool Modem::sendSmsPdu(const String& rawNumber, const String& content, String* error) {
  String ucs2 = utf8ToUcs2(content);

  // 先按本机国家区号规范化号码，再构造 PDU
  String number = normalizeNumber(rawNumber);
  if (number != rawNumber) {
    LOGI("[SLOT%d] number normalized: %s -> %s (cc=%s)", slotIndex_,
         rawNumber.c_str(), number.c_str(), countryCode().c_str());
  }

  // 诊断：打印设备实际收到的 UTF-8 字节，确认传输无损
  {
    String hexIn;
    char b[4];
    for (size_t i = 0; i < content.length() && i < 40; i++) {
      snprintf(b, sizeof(b), "%02X", (uint8_t)content[i]);
      hexIn += b;
    }
    LOGI("[SLOT%d] content utf8 hex: %s (%u bytes)", slotIndex_, hexIn.c_str(),
         (unsigned)content.length());
  }

  // 查短信中心号码，显式写进 PDU（比依赖 SIM 读取更可靠）
  String smscNumber;
  if (sendAt("AT+CMGF=0", "OK", 3000)) {
    String cscaResp;
    if (sendAt("AT+CSCA?", "OK", 3000, &cscaResp)) {
      String v = cscaResp;
      v.replace("\r", "");
      v.replace("\n", "|");
      v.trim();
      LOGI("[SLOT%d] SMSC: %s", slotIndex_, v.c_str());

      // 从 +CSCA: "+8613334113200",145 里取出号码
      int q1 = v.indexOf('"');
      if (q1 >= 0) {
        int q2 = v.indexOf('"', q1 + 1);
        if (q2 > q1) smscNumber = v.substring(q1 + 1, q2);
      }
    }
  }

  // 第一次：国内号码格式（81）
  if (sendSmsPduOnce(number, ucs2, smscNumber, false, error)) {
    sendAt("AT+CMGF=1", "OK", 2000);
    return true;
  }

  // 第二次：国际号码格式（91 + 86），很多网络只认这种
  LOGW("[SLOT%d] retry PDU with +86 international format", slotIndex_);
  sendAt("AT+CMGF=0", "OK", 3000);
  bool ok = sendSmsPduOnce(number, ucs2, smscNumber, true, error);

  // 无论成败都恢复文本模式（收短信依赖 CMGF=1）
  sendAt("AT+CMGF=1", "OK", 2000);
  return ok;
}

// 单次 PDU 发送（调用前需先 CMGF=0）
bool Modem::sendSmsPduOnce(const String& number, const String& ucs2,
                           const String& smscNumber, bool forceIntl, String* error) {
  int tpduLen = 0;
  String pdu = buildSmsPdu(number, ucs2, smscNumber, forceIntl, &tpduLen);
  if (pdu.length() < 20 || tpduLen <= 0) {
    if (error) *error = "invalid pdu";
    LOGE("[SLOT%d] pdu build failed (len=%u)", slotIndex_, (unsigned)pdu.length());
    return false;
  }

  LOGI("[SLOT%d] PDU(intl=%d) tpdu=%d pdu=%s", slotIndex_, forceIntl ? 1 : 0,
       tpduLen, pdu.c_str());

  while (serial_->available()) serial_->read();
  String cmd = "AT+CMGS=" + String(tpduLen);
  serial_->println(cmd);

  // 等 '>' 提示符
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
    LOGE("[SLOT%d] CMGS(PDU) rejected: %s", slotIndex_, errLine.c_str());
    return false;
  }
  if (!gotPrompt) {
    if (error) *error = "no prompt (pdu)";
    LOGE("[SLOT%d] CMGS(PDU) no prompt", slotIndex_);
    return false;
  }

  serial_->print(pdu);
  serial_->write(0x1A);
  serial_->flush();

  // 等 +CMGS: <mr> 与 OK
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
          LOGI("[SLOT%d] PDU submitted %s", slotIndex_, line.c_str());
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
    LOGE("[SLOT%d] PDU send failed %s", slotIndex_, finalErr.c_str());
    return false;
  }
  if (!ok && error) *error = "pdu send timeout";
  if (ok) LOGI("[SLOT%d] SMS(PDU/Chinese) sent -> %s", slotIndex_, number.c_str());
  return ok;
}
