// ============================================================================
//  SMSATBOX · eUICC / eSIM 适配模块实现
// ============================================================================
#include "euicc.h"

#include "config.h"
#include "logger.h"
#include "modem.h"

namespace {

// ISD-R（Issuer Security Domain - Root）AID：eUICC 管理入口
constexpr const char* ISD_R_AID = "A0000005591010FFFFFFFF8900000100";

// ---------------------------------------------------------------------------
// 十六进制工具
// ---------------------------------------------------------------------------
uint8_t hexVal(char c) {
  if (c >= '0' && c <= '9') return (uint8_t)(c - '0');
  if (c >= 'A' && c <= 'F') return (uint8_t)(c - 'A' + 10);
  if (c >= 'a' && c <= 'f') return (uint8_t)(c - 'a' + 10);
  return 0xFF;
}

bool isHexString(const String& s) {
  if (s.length() == 0 || (s.length() & 1)) return false;
  for (size_t i = 0; i < s.length(); i++) {
    if (hexVal(s[i]) == 0xFF) return false;
  }
  return true;
}

size_t hexToBytes(const String& hex, uint8_t* out, size_t maxLen) {
  size_t n = hex.length() / 2;
  if (n > maxLen) n = maxLen;
  for (size_t i = 0; i < n; i++) {
    out[i] = (uint8_t)((hexVal(hex[i * 2]) << 4) | hexVal(hex[i * 2 + 1]));
  }
  return n;
}

String bytesToHex(const uint8_t* data, size_t len) {
  static const char* kHex = "0123456789ABCDEF";
  String out;
  out.reserve(len * 2);
  for (size_t i = 0; i < len; i++) {
    out += kHex[(data[i] >> 4) & 0x0F];
    out += kHex[data[i] & 0x0F];
  }
  return out;
}

// ---------------------------------------------------------------------------
// DER TLV 解析（SGP.22 用 BER-TLV）
// ---------------------------------------------------------------------------
struct Tlv {
  uint32_t tag = 0;
  String value;  // 原始字节（以 String 承载二进制）
};

/** 把一段 TL V 序列解析到 out 里。返回是否成功。 */
bool parseTlvs(const String& data, std::vector<Tlv>* out) {
  out->clear();
  size_t pos = 0;
  const size_t len = data.length();
  while (pos < len) {
    // ---- tag（可能多字节）----
    uint32_t tag = (uint8_t)data[pos++];
    if ((tag & 0x1F) == 0x1F) {
      uint8_t b;
      do {
        if (pos >= len) return false;
        b = (uint8_t)data[pos++];
        tag = (tag << 8) | b;
      } while (b & 0x80);
    }

    // ---- length ----
    if (pos >= len) return false;
    uint8_t first = (uint8_t)data[pos++];
    size_t valueLen = 0;
    if (first & 0x80) {
      int count = first & 0x7F;
      if (count == 0 || count > 3) return false;  // 不支持不定长
      for (int i = 0; i < count; i++) {
        if (pos >= len) return false;
        valueLen = (valueLen << 8) | (uint8_t)data[pos++];
      }
    } else {
      valueLen = first;
    }

    if (pos + valueLen > len) return false;
    Tlv node;
    node.tag = tag;
    node.value = data.substring(pos, pos + valueLen);
    out->push_back(node);
    pos += valueLen;
  }
  return true;
}

/** 在 TLV 列表里找指定 tag */
bool findTlv(const std::vector<Tlv>& list, uint32_t tag, Tlv* found) {
  for (const auto& t : list) {
    if (t.tag == tag) {
      if (found) *found = t;
      return true;
    }
  }
  return false;
}

/** 在一段原始数据里直接找 tag（不预先解析整层） */
bool findTlvInData(const String& data, uint32_t wantTag, Tlv* found) {
  std::vector<Tlv> list;
  if (!parseTlvs(data, &list)) return false;
  return findTlv(list, wantTag, found);
}

/** 构造 DER：wrap(tag, value)，tag 用 hex 字符串形式传入 */
String wrapTlv(const String& tagHex, const String& value) {
  uint8_t tagBuf[4];
  size_t tagLen = hexToBytes(tagHex, tagBuf, sizeof(tagBuf));

  String out;
  for (size_t i = 0; i < tagLen; i++) out += (char)tagBuf[i];

  size_t n = value.length();
  if (n < 128) {
    out += (char)(uint8_t)n;
  } else if (n < 256) {
    out += (char)0x81;
    out += (char)(uint8_t)n;
  } else {
    out += (char)0x82;
    out += (char)(uint8_t)((n >> 8) & 0xFF);
    out += (char)(uint8_t)(n & 0xFF);
  }
  out += value;
  return out;
}

// ---------------------------------------------------------------------------
// ICCID 工具
// ---------------------------------------------------------------------------

/** ICCID 十进制字符串 -> PDU 风格的交换 BCD（奇数位补 F） */
String iccidToBcd(const String& iccid) {
  String padded = iccid;
  if (padded.length() % 2) padded += 'F';
  String out;
  for (size_t i = 0; i + 1 < padded.length(); i += 2) {
    out += padded[i + 1];
    out += padded[i];
  }
  return out;
}

/** 交换 BCD -> ICCID 十进制字符串（去掉尾部 F） */
String bcdToIccid(const String& bcdHex) {
  String swapped;
  for (size_t i = 0; i + 1 < bcdHex.length(); i += 2) {
    swapped += bcdHex[i + 1];
    swapped += bcdHex[i];
  }
  while (swapped.length() && (swapped.endsWith("F") || swapped.endsWith("f"))) {
    swapped.remove(swapped.length() - 1);
  }
  return swapped;
}

/** 从原始 DER 里取 profile 名称类字段（可能带语言前缀） */
String decodeUtf8Field(const String& raw) {
  // SGP.22 的 profileName 结构：1 字节语言长度 + 语言码 + UTF-8 文本
  // 但很多卡直接给纯 UTF-8。这里优先尝试跳过语言前缀。
  if (raw.length() < 1) return String();

  uint8_t langLen = (uint8_t)raw[0];
  // 合理语言码长度 0-3，且后面剩余要够
  if (langLen <= 3 && raw.length() > (size_t)(1 + langLen)) {
    String tail = raw.substring(1 + langLen);
    // 检查是否像可打印 UTF-8
    bool printable = true;
    for (size_t i = 0; i < tail.length(); i++) {
      uint8_t c = (uint8_t)tail[i];
      if (c < 0x20 && c != '\n' && c != '\t') {
        printable = false;
        break;
      }
    }
    if (printable && tail.length() > 0) return tail;
  }

  // 退化为原样
  String out;
  for (size_t i = 0; i < raw.length(); i++) {
    uint8_t c = (uint8_t)raw[i];
    if (c >= 0x20) out += (char)c;
  }
  return out;
}

}  // namespace

