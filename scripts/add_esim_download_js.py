# -*- coding: utf-8 -*-
"""给 esim.html 加写卡（扫码 + 激活码）逻辑"""
from pathlib import Path

P = Path(r"D:\SMSATBOX\server\app\static\esim.html")
c = P.read_text(encoding="utf-8")

if "setupDownload" in c:
    print("已存在，跳过")
    raise SystemExit(0)

JS = r"""  // ---------- 写卡：扫码 + 提交 ----------
  function logDownload(text) {
    const el = $("downloadLog");
    el.style.display = "block";
    el.textContent += text + "\n";
    el.scrollTop = el.scrollHeight;
  }

  function setDownloadState(text, err) {
    const el = $("downloadState");
    el.textContent = text;
    el.style.color = err ? "var(--danger)" : "var(--sub)";
  }

  // 解析 LPA 激活码：LPA:1$smdp.example.com$MATCHING_ID
  function parseLpa(code) {
    const s = (code || "").trim();
    const m = s.match(/^LPA:?\d*\$([^\$]+)\$(.+)$/i);
    if (!m) return null;
    return { smdp: m[1].trim(), matchingId: m[2].trim() };
  }

  let qrStream = null;
  let qrTimer = null;

  function stopQr() {
    if (qrTimer) { clearInterval(qrTimer); qrTimer = null; }
    if (qrStream) {
      qrStream.getTracks().forEach((t) => t.stop());
      qrStream = null;
    }
    const wrap = $("qrPreviewWrap");
    if (wrap) wrap.style.display = "none";
  }

  async function startQr() {
    // 优先用浏览器原生 BarcodeDetector（Chrome/Edge 支持）
    if (!("BarcodeDetector" in window)) {
      note("当前浏览器不支持扫码，请手动输入激活码", true);
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment" },
      });
      qrStream = stream;
      const video = $("qrVideo");
      video.srcObject = stream;
      $("qrPreviewWrap").style.display = "block";

      const detector = new window.BarcodeDetector({ formats: ["qr_code"] });
      qrTimer = setInterval(async () => {
        try {
          const codes = await detector.detect(video);
          if (codes && codes.length) {
            const raw = codes[0].rawValue || "";
            if (/^LPA:/i.test(raw)) {
              $("activationCode").value = raw;
              stopQr();
              setDownloadState("已识别激活码，点「开始下卡」");
              note("二维码识别成功");
            }
          }
        } catch (e) { /* 单帧识别失败忽略 */ }
      }, 400);
    } catch (e) {
      note("无法打开摄像头：" + e.message, true);
    }
  }

  async function submitDownload() {
    const raw = $("activationCode").value.trim();
    if (!raw) return note("请先填写或扫描激活码", true);
    const parsed = parseLpa(raw);
    if (!parsed) {
      return note("激活码格式不对，应为 LPA:1$服务器$匹配ID", true);
    }
    if (!currentEuicc) return note("当前卡槽没有 eUICC 卡", true);

    $("downloadBtn").disabled = true;
    setDownloadState("正在提交下卡任务…");
    $("downloadLog").textContent = "";
    logDownload("SM-DP+ : " + parsed.smdp);
    logDownload("匹配ID : " + parsed.matchingId);

    try {
      const r = await api("/esim/download", {
        method: "POST",
        body: {
          device_id: currentEuicc.device_id,
          slot_index: currentEuicc.slot_index,
          activation_code: raw,
          confirmation_code: $("confirmationCode").value.trim(),
        },
      });
      logDownload("任务已创建 #" + (r.task_id || "?"));
      setDownloadState(r.message || "已排队，等待设备执行");
      if (r.supported === false) {
        setDownloadState("服务端写卡引擎未就绪（RSP 引擎待接入）", true);
      }
    } catch (e) {
      setDownloadState(e.message, true);
      logDownload("失败：" + e.message);
    } finally {
      $("downloadBtn").disabled = false;
    }
  }

  function setupDownload() {
    const scanBtn = $("scanQrBtn");
    if (scanBtn) scanBtn.addEventListener("click", startQr);
    const stopBtn = $("qrStopBtn");
    if (stopBtn) stopBtn.addEventListener("click", stopQr);
    const dlBtn = $("downloadBtn");
    if (dlBtn) dlBtn.addEventListener("click", submitDownload);
  }

  // ---------- 轮询 ----------"""

ANCHOR = "  // ---------- 轮询 ----------"
if ANCHOR not in c:
    print("✗ 未找到锚点")
    raise SystemExit(1)

c = c.replace(ANCHOR, JS, 1)
c = c.replace(
    "  loadAll();\n  setInterval(loadAll, 8000);",
    "  setupDownload();\n  loadAll();\n  setInterval(loadAll, 8000);",
)
P.write_bytes(c.encode("utf-8"))
print("✓ esim.html 已加扫码与下卡逻辑")
