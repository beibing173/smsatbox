// ============================================================================
//  SMSATBOX · OTA 双分区升级实现
// ============================================================================
#include "ota.h"

#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <Update.h>
#include <WiFiClientSecure.h>

#include "cloud.h"
#include "config_store.h"
#include "logger.h"
#include "network.h"

namespace ota {

namespace {

/** 把相对路径拼成完整 URL */
String resolveUrl(const String& raw) {
  if (raw.startsWith("http://") || raw.startsWith("https://")) {
    return raw;
  }
  const DeviceConfig& c = cfg::get();
  String base = c.serverUrl;
  if (base.isEmpty()) return String();
  if (raw.startsWith("/")) return base + raw;
  return base + "/" + raw;
}

// MD5 分块累加所需的上下文
struct Md5Ctx {
  uint32_t a, b, c, d;
  uint64_t len;
  uint8_t buf[64];
  size_t bufLen;
};

inline uint32_t rotl(uint32_t x, int n) { return (x << n) | (x >> (32 - n)); }

void md5Init(Md5Ctx* ctx) {
  ctx->a = 0x67452301;
  ctx->b = 0xefcdab89;
  ctx->c = 0x98badcfe;
  ctx->d = 0x10325476;
  ctx->len = 0;
  ctx->bufLen = 0;
}

void md5Block(Md5Ctx* ctx, const uint8_t* p) {
  static const uint32_t K[64] = {
      0xd76aa478, 0xe8c7b756, 0x242070db, 0xc1bdceee, 0xf57c0faf, 0x4787c62a,
      0xa8304613, 0xfd469501, 0x698098d8, 0x8b44f7af, 0xffff5bb1, 0x895cd7be,
      0x6b901122, 0xfd987193, 0xa679438e, 0x49b40821, 0xf61e2562, 0xc040b340,
      0x265e5a51, 0xe9b6c7aa, 0xd62f105d, 0x02441453, 0xd8a1e681, 0xe7d3fbc8,
      0x21e1cde6, 0xc33707d6, 0xf4d50d87, 0x455a14ed, 0xa9e3e905, 0xfcefa3f8,
      0x676f02d9, 0x8d2a4c8a, 0xfffa3942, 0x8771f681, 0x6d9d6122, 0xfde5380c,
      0xa4beea44, 0x4bdecfa9, 0xf6bb4b60, 0xbebfbc70, 0x289b7ec6, 0xeaa127fa,
      0xd4ef3085, 0x04881d05, 0xd9d4d039, 0xe6db99e5, 0x1fa27cf8, 0xc4ac5665,
      0xf4292244, 0x432aff97, 0xab9423a7, 0xfc93a039, 0x655b59c3, 0x8f0ccc92,
      0xffeff47d, 0x85845dd1, 0x6fa87e4f, 0xfe2ce6e0, 0xa3014314, 0x4e0811a1,
      0xf7537e82, 0xbd3af235, 0x2ad7d2bb, 0xeb86d391};
  static const uint8_t S[64] = {7, 12, 17, 22, 7, 12, 17, 22, 7, 12, 17, 22, 7,
                                12, 17, 22, 5, 9,  14, 20, 5, 9,  14, 20, 5,  9,
                                14, 20, 5, 9,  14, 20, 4, 11, 16, 23, 4, 11, 16,
                                23, 4, 11, 16, 23, 4, 11, 16, 23, 6, 10, 15, 21,
                                6, 10, 15, 21, 6, 10, 15, 21, 6, 10, 15, 21};

  uint32_t M[16];
  for (int i = 0; i < 16; i++) {
    M[i] = (uint32_t)p[i * 4] | ((uint32_t)p[i * 4 + 1] << 8) |
           ((uint32_t)p[i * 4 + 2] << 16) | ((uint32_t)p[i * 4 + 3] << 24);
  }
  uint32_t a = ctx->a, b = ctx->b, c = ctx->c, d = ctx->d;
  for (int i = 0; i < 64; i++) {
    uint32_t f;
    int g;
    if (i < 16) {
      f = (b & c) | (~b & d);
      g = i;
    } else if (i < 32) {
      f = (d & b) | (~d & c);
      g = (5 * i + 1) % 16;
    } else if (i < 48) {
      f = b ^ c ^ d;
      g = (3 * i + 5) % 16;
    } else {
      f = c ^ (b | ~d);
      g = (7 * i) % 16;
    }
    uint32_t tmp = d;
    d = c;
    c = b;
    b = b + rotl(a + f + K[i] + M[g], S[i]);
    a = tmp;
  }
  ctx->a += a;
  ctx->b += b;
  ctx->c += c;
  ctx->d += d;
}

void md5Update(Md5Ctx* ctx, const uint8_t* data, size_t len) {
  ctx->len += len;
  while (len > 0) {
    size_t take = 64 - ctx->bufLen;
    if (take > len) take = len;
    memcpy(ctx->buf + ctx->bufLen, data, take);
    ctx->bufLen += take;
    data += take;
    len -= take;
    if (ctx->bufLen == 64) {
      md5Block(ctx, ctx->buf);
      ctx->bufLen = 0;
    }
  }
}

String md5Final(Md5Ctx* ctx) {
  uint64_t bits = ctx->len * 8ULL;
  uint8_t pad = 0x80;
  md5Update(ctx, &pad, 1);
  uint8_t zero = 0;
  while (ctx->bufLen != 56) {
    md5Update(ctx, &zero, 1);
  }
  uint8_t lenBytes[8];
  for (int i = 0; i < 8; i++) {
    lenBytes[i] = (uint8_t)((bits >> (8 * i)) & 0xFF);
  }
  md5Update(ctx, lenBytes, 8);

  char out[33];
  const uint32_t vals[4] = {ctx->a, ctx->b, ctx->c, ctx->d};
  for (int i = 0; i < 4; i++) {
    for (int j = 0; j < 4; j++) {
      snprintf(out + i * 8 + j * 2, 3, "%02x",
               (unsigned)((vals[i] >> (8 * j)) & 0xFF));
    }
  }
  out[32] = '\0';
  return String(out);
}

}  // namespace

String runningVersion() { return String(SMSATBOX_VERSION); }

bool performUpdate(const String& rawUrl, const String& expectedMd5,
                   const String& version, String* error) {
  if (!net::online()) {
    if (error) *error = "网络不可用";
    return false;
  }

  String url = resolveUrl(rawUrl);
  if (url.isEmpty()) {
    if (error) *error = "固件地址无效";
    return false;
  }

  LOGI("OTA start: v%s <- %s", version.c_str(), url.c_str());

  HTTPClient http;
  http.setTimeout(60000);
  http.setConnectTimeout(10000);

  bool isHttps = url.startsWith("https://");
  WiFiClientSecure secureClient;
  WiFiClient plainClient;
  if (isHttps) {
    secureClient.setInsecure();
    if (!http.begin(secureClient, url)) {
      if (error) *error = "连接失败";
      return false;
    }
  } else {
    if (!http.begin(plainClient, url)) {
      if (error) *error = "连接失败";
      return false;
    }
  }

  http.addHeader("X-Device-Token", cfg::get().deviceToken);
  http.addHeader("X-Client-Version", SMSATBOX_VERSION);

  int code = http.GET();
  if (code != 200) {
    http.end();
    if (error) *error = String("下载失败 HTTP ") + code;
    LOGE("OTA download failed code=%d", code);
    return false;
  }

  int totalSize = http.getSize();
  if (totalSize <= 0) {
    LOGW("OTA size unknown, continue");
  }

  // 检查备用分区空间
  uint32_t maxSketch = ESP.getFreeSketchSpace();
  if (totalSize > 0 && (uint32_t)totalSize > maxSketch) {
    http.end();
    if (error) *error = "分区空间不足";
    LOGE("OTA no space: need %d have %u", totalSize, maxSketch);
    return false;
  }

  if (!Update.begin(totalSize > 0 ? totalSize : UPDATE_SIZE_UNKNOWN)) {
    http.end();
    if (error) *error = "无法开始写入";
    LOGE("Update.begin failed: %s", Update.errorString());
    return false;
  }

  Md5Ctx md5ctx;
  md5Init(&md5ctx);

  WiFiClient* stream = http.getStreamPtr();
  uint8_t buf[1024];
  int written = 0;
  uint32_t lastProgress = 0;

  while (http.connected() && (totalSize <= 0 || written < totalSize)) {
    size_t avail = stream->available();
    if (avail == 0) {
      delay(5);
      continue;
    }
    size_t toRead = avail > sizeof(buf) ? sizeof(buf) : avail;
    int n = stream->readBytes(buf, toRead);
    if (n <= 0) break;

    if (Update.write(buf, n) != (size_t)n) {
      Update.abort();
      http.end();
      if (error) *error = "写入失败";
      LOGE("Update.write failed: %s", Update.errorString());
      return false;
    }
    md5Update(&md5ctx, buf, n);
    written += n;

    // 每 25% 打印一次进度
    if (totalSize > 0) {
      uint32_t pct = (uint32_t)((uint64_t)written * 100 / totalSize);
      if (pct >= lastProgress + 25) {
        lastProgress = pct;
        LOGI("OTA progress %u%% (%d/%d)", pct, written, totalSize);
      }
    }
  }
  http.end();

  if (totalSize > 0 && written != totalSize) {
    Update.abort();
    if (error) *error = String("下载不完整 ") + written + "/" + totalSize;
    LOGE("OTA incomplete %d/%d", written, totalSize);
    return false;
  }

  // ---- MD5 校验（核心安全闸门） ----
  String actual = md5Final(&md5ctx);
  String expected = expectedMd5;
  expected.toLowerCase();
  LOGI("OTA md5 actual=%s expect=%s", actual.c_str(), expected.c_str());
  if (expected.length() == 32 && actual != expected) {
    Update.abort();
    if (error) *error = "MD5 校验失败";
    LOGE("OTA md5 mismatch, aborted");
    return false;
  }

  if (!Update.end(true)) {
    if (error) *error = String("提交失败: ") + Update.errorString();
    LOGE("Update.end failed: %s", Update.errorString());
    return false;
  }

  LOGI("OTA written %d bytes, rebooting", written);
  return true;
}

}  // namespace ota