// ============================================================================
// Euicc 实现
// ============================================================================

void Euicc::bindSlot(int slotIndex) {
  slot_ = slotIndex;
  probed_ = false;
  isEuicc_ = false;
  lastError_ = "";
}

void Euicc::setError(const String& msg) {
  lastError_ = msg;
  LOGW("[SLOT%d] eUICC: %s", slot_, msg.c_str());
}

// ---------------------------------------------------------------------------
// AT 指令（需要已持有 modem 独占锁）
// ---------------------------------------------------------------------------
bool Euicc::atCommand(const String& cmd, const String& expect, uint32_t timeoutMs,
                      String* response) {
  Modem* m = modemForSlot(slot_);
  if (m == nullptr) {
    setError("modem not available");
    return false;
  }
  return m->atRaw(cmd, expect, timeoutMs, response);
}

// ---------------------------------------------------------------------------
// 逻辑通道
// ---------------------------------------------------------------------------
bool Euicc::openChannel(const String& aid, int* channel) {
  String resp;
  String cmd = "AT+CCHO=\"" + aid + "\"";
  if (!atCommand(cmd, "OK", 15000, &resp)) {
    // 失败通常是"不是 eUICC 卡"，属于正常情况，不打错误日志
    return false;
  }

  // 从 +CCHO: <ch> 里取通道号；有的模组只回一个裸数字
  int ch = -1;
  int p = resp.indexOf("+CCHO:");
  if (p >= 0) {
    ch = resp.substring(p + 6).toInt();
  } else {
    // 逐行找纯数字行
    int from = 0;
    while (from < (int)resp.length()) {
      int nl = resp.indexOf('\n', from);
      String line = (nl < 0) ? resp.substring(from) : resp.substring(from, nl);
      line.trim();
      from = (nl < 0) ? resp.length() : nl + 1;
      if (line.length() && line.length() < 4) {
        bool allDigit = true;
        for (size_t i = 0; i < line.length(); i++) {
          if (!isDigit(line[i])) {
            allDigit = false;
            break;
          }
        }
        if (allDigit) {
          ch = line.toInt();
          break;
        }
      }
    }
  }

  if (ch <= 0) return false;
  *channel = ch;
  return true;
}

