# -*- coding: utf-8 -*-
"""修正 modem.cpp 里 restartSimStack 的成员名与 atRaw 签名"""
from pathlib import Path

P = Path(r"D:\SMSATBOX\esp32\src\modem.cpp")
c = P.read_text(encoding="utf-8")

OLD = """bool Modem::restartSimStack() {
  if (!isPresent()) return false;

  LOGI("[SLOT%d] restarting SIM stack (CFUN cycle)", slot_);

  // 关协议栈：让模组放开 SIM
  if (!lockExtension()) {
    LOGW("[SLOT%d] restartSimStack: cannot lock", slot_);
    return false;
  }
  atRaw("AT+CFUN=0", 8000);
  unlockExtension();

  delay(8000);

  // 开协议栈：模组重新初始化 USIM
  if (!lockExtension()) return false;
  atRaw("AT+CFUN=1", 15000);
  unlockExtension();

  delay(10000);
  LOGI("[SLOT%d] SIM stack restarted", slot_);
  return true;
}"""

NEW = """bool Modem::restartSimStack() {
  if (!present_) return false;

  LOGI("[SLOT%d] restarting SIM stack (CFUN cycle)", slotIndex_);

  // 关协议栈：让模组放开 SIM
  atRaw("AT+CFUN=0", "OK", 8000);
  delay(8000);

  // 开协议栈：模组重新初始化 USIM
  atRaw("AT+CFUN=1", "OK", 15000);

  delay(10000);
  LOGI("[SLOT%d] SIM stack restarted", slotIndex_);
  return true;
}"""

if OLD in c:
    c = c.replace(OLD, NEW, 1)
    P.write_bytes(c.encode("utf-8"))
    print("✓ 已修正 restartSimStack")
else:
    print("✗ 未匹配")
