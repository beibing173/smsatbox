# -*- coding: utf-8 -*-
"""实现完整的切卡方案

实机验证结论（2026-11-08）：
  1. EnableProfile 用 refreshFlag=TRUE 会返回 commandError(7)
     —— ML307A 不处理 eUICC 发来的 STK REFRESH 主动命令
  2. EnableProfile 用 refreshFlag=FALSE 时，卡能成功切换，
     但模组仍持有旧卡的会话状态，必须 CFUN 重启协议栈才会重读卡
  3. 恢复动作：AT+CFUN=0 -> 等 8s -> AT+CFUN=1 -> 等 10s
     之后 CPIN 恢复 READY，IMSI 变成新 profile 的号码

所以切卡流程改为：
  ES10 EnableProfile(refreshFlag=FALSE)
    -> 关闭逻辑通道
    -> AT+CFUN=0 / 等待 / AT+CFUN=1
    -> 重新读取 ICCID 校验是否切成功
"""
from pathlib import Path

ROOT = Path(r"D:\SMSATBOX")
done = []


def patch(rel, old, new, desc):
    p = ROOT / rel
    if not p.exists():
        print(f"  ✗ {rel} 不存在")
        return
    c = p.read_text(encoding="utf-8")
    if old not in c:
        if new in c:
            print(f"  = {desc}（已是目标）")
        else:
            print(f"  ✗ {desc}：未找到锚点")
        return
    c = c.replace(old, new, 1)
    p.write_bytes(c.encode("utf-8"))
    done.append(desc)
    print(f"  ✓ {desc}")


# ---------------------------------------------------------------------------
# 1) modem.h 增加 restartSimStack() —— CFUN 循环
# ---------------------------------------------------------------------------
patch(
    "esp32/src/modem.h",
    "  /// 重新启动模组（硬复位）\n  void restart();",
    """  /// 重新启动模组（硬复位）
  void restart();

  /// 重启 SIM 协议栈：AT+CFUN=0 -> 等 -> AT+CFUN=1 -> 等
  /// 用于 eUICC 切换 profile 后让模组重新读卡（实测有效）
  bool restartSimStack();""",
    "modem.h 声明 restartSimStack",
)

# ---------------------------------------------------------------------------
# 2) modem.cpp 实现 restartSimStack()
# ---------------------------------------------------------------------------
patch(
    "esp32/src/modem.cpp",
    "void Modem::restart() {",
    """bool Modem::restartSimStack() {
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
}

void Modem::restart() {""",
    "modem.cpp 实现 restartSimStack",
)

# ---------------------------------------------------------------------------
# 3) euicc.cpp：enable/disable 后调用 CFUN 循环（替换原来的 m->restart()）
# ---------------------------------------------------------------------------
p = ROOT / "esp32/src/euicc.cpp"
c = p.read_text(encoding="utf-8")

old_enable = """  if (ok) {
    LOGI("[SLOT%d] eUICC profile enabled: %s", slot_, iccid.c_str());
    // 切换 profile 会触发 REFRESH，模组需要重启才能用新卡
    m->restart();
  }
  return ok;"""

new_enable = """  // 无论 ES10 的响应如何都要重启 SIM 协议栈：
  //   refreshFlag=FALSE 时卡会切成功但可能不回完整响应，
  //   模组也必须 CFUN 重启才会重新读卡（实测：不重启则 +CME ERROR: 10）。
  LOGI("[SLOT%d] eUICC enable done ok=%d iccid=%s, restarting SIM stack",
       slot_, (int)ok, iccid.c_str());
  m->restartSimStack();
  return ok;"""

if old_enable in c:
    c = c.replace(old_enable, new_enable, 1)
    print("  ✓ euicc.cpp enable 后改用 restartSimStack")
    done.append("enable 后 CFUN 重启")
else:
    print("  · enable 段格式不同，尝试宽松替换")
    import re

    m = re.search(
        r"  if \(ok\) \{\s*\n\s*LOGI\(\"\[SLOT%d\] eUICC profile enabled.*?\n\s*m->restart\(\);\s*\n\s*\}\s*\n\s*return ok;",
        c,
        re.S,
    )
    if m:
        c = (
            c[: m.start()]
            + """  LOGI("[SLOT%d] eUICC enable done ok=%d iccid=%s, restarting SIM stack",
       slot_, (int)ok, iccid.c_str());
  m->restartSimStack();
  return ok;"""
            + c[m.end() :]
        )
        print("  ✓ 宽松替换成功")
        done.append("enable 后 CFUN 重启（宽松）")
    else:
        print("  ✗ 仍未匹配")

old_disable = """  if (ok) {
    LOGI("[SLOT%d] eUICC profile disabled: %s", slot_, iccid.c_str());
    m->restart();
  }
  return ok;"""

new_disable = """  LOGI("[SLOT%d] eUICC disable done ok=%d iccid=%s, restarting SIM stack",
       slot_, (int)ok, iccid.c_str());
  m->restartSimStack();
  return ok;"""

if old_disable in c:
    c = c.replace(old_disable, new_disable, 1)
    print("  ✓ euicc.cpp disable 后改用 restartSimStack")
    done.append("disable 后 CFUN 重启")
else:
    print("  · disable 段未匹配（可接受）")

p.write_bytes(c.encode("utf-8"))

print()
print(f"共完成 {len(done)} 项")
for d in done:
    print("  -", d)