bool Euicc::closeChannel(int channel) {
  String resp;
  return atCommand("AT+CCHC=" + String(channel), "OK", 10000, &resp);
}

bool Euicc::transmit(int channel, const String& apduHex, String* respHex) {
  String resp;
  String cmd = "AT+CGLA=" + String(channel) + "," + String(apduHex.length()) +
               ",\"" + apduHex + "\"";
  if (!atCommand(cmd, "OK", 30000, &resp)) {
    setError("CGLA failed");
    return false;
  }

  // 诊断：把原始响应打出来（换行压成分隔符，截断 160 字符）
  {
    String raw = resp;
    raw.replace("\r", "");
    raw.replace("\n", "|");
    raw.trim();
    if (raw.length() > 160) raw = raw.substring(0, 160) + "...";
    LOGI("[SLOT%d] CGLA raw: %s", slot_, raw.c_str());
  }

  // +CGLA: <len>,"<response hex>"
  int p = resp.indexOf("+CGLA:");
  if (p < 0) {
    setError("no +CGLA in response");
    return false;
  }
  String rest = resp.substring(p + 6);

  int q1 = rest.indexOf('"');
  if (q1 < 0) {
    setError("bad +CGLA format (no quote)");
    return false;
  }
  int q2 = rest.indexOf('"', q1 + 1);
  if (q2 < 0) {
    // 有些模组最后一个引号可能被截断，退化为取到行尾
    q2 = rest.length();
    LOGW("[SLOT%d] CGLA: closing quote missing, use rest of line", slot_);
  }

  String hex = rest.substring(q1 + 1, q2);
  hex.trim();
  // 去掉可能的空白/换行残留
  hex.replace(" ", "");
  hex.replace("\n", "");
  hex.replace("|", "");

  if (!isHexString(hex)) {
    setError("non-hex APDU response");
    return false;
  }
  *respHex = hex;
  return true;
}

