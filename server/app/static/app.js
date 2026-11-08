/* ==========================================================================
 * SMSATBOX · Web 管理端
 * 单文件前端：API 客户端 / 路由 / 实时 WebSocket / PWA
 * 全平台版本 v1.0.0 —— 所有请求均携带 X-Client-Version 头
 * ========================================================================== */
(function () {
  "use strict";

  const VERSION = "1.0.2";
  const API = "/api/v1";
  const LS_TOKEN = "smsatbox.token";
  const LS_USER = "smsatbox.user";
  const LS_THEME = "smsatbox.theme";

  const state = {
    token: localStorage.getItem(LS_TOKEN) || "",
    user: JSON.parse(localStorage.getItem(LS_USER) || "null"),
    route: "messages",
    messages: { items: [], offset: 0, total: 0, limit: 50 },
    slots: [],
    devices: [],
    users: [],
    ws: null,
    wsRetry: 0,
    filters: { keyword: "", kind: "", slot_id: "" },
  };

  /* ------------------------------------------------------------------ DOM */
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const esc = (v) =>
    String(v == null ? "" : v).replace(/[&<>"']/g, (c) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));

  /* --------------------------------------------------------------- 主题 */
  const THEME_META = {
    dark: { ico: "🌙", label: "深色", next: "浅色" },
    light: { ico: "☀️", label: "浅色", next: "深色" },
  };

  const theme = {
    /** 用户选择："system" | "dark" | "light" */
    pref: (function () {
      const saved = localStorage.getItem(LS_THEME);
      return saved === "dark" || saved === "light" ? saved : "system";
    })(),
    media: window.matchMedia ? window.matchMedia("(prefers-color-scheme: light)") : null,

    /** 解析出当前实际生效的主题 */
    resolved() {
      if (this.pref === "dark" || this.pref === "light") return this.pref;
      return this.media && this.media.matches ? "light" : "dark";
    },

    apply() {
      const active = this.resolved();
      document.documentElement.setAttribute("data-theme", active);
      const meta = THEME_META[active];
      $$(".theme-toggle").forEach((btn) => {
        const ico = btn.querySelector(".ico");
        const lbl = btn.querySelector(".lbl");
        if (ico) ico.textContent = meta.ico;
        if (lbl) lbl.textContent = active === "dark" ? "深色模式" : "浅色模式";
        btn.setAttribute("aria-label", "当前" + meta.label + "主题，点击切换");
        btn.title = "当前" + meta.label + "主题 · 点击切换到" + meta.next;
      });
      const select = $("#theme-select");
      if (select) select.value = this.pref;
      const cur = $("#theme-current");
      if (cur) cur.textContent = meta.label + (this.pref === "system" ? "（跟随系统）" : "");
      // 同步浏览器地址栏配色
      let metaTag = document.querySelector('meta[name="theme-color"]');
      if (metaTag) metaTag.setAttribute("content", active === "light" ? "#f4f7fb" : "#0b111d");
    },

    /** 在 深色 -> 浅色 -> 跟随系统 之间循环 */
    toggle() {
      if (this.pref === "dark") this.pref = "light";
      else if (this.pref === "light") this.pref = "system";
      else this.pref = "dark";
      this.persist();
      this.apply();
      toast("主题：" + (this.pref === "system" ? "跟随系统" : THEME_META[this.pref].label), "ok");
    },

    set(pref) {
      this.pref = pref === "dark" || pref === "light" ? pref : "system";
      this.persist();
      this.apply();
    },

    persist() {
      try {
        if (this.pref === "system") localStorage.removeItem(LS_THEME);
        else localStorage.setItem(LS_THEME, this.pref);
      } catch (e) {
        /* 隐私模式下 localStorage 可能不可用，忽略即可 */
      }
    },

    init() {
      this.apply();
      // 跟随系统时，系统主题变化要实时响应
      if (this.media) {
        const onChange = () => {
          if (this.pref === "system") this.apply();
        };
        if (this.media.addEventListener) this.media.addEventListener("change", onChange);
        else if (this.media.addListener) this.media.addListener(onChange);
      }
      $$(".theme-toggle").forEach((btn) => {
        btn.addEventListener("click", () => this.toggle());
      });
      const select = $("#theme-select");
      if (select) {
        select.addEventListener("change", (ev) => {
          this.set(ev.target.value);
          toast("主题：" + (this.pref === "system" ? "跟随系统" : THEME_META[this.pref].label), "ok");
        });
      }
    },
  };

  /* --------------------------------------------------------------- Toasts */
  function toast(msg, type = "") {
    const el = document.createElement("div");
    el.className = "toast " + type;
    el.textContent = msg;
    $("#toasts").appendChild(el);
    setTimeout(() => {
      el.style.opacity = "0";
      el.style.transition = "opacity .25s";
      setTimeout(() => el.remove(), 260);
    }, 2600);
  }

  /* ------------------------------------------------------------ API client */
  async function api(path, options = {}) {
    const opts = Object.assign({ method: "GET", headers: {} }, options);
    opts.headers = Object.assign(
      {
        "X-Client-Version": VERSION,
        "X-Client-Platform": "web",
        Accept: "application/json",
      },
      opts.headers
    );
    if (state.token) opts.headers.Authorization = "Bearer " + state.token;
    if (opts.body && !(opts.body instanceof FormData)) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(opts.body);
    }
    const res = await fetch(API + path, opts);
    let data = null;
    try {
      data = await res.json();
    } catch (e) {
      data = null;
    }
    if (res.status === 401) {
      logout(false);
      throw new Error((data && data.detail) || "登录已失效");
    }
    if (!res.ok) {
      const detail =
        (data && (data.detail || data.message)) ||
        (data && data.errors ? JSON.stringify(data.errors) : null) ||
        "请求失败 (" + res.status + ")";
      throw new Error(typeof detail === "string" ? detail : "请求失败");
    }
    return data || {};
  }

  /* ------------------------------------------------------------- 登录/登出 */
  function showLogin() {
    $("#login-view").style.display = "flex";
    $("#app-view").classList.remove("active");
  }

  function showApp() {
    $("#login-view").style.display = "none";
    $("#app-view").classList.add("active");
    $("#side-user").textContent =
      (state.user && (state.user.display_name || state.user.username)) || "-";
    $("#set-user").textContent = (state.user && state.user.username) || "-";
    const roleText = state.user && state.user.role === "superadmin" ? "超级管理员" : "普通成员";
    $("#set-role").textContent = roleText;
    $("#btn-dev-add").classList.toggle("hidden", !(state.user && state.user.role === "superadmin"));
    $("#nav-members").classList.toggle("hidden", !(state.user && state.user.role === "superadmin"));
  }

  function logout(withServerCall = true) {
    if (withServerCall && state.token) {
      api("/auth/logout", { method: "POST" }).catch(() => {});
    }
    state.token = "";
    state.user = null;
    localStorage.removeItem(LS_TOKEN);
    localStorage.removeItem(LS_USER);
    if (state.ws) {
      try { state.ws.close(); } catch (e) {}
      state.ws = null;
    }
    showLogin();
  }

  $("#login-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const btn = $("#login-btn");
    btn.disabled = true;
    btn.textContent = "登录中…";
    try {
      const data = await api("/auth/login", {
        method: "POST",
        body: {
          username: $("#login-user").value.trim(),
          password: $("#login-pass").value,
        },
      });
      state.token = data.access_token;
      state.user = data.user;
      localStorage.setItem(LS_TOKEN, state.token);
      localStorage.setItem(LS_USER, JSON.stringify(state.user));
      $("#login-pass").value = "";
      showApp();
      await bootstrap();
      toast("欢迎回来，" + (state.user.display_name || state.user.username), "ok");
    } catch (err) {
      toast(err.message, "err");
    } finally {
      btn.disabled = false;
      btn.textContent = "登 录";
    }
  });

  /* ------------------------------------------------------------------ 路由 */
  const TITLES = {
    messages: "消息总览",
    send: "反向控制",
    devices: "设备管理",
    members: "成员权限",
    settings: "设置",
  };

  function switchRoute(route) {
    if (route === "members" && !(state.user && state.user.role === "superadmin")) route = "messages";
    state.route = route;
    $$(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.route === route));
    $$(".route").forEach((s) => s.classList.add("hidden"));
    const el = $("#route-" + route);
    if (el) el.classList.remove("hidden");
    document.title = "SMSATBOX · " + (TITLES[route] || "") + " · v" + VERSION;
    if (location.hash.slice(1) !== route) history.replaceState(null, "", "#" + route);

    if (route === "messages") loadMessages(true);
    if (route === "send") { loadSlots().then(fillSendSlots); loadCommands(); }
    if (route === "devices") loadDevices();
    if (route === "members") loadUsers();
    if (route === "settings") loadVersion();
  }

  $("#nav").addEventListener("click", (ev) => {
    const btn = ev.target.closest(".nav-item");
    if (btn && btn.dataset.route) switchRoute(btn.dataset.route);
  });

  /* ------------------------------------------------------------ 通用滑块槽 */
  async function loadSlots() {
    try {
      const data = await api("/devices");
      state.devices = data.items || [];
      const slots = [];
      state.devices.forEach((d) => {
        (d.slots || []).forEach((s) => {
          slots.push(Object.assign({ device_name: d.device_name }, s));
        });
      });
      state.slots = slots;
      return slots;
    } catch (err) {
      toast(err.message, "err");
      return [];
    }
  }

  function slotLabel(s) {
    const num = s.phone_number || s.slot_number || "未设置号码";
    return s.device_name + " · 卡槽" + s.slot_index + " · " + num;
  }

  function fillSlotSelect(sel, { withAll = false, withDevices = false } = {}) {
    const el = typeof sel === "string" ? $(sel) : sel;
    if (!el) return;
    const prev = el.value;
    let html = withAll ? '<option value="">全部卡槽</option>' : "";
    let lastDevice = null;
    state.slots.forEach((s) => {
      if (withDevices && s.device_name !== lastDevice) {
        lastDevice = s.device_name;
      }
      html += '<option value="' + s.id + '">' + esc(slotLabel(s)) + "</option>";
    });
    el.innerHTML = html;
    if (prev) el.value = prev;
  }

  /* -------------------------------------------------------------- 消息总览 */
  function renderStats(stats) {
    $("#stat-total").textContent = stats.total ?? 0;
    $("#stat-unread").textContent = stats.unread ?? 0;
    $("#stat-today").textContent = stats.today ?? 0;
    $("#stat-codes").textContent = stats.codes ?? 0;
    const badge = $("#nav-unread");
    const n = statNumber(stats.unread);
    badge.textContent = n > 99 ? "99+" : n;
    badge.classList.toggle("hidden", !n);
  }

  function statNumber(v) { return Number(v || 0); }

  async function loadMessages(reset = false) {
    if (reset) {
      state.messages.offset = 0;
      state.messages.items = [];
    }
    const params = new URLSearchParams();
    params.set("limit", String(state.messages.limit));
    params.set("offset", String(state.messages.offset));
    if (state.filters.kind) params.set("kind", state.filters.kind);
    if (state.filters.keyword) params.set("keyword", state.filters.keyword);
    if (state.filters.slot_id) params.set("slot_id", state.filters.slot_id);
    try {
      const [data, stats] = await Promise.all([
        api("/messages?" + params.toString()),
        api("/messages/stats"),
      ]);
      if (reset) state.messages.items = data.items || [];
      else state.messages.items = state.messages.items.concat(data.items || []);
      state.messages.total = data.total || 0;
      renderMessages();
      renderStats(stats);
      const more = $("#btn-more");
      more.classList.toggle("hidden", state.messages.items.length >= state.messages.total);
      if (!state.messages.total) {
        $("#msg-list").innerHTML = '<div class="empty">还没有任何消息。<br/>设备联机并上报后会实时出现在这里。</div>';
      }
    } catch (err) {
      toast(err.message, "err");
    }
  }

  function fmtTime(iso) {
    if (!iso) return "-";
    const d = new Date(iso);
    if (isNaN(d.getTime())) return esc(iso);
    const p = (n) => String(n).padStart(2, "0");
    const now = new Date();
    const sameDay =
      d.getFullYear() === now.getFullYear() &&
      d.getMonth() === now.getMonth() &&
      d.getDate() === now.getDate();
    const hm = p(d.getHours()) + ":" + p(d.getMinutes());
    if (sameDay) return "今天 " + hm;
    return (
      d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate()) + " " + hm
    );
  }

  function renderMessages() {
    const list = $("#msg-list");
    if (!state.messages.items.length) {
      list.innerHTML =
        '<div class="empty">还没有任何消息。<br/>设备联机并上报后会实时出现在这里。</div>';
      return;
    }
    list.innerHTML = state.messages.items
      .map((m) => {
        const kindTag =
          m.kind === "call"
            ? '<span class="tag call">来电</span>'
            : m.kind === "system"
            ? '<span class="tag">系统</span>'
            : '<span class="tag sms">短信</span>';
        const slotTag = m.slot_index
          ? '<span class="tag slot">卡槽 ' + m.slot_index + "</span>"
          : "";
        const codeChip = m.code
          ? '<div class="code-chip" data-copy="' + esc(m.code) + '" title="点击复制验证码">' + esc(m.code) + " ⧉</div>"
          : "";
        return (
          '<article class="msg ' + (m.is_read ? "" : "unread ") + (m.kind === "call" ? "called" : "") + '" data-id="' + m.id + '">' +
          '<div class="msg-head">' +
          kindTag + slotTag +
          '<span class="msg-sender">' + esc(m.sender || "未知号码") + "</span>" +
          '<span class="msg-meta">' + fmtTime(m.received_at) + "</span>" +
          "</div>" +
          '<div class="msg-body">' + esc(m.content || (m.kind === "call" ? "未接来电" : "")) + "</div>" +
          '<div class="msg-foot">' + codeChip +
          '<button class="btn btn-sm btn-ghost" data-act="copy">复制内容</button>' +
          (m.is_read ? "" : '<button class="btn btn-sm btn-ghost" data-act="read">标为已读</button>') +
          "</div></article>"
        );
      })
      .join("");
  }

  $("#msg-list").addEventListener("click", async (ev) => {
    const chip = ev.target.closest(".code-chip");
    if (chip) {
      copyText(chip.dataset.copy);
      return;
    }
    const btn = ev.target.closest("[data-act]");
    if (!btn) return;
    const card = ev.target.closest(".msg");
    const id = Number(card.dataset.id);
    const item = state.messages.items.find((m) => m.id === id);
    if (btn.dataset.act === "copy") {
      copyText((item && item.content) || "");
    } else if (btn.dataset.act === "read") {
      try {
        await api("/messages/" + id, { method: "PATCH", body: { is_read: true } });
        if (item) item.is_read = true;
        renderMessages();
        loadStats();
      } catch (err) {
        toast(err.message, "err");
      }
    }
  });

  function loadStats() {
    api("/messages/stats").then(renderStats).catch(() => {});
  }

  function copyText(text) {
    if (!text) return;
    const done = () => toast("已复制：" + text, "ok");
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(done).catch(() => fallbackCopy(text, done));
    } else {
      fallbackCopy(text, done);
    }
  }

  function fallbackCopy(text, done) {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); done(); } catch (e) { toast("复制失败", "err"); }
    ta.remove();
  }

  let searchTimer = null;
  $("#msg-search").addEventListener("input", (ev) => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.filters.keyword = ev.target.value.trim();
      loadMessages(true);
    }, 260);
  });
  $("#msg-kind").addEventListener("change", (ev) => {
    state.filters.kind = ev.target.value;
    loadMessages(true);
  });
  $("#msg-slot").addEventListener("change", (ev) => {
    state.filters.slot_id = ev.target.value;
    loadMessages(true);
  });
  $("#btn-refresh").addEventListener("click", () => loadMessages(true));
  $("#btn-more").addEventListener("click", () => {
    state.messages.offset += state.messages.limit;
    loadMessages(false);
  });
  $("#btn-readall").addEventListener("click", async () => {
    try {
      const r = await api("/messages/read-all", { method: "POST" });
      toast("已标记 " + (r.updated ?? 0) + " 条为已读", "ok");
      loadMessages(true);
    } catch (err) {
      toast(err.message, "err");
    }
  });

  /* ------------------------------------------------------------ 反向控制 */
  function fillSendSlots() {
    fillSlotSelect("#send-slot");
  }

  $("#btn-send").addEventListener("click", async () => {
    const slotId = $("#send-slot").value;
    const target = $("#send-target").value.trim();
    const content = $("#send-content").value.trim();
    if (!slotId) return toast("请先选择卡槽", "err");
    if (!target) return toast("请填写接收号码", "err");
    if (!content) return toast("请填写短信内容", "err");
    const btn = $("#btn-send");
    btn.disabled = true;
    try {
      const r = await api("/messages/send", {
        method: "POST",
        body: { slot_id: Number(slotId), target_number: target, content },
      });
      toast(r.pushed ? "指令已推送至设备" : r.note || "指令已排队", r.pushed ? "ok" : "");
      $("#send-content").value = "";
      loadCommands();
    } catch (err) {
      toast(err.message, "err");
    } finally {
      btn.disabled = false;
    }
  });

  const STATUS_TEXT = {
    pending: "待下发",
    sent: "已发送",
    delivered: "已送达",
    failed: "失败",
  };

  async function loadCommands() {
    try {
      const data = await api("/messages/commands/list?limit=30");
      const rows = (data.items || []).map(
        (c) =>
          "<tr><td>" + c.id + "</td><td>" + esc(c.target_number) + "</td><td>" +
          esc((c.content || "").slice(0, 40)) + "</td><td>" +
          '<span class="tag ' + (c.status === "failed" ? "call" : "") + '">' +
          (STATUS_TEXT[c.status] || c.status) + "</span></td><td>" +
          fmtTime(c.created_at) + "</td></tr>"
      );
      $("#cmd-table").innerHTML =
        rows.join("") || '<tr><td colspan="5" class="empty">暂无指令</td></tr>';
    } catch (err) {
      toast(err.message, "err");
    }
  }

  /* ------------------------------------------------------------ 设备管理 */
  async function loadDevices() {
    try {
      const data = await api("/devices");
      state.devices = data.items || [];
      renderDevices();
      await loadSlots();
      fillSlotSelect("#msg-slot", { withAll: true });
      fillSendSlots();
    } catch (err) {
      toast(err.message, "err");
    }
  }

  /** 信号格：把 dBm 转成 0-4 格的可视化 */
  function signalBars(level) {
    const n = Math.max(0, Math.min(4, Number(level) || 0));
    let html = '<span class="bars">';
    for (let i = 1; i <= 4; i++) {
      html += '<i class="' + (i <= n ? "on" : "") + '"></i>';
    }
    html += "</span>";
    return html;
  }

  /** 渲染单个卡槽（含模组真实状态、备注、隐藏标记） */
  function renderSlot(s, isAdmin) {
    const m = s.module || {};
    const hidden = s.visible === false;
    const expire = s.plan_expire_at ? s.plan_expire_at.slice(0, 10) : "未设置";
    const expired = s.plan_expire_at && new Date(s.plan_expire_at) < new Date();

    // 模组状态徽标
    let moduleBadge;
    if (!m.present) {
      moduleBadge = '<span class="tag danger">未检测到模组</span>';
    } else if (m.module_state !== "ready") {
      moduleBadge = '<span class="tag warn">模组 ' + esc(m.module_state || "未知") + "</span>";
    } else if (!m.registered) {
      moduleBadge = '<span class="tag warn">' + esc(m.reg_text || "未注册网络") + "</span>";
    } else {
      moduleBadge = '<span class="tag ok">' + esc(m.reg_text || "已注册") + "</span>";
    }

    const simBadge =
      m.sim_state === "ready"
        ? '<span class="tag">SIM 就绪</span>'
        : m.present
        ? '<span class="tag warn">无 SIM 卡</span>'
        : "";

    const sigHtml = m.present && m.rssi_csq !== undefined && m.rssi_csq !== 99
      ? signalBars(m.signal_level) +
        '<span class="sig-txt">' + (m.signal_dbm ?? "-") + " dBm</span>"
      : "";

    return (
      '<div class="slot-row' + (hidden ? " slot-hidden" : "") + '">' +
      '<div class="slot-no">' + s.slot_index + "</div>" +
      "<div class=\"slot-main\">" +
        "<div>" +
          "<b>" + esc(s.phone_number || m.phone_number || "未设置号码") + "</b>" +
          (s.remark ? '<span class="slot-remark">' + esc(s.remark) + "</span>" : "") +
          (hidden ? '<span class="tag">已隐藏</span>' : "") +
        "</div>" +
        '<div class="slot-tags">' + moduleBadge + simBadge +
          (m.carrier ? "<span class=\"tag\">" + esc(m.carrier) + "</span>" : "") +
          (sigHtml ? '<span class="tag">' + sigHtml + "</span>" : "") +
        "</div>" +
      "</div>" +
      '<div class="tag" style="' + (expired ? "color:var(--danger);border-color:#6b2b32" : "") + '">套餐 ' + esc(expire) + "</div>" +
      (isAdmin
        ? '<button class="btn btn-sm" data-slot="' + s.id + '">编辑</button>' +
          '<button class="btn btn-sm btn-ghost" data-toggle="' + s.id + '" data-visible="' +
          (hidden ? "0" : "1") + '">' + (hidden ? "显示" : "隐藏") + "</button>"
        : "") +
      "</div>"
    );
  }

  function renderDevices() {
    const box = $("#device-list");
    if (!state.devices.length) {
      box.innerHTML = '<div class="card empty">还没有设备。点击右上角“新增设备”生成 Device_Token。</div>';
      return;
    }
    const isAdmin = state.user && state.user.role === "superadmin";
    box.innerHTML = state.devices
      .map((d) => {
        const online = !!d.online;
        const slots = (d.slots || []).map((s) => renderSlot(s, isAdmin)).join("");

        // 模组总览：统计检测到几个模组
        const modules = d.modules || [];
        const presentCount = modules.filter((m) => m && m.present).length;
        const regCount = modules.filter((m) => m && m.registered).length;

        return (
          '<div class="card dev-card">' +
          '<div class="dev-head">' +
          '<span class="dot ' + (online ? "on" : "off") + '"></span>' +
          '<span class="dev-name">' + esc(d.device_name || "未命名设备") + "</span>" +
          '<span class="dev-id">#' + d.id + "</span>" +
          '<span class="pill">' + (online ? "在线" : "离线") + "</span>" +
          '<span class="pill">固件 v' + esc(d.firmware_version || "-") + "</span>" +
          (modules.length
            ? '<span class="pill">模组 ' + presentCount + "/" + modules.length +
              " · 已注册 " + regCount + "</span>"
            : "") +
          '<div class="spacer" style="flex:1"></div>' +
          '<button class="btn btn-sm" data-devid="' + d.id + '" data-act="detail">详情</button>' +
          (isAdmin
            ? '<button class="btn btn-sm" data-devid="' + d.id + '" data-act="rename">编辑</button>' +
              '<button class="btn btn-sm" data-devid="' + d.id + '" data-act="ota">OTA 升级</button>' +
              '<button class="btn btn-sm btn-danger" data-devid="' + d.id + '" data-act="del">删除</button>'
            : "") +
          "</div>" +
          (d.remark ? '<div class="dev-remark">' + esc(d.remark) + "</div>" : "") +
          '<div class="dev-grid">' +
          kv("网络模式", d.net_mode === "4g" ? "4G 流量" : d.net_mode === "wifi" ? "WiFi" : "-") +
          kv("局域网 IP", d.local_ip || "-") +
          kv("WiFi 信号", d.wifi_rssi ? d.wifi_rssi + " dBm" : "-") +
          kv("最后在线", fmtTime(d.last_seen_at)) +
          "</div>" +
          slots +
          "</div>"
        );
      })
      .join("");
  }

  function kv(k, v) {
    return '<div class="kv"><div class="k">' + esc(k) + '</div><div class="v">' + esc(v) + "</div></div>";
  }

  $("#device-list").addEventListener("click", async (ev) => {
    const btn = ev.target.closest("button[data-act], button[data-slot], button[data-toggle]");
    if (!btn) return;

    // 卡槽编辑
    if (btn.dataset.slot) return openSlotEditor(Number(btn.dataset.slot));

    // 卡槽显示/隐藏切换
    if (btn.dataset.toggle) {
      const slotId = Number(btn.dataset.toggle);
      const currentlyVisible = btn.dataset.visible === "1";
      try {
        await api("/devices/slots/" + slotId, {
          method: "PATCH",
          body: { is_active: !currentlyVisible },
        });
        toast(currentlyVisible ? "卡槽已隐藏" : "卡槽已显示", "ok");
        await loadDevices();
      } catch (err) {
        toast(err.message, "err");
      }
      return;
    }

    const id = Number(btn.dataset.devid);
    if (btn.dataset.act === "ota") return openOtaDialog(id);
    if (btn.dataset.act === "detail") return openDeviceDetail(id);
    if (btn.dataset.act === "rename") return openDeviceRename(id);
    if (btn.dataset.act === "del") return confirmDeleteDevice(id);
  });

  /** 删除设备（连带卡槽、消息、OTA 任务一起删，需二次确认） */
  function confirmDeleteDevice(deviceId) {
    const d = state.devices.find((x) => x.id === deviceId);
    if (!d) return;
    const slotCount = (d.slots || []).length;
    openModal({
      title: "删除设备",
      sub: "此操作不可撤销",
      body:
        '<p style="color:var(--text-1);line-height:1.8;margin:0 0 12px">' +
        "即将删除设备 <b style=\"color:var(--danger)\">" + esc(d.device_name || "未命名设备") + "</b>" +
        "（#" + d.id + "）</p>" +
        '<div class="dev-remark" style="border-left-color:var(--danger)">' +
        "删除后该设备的 " + slotCount + " 个卡槽、全部短信与来电记录、OTA 任务都会一并清除，" +
        "且<b>无法恢复</b>。设备本身需要重新配网才能再次接入。" +
        "</div>",
      okText: "确认删除",
      onOk: async () => {
        await api("/devices/" + deviceId, { method: "DELETE" });
        closeModal();
        toast("设备已删除", "ok");
        await loadDevices();
      },
    });
  }

  /** 编辑设备名称与备注 */
  function openDeviceRename(deviceId) {
    const d = state.devices.find((x) => x.id === deviceId);
    if (!d) return;
    openModal({
      title: "编辑设备",
      sub: "设备 #" + d.id,
      body:
        '<div class="field"><label>设备名称</label>' +
        '<input id="ed-name" value="' + esc(d.device_name || "") + '" placeholder="例如 客厅盒子" /></div>' +
        '<div class="field"><label>备注</label>' +
        '<input id="ed-remark" value="' + esc(d.remark || "") + '" placeholder="可选，例如 主力机 / 备用" /></div>',
      okText: "保存",
      onOk: async () => {
        await api("/devices/" + deviceId, {
          method: "PATCH",
          body: {
            device_name: $("#ed-name").value.trim(),
            remark: $("#ed-remark").value.trim(),
          },
        });
        closeModal();
        await loadDevices();
        toast("设备信息已更新", "ok");
      },
    });
  }

  $("#btn-dev-refresh").addEventListener("click", loadDevices);

  $("#btn-dev-add").addEventListener("click", () => {
    openModal({
      title: "新增设备",
      sub: "创建后生成的 Device_Token 只会显示一次，请填入 ESP32 配网页面。",
      body:
        '<div class="field"><label>设备名称</label><input id="nd-name" placeholder="例如 客厅盒子" /></div>' +
        '<div class="field"><label>硬件型号</label><input id="nd-model" value="ESP32-S3-N16R8" /></div>' +
        '<div class="field"><label>备注</label><input id="nd-remark" placeholder="可选" /></div>',
      okText: "创建",
      onOk: async () => {
        const r = await api("/devices", {
          method: "POST",
          body: {
            device_name: $("#nd-name").value.trim(),
            hardware_model: $("#nd-model").value.trim(),
            remark: $("#nd-remark").value.trim(),
            slots: 2,
          },
        });
        closeModal();
        await loadDevices();
        openModal({
          title: "设备已创建",
          sub: "请立刻复制 Device_Token",
          body:
            '<div class="code-chip" style="letter-spacing:0;word-break:break-all">' +
            esc(r.device.device_token) + "</div>" +
            '<p style="font-size:12px;color:var(--warn);margin-top:10px">关闭后无法再次查看，只能重置。</p>',
          okText: "我已保存",
          onOk: async () => {
            copyText(r.device.device_token);
            closeModal();
          },
        });
      },
    });
  });

  async function openDeviceDetail(id) {
    try {
      const r = await api("/devices/" + id);
      const d = r.device;

      // eSIM / eUICC 数据（失败不影响主详情展示）
      let euiccList = [];
      try {
        const er = await api("/esim");
        euiccList = (er.items || []).filter((e) => e.device_id === d.id);
      } catch (e) {
        euiccList = [];
      }

      // 每个卡槽的模组详情区块
      const moduleBlocks = (d.slots || [])
        .map((s) => {
          const m = s.module || {};
          const rows = [];
          rows.push(["槽位", "卡槽 " + s.slot_index + (s.remark ? "（" + s.remark + "）" : "")]);
          rows.push(["模组检测", m.present ? "已检测到" : "未检测到"]);
          rows.push(["模组状态", m.module_state || "-"]);
          rows.push(["SIM 卡", m.sim_state === "ready" ? "就绪" : "未就绪"]);
          rows.push([
            "网络注册",
            (m.registered ? "已注册" : "未注册") + (m.reg_text ? " · " + m.reg_text : ""),
          ]);
          if (m.lac || m.cell_id) rows.push(["LAC / 小区", (m.lac || "-") + " / " + (m.cell_id || "-")]);
          if (m.rssi_csq !== undefined)
            rows.push([
              "信号强度",
              (m.signal_dbm ?? "-") + " dBm（CSQ " + (m.rssi_csq ?? "-") + "，等级 " + (m.signal_level ?? 0) + "/4）",
            ]);
          if (m.carrier) rows.push(["运营商", m.carrier]);
          if (m.phone_number) rows.push(["本机号码", m.phone_number]);
          if (m.imsi) rows.push(["IMSI", m.imsi]);
          if (m.iccid) rows.push(["ICCID", m.iccid]);
          if (m.imei) rows.push(["IMEI", m.imei]);

          return (
            '<div class="module-card">' +
            '<div class="module-title">' +
            '<span class="slot-no">' + s.slot_index + "</span>" +
            "<span>" + esc(s.remark || "卡槽 " + s.slot_index) + "</span>" +
            '<span class="dot ' + (m.registered ? "on" : "off") + '"></span>' +
            (s.visible === false ? '<span class="tag">已隐藏</span>' : "") +
            "</div>" +
            '<table class="module-table">' +
            rows
              .map(
                ([k, v]) =>
                  "<tr><td>" + esc(k) + "</td><td>" + esc(String(v)) + "</td></tr>"
              )
              .join("") +
            "</table></div>"
          );
        })
        .join("");

      // eSIM 区块：直接嵌在设备详情里，不再跳到独立页面
      const esimBlocks = euiccList
        .map((e) => {
          const profiles = (e.profiles || [])
            .map((p) => {
              const name = p.nickname || p.profile_name || p.provider || "未命名配置";
              const active = p.state === 1;
              const btns = [];
              btns.push(
                '<button class="btn btn-sm" data-esim-act="nickname" data-euicc="' +
                  e.id + '" data-iccid="' + esc(p.iccid) + '" data-name="' + esc(name) + '">改名</button>'
              );
              if (active) {
                btns.push(
                  '<button class="btn btn-sm" data-esim-act="disable" data-euicc="' +
                    e.id + '" data-iccid="' + esc(p.iccid) + '">停用</button>'
                );
              } else {
                btns.push(
                  '<button class="btn btn-sm btn-primary" data-esim-act="enable" data-euicc="' +
                    e.id + '" data-iccid="' + esc(p.iccid) + '">启用</button>'
                );
                btns.push(
                  '<button class="btn btn-sm btn-danger" data-esim-act="delete" data-euicc="' +
                    e.id + '" data-iccid="' + esc(p.iccid) + '">删除</button>'
                );
              }
              return (
                '<div class="esim-profile' + (active ? " active" : "") + '">' +
                '<div class="esim-main">' +
                '<div class="esim-name">' + esc(name) +
                '<span class="tag ' + (active ? "ok" : "") + '">' + (active ? "使用中" : "未启用") + "</span>" +
                (p.provider ? '<span class="tag">' + esc(p.provider) + "</span>" : "") +
                "</div>" +
                '<div class="mono esim-iccid">' + esc(p.iccid) + "</div>" +
                "</div>" +
                '<div class="esim-actions">' + btns.join("") + "</div>" +
                "</div>"
              );
            })
            .join("");

          const freeKb = e.free_nonvolatile > 0 ? Math.round(e.free_nonvolatile / 1024) + " KB" : "—";
          return (
            '<div class="module-card esim-card">' +
            '<div class="module-title">' +
            '<span class="slot-no">' + e.slot_index + "</span>" +
            "<span>eUICC 可编程卡</span>" +
            '<span class="dot ' + (e.online ? "on" : "off") + '"></span>' +
            (e.user_enabled ? "" : '<span class="tag">功能已关闭</span>') +
            "</div>" +
            '<table class="module-table">' +
            '<tr><td>EID</td><td class="mono">' + esc(e.eid || "（未读取）") + "</td></tr>" +
            "<tr><td>已装配置</td><td>" + (e.profiles || []).length + " 个</td></tr>" +
            "<tr><td>剩余存储</td><td>" + freeKb + "</td></tr>" +
            "</table>" +
            (profiles
              ? '<div class="esim-list">' + profiles + "</div>"
              : '<div class="empty" style="padding:16px">卡内还没有配置，需要用 LPA 激活码下载</div>') +
            '<div class="esim-foot">' +
            '<button class="btn btn-sm" data-esim-act="refresh" data-euicc="' + e.id + '">刷新卡片</button>' +
            '<button class="btn btn-sm" data-esim-act="toggle" data-euicc="' + e.id +
            '" data-enabled="' + (e.user_enabled ? "1" : "0") + '">' +
            (e.user_enabled ? "关闭 eSIM 管理" : "启用 eSIM 管理") + "</button>" +
            "</div></div>"
          );
        })
        .join("");

      openModal({
        title: d.device_name || "设备详情",
        sub: "设备 #" + d.id + " · " + (d.online ? "在线" : "离线"),
        body:
          '<div class="dev-grid">' +
          kv("固件版本", "v" + (d.firmware_version || "-")) +
          kv("Server 版本", d.server_version ? "v" + d.server_version : "-") +
          kv("硬件型号", d.hardware_model) +
          kv("网络模式", d.net_mode) +
          kv("局域网 IP", d.local_ip || "-") +
          kv("WiFi RSSI", d.wifi_rssi ? d.wifi_rssi + " dBm" : "-") +
          kv("最后在线", fmtTime(d.last_seen_at)) +
          kv("WebSocket", (d.ws_connections || 0) + " 条") +
          "</div>" +
          (d.remark ? '<div class="dev-remark" style="margin-top:10px">' + esc(d.remark) + "</div>" : "") +
          '<h4 class="modal-section">4G 模组</h4>' +
          (moduleBlocks || '<div class="empty" style="padding:20px">该设备尚未上报模组状态</div>') +
          (esimBlocks
            ? '<h4 class="modal-section">eSIM 配置</h4>' + esimBlocks
            : "") +
          (state.user.role === "superadmin"
            ? '<div class="field" style="margin-top:14px">' +
              '<button class="btn btn-sm" id="btn-edit-dev" style="margin-right:8px">编辑设备</button>' +
              '<button class="btn btn-sm btn-danger" id="btn-rotate">重置 Device_Token</button></div>'
            : ""),
        okText: "关闭",
        onOk: async () => closeModal(),
      });

      // eSIM 操作事件（闭包内定义，可直接访问 euiccList）
      const onEsimAction = async (btn, deviceId) => {
        const act = btn.dataset.esimAct;
        const euiccId = Number(btn.dataset.euicc);
        const euicc = euiccList.find((x) => x.id === euiccId);
        if (!euicc) return;
        const iccid = btn.dataset.iccid || "";

        try {
          if (act === "toggle") {
            const next = btn.dataset.enabled !== "1";
            await api("/esim/" + euiccId + "/toggle", {
              method: "PATCH",
              body: { user_enabled: next },
            });
            toast(next ? "已启用 eSIM 管理" : "已关闭 eSIM 管理", "ok");
            closeModal();
            return openDeviceDetail(deviceId);
          }

          if (act === "nickname") {
            const cur = btn.dataset.name || "";
            const name = prompt("给这个配置起个名字（最多 64 字）：", cur);
            if (name === null) return;
            await api("/esim/command", {
              method: "POST",
              body: {
                device_id: deviceId,
                slot_index: euicc.slot_index,
                operation: "nickname",
                iccid,
                nickname: name.trim(),
              },
            });
            toast("改名指令已下发", "ok");
            closeModal();
            return;
          }

          if (act === "delete") {
            if (!confirm("删除后无法恢复，确定删除这个配置？\n\n" + iccid)) return;
          }

          // refresh / enable / disable / delete 都走指令队列
          await api("/esim/command", {
            method: "POST",
            body: {
              device_id: deviceId,
              slot_index: euicc.slot_index,
              operation: act,
              iccid,
            },
          });
          const label = { refresh: "刷新", enable: "启用", disable: "停用", delete: "删除" }[act] || act;
          toast(label + "指令已下发，等待设备执行…");
          closeModal();
        } catch (e) {
          toast(e.message, "err");
        }
      };

      $$("[data-esim-act]").forEach((btn) => {
        btn.addEventListener("click", () => onEsimAction(btn, id));
      });

      const editDev = $("#btn-edit-dev");
      if (editDev) {
        editDev.addEventListener("click", () => {
          closeModal();
          openDeviceRename(id);
        });
      }

      const rotate = $("#btn-rotate");
      if (rotate) {
        rotate.addEventListener("click", async () => {
          if (!confirm("重置后原 Token 立即失效，设备需重新配网。继续？")) return;
          const res = await api("/devices/" + id + "/rotate-token", { method: "POST" });
          copyText(res.device_token);
          closeModal();
          loadDevices();
        });
      }
    } catch (err) {
      toast(err.message, "err");
    }
  }

  function openSlotEditor(slotId) {
    const slot = state.slots.find((s) => s.id === slotId);
    if (!slot) return;
    const hidden = slot.visible === false;
    openModal({
      title: "编辑卡槽 " + slot.slot_index,
      sub: slot.device_name,
      body:
        '<div class="field"><label>备注名称</label>' +
        '<input id="es-remark" value="' + esc(slot.remark || "") +
        '" placeholder="例如 主力卡 / 副卡 / 工作号" /></div>' +
        '<div class="field"><label>手机号码</label>' +
        '<input id="es-number" value="' + esc(slot.phone_number || "") + '" /></div>' +
        '<div class="field"><label>运营商</label>' +
        '<input id="es-carrier" value="' + esc(slot.carrier || "") + '" /></div>' +
        '<div class="field"><label>套餐名称</label>' +
        '<input id="es-plan" value="' + esc(slot.plan_name || "") + '" /></div>' +
        '<div class="field"><label>套餐到期日（YYYY-MM-DD）</label>' +
        '<input id="es-expire" type="date" value="' +
        esc((slot.plan_expire_at || "").slice(0, 10)) + '" /></div>' +
        '<div class="field" style="display:flex;align-items:center;gap:9px">' +
        '<input id="es-visible" type="checkbox" style="width:auto" ' +
        (hidden ? "" : "checked") + " />" +
        "<label style=\"margin:0\">在消息列表中显示此卡槽</label></div>",
      okText: "保存",
      onOk: async () => {
        const body = {
          remark: $("#es-remark").value.trim(),
          phone_number: $("#es-number").value.trim(),
          carrier: $("#es-carrier").value.trim(),
          plan_name: $("#es-plan").value.trim(),
          is_active: $("#es-visible").checked,
        };
        const exp = $("#es-expire").value;
        body.plan_expire_at = exp ? exp + "T00:00:00Z" : null;
        await api("/devices/slots/" + slotId, { method: "PATCH", body });
        closeModal();
        await loadDevices();
        toast("卡槽已更新", "ok");
      },
    });
  }

  function openOtaDialog(deviceId) {
    openModal({
      title: "ESP32 固件 OTA",
      sub: "上传 .bin 文件后将通过 WebSocket 下发，设备静默下载并做 MD5 校验。",
      body:
        '<div class="field"><label>固件版本号</label><input id="ota-ver" value="1.0.0" /></div>' +
        '<div class="field"><label>选择 .bin 文件</label><input id="ota-file" type="file" accept=".bin" /></div>',
      okText: "上传并下发",
      onOk: async () => {
        const file = $("#ota-file").files[0];
        if (!file) throw new Error("请选择固件文件");
        const fd = new FormData();
        fd.append("version", $("#ota-ver").value.trim() || "1.0.0");
        fd.append("file", file);
        const r = await api("/devices/" + deviceId + "/ota", { method: "POST", body: fd });
        closeModal();
        toast(
          r.pushed ? "OTA 已下发（MD5 " + r.md5.slice(0, 8) + "）" : "设备离线，OTA 已排队",
          "ok"
        );
      },
    });
  }

  /* ------------------------------------------------------------ 成员权限 */
  async function loadUsers() {
    try {
      const data = await api("/users");
      state.users = data.items || [];
      renderUsers();
    } catch (err) {
      toast(err.message, "err");
    }
  }

  function renderUsers() {
    const rows = state.users.map((u) => {
      const permText =
        u.role === "superadmin"
          ? '<span class="tag slot">全部卡槽</span>'
          : (u.permissions || []).length
          ? u.permissions
              .map((p) => {
                const slot = state.slots.find((s) => s.id === p.slot_id);
                return (
                  '<span class="tag slot">' +
                  (slot ? slot.device_name + "·卡槽" + slot.slot_index : "卡槽" + p.slot_id) +
                  (p.can_send_sms ? " ✉" : "") +
                  "</span>"
                );
              })
              .join(" ")
          : '<span class="tag">未授权</span>';
      return (
        "<tr><td>" + u.id + "</td><td>" + esc(u.display_name || u.username) +
        "<br/><span style='color:var(--text-2);font-size:11px'>" + esc(u.username) + "</span></td>" +
        "<td>" + (u.role === "superadmin" ? "超级管理员" : "普通成员") + "</td>" +
        "<td>" + (u.is_active ? '<span class="dot on"></span> 启用' : '<span class="dot off"></span> 禁用') + "</td>" +
        "<td>" + permText + "</td>" +
        "<td>" +
        (u.role === "superadmin"
          ? ""
          : '<button class="btn btn-sm" data-uid="' + u.id + '" data-act="perm">分配权限</button> ' +
            '<button class="btn btn-sm btn-danger" data-uid="' + u.id + '" data-act="del">删除</button>') +
        "</td></tr>"
      );
    });
    $("#user-table").innerHTML =
      rows.join("") || '<tr><td colspan="6" class="empty">暂无成员</td></tr>';
  }

  $("#user-table").addEventListener("click", async (ev) => {
    const btn = ev.target.closest("button[data-uid]");
    if (!btn) return;
    const uid = Number(btn.dataset.uid);
    if (btn.dataset.act === "del") {
      if (!confirm("确认删除该成员？")) return;
      try {
        await api("/users/" + uid, { method: "DELETE" });
        toast("成员已删除", "ok");
        loadUsers();
      } catch (err) {
        toast(err.message, "err");
      }
      return;
    }
    openPermissionDialog(uid);
  });

  async function openPermissionDialog(userId) {
    await loadSlots();
    const u = state.users.find((x) => x.id === userId);
    if (!u) return;
    const granted = new Map((u.permissions || []).map((p) => [p.slot_id, p]));
    const body = state.slots.length
      ? state.slots
          .map((s) => {
            const g = granted.get(s.id) || {};
            return (
              '<div class="slot-row">' +
              '<div class="slot-no">' + s.slot_index + "</div>" +
              "<div>" + esc(s.device_name) + " · " + esc(s.phone_number || "未设置号码") + "</div>" +
              '<div class="spacer" style="flex:1"></div>' +
              '<label style="font-size:12px"><input type="checkbox" data-slot="' + s.id + '" data-kind="read" ' +
              (g.can_read ? "checked" : "") + "/> 可见</label>" +
              '<label style="font-size:12px;margin-left:10px"><input type="checkbox" data-slot="' + s.id + '" data-kind="send" ' +
              (g.can_send_sms ? "checked" : "") + "/> 可发短信</label>" +
              "</div>"
            );
          })
          .join("")
      : '<div class="empty">暂无卡槽，请先添加设备</div>';
    openModal({
      title: "分配权限 · " + (u.display_name || u.username),
      sub: "勾选后立即生效",
      body,
      okText: "保存",
      onOk: async () => {
        const items = [];
        $$('#modal-root input[data-kind="read"]').forEach((cb) => {
          const slotId = Number(cb.dataset.slot);
          const send = $(
            '#modal-root input[data-kind="send"][data-slot="' + slotId + '"]'
          );
          if (cb.checked || (send && send.checked)) {
            items.push({
              slot_id: slotId,
              can_read: cb.checked,
              can_send_sms: !!(send && send.checked),
            });
          }
        });
        await api("/users/" + userId + "/permissions", {
          method: "PUT",
          body: { items },
        });
        closeModal();
        toast("权限已更新", "ok");
        loadUsers();
      },
    });
  }

  $("#btn-user-add").addEventListener("click", () => {
    openModal({
      title: "新增成员",
      sub: "成员只能看到被授权的卡槽",
      body:
        '<div class="field"><label>用户名</label><input id="nu-name" placeholder="至少 3 位" /></div>' +
        '<div class="field"><label>显示名称</label><input id="nu-display" placeholder="可选" /></div>' +
        '<div class="field"><label>初始密码</label><input id="nu-pass" type="password" placeholder="至少 8 位" /></div>',
      okText: "创建",
      onOk: async () => {
        await api("/users", {
          method: "POST",
          body: {
            username: $("#nu-name").value.trim(),
            display_name: $("#nu-display").value.trim(),
            password: $("#nu-pass").value,
            role: "member",
          },
        });
        closeModal();
        toast("成员已创建", "ok");
        loadUsers();
      },
    });
  });

  /* ---------------------------------------------------------------- 设置 */
  function loadVersion() {
    api("/version")
      .then((v) => {
        $("#set-server-ver").textContent = "v" + v.version;
        $("#side-version").textContent = "v" + v.version;
        $("#login-version").textContent = "v" + v.version;
        $("#mobile-version").textContent = "v" + v.version;
        document.title = "SMSATBOX · " + (TITLES[state.route] || "") + " · v" + v.version;
      })
      .catch(() => {});
  }

  $("#btn-pass").addEventListener("click", async () => {
    try {
      await api("/auth/password", {
        method: "POST",
        body: { old_password: $("#old-pass").value, new_password: $("#new-pass").value },
      });
      $("#old-pass").value = "";
      $("#new-pass").value = "";
      toast("密码已修改", "ok");
    } catch (err) {
      toast(err.message, "err");
    }
  });

  $("#btn-mktoken").addEventListener("click", async () => {
    try {
      const r = await api("/auth/client-tokens", {
        method: "POST",
        body: { name: "web-generated" },
      });
      $("#token-box").classList.remove("hidden");
      $("#token-value").textContent = r.token;
      $("#token-value").dataset.copy = r.token;
      toast("令牌已生成，仅显示一次", "ok");
    } catch (err) {
      toast(err.message, "err");
    }
  });
  $("#token-value").addEventListener("click", (ev) => {
    copyText(ev.target.dataset.copy || ev.target.textContent);
  });

  $("#btn-logout").addEventListener("click", () => logout(true));

  /* ------------------------------------------------------------- WebSocket */
  function connectWs() {
    if (!state.token) return;
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const url = proto + "//" + location.host + API + "/ws?token=" + encodeURIComponent(state.token);
    let ws;
    try {
      ws = new WebSocket(url);
    } catch (e) {
      return;
    }
    state.ws = ws;
    setWsState(false, "连接中…");

    ws.onopen = () => {
      state.wsRetry = 0;
      setWsState(true, "实时已连接");
    };
    ws.onclose = () => {
      setWsState(false, "已断开");
      state.ws = null;
      if (!state.token) return;
      const delay = Math.min(30000, 1500 * Math.pow(1.6, state.wsRetry++));
      setTimeout(connectWs, delay);
    };
    ws.onerror = () => {};
    ws.onmessage = (ev) => {
      let payload;
      try { payload = JSON.parse(ev.data); } catch (e) { return; }
      handleWsEvent(payload.event, payload.data || {});
    };
  }

  function setWsState(online, text) {
    $("#ws-dot").className = "dot " + (online ? "on" : "off");
    $("#ws-text").textContent = text;
    $("#side-ws").textContent = text;
  }

  function handleWsEvent(event, data) {
    switch (event) {
      case "new_message": {
        const msg = data.message;
        if (!msg) return;
        const match =
          (!state.filters.kind || state.filters.kind === msg.kind) &&
          (!state.filters.slot_id || Number(state.filters.slot_id) === msg.slot_id) &&
          (!state.filters.keyword ||
            (msg.content || "").includes(state.filters.keyword) ||
            (msg.sender || "").includes(state.filters.keyword));
        if (match && state.route === "messages") {
          state.messages.items.unshift(msg);
          state.messages.total += 1;
          renderMessages();
        }
        loadStats();
        const prefix = msg.kind === "call" ? "📞 来电提醒" : msg.code ? "🔑 验证码 " + msg.code : "💬 新短信";
        toast(prefix + " · " + (msg.sender || "未知号码"), "ok");
        if (Notification && Notification.permission === "granted") {
          try {
            new Notification("SMSATBOX · 卡槽" + (msg.slot_index || "?"), {
              body: (msg.sender || "") + "： " + (msg.content || ""),
            });
          } catch (e) {}
        }
        break;
      }
      case "device_status":
        if (state.route === "devices") loadDevices();
        break;
      case "command_result":
        if (state.route === "send") loadCommands();
        break;
      case "ota_update":
        toast("OTA 状态更新：" + data.status, data.status === "success" ? "ok" : "");
        break;
      case "connected":
        break;
      case "pong":
        break;
    }
  }

  /* ------------------------------------------------------------ 模态框工具 */
  function openModal({ title, sub, body, okText, onOk }) {
    closeModal();
    const root = $("#modal-root");
    root.innerHTML =
      '<div class="modal-mask"><div class="modal">' +
      "<h3>" + esc(title) + "</h3>" +
      (sub ? '<div class="sub">' + esc(sub) + "</div>" : "") +
      body +
      '<div class="modal-actions">' +
      '<button class="btn btn-ghost" data-modal="cancel">取消</button>' +
      '<button class="btn btn-primary" data-modal="ok">' + esc(okText || "确定") + "</button>" +
      "</div></div></div>";
    const mask = root.querySelector(".modal-mask");
    mask.addEventListener("click", (ev) => {
      if (ev.target === mask) closeModal();
    });
    root.querySelector('[data-modal="cancel"]').addEventListener("click", closeModal);
    root.querySelector('[data-modal="ok"]').addEventListener("click", async (ev) => {
      const btn = ev.currentTarget;
      btn.disabled = true;
      try {
        if (onOk) await onOk();
      } catch (err) {
        toast(err.message, "err");
      } finally {
        btn.disabled = false;
      }
    });
  }

  function closeModal() {
    $("#modal-root").innerHTML = "";
  }

  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") closeModal();
  });

  /* --------------------------------------------------------------- 启动 */
  async function bootstrap() {
    loadVersion();
    await loadSlots();
    fillSlotSelect("#msg-slot", { withAll: true });
    fillSendSlots();

    // 支持 #devices/<id> 直达某台设备的详情（方便分享链接 / 从通知跳转）
    const raw = location.hash.slice(1) || "messages";
    const m = raw.match(/^([a-z]+)\/(\d+)$/);
    if (m) {
      switchRoute(m[1]);
      const did = Number(m[2]);
      if (m[1] === "devices" && did > 0) {
        await loadDevices();
        setTimeout(() => openDeviceDetail(did), 120);
      }
    } else {
      switchRoute(raw);
    }

    connectWs();
    if (Notification && Notification.permission === "default") {
      setTimeout(() => Notification.requestPermission().catch(() => {}), 4000);
    }
  }

  (async function init() {
    theme.init();
    $("#login-server").textContent = location.origin + API;
    loadVersion();
    if (!state.token) return showLogin();
    try {
      const me = await api("/auth/me");
      state.user = me.user;
      showApp();
      await bootstrap();
    } catch (err) {
      showLogin();
    }
  })();

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/sw.js").catch(() => {});
    });
  }
})();
