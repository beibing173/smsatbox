// ============================================================================
//  SMSATBOX · 内置网页模板（PROGMEM 存储，节省 RAM）
//  ---------------------------------------------------------------------------
//  两套页面：
//    1) 配网 Captive Portal —— 仅三项输入
//    2) 局域网调试页 —— 设备状态 + 日志（只读）
//  主题：黑白双色可切换，与 Web 管理端保持同一套设计语言
// ============================================================================
#pragma once

#include <Arduino.h>

// ---------------------------------------------------------------------------
// 公共样式 + 主题切换脚本（配网页与调试页共用）
// ---------------------------------------------------------------------------
static const char PAGE_COMMON_HEAD[] PROGMEM = R"HTML(<!DOCTYPE html>
<html lang="zh-CN" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#0b111d">
<title>SMSATBOX 设备</title>
<style>
:root{--bg0:#070b14;--bg1:#0b111d;--surf:#0d1626;--surf2:#131e2e;--line:#1e2b40;
--line-soft:#172235;--t0:#e8f0ff;--t1:#9fb0c9;--t2:#64748b;--brand:#22d3ee;
--brand2:#6366f1;--ok:#34d399;--warn:#fbbf24;--err:#f87171;--okbg:#08221a;
--errbg:#240f12;--glow:#22d3ee44}
[data-theme="light"]{--bg0:#f4f7fb;--bg1:#fff;--surf:#fff;--surf2:#f4f7fb;
--line:#d8e0ec;--line-soft:#e7edf5;--t0:#10192b;--t1:#4a5a72;--t2:#8394a8;
--brand:#0891b2;--brand2:#4f46e5;--ok:#10b981;--warn:#b45309;--err:#dc2626;
--okbg:#e8f8f1;--errbg:#fdeeee;--glow:#0891b233}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;background:var(--bg0);color:var(--t0);
font:14px/1.6 "Segoe UI","PingFang SC","Microsoft YaHei",system-ui,sans-serif;
display:flex;align-items:center;justify-content:center;padding:20px 14px;
transition:background .22s,color .22s}
.card{width:100%;max-width:440px;background:linear-gradient(180deg,var(--surf),var(--bg1));
border:1px solid var(--line);border-radius:18px;padding:26px 22px;
box-shadow:0 10px 30px -14px #0008;position:relative;overflow:hidden}
.card::before{content:"";position:absolute;inset:0 0 auto;height:2px;
background:linear-gradient(90deg,transparent,var(--brand),var(--brand2),transparent)}
.brand{display:flex;align-items:center;gap:10px;margin-bottom:6px}
.logo{width:38px;height:38px;border-radius:11px;display:grid;place-items:center;
background:linear-gradient(135deg,#0891b2,#4f46e5);font-size:19px;flex:0 0 auto}
h1{font-size:17px;margin:0;letter-spacing:.5px}
.sub{color:var(--t2);font-size:12px;margin-top:2px}
h2{font-size:14px;margin:20px 0 4px;color:var(--t0)}
p{color:var(--t1);font-size:13px}
.field{margin-top:14px}
label{display:block;font-size:12px;color:var(--t1);margin-bottom:6px}
input{width:100%;padding:11px 12px;background:var(--surf2);border:1px solid var(--line);
border-radius:9px;color:var(--t0);outline:none;transition:.15s;font-size:14px}
input:focus{border-color:var(--brand);box-shadow:0 0 0 3px var(--glow)}
button{width:100%;margin-top:18px;padding:12px;border:none;border-radius:9px;
background:linear-gradient(135deg,var(--brand),var(--brand2));color:#fff;
font-size:15px;font-weight:600;cursor:pointer;box-shadow:0 6px 20px -8px var(--glow)}
button:active{transform:translateY(1px)}
.err{background:var(--errbg);border:1px solid var(--err);color:var(--err);
padding:10px 12px;border-radius:9px;margin-top:14px;font-size:13px}
.ok{background:var(--okbg);border:1px solid var(--ok);color:var(--ok);
padding:10px 12px;border-radius:9px;margin-top:14px;font-size:13px}
.theme-btn{position:absolute;top:14px;right:14px;width:34px;height:34px;padding:0;
margin:0;border-radius:50%;background:var(--surf2);border:1px solid var(--line);
color:var(--t1);font-size:15px;box-shadow:none;cursor:pointer}
.theme-btn:active{transform:none}
.kv{display:grid;grid-template-columns:1fr 1fr;gap:9px;margin-top:12px}
.kv div{background:var(--surf2);border:1px solid var(--line-soft);border-radius:9px;
padding:8px 10px}
.kv b{display:block;font-size:11px;color:var(--t2);font-weight:400}
.kv span{font-size:13px;font-weight:600}
.dot{display:inline-block;width:7px;height:7px;border-radius:50%;
background:var(--t2);margin-right:5px}
.dot.on{background:var(--ok);box-shadow:0 0 8px var(--ok)}
.dot.off{background:var(--err)}
pre{background:var(--surf2);border:1px solid var(--line-soft);border-radius:9px;
padding:11px;font-size:11px;line-height:1.55;color:var(--t1);overflow:auto;
max-height:240px;white-space:pre-wrap;word-break:break-all;margin:10px 0 0}
.foot{margin-top:16px;text-align:center;font-size:11px;color:var(--t2)}
a{color:var(--brand)}
</style>
<script>
(function(){try{var t=localStorage.getItem("smsatbox.theme");
if(t!=="light"&&t!=="dark"){t=window.matchMedia("(prefers-color-scheme: light)").matches?"light":"dark";}
document.documentElement.setAttribute("data-theme",t);}catch(e){}})();
function smsatToggleTheme(){var d=document.documentElement;
var next=d.getAttribute("data-theme")==="light"?"dark":"light";
d.setAttribute("data-theme",next);
try{localStorage.setItem("smsatbox.theme",next);}catch(e){}
var b=document.getElementById("themeBtn");
if(b){b.textContent=next==="light"?"\u2600":"\u{1F319}";}}
</script>
</head>
<body>
<div class="card">
<button class="theme-btn" id="themeBtn" onclick="smsatToggleTheme()" title="切换深浅色">&#127769;</button>
<div class="brand"><div class="logo">&#128228;</div>
<div><h1>SMSATBOX</h1><div class="sub">短信 / 未接来电 多卡提醒盒子</div></div></div>
)HTML";

// ---------------------------------------------------------------------------
// 配网页页脚
// ---------------------------------------------------------------------------
static const char PAGE_PORTAL_FOOT[] PROGMEM = R"HTML(
<div class="foot">设备仅保存以上三项 · 用户与权限全部由云端裁决</div>
<div class="foot" style="margin-top:6px">Firmware v1.0.0</div>
</div></body></html>
)HTML";

static const char PAGE_PORTAL_HEAD[] PROGMEM = R"HTML(
<p style="margin-top:14px">首次使用请完成配网。设备不会保存任何账号密码，
<br>只有下方三项会被写入。</p>
)HTML";

// ---------------------------------------------------------------------------
// 局域网调试页页脚
// ---------------------------------------------------------------------------
static const char PAGE_STATUS_FOOT[] PROGMEM = R"HTML(
<div class="foot">Firmware v1.0.0 · 局域网调试页（只读）</div>
</div></body></html>
)HTML";

// 动态部分在 web_page.cpp 里拼装
String buildStatusPage();