// ---------------------------------------------------------------------------
// ES10 请求-响应（带分片）
// 参考 lpac / HoshinoDesu 实现：
//   分片 APDU = [CLA=80|ch][INS=E2][P1: 91=最后一片, 11=中间][P2=序号][Lc][data]
//   响应 SW1=61 -> 用 C0 GET RESPONSE 继续取
// ---------------------------------------------------------------------------
bool Euicc::es10Exchange(int channel, const String& bodyHex, String* outHex) {
  uint8_t body[1024];
  size_t bodyLen = hexToBytes(bodyHex, body, sizeof(body));
  if (bodyLen == 0) {
    setError("empty ES10 body");
    return false;
  }

  String collected;  // 累积响应数据（不含 SW）

  for (size_t pos = 0; pos < bodyLen; pos += 255) {
    size_t chunk = (bodyLen - pos > 255) ? 255 : (bodyLen - pos);
    bool last = (pos + chunk >= bodyLen);

    uint8_t apdu[300];
    size_t apduLen = 0;
    apdu[apduLen++] = (uint8_t)(0x80 | channel);  // CLA：逻辑通道
    apdu[apduLen++] = 0xE2;                        // INS：TRANSMIT
    apdu[apduLen++] = last ? 0x91 : 0x11;          // P1
    apdu[apduLen++] = (uint8_t)((pos / 255) & 0xFF);  // P2：分片序号
    apdu[apduLen++] = (uint8_t)chunk;              // Lc
    memcpy(apdu + apduLen, body + pos, chunk);
    apduLen += chunk;

    String apduHex = bytesToHex(apdu, apduLen);

    // 发送并处理 61xx 后续
    for (int guard = 0; guard < 64; guard++) {
      String respHex;
      if (!transmit(channel, apduHex, &respHex)) return false;

      if (respHex.length() < 4) {
        setError("APDU response too short");
        return false;
      }

      String swHex = respHex.substring(respHex.length() - 4);
      String dataHex = respHex.substring(0, respHex.length() - 4);
      uint8_t sw1 = (uint8_t)((hexVal(swHex[0]) << 4) | hexVal(swHex[1]));
      uint8_t sw2 = (uint8_t)((hexVal(swHex[2]) << 4) | hexVal(swHex[3]));

      collected += dataHex;

      if (sw1 == 0x61) {
        // ISO 7816：SW1=0x61 表示「还有数据」，SW2 是剩余字节数。
        // 特例：SW2=0 按标准解释为 256 字节（不是 0！）。
        // GET RESPONSE 的 CLA 用通道号本身（不带 0x80），与 lpac 参考实现一致。
        uint8_t le = sw2;
        uint8_t getResp[5] = {(uint8_t)channel, 0xC0, 0x00, 0x00, le};
        apduHex = bytesToHex(getResp, sizeof(getResp));
        continue;
      }

      if (sw1 == 0x91) {
        // 91xx：分片完成状态，正常
        break;
      }

      if (swHex == "9000") {
        break;
      }

      setError("card status " + swHex);
      return false;
    }
  }

  *outHex = collected;
  return true;
}

// ---------------------------------------------------------------------------
// probe：检测是否为 eUICC 卡
// ---------------------------------------------------------------------------
bool Euicc::probe(bool force) {
  if (probed_ && !force) return isEuicc_;

  probed_ = true;
  isEuicc_ = false;

  Modem* m = modemForSlot(slot_);
  if (m == nullptr || !m->isReady()) {
    return false;
  }

  if (!m->lockExtension()) {
    return false;
  }

  int channel = -1;
  bool ok = openChannel(ISD_R_AID, &channel);
  if (ok) {
    closeChannel(channel);
  }

  m->unlockExtension();

  isEuicc_ = ok;
  if (ok) {
    LOGI("[SLOT%d] eUICC detected (ISD-R channel opened)", slot_);
  } else {
    LOGI("[SLOT%d] not an eUICC card (normal SIM)", slot_);
  }
  return isEuicc_;
}

// ---------------------------------------------------------------------------
// 读取 EID 与容量
// ---------------------------------------------------------------------------
bool Euicc::readInfo(EuiccInfo* out) {
  if (!available()) return false;

  Modem* m = modemForSlot(slot_);
  if (m == nullptr || !m->lockExtension()) return false;

  bool ok = false;
  int channel = -1;

  do {
    if (!openChannel(ISD_R_AID, &channel)) {
      setError("cannot open ISD-R channel");
      break;
    }

    EuiccInfo info;
    info.valid = false;

    // ---- EID：BF3E 03 5C 01 5A ----
    String respHex;
    if (es10Exchange(channel, "BF3E035C015A", &respHex)) {
      Tlv bf3e;
      if (findTlvInData(*reinterpret_cast<String*>(&respHex), 0xBF3E, &bf3e)) {
        Tlv eidTlv;
        if (findTlvInData(bf3e.value, 0x5A, &eidTlv)) {
          info.eid = bytesToHex((const uint8_t*)eidTlv.value.c_str(),
                                eidTlv.value.length());
          info.valid = true;
        }
      }
    }

    // ---- 内存信息：BF22 00 ----
    String memHex;
    if (es10Exchange(channel, "BF2200", &memHex)) {
      Tlv bf22;
      if (findTlvInData(memHex, 0xBF22, &bf22)) {
        Tlv list84;
        if (findTlvInData(bf22.value, 0x84, &list84)) {
          std::vector<Tlv> items;
          if (parseTlvs(list84.value, &items)) {
            for (const auto& it : items) {
              long v = 0;
              for (size_t i = 0; i < it.value.length(); i++) {
                v = (v << 8) | (uint8_t)it.value[i];
              }
              if (it.tag == 0x81) info.installedApps = (int)v;
              else if (it.tag == 0x82) info.freeNonVolatile = v;
              else if (it.tag == 0x83) info.freeVolatile = v;
            }
          }
        }
      }
    }

    info_ = info;
    if (out) *out = info;
    ok = info.valid;
  } while (false);

  if (channel > 0) closeChannel(channel);
  m->unlockExtension();
  return ok;
}

