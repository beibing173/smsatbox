# -*- coding: utf-8 -*-
"""修复 euicc.cpp：补回被误删的 disableProfile 函数头"""
from pathlib import Path

P = Path(r"D:\SMSATBOX\esp32\src\euicc.cpp")
c = P.read_text(encoding="utf-8")

# 锚点：refresh() 结束后紧跟孤立的 "  do {"
ANCHOR = """bool Euicc::refresh() {
  if (!available()) return false;
  bool a = readInfo(nullptr);
  bool b = listProfiles(nullptr);
  lastRefreshMs_ = millis();
  return a || b;
}

  do {"""

REPAIR = """bool Euicc::refresh() {
  if (!available()) return false;
  bool a = readInfo(nullptr);
  bool b = listProfiles(nullptr);
  lastRefreshMs_ = millis();
  return a || b;
}

// ---------------------------------------------------------------------------
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

  do {"""

if ANCHOR in c:
    c = c.replace(ANCHOR, REPAIR, 1)
    P.write_bytes(c.encode("utf-8"))
    print("✓ 已补回 disableProfile 函数头")
else:
    print("✗ 未找到锚点，输出上下文：")
    i = c.find("bool Euicc::refresh()")
    print(repr(c[i : i + 500]))