// ---------------------------------------------------------------------------
// 列出 profile
// ---------------------------------------------------------------------------
bool Euicc::listProfiles(std::vector<EuiccProfile>* out) {
  if (!available()) return false;

  Modem* m = modemForSlot(slot_);
  if (m == nullptr || !m->lockExtension()) return false;

  bool ok = false;
  int channel = -1;
  std::vector<EuiccProfile> result;

  do {
    if (!openChannel(ISD_R_AID, &channel)) {
      setError("cannot open ISD-R channel");
      break;
    }

    // GetProfilesInfo：BF2D 08 5C 06 5A 9F70 90 91 92
    String respHex;
    if (!es10Exchange(channel, "BF2D085C065A9F70909192", &respHex)) {
      setError("GetProfilesInfo failed");
      break;
    }

    String raw;
    for (size_t i = 0; i + 1 < respHex.length(); i += 2) {
      raw += (char)(uint8_t)((hexVal(respHex[i]) << 4) | hexVal(respHex[i + 1]));
    }

    Tlv bf2d;
    if (!findTlvInData(raw, 0xBF2D, &bf2d)) {
      setError("no BF2D in profile list");
      break;
    }

    Tlv a0;
    if (!findTlvInData(bf2d.value, 0xA0, &a0)) {
      // 空列表（没有 profile）
      profiles_.clear();
      if (out) out->clear();
      lastRefreshMs_ = millis();
      ok = true;
      break;
    }

    std::vector<Tlv> profileTlvs;
    if (!parseTlvs(a0.value, &profileTlvs)) {
      setError("profile list TLV broken");
      break;
    }

    for (const auto& node : profileTlvs) {
      if (node.tag != 0xE3) continue;

      EuiccProfile p;
      std::vector<Tlv> fields;
      if (!parseTlvs(node.value, &fields)) {
        p.malformed = true;
        result.push_back(p);
        continue;
      }

      for (const auto& f : fields) {
        if (f.tag == 0x5A) {
          p.iccid = bcdToIccid(bytesToHex((const uint8_t*)f.value.c_str(),
                                          f.value.length()));
        } else if (f.tag == 0x9F70) {
          p.state = f.value.length() ? (uint8_t)f.value[0] : 0;
        } else if (f.tag == 0x90) {
          p.nickname = decodeUtf8Field(f.value);
        } else if (f.tag == 0x91) {
          p.provider = decodeUtf8Field(f.value);
        } else if (f.tag == 0x92) {
          p.name = decodeUtf8Field(f.value);
        }
      }
      result.push_back(p);
    }

    profiles_ = result;
    lastRefreshMs_ = millis();
    if (out) *out = result;
    ok = true;
  } while (false);

  if (channel > 0) closeChannel(channel);
  m->unlockExtension();
  return ok;
}

// ---------------------------------------------------------------------------
// 启用 / 禁用 / 删除 / 改名
// ---------------------------------------------------------------------------
bool Euicc::enableProfile(const String& iccid) {
  if (!available()) return false;
  if (iccid.length() < 19) {
    setError("invalid ICCID");
    return false;
  }

  Modem* m = modemForSlot(slot_);
  if (m == nullptr || !m->lockExtension()) return false;

  bool ok = false;
  int channel = -1;

  do {
    if (!openChannel(ISD_R_AID, &channel)) {
      setError("cannot open ISD-R channel");
      break;
    }

    String bcd = iccidToBcd(iccid);
    // ICCID 的 BCD 转成原始字节（SGP.22 的 5A 字段要的是二进制）
    String iccidBytes;
    for (size_t i = 0; i + 1 < bcd.length(); i += 2) {
      iccidBytes += (char)(uint8_t)((hexVal(bcd[i]) << 4) | hexVal(bcd[i + 1]));
    }

    // BF31 { A0 { 5A iccid } 81 01 FF }
    String body = wrapTlv("A0", wrapTlv("5A", iccidBytes)) + wrapTlv("81", "\xFF");
    String reqHex = wrapTlv("BF31", body);
    String outHex;
    if (!es10Exchange(channel, bytesToHex((const uint8_t*)reqHex.c_str(),
                                          reqHex.length()),
                      &outHex)) {
      setError("enableProfile APDU failed");
      break;
    }

    String raw;
    for (size_t i = 0; i + 1 < outHex.length(); i += 2) {
      raw += (char)(uint8_t)((hexVal(outHex[i]) << 4) | hexVal(outHex[i + 1]));
    }
    Tlv bf31;
    if (!findTlvInData(raw, 0xBF31, &bf31)) {
      setError("no BF31 result");
      break;
    }
    Tlv code;
    if (findTlvInData(bf31.value, 0x80, &code) && code.value.length()) {
      uint8_t c = (uint8_t)code.value[0];
      if (c != 0) {
        setError("enable result code " + String(c));
        break;
      }
    }
    ok = true;
  } while (false);

  if (channel > 0) closeChannel(channel);
  m->unlockExtension();

  if (ok) {
    LOGI("[SLOT%d] eUICC profile enabled: %s", slot_, iccid.c_str());
    // 切换 profile 会触发 REFRESH，模组需要重启才能用新卡
    m->restart();
  }
  return ok;
}

bool Euicc::disableProfile(const String& iccid) {
  if (!available()) return false;
  if (iccid.length() < 19) {
    setError("invalid ICCID");
    return false;
  }

  Modem* m = modemForSlot(slot_);
  if (m == nullptr || !m->lockExtension()) return false;

  bool ok = false;
  int channel = -1;

  do {
    if (!openChannel(ISD_R_AID, &channel)) {
      setError("cannot open ISD-R channel");
      break;
    }

    String bcd = iccidToBcd(iccid);
    String iccidBytes;
    for (size_t i = 0; i + 1 < bcd.length(); i += 2) {
      iccidBytes += (char)(uint8_t)((hexVal(bcd[i]) << 4) | hexVal(bcd[i + 1]));
    }

    String body = wrapTlv("A0", wrapTlv("5A", iccidBytes)) + wrapTlv("81", "\xFF");
    String reqHex = wrapTlv("BF32", body);
    String outHex;
    if (!es10Exchange(channel, bytesToHex((const uint8_t*)reqHex.c_str(),
                                          reqHex.length()),
                      &outHex)) {
      setError("disableProfile APDU failed");
      break;
    }

    String raw;
    for (size_t i = 0; i + 1 < outHex.length(); i += 2) {
      raw += (char)(uint8_t)((hexVal(outHex[i]) << 4) | hexVal(outHex[i + 1]));
    }
    Tlv bf32;
    if (!findTlvInData(raw, 0xBF32, &bf32)) {
      setError("no BF32 result");
      break;
    }
    Tlv code;
    if (findTlvInData(bf32.value, 0x80, &code) && code.value.length()) {
      uint8_t c = (uint8_t)code.value[0];
      if (c != 0) {
        setError("disable result code " + String(c));
        break;
      }
    }
    ok = true;
  } while (false);

  if (channel > 0) closeChannel(channel);
  m->unlockExtension();

  if (ok) {
    LOGI("[SLOT%d] eUICC profile disabled: %s", slot_, iccid.c_str());
    m->restart();
  }
  return ok;
}

bool Euicc::deleteProfile(const String& iccid) {
  if (!available()) return false;
  if (iccid.length() < 19) {
    setError("invalid ICCID");
    return false;
  }

  Modem* m = modemForSlot(slot_);
  if (m == nullptr || !m->lockExtension()) return false;

  bool ok = false;
  int channel = -1;

  do {
    if (!openChannel(ISD_R_AID, &channel)) {
      setError("cannot open ISD-R channel");
      break;
    }

    String bcd = iccidToBcd(iccid);
    String iccidBytes;
    for (size_t i = 0; i + 1 < bcd.length(); i += 2) {
      iccidBytes += (char)(uint8_t)((hexVal(bcd[i]) << 4) | hexVal(bcd[i + 1]));
    }

    // BF33 { 5A iccid }  —— 删除不需要 81 字段
    String body = wrapTlv("5A", iccidBytes);
    String reqHex = wrapTlv("BF33", body);
    String outHex;
    if (!es10Exchange(channel, bytesToHex((const uint8_t*)reqHex.c_str(),
                                          reqHex.length()),
                      &outHex)) {
      setError("deleteProfile APDU failed");
      break;
    }

    String raw;
    for (size_t i = 0; i + 1 < outHex.length(); i += 2) {
      raw += (char)(uint8_t)((hexVal(outHex[i]) << 4) | hexVal(outHex[i + 1]));
    }
    Tlv bf33;
    if (!findTlvInData(raw, 0xBF33, &bf33)) {
      setError("no BF33 result");
      break;
    }
    Tlv code;
    if (findTlvInData(bf33.value, 0x80, &code) && code.value.length()) {
      uint8_t c = (uint8_t)code.value[0];
      if (c != 0) {
        setError("delete result code " + String(c));
        break;
      }
    }
    ok = true;
  } while (false);

  if (channel > 0) closeChannel(channel);
  m->unlockExtension();

  if (ok) {
    LOGI("[SLOT%d] eUICC profile deleted: %s", slot_, iccid.c_str());
  }
  return ok;
}

bool Euicc::setNickname(const String& iccid, const String& nickname) {
  if (!available()) return false;
  if (iccid.length() < 19) {
    setError("invalid ICCID");
    return false;
  }
  if (nickname.length() > 64) {
    setError("nickname too long");
    return false;
  }

  Modem* m = modemForSlot(slot_);
  if (m == nullptr || !m->lockExtension()) return false;

  bool ok = false;
  int channel = -1;

  do {
    if (!openChannel(ISD_R_AID, &channel)) {
      setError("cannot open ISD-R channel");
      break;
    }

    String bcd = iccidToBcd(iccid);
    String iccidBytes;
    for (size_t i = 0; i + 1 < bcd.length(); i += 2) {
      iccidBytes += (char)(uint8_t)((hexVal(bcd[i]) << 4) | hexVal(bcd[i + 1]));
    }

    // BF29 { 5A iccid, 90 nickname }
    String body = wrapTlv("5A", iccidBytes) + wrapTlv("90", nickname);
    String reqHex = wrapTlv("BF29", body);
    String outHex;
    if (!es10Exchange(channel, bytesToHex((const uint8_t*)reqHex.c_str(),
                                          reqHex.length()),
                      &outHex)) {
      setError("setNickname APDU failed");
      break;
    }

    String raw;
    for (size_t i = 0; i + 1 < outHex.length(); i += 2) {
      raw += (char)(uint8_t)((hexVal(outHex[i]) << 4) | hexVal(outHex[i + 1]));
    }
    Tlv bf29;
    if (!findTlvInData(raw, 0xBF29, &bf29)) {
      setError("no BF29 result");
      break;
    }
    Tlv code;
    if (findTlvInData(bf29.value, 0x80, &code) && code.value.length()) {
      uint8_t c = (uint8_t)code.value[0];
      if (c != 0) {
        setError("nickname result code " + String(c));
        break;
      }
    }
    ok = true;
  } while (false);

  if (channel > 0) closeChannel(channel);
  m->unlockExtension();
  return ok;
}

// ---------------------------------------------------------------------------
bool Euicc::refresh() {
  if (!available()) return false;
  bool a = readInfo(nullptr);
  bool b = listProfiles(nullptr);
  lastRefreshMs_ = millis();
  return a || b;
}
