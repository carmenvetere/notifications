/*
 * Notification Center panel: Rules, Recent and Settings tabs plus a
 * one-page rule editor.
 *
 * One vanilla web component, no framework or build step. It talks to the
 * integration over the WebSocket API (notification_center/...): meta,
 * rules/list|create|update|delete|test, render, history/list and
 * settings/get|update|test_push|test_announcement.
 *
 * Rendering model: the view is rebuilt from state with innerHTML. Focus and
 * the text caret are restored after each render through a stable data-f key
 * on every focusable control, so text fields can re-render while typing.
 * Colours come from Home Assistant theme variables (light and dark).
 */

const TABS = [
  ["rules", "Rules"],
  ["recent", "Recent"],
  ["settings", "Settings"],
];

const PRI = {
  critical: {
    label: "Critical",
    solid: "#c8321f",
    onSolid: "#ffffff",
    pill: "#e0685c",
    wall: "#ee8478",
    desc: "Breaks through silent mode and Do Not Disturb. Stays until resolved.",
    push: "Critical push: sounds even in silent mode and Do Not Disturb.",
    icon: "mdi:alert-octagon",
  },
  warning: {
    label: "Warning",
    solid: "#f0a020",
    onSolid: "#2a1c00",
    pill: "#e3a84a",
    wall: "#e3a84a",
    desc: "Surfaces above other notifications. Stays until resolved.",
    push: "Time-sensitive push: shows above other notifications.",
    icon: "mdi:alert",
  },
  info: {
    label: "Info",
    solid: "#4f6f8c",
    onSolid: "#ffffff",
    pill: "",
    wall: "#f2f0ec",
    desc: "Delivered quietly. Can be dismissed, snoozed or rolled into a digest.",
    push: "Passive push: arrives quietly, no sound.",
    icon: "mdi:information",
  },
};
const PRIORITIES = ["critical", "warning", "info"];

const PUSH_LABEL = {
  critical: "Critical push",
  "time-sensitive": "Time-sensitive push",
  passive: "Passive push",
  active: "Normal push",
};

const CHANNELS = [
  { id: "mobile", label: "Mobile", short: "Mobile", icon: "mdi:cellphone", desc: "Push to phones through the Home Assistant app" },
  { id: "bell", label: "Bell", short: "Bell", icon: "mdi:bell-outline", desc: "A persistent notification inside Home Assistant" },
  { id: "wall", label: "Wall panels", short: "Wall panels", icon: "mdi:tablet-dashboard", desc: "ESP32 wall panels. Always listed in their Notifications sheet." },
  { id: "tts", label: "Speakers", short: "Speakers", icon: "mdi:bullhorn-outline", desc: "A spoken announcement" },
];

const STATE_OPS = [
  ["==", "is"],
  ["!=", "is not"],
];
const NUMERIC_OPS = [
  [">", "goes above"],
  ["<", "drops below"],
  [">=", "is at least"],
  ["<=", "is at most"],
  ["==", "equals"],
  ["!=", "doesn't equal"],
];

const QUIET = [
  ["", "Use the priority default", null],
  ["ignore", "Send as normal", "Quiet hours make no difference to this rule."],
  ["downgrade", "Send quietly", "Arrives silently during quiet hours, with no sound or speech."],
  ["suppress", "Don't send", "Dropped during quiet hours. It will not show up later."],
  ["batch", "Hold until quiet hours end", "Held back and sent as one summary when quiet hours end."],
];
const PRESENCE = [
  ["all", "Everyone, home or away", "Sent to everyone picked above."],
  ["away_only", "Only people who are away", "Skips anyone who is at home."],
  ["per_person", "Only people who are home", "Skips anyone who is away."],
];

const SNOOZE_CHOICES = [15, 30, 60, 120, 240, 480, 1440, 10080];

const COMMON_ICONS = [
  "mdi:flash-alert",
  "mdi:water-alert",
  "mdi:garage-open",
  "mdi:thermometer-alert",
  "mdi:bag-suitcase",
  "mdi:air-filter",
  "mdi:battery-alert",
  "mdi:dishwasher",
];

const COLORS = [
  ["", "Priority default"],
  ["#c8321f", "Red"],
  ["#b85c00", "Orange"],
  ["#1f8a4c", "Green"],
  ["#1e6fd9", "Blue"],
  ["#7b57c9", "Purple"],
];

// Fields that hold templates and are rendered for the preview.
const TEMPLATE_FIELDS = [
  "title_template",
  "message_template",
  "tts_message",
  "wall_takeover_text",
  "progress_template",
  "progress_max_template",
  "critical_text_template",
  "condition_template",
];

function esc(s) {
  return String(s == null ? "" : s).replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

function slugify(s) {
  return String(s || "")
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function clone(v) {
  return v == null ? v : JSON.parse(JSON.stringify(v));
}

function asList(v) {
  if (v == null || v === "") return [];
  if (Array.isArray(v)) return v.map(String).filter(Boolean);
  return String(v)
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);
}

function hasTemplate(s) {
  return /\{\{|\{%/.test(String(s || ""));
}

function durationLabel(m) {
  m = Number(m) || 0;
  if (m % 10080 === 0) return `${m / 10080} week${m > 10080 ? "s" : ""}`;
  if (m % 1440 === 0) return `${m / 1440} day${m > 1440 ? "s" : ""}`;
  if (m % 60 === 0) return `${m / 60} hour${m > 60 ? "s" : ""}`;
  return `${m} min`;
}

function sinceLabel(iso) {
  const t = Date.parse(iso || "");
  if (!t) return "";
  const min = Math.max(0, Math.round((Date.now() - t) / 60000));
  if (min < 1) return "just now";
  if (min < 60) return `${min} min`;
  if (min < 1440) return `${Math.floor(min / 60)} h`;
  return `${Math.floor(min / 1440)} d`;
}

function spanLabel(fromIso, toIso) {
  const a = Date.parse(fromIso || "");
  const b = Date.parse(toIso || "");
  if (!a || !b || b < a) return "";
  const min = Math.round((b - a) / 60000);
  if (min < 1) return "under a minute";
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60);
  const rest = min % 60;
  if (h < 24) return rest ? `${h} h ${rest} min` : `${h} h`;
  return `${Math.floor(h / 24)} d ${h % 24} h`;
}

function clockLabel(iso) {
  const d = new Date(iso || "");
  if (isNaN(d)) return "";
  return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function dayLabel(iso) {
  const d = new Date(iso || "");
  if (isNaN(d)) return "Earlier";
  const today = new Date();
  const start = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((start(today) - start(d)) / 86400000);
  if (diff === 0) return "Today";
  if (diff === 1) return "Yesterday";
  return d.toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" });
}

function hhmm(v) {
  const m = String(v || "").match(/^(\d{1,2}):(\d{2})/);
  return m ? `${m[1].padStart(2, "0")}:${m[2]}` : "";
}

function minutesOfDay(v) {
  const m = String(v || "").match(/^(\d{1,2}):(\d{2})/);
  return m ? Number(m[1]) * 60 + Number(m[2]) : 0;
}

function quietLength(start, end) {
  const a = minutesOfDay(start);
  const b = minutesOfDay(end);
  if (a === b) return "";
  const len = b > a ? b - a : 1440 - a + b;
  const h = Math.floor(len / 60);
  const m = len % 60;
  return `${h} h${m ? ` ${m} min` : ""}${b < a ? ", overnight" : ""}`;
}

function quietSegments(start, end) {
  const a = minutesOfDay(start);
  const b = minutesOfDay(end);
  const pct = (x) => `${(x / 1440) * 100}%`;
  if (a === b) return [];
  if (b > a) return [{ left: pct(a), width: pct(b - a) }];
  return [
    { left: pct(a), width: pct(1440 - a) },
    { left: "0%", width: pct(b) },
  ];
}

function phoneName(service) {
  return String(service || "")
    .replace(/^notify\./, "")
    .replace(/^mobile_app_/, "")
    .split("_")
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

// Wall action string <-> {type, name, chime}.
// "chime" is the default sound; "sound:<name>" any other sound (#63).
function parseWallAction(s) {
  const out = { type: "none", name: "", sound: "", extra: [] };
  for (const part of asList(s)) {
    if (part === "chime" && !out.sound) out.sound = "chime";
    else if (/^sound:/.test(part) && !out.sound) out.sound = part.slice(6);
    else if (/^(sheet|page):/.test(part) && out.type === "none") {
      const [type, ...rest] = part.split(":");
      out.type = type;
      out.name = rest.join(":");
    } else out.extra.push(part);
  }
  return out;
}

function buildWallAction(w) {
  const parts = [];
  if (w.type !== "none" && w.name) parts.push(`${w.type}:${w.name}`);
  parts.push(...(w.extra || []));
  if (w.sound) parts.push(w.sound === "chime" ? "chime" : `sound:${w.sound}`);
  return parts.join(",");
}

// Quiet-hours behaviour that applies to a draft rule ("" = priority default).
function quietBehaviour(d, meta) {
  const pri = d.priority || "info";
  return d.quiet_hours_behavior || ((meta && meta.quiet_defaults) || {})[pri] || "ignore";
}

function parseTarget(s) {
  const m = String(s || "").match(/^(sheet|page):(.+)$/);
  return m ? { type: m[1], name: m[2] } : { type: "default", name: "" };
}

// Suggested values for a state rule (design §6).
function stateSuggestions(entityId, st) {
  const domain = String(entityId || "").split(".")[0];
  const attrs = (st && st.attributes) || {};
  let out = [];
  if (Array.isArray(attrs.options) && attrs.options.length) out = attrs.options.map(String);
  else if (["binary_sensor", "input_boolean", "switch", "light", "fan", "automation", "siren"].includes(domain))
    out = ["on", "off"];
  else if (domain === "cover") out = ["open", "closed", "opening", "closing"];
  else if (domain === "lock") out = ["locked", "unlocked", "jammed"];
  else if (domain === "alarm_control_panel")
    out = ["disarmed", "armed_home", "armed_away", "armed_night", "pending", "triggered"];
  else if (domain === "person" || domain === "device_tracker") out = ["home", "not_home"];
  else if (domain === "media_player") out = ["playing", "paused", "idle", "off"];
  else if (domain === "climate") out = ["heat", "cool", "heat_cool", "off"];
  if (st && st.state && !out.includes(st.state) && !["unknown", "unavailable"].includes(st.state))
    out.push(st.state);
  return out.slice(0, 12);
}

function friendly(hass, entityId) {
  const st = hass && hass.states && hass.states[entityId];
  return (st && st.attributes && st.attributes.friendly_name) || entityId || "";
}

function evalTrigger(sourceType, op, value, stateVal) {
  if (stateVal == null || ["unknown", "unavailable", ""].includes(String(stateVal))) return false;
  if (sourceType === "numeric") {
    const a = parseFloat(stateVal);
    const b = parseFloat(value);
    if (isNaN(a) || isNaN(b)) return false;
    return { ">": a > b, "<": a < b, ">=": a >= b, "<=": a <= b, "==": a === b, "!=": a !== b }[op || ">"];
  }
  return (op || "==") === "!=" ? String(stateVal) !== String(value ?? "") : String(stateVal) === String(value ?? "");
}

class NotificationCenterPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._route = { view: "rules", id: null };
    this._meta = null;
    this._rules = null; // null = loading
    this._rulesError = null;
    this._history = null;
    this._historyError = null;
    this._settings = null; // { settings, health, phone_status, available_phones }
    this._settingsError = null;
    this._sDraft = null;
    this._sSaved = null;
    this._draft = null; // rule being edited
    this._saved = null; // JSON of the rule as last saved/loaded
    this._editingId = null;
    this._isNew = false;
    this._rendered = {}; // template -> {text}|{error}
    this._ui = { q: "", filter: "all", menu: null, confirm: null, folds: {}, picker: null, pickQ: "", moreIcons: false };
    this._recentUi = { q: "", filter: "all" };
    this._banner = null; // {kind, ...}
    this._phoneNotes = {}; // notify service -> {ok, text}
    this._playNote = null;
    this._advOpen = false;
    this._busy = false;
    this._onHash = () => this._applyHash();
    this._onBeforeUnload = (e) => {
      if (this._dirty()) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    this.shadowRoot.addEventListener("click", (e) => this._onClick(e));
    this.shadowRoot.addEventListener("input", (e) => this._onInput(e));
    this.shadowRoot.addEventListener("change", (e) => this._onChange(e));
    this.shadowRoot.addEventListener("keydown", (e) => this._onKey(e));
  }

  // --- Home Assistant hooks ----------------------------------------------
  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._start();
    // Live "Now:" chips and states change constantly; refresh the editor's
    // trigger line cheaply without stealing focus.
    else if (this._route.view === "rule" && this._draft) this._refreshLive();
  }

  set narrow(v) {
    this._narrow = v;
  }

  connectedCallback() {
    window.addEventListener("hashchange", this._onHash);
    window.addEventListener("beforeunload", this._onBeforeUnload);
    if (this._hass) this._render();
  }

  disconnectedCallback() {
    window.removeEventListener("hashchange", this._onHash);
    window.removeEventListener("beforeunload", this._onBeforeUnload);
    clearInterval(this._poll);
  }

  async _start() {
    this._applyHash(true);
    try {
      this._meta = await this._ws("notification_center/meta");
    } catch (e) {
      this._metaError = (e && e.message) || "Couldn't reach Notification Center.";
    }
    await this._loadRules();
    this._poll = setInterval(() => {
      if (document.visibilityState === "visible" && ["rules", "rule"].includes(this._route.view)) this._loadRules(true);
    }, 10000);
    this._applyHash(true);
  }

  _ws(type, extra) {
    return this._hass.connection.sendMessagePromise({ type, ...(extra || {}) });
  }

  get _readOnly() {
    return !!(this._meta && this._meta.read_only);
  }

  // --- Data ----------------------------------------------------------------
  async _loadRules(quiet) {
    try {
      const res = await this._ws("notification_center/rules/list");
      this._rules = res.rules || [];
      this._rulesError = null;
    } catch (e) {
      if (!quiet) this._rulesError = (e && e.message) || "Couldn't load the rules.";
    }
    if (!quiet || this._route.view === "rules") this._render();
    else if (this._route.view === "rule") this._refreshTestingBanner();
  }

  async _loadHistory() {
    this._history = null;
    this._historyError = null;
    this._render();
    try {
      const res = await this._ws("notification_center/history/list", { limit: 50 });
      this._history = res.history || [];
    } catch (e) {
      this._historyError = (e && e.message) || "Couldn't load recent alerts.";
    }
    this._render();
  }

  async _loadSettings() {
    this._settingsError = null;
    try {
      const res = await this._ws("notification_center/settings/get");
      this._settings = res;
      this._sDraft = clone(res.settings);
      this._sSaved = JSON.stringify(res.settings);
    } catch (e) {
      this._settingsError = (e && e.message) || "Couldn't load settings.";
    }
    this._render();
  }

  _ruleById(id) {
    return (this._rules || []).find((r) => r.subentry_id === id) || null;
  }

  // --- Routing (#rules, #recent, #settings, #rule/<id>, #rule/new) ----------
  _parseHash() {
    const h = (location.hash || "").replace(/^#/, "");
    if (h.startsWith("rule/")) return { view: "rule", id: decodeURIComponent(h.slice(5)) };
    if (["rules", "recent", "settings"].includes(h)) return { view: h, id: null };
    return { view: "rules", id: null };
  }

  _hashFor(route) {
    return route.view === "rule" ? `#rule/${encodeURIComponent(route.id)}` : `#${route.view}`;
  }

  _dirty() {
    if (this._route.view === "rule") return !!this._draft && JSON.stringify(this._draft) !== this._saved;
    if (this._route.view === "settings") return !!this._sDraft && JSON.stringify(this._sDraft) !== this._sSaved;
    return false;
  }

  _go(hash) {
    if (hash === this._hashFor(this._route)) return;
    if (this._dirty()) {
      this._banner = { kind: "leave", to: hash };
      this._render();
      return;
    }
    location.hash = hash;
  }

  _applyHash(force) {
    const next = this._parseHash();
    const same = next.view === this._route.view && next.id === this._route.id;
    if (same && !force) return;
    if (!same && this._dirty()) {
      // Browser back/forward while editing: stay, and ask.
      const to = this._hashFor(next);
      history.replaceState(null, "", this._hashFor(this._route));
      this._banner = { kind: "leave", to };
      this._render();
      return;
    }
    this._route = next;
    this._banner = null;
    this._ui.menu = null;
    this._ui.confirm = null;
    if (next.view === "rule") this._openEditor(next.id);
    else if (next.view === "recent" && (!same || force)) {
      this._loadHistory();
      return;
    } else if (next.view === "settings" && (!same || force || !this._settings)) {
      this._settings = null;
      this._loadSettings();
      return;
    }
    this._render();
    if (!same) this.shadowRoot.host.scrollIntoView && window.scrollTo && window.scrollTo(0, 0);
  }

  _discardAndLeave() {
    const to = this._banner && this._banner.to;
    if (this._route.view === "rule") this._saved = JSON.stringify(this._draft);
    if (this._route.view === "settings") this._sDraft = JSON.parse(this._sSaved);
    this._banner = null;
    if (to) location.hash = to;
    else this._render();
  }

  // --- Events --------------------------------------------------------------
  _onClick(e) {
    const el = e.target.closest("[data-act]");
    if (!el || el.disabled) return;
    const act = el.getAttribute("data-act");
    const arg = el.getAttribute("data-arg");
    if (el.tagName === "A") e.preventDefault();
    const fn = this[`_a_${act}`];
    if (fn) fn.call(this, arg, el, e);
  }

  _onInput(e) {
    const el = e.target;
    const key = el.getAttribute && el.getAttribute("data-in");
    if (!key) return;
    this._setField(key, el.value, el, true);
  }

  _onChange(e) {
    const el = e.target;
    const key = el.getAttribute && el.getAttribute("data-ch");
    if (!key) return;
    this._setField(key, el.value, el, false);
  }

  _onKey(e) {
    if (e.key === "Escape") {
      if (this._ui.menu || this._ui.picker) {
        this._ui.menu = null;
        this._ui.picker = null;
        this._render();
      }
      return;
    }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
      if (this._route.view === "rule" && this._dirty()) {
        e.preventDefault();
        this._a_save();
      } else if (this._route.view === "settings" && this._dirty()) {
        e.preventDefault();
        this._a_saveSettings();
      }
    }
    // Switches, chips and cards are real buttons; Space/Enter already click.
  }

  // Generic field setter. Keys: "r.<field>" (rule draft), "s.<field>"
  // (settings draft), "ui.<field>", "recent.<field>".
  _setField(key, value, el, typing) {
    const [ns, ...rest] = key.split(".");
    const field = rest.join(".");
    if (ns === "r" && this._draft) {
      this._setRule(field, value);
      if (typing) {
        this._updateStatus();
        this._scheduleRender();
        return;
      }
    } else if (ns === "s" && this._sDraft) {
      this._sDraft[field] = value;
      if (typing) {
        this._updateStatus();
        return;
      }
    } else if (ns === "ui") {
      this._ui[field] = value;
    } else if (ns === "recent") {
      this._recentUi[field] = value;
    } else if (ns === "fn") {
      const fn = this[`_c_${field}`];
      if (fn) fn.call(this, value, el);
      return;
    }
    this._render();
  }

  // Header status text without a full render (while typing).
  _updateStatus() {
    const s = this.shadowRoot.getElementById("status");
    const dirty = this._dirty();
    if (s) {
      s.textContent = dirty ? "Unsaved changes" : "Saved";
      s.className = dirty ? "status warn" : "status";
    }
    const save = this.shadowRoot.getElementById("save");
    if (save) save.classList.toggle("dim", !dirty || this._readOnly);
    const discard = this.shadowRoot.getElementById("discard");
    if (discard) discard.hidden = !dirty;
  }

  _scheduleRender() {
    clearTimeout(this._typeTimer);
    this._typeTimer = setTimeout(() => this._renderTemplates(), 400);
  }

  // --- Render --------------------------------------------------------------
  _render() {
    if (!this.shadowRoot || !this._hass) return;
    const root = this.shadowRoot;
    const active = root.activeElement;
    const key = active && active.getAttribute && active.getAttribute("data-f");
    let sel = null;
    try {
      if (active && "selectionStart" in active && active.selectionStart != null)
        sel = [active.selectionStart, active.selectionEnd, active.scrollTop];
    } catch (_) {
      sel = null;
    }
    this._focusKey = key;
    let body;
    try {
      body = this._renderView();
    } catch (err) {
      console.error("notification-center-panel: render failed", err);
      body = `<div class="wrap"><p class="error">Something went wrong drawing this page: ${esc(err.message)}</p></div>`;
    }
    root.innerHTML = `<style>${STYLES}</style><div class="nc">${body}</div>`;
    if (key) {
      const el = root.querySelector(`[data-f="${CSS.escape(key)}"]`);
      if (el) {
        el.focus({ preventScroll: true });
        if (sel && "setSelectionRange" in el) {
          try {
            el.setSelectionRange(sel[0], sel[1]);
            el.scrollTop = sel[2];
          } catch (_) {
            /* not a text control */
          }
        }
      }
    }
    this._afterRender();
  }

  _afterRender() {
    if (this._route.view === "rule") this._mountIconPicker();
    const banner = this._banner && this.shadowRoot.querySelector(".banner[role=alert]");
    if (banner && !this._bannerSeen) banner.scrollIntoView({ block: "nearest", behavior: "smooth" });
    this._bannerSeen = !!banner;
  }

  _renderView() {
    if (this._metaError && !this._meta)
      return `<div class="wrap">${this._errorBox(this._metaError, "reload")}</div>`;
    const ro = this._readOnly
      ? `<div class="banner info" role="note">These rules are defined in configuration.yaml, so this panel is read-only.</div>`
      : "";
    if (this._route.view === "rule") return `${this._renderEditor(ro)}`;
    const v = this._route.view;
    let header = "";
    const menu = this._narrow
      ? `<button type="button" class="iconbtn" data-act="menu" aria-label="Open the sidebar"><ha-icon icon="mdi:menu"></ha-icon></button>`
      : "";
    if (v === "settings") {
      const dirty = this._dirty();
      header = `<header class="top sticky">
        <div class="titlerow">${menu}<h1>Notifications</h1>
          <span id="status" class="status ${dirty ? "warn" : ""}">${this._sDraft ? (dirty ? "Unsaved changes" : "Saved") : ""}</span>
          <div class="actions">
            <button type="button" id="discard" class="btn ghost" data-act="discardSettings" ${dirty ? "" : "hidden"}>Discard</button>
            <button type="button" id="save" class="btn primary ${dirty ? "" : "dim"}" data-act="saveSettings" data-f="save">Save</button>
          </div></div>${this._renderTabs()}</header>`;
    } else {
      const add =
        v === "rules"
          ? `<a class="btn primary" href="#rule/new" data-act="addRule" data-f="add" ${this._readOnly ? 'aria-disabled="true" tabindex="-1"' : ""}><ha-icon icon="mdi:plus"></ha-icon>Add rule</a>`
          : "";
      header = `<header class="top"><div class="titlerow">${menu}<div class="grow"><h1>Notifications</h1>
          <p class="sub">${this._headline()}</p></div>${add}</div>${this._renderTabs()}</header>`;
    }
    let content = "";
    if (v === "rules") content = this._renderRules();
    else if (v === "recent") content = this._renderRecent();
    else if (v === "settings") content = this._renderSettings();
    return `<div class="wrap ${v === "settings" ? "narrowcol" : ""}">${header}${ro}${this._renderBanner()}${content}</div>`;
  }

  _renderTabs() {
    return `<nav class="tabs" aria-label="Panel sections">${TABS.map(
      ([id, label]) =>
        `<button type="button" class="tab ${this._route.view === id ? "on" : ""}" data-act="tab" data-arg="${id}" data-f="tab-${id}" ${
          this._route.view === id ? 'aria-current="page"' : ""
        }>${label}</button>`
    ).join("")}</nav>`;
  }

  _headline() {
    if (!this._rules) return "&nbsp;";
    const active = this._rules.filter((r) => r.active && r.data.enabled !== false).length;
    return `${active} active now · ${this._rules.length} rule${this._rules.length === 1 ? "" : "s"}`;
  }

  _renderBanner() {
    const b = this._banner;
    if (!b) return "";
    if (b.kind === "leave") {
      const what = this._route.view === "settings" ? "settings" : "changes to this rule";
      return `<div class="banner warn" role="alert"><span class="grow"><strong>You have unsaved ${what}.</strong> Leaving now throws them away.</span>
        <button type="button" class="btn" data-act="stay" data-f="stay">Keep editing</button>
        <button type="button" class="btn danger-text" data-act="discardLeave">Discard and leave</button>
        <button type="button" class="btn primary" data-act="saveLeave">Save</button></div>`;
    }
    if (b.kind === "error")
      return `<div class="banner error" role="alert"><span class="grow"><strong>Couldn't save.</strong> ${esc(b.text)}</span>
        <button type="button" class="btn" data-act="dismissBanner">OK</button></div>`;
    return "";
  }

  _errorBox(text, retry) {
    return `<div class="card errorbox" role="alert"><p>${esc(text)}</p><button type="button" class="btn" data-act="retry" data-arg="${retry}">Retry</button></div>`;
  }

  _skeleton() {
    return `<div class="card list" aria-busy="true">${[0, 1, 2]
      .map(() => `<div class="row skel"><span class="sk sk-icon"></span><span class="sk sk-line"></span></div>`)
      .join("")}</div>`;
  }

  // Shared controls ----------------------------------------------------------
  _switch(on, act, label, opts = {}) {
    const dis = opts.disabled ? 'disabled aria-disabled="true"' : "";
    return `<button type="button" class="tg" role="switch" aria-checked="${on ? "true" : "false"}" aria-label="${esc(label)}"
      data-act="${act}" ${opts.arg != null ? `data-arg="${esc(opts.arg)}"` : ""} data-f="${esc(opts.f || act + (opts.arg || ""))}" ${dis}>
      <span class="tgt ${on ? "on" : ""}"><span class="tgk"></span></span></button>`;
  }

  _chip(label, on, act, arg, opts = {}) {
    const dis = opts.disabled ? 'disabled aria-disabled="true"' : "";
    return `<button type="button" class="chip ${on ? "on" : ""}" aria-pressed="${on ? "true" : "false"}" data-act="${act}"
      data-arg="${esc(arg)}" data-f="${esc(act + ":" + arg)}" ${dis}>${on ? '<ha-icon class="ck" icon="mdi:check"></ha-icon>' : ""}${esc(label)}</button>`;
  }

  _select(key, options, value, opts = {}) {
    const dis = opts.disabled ? 'disabled aria-disabled="true"' : "";
    return `<select ${opts.id ? `id="${opts.id}"` : ""} data-ch="${key}" data-f="${key}" ${dis} ${opts.label ? `aria-label="${esc(opts.label)}"` : ""}>${options
      .map(([v, l]) => `<option value="${esc(v)}" ${String(v) === String(value ?? "") ? "selected" : ""}>${esc(l)}</option>`)
      .join("")}</select>`;
  }

  _fold(id, title, summary, inner) {
    const open = !!this._ui.folds[id];
    return `<section class="fold">
      <button type="button" class="foldhead" aria-expanded="${open}" data-act="fold" data-arg="${id}" data-f="fold-${id}">
        <span class="grow"><span class="foldtitle">${title}</span><span class="foldsum">${summary}</span></span>
        <ha-icon icon="mdi:chevron-down" class="${open ? "rot" : ""}"></ha-icon></button>
      ${open ? `<div class="foldbody">${inner}</div>` : ""}</section>`;
  }

  // Generic actions ----------------------------------------------------------
  _a_menu() {
    this.dispatchEvent(new CustomEvent("hass-toggle-menu", { bubbles: true, composed: true }));
  }
  _a_tab(id) {
    this._go(`#${id}`);
  }
  _a_stay() {
    this._banner = null;
    this._render();
  }
  _a_discardLeave() {
    this._discardAndLeave();
  }
  async _a_saveLeave() {
    const to = this._banner && this._banner.to;
    const ok = this._route.view === "settings" ? await this._a_saveSettings() : await this._a_save();
    if (ok && to) location.hash = to;
  }
  _a_dismissBanner() {
    this._banner = null;
    this._render();
  }
  _a_retry(what) {
    if (what === "reload") location.reload();
    else if (what === "rules") {
      this._rules = null;
      this._render();
      this._loadRules();
    } else if (what === "recent") this._loadHistory();
    else if (what === "settings") this._loadSettings();
  }

  // =====================================================================
  // Rules tab
  // =====================================================================
  _summary(d) {
    if (d.source_type === "template") return "Custom template";
    const name = friendly(this._hass, d.entity_id) || "an entity";
    if (d.source_type === "numeric") {
      const st = this._hass.states[d.entity_id];
      const unit = (st && st.attributes && st.attributes.unit_of_measurement) || "";
      const op = { ">": "is above", "<": "is below", ">=": "is at least", "<=": "is at most", "==": "equals", "!=": "doesn't equal" }[
        d.operator || ">"
      ];
      return `When ${name} ${op} ${d.value ?? "…"}${unit ? " " + unit : ""}`;
    }
    return `When ${name} ${d.operator === "!=" ? "is not" : "is"} ${d.value ?? "…"}`;
  }

  _whoLabel(d) {
    const rec = asList(d.recipients);
    if (!rec.length) return "Everyone";
    const people = (this._meta && this._meta.persons) || [];
    return rec
      .map((r) => {
        const p = people.find((x) => x.person === r);
        return p ? p.name : r.startsWith("notify.") ? phoneName(r) : friendly(this._hass, r);
      })
      .join(", ");
  }

  _channelIcons(chans) {
    const on = CHANNELS.filter((c) => chans.includes(c.id));
    const label = on.length ? `Goes to ${on.map((c) => c.short).join(", ")}` : "No channels";
    return `<span class="chicons" role="img" aria-label="${esc(label)}" title="${esc(label)}">${CHANNELS.map(
      (c) => `<ha-icon icon="${c.icon}" class="${chans.includes(c.id) ? "" : "faint"}"></ha-icon>`
    ).join("")}</span>`;
  }

  _priOf(r) {
    return PRIORITIES.includes(r.data.priority) ? r.data.priority : "info";
  }

  _renderRules() {
    if (this._rulesError && !this._rules) return this._errorBox(this._rulesError, "rules");
    if (!this._rules) return this._skeleton();
    const ui = this._ui;
    const q = ui.q.trim().toLowerCase();
    const shown = this._rules.filter((r) => {
      const d = r.data;
      if (q && `${d.name || ""} ${this._summary(d)}`.toLowerCase().indexOf(q) < 0) return false;
      if (ui.filter === "active") return r.active && d.enabled !== false;
      if (ui.filter !== "all") return this._priOf(r) === ui.filter;
      return true;
    });
    const activeCount = this._rules.filter((r) => r.active && r.data.enabled !== false).length;
    const filters = [
      ["all", "All"],
      ["active", `Active now · ${activeCount}`],
      ["critical", "Critical"],
      ["warning", "Warning"],
      ["info", "Info"],
    ];
    const meta = this._meta || {};
    const note = meta.rules_file
      ? `<p class="filenote"><ha-icon icon="mdi:file-document-outline"></ha-icon><span>Saved to <span class="mono strong">${esc(
          meta.rules_file
        )}</span>. Changes made in that file show up here within a few seconds.</span></p>`
      : "";
    let list;
    if (!this._rules.length) {
      list = `<div class="card empty"><p class="strong">No rules yet</p><p class="muted">A rule watches something in your home and tells the right people when it happens.</p>
        ${this._readOnly ? "" : `<a class="btn primary" href="#rule/new" data-act="addRule"><ha-icon icon="mdi:plus"></ha-icon>Add your first rule</a>`}</div>`;
    } else if (!shown.length) {
      list = `<div class="card empty"><p class="strong">No rules match</p>
        <button type="button" class="btn" data-act="clearFilters" data-f="clearFilters">Clear search and filters</button></div>`;
    } else {
      list = PRIORITIES.map((p) => {
        const rs = shown.filter((r) => this._priOf(r) === p);
        if (!rs.length) return "";
        return `<section class="group"><h2 class="ghead pri-${p}">${PRI[p].label} <span class="muted">${rs.length}</span></h2>
          <div class="card list">${rs.map((r) => this._ruleRow(r)).join("")}</div></section>`;
      }).join("");
    }
    return `<div class="stack">
      <div class="toolbar">
        <label class="search"><ha-icon icon="mdi:magnify"></ha-icon>
          <input type="search" aria-label="Search rules" placeholder="Search rules" value="${esc(ui.q)}" data-in="ui.q" data-f="q"></label>
        <div class="chips" role="group" aria-label="Filter rules">${filters
          .map(([id, label]) => this._chip(label, ui.filter === id, "filter", id))
          .join("")}</div>
      </div>${note}${list}</div>`;
  }

  _ruleRow(r) {
    const d = r.data;
    const p = this._priOf(r);
    const id = r.subentry_id;
    const enabled = d.enabled !== false;
    const chans = asList(d.channels);
    const icon = d.icon || (r.effective && r.effective.icon) || PRI[p].icon;
    const ro = this._readOnly;
    const badges = [
      r.active && enabled ? `<span class="badge soft-${p}"><span class="dot"></span>Active ${esc(sinceLabel(r.active_since))}</span>` : "",
      r.testing ? `<span class="badge testing">Testing</span>` : "",
      d.deliver_as_digest ? `<span class="badge soft-info">Digest</span>` : "",
      !enabled ? `<span class="muted small">Turned off</span>` : "",
    ].join("");
    const menuOpen = this._ui.menu === id;
    const confirming = this._ui.confirm === id;
    return `<div class="row rulerow ${enabled ? "" : "dim"}">
      <div class="rowmain">
        <div class="ident">
          ${this._switch(enabled, "toggleRule", `Enable ${d.name || "rule"}`, { arg: id, disabled: ro })}
          <span class="tile soft-${p}"><ha-icon icon="${esc(icon)}"></ha-icon></span>
          <div class="minw"><a class="rname" href="#rule/${encodeURIComponent(id)}" data-act="edit" data-arg="${esc(id)}" data-f="name-${esc(id)}">${esc(
            d.name || "Untitled rule"
          )}</a><div class="muted">${esc(this._summary(d))}</div></div>
        </div>
        <div class="badges">${badges}</div>
        ${this._channelIcons(chans)}
        <span class="muted small who" title="${esc(chans.includes("mobile") ? this._whoLabel(d) : "")}">${esc(
          chans.includes("mobile") ? this._whoLabel(d) : ""
        )}</span>
        <div class="rowacts">
          <button type="button" class="btn small" data-act="test" data-arg="${esc(id)}" data-f="test-${esc(id)}">
            <ha-icon icon="${r.testing ? "mdi:stop" : "mdi:play"}"></ha-icon>${r.testing ? "Stop test" : "Test"}</button>
          <a class="link" href="#rule/${encodeURIComponent(id)}" data-act="edit" data-arg="${esc(id)}">Edit</a>
          <div class="menuwrap">
            <button type="button" class="iconbtn" aria-label="More actions for ${esc(d.name || "rule")}" aria-expanded="${menuOpen}"
              data-act="more" data-arg="${esc(id)}" data-f="more-${esc(id)}" ${ro ? "disabled" : ""}><ha-icon icon="mdi:dots-vertical"></ha-icon></button>
            ${
              menuOpen
                ? `<div class="menu" role="menu"><button type="button" role="menuitem" data-act="duplicate" data-arg="${esc(id)}" data-f="dup-${esc(
                    id
                  )}">Duplicate</button>
                   <button type="button" role="menuitem" class="danger-text" data-act="askDelete" data-arg="${esc(id)}">Delete…</button></div>`
                : ""
            }
          </div>
        </div>
      </div>
      ${
        confirming
          ? `<div class="confirm" role="alert"><span class="grow">Delete this rule?${
              this._meta && this._meta.rules_file ? " It is removed from rules.yaml too." : ""
            }</span>
          <button type="button" class="btn" data-act="keep" data-f="keep-${esc(id)}">Keep it</button>
          <button type="button" class="btn danger" data-act="deleteRule" data-arg="${esc(id)}">Delete rule</button></div>`
          : ""
      }
    </div>`;
  }

  _a_filter(id) {
    this._ui.filter = id;
    this._render();
  }
  _a_clearFilters() {
    this._ui.q = "";
    this._ui.filter = "all";
    this._render();
  }
  _a_addRule(_, el) {
    if (this._readOnly) return;
    this._go("#rule/new");
  }
  _a_edit(id) {
    this._go(`#rule/${encodeURIComponent(id)}`);
  }
  _a_more(id) {
    this._ui.menu = this._ui.menu === id ? null : id;
    this._render();
  }
  _a_askDelete(id) {
    this._ui.menu = null;
    this._ui.confirm = id;
    this._render();
  }
  _a_keep() {
    this._ui.confirm = null;
    this._render();
  }
  async _a_deleteRule(id) {
    this._ui.confirm = null;
    try {
      await this._ws("notification_center/rules/delete", { subentry_id: id });
      await this._loadRules();
    } catch (e) {
      this._banner = { kind: "error", text: (e && e.message) || "Delete failed." };
      this._render();
    }
  }
  async _a_toggleRule(id) {
    const r = this._ruleById(id);
    if (!r || this._readOnly) return;
    const rule = { ...r.data, enabled: r.data.enabled === false };
    r.data.enabled = rule.enabled; // optimistic
    this._render();
    try {
      await this._ws("notification_center/rules/update", { subentry_id: id, rule });
    } catch (e) {
      this._banner = { kind: "error", text: (e && e.message) || "Couldn't change the rule." };
    }
    await this._loadRules();
  }
  async _a_test(id) {
    const r = this._ruleById(id);
    if (!r) return;
    try {
      await this._ws("notification_center/rules/test", { subentry_id: id, enabled: !r.testing });
    } catch (e) {
      this._banner = { kind: "error", text: (e && e.message) || "Test failed." };
    }
    await this._loadRules();
  }
  async _a_duplicate(id) {
    const r = this._ruleById(id);
    this._ui.menu = null;
    if (!r) return;
    const name = `${r.data.name || "Rule"} (copy)`;
    const taken = new Set((this._rules || []).map((x) => x.data.dedup_tag || slugify(x.data.name)));
    let tag = slugify(name);
    for (let i = 2; taken.has(tag); i++) tag = `${slugify(name)}_${i}`;
    const rule = { ...clone(r.data), name, enabled: false, dedup_tag: tag };
    try {
      await this._ws("notification_center/rules/create", { rule });
    } catch (e) {
      this._banner = { kind: "error", text: (e && e.message) || "Couldn't duplicate the rule." };
    }
    await this._loadRules();
  }

  // =====================================================================
  // Recent tab
  // =====================================================================
  _renderRecent() {
    if (this._historyError) return this._errorBox(this._historyError, "recent");
    if (!this._history) return this._skeleton();
    const ui = this._recentUi;
    const q = ui.q.trim().toLowerCase();
    const items = this._history.filter((h) => {
      if (q && `${h.title || ""} ${h.message || ""} ${h.name || ""}`.toLowerCase().indexOf(q) < 0) return false;
      if (ui.filter !== "all") return (h.priority || "info") === ui.filter;
      return true;
    });
    const filters = [
      ["all", "All"],
      ["critical", "Critical"],
      ["warning", "Warning"],
      ["info", "Info"],
    ];
    const toolbar = `<div class="toolbar">
        <label class="search"><ha-icon icon="mdi:magnify"></ha-icon>
          <input type="search" aria-label="Search recent alerts" placeholder="Search recent alerts" value="${esc(ui.q)}" data-in="recent.q" data-f="rq"></label>
        <div class="chips" role="group" aria-label="Filter recent alerts">${filters
          .map(([id, label]) => this._chip(label, ui.filter === id, "rfilter", id))
          .join("")}</div></div>`;
    if (!this._history.length)
      return `<div class="stack">${toolbar}<div class="card empty"><p class="strong">Nothing has fired yet.</p>
        <p class="muted">Alerts show up here once they clear: when the problem resolves, someone dismisses or snoozes them, or a test ends.</p></div></div>`;
    if (!items.length)
      return `<div class="stack">${toolbar}<div class="card empty"><p class="strong">No alerts match</p>
        <button type="button" class="btn" data-act="clearRecent">Clear search and filters</button></div></div>`;
    const days = [];
    for (const h of items) {
      const label = dayLabel(h.created_at || h.cleared_at);
      let g = days.find((x) => x.label === label);
      if (!g) days.push((g = { label, items: [] }));
      g.items.push(h);
    }
    return `<div class="stack">${toolbar}${days
      .map(
        (g) => `<section class="group"><h2 class="ghead">${esc(g.label)} <span class="muted">${g.items.length}</span></h2>
        <div class="card list">${g.items.map((h) => this._historyRow(h)).join("")}</div></section>`
      )
      .join("")}</div>`;
  }

  _historyRow(h) {
    const p = PRIORITIES.includes(h.priority) ? h.priority : "info";
    const by = h.cleared_by ? ` by ${esc(h.cleared_by)}` : "";
    const ended = h.was_test
      ? ""
      : {
          resolved: "Resolved",
          dismissed: `Dismissed${by}`,
          snoozed: `Snoozed${by}`,
          action: "A button was pressed",
          test: "Test",
        }[h.reason] || esc(h.reason || "Cleared");
    const lasted = spanLabel(h.created_at, h.cleared_at);
    const rule = h.rule_id && this._ruleById(h.rule_id);
    const ruleLink = rule
      ? `<a class="link small" href="#rule/${encodeURIComponent(h.rule_id)}" data-act="edit" data-arg="${esc(h.rule_id)}">${esc(
          rule.data.name || "Rule"
        )}</a>`
      : h.name
      ? `<span class="muted small">${esc(h.name)}</span>`
      : "";
    return `<div class="row histrow">
      <span class="tile soft-${p}"><ha-icon icon="${esc(h.icon || PRI[p].icon)}"></ha-icon></span>
      <div class="minw grow"><div class="strong">${esc(h.title || h.name || "Alert")}</div>
        ${h.message ? `<div class="muted">${esc(h.message)}</div>` : ""}
        <div class="muted small">Fired ${esc(clockLabel(h.created_at))}${lasted ? ` · lasted ${esc(lasted)}` : ""}${ended ? ` · ${ended}` : ""}${
      h.was_test ? ' <span class="badge testing">Test</span>' : ""
    }</div></div>
      <div class="histmeta">${this._channelIcons(asList(h.channels))}${ruleLink}</div></div>`;
  }

  _a_rfilter(id) {
    this._recentUi.filter = id;
    this._render();
  }
  _a_clearRecent() {
    this._recentUi = { q: "", filter: "all" };
    this._render();
  }

  // =====================================================================
  // Rule editor
  // =====================================================================
  _openEditor(id) {
    this._ui.picker = null;
    this._ui.pickQ = "";
    this._ui.moreIcons = false;
    this._ui.folds = {};
    this._banner = null;
    this._testPrompt = false;
    if (!this._rules) {
      this._draft = null;
      return; // _start re-applies the hash once rules load
    }
    if (id === "new") {
      this._isNew = true;
      this._editingId = null;
      this._draft = {
        name: "",
        enabled: true,
        source_type: "state",
        entity_id: "",
        operator: "==",
        value: "",
        priority: "warning",
        channels: ["mobile", "bell", "wall"],
        presence_routing: "all",
        actions_follow_priority: true,
      };
    } else {
      const r = this._ruleById(id);
      this._isNew = false;
      this._editingId = id;
      this._draft = r ? clone(r.data) : null;
    }
    this._origKeys = new Set(Object.keys(this._draft || {}));
    this._saved = JSON.stringify(this._draft);
    this._renderTemplates();
  }

  // Set a rule field. Clearing a field the rule didn't have removes the key,
  // so opening and saving a rule untouched doesn't change rules.yaml.
  _setRule(field, value) {
    const d = this._draft;
    if (field.startsWith("ca.")) {
      const [, idx, key] = field.split(".");
      const list = (d.custom_actions = Array.isArray(d.custom_actions) ? d.custom_actions : []);
      const a = (list[Number(idx)] = list[Number(idx)] || {});
      if (value === "" && key !== "label") delete a[key];
      else a[key] = value;
      return;
    }
    if (value === "" && !this._origKeys.has(field)) delete d[field];
    else d[field] = value;
  }

  _rText(field) {
    // {text, error, pending} for a draft field, rendered if it's a template.
    const src = this._draft[field];
    if (src == null || src === "") return { text: "" };
    if (!hasTemplate(src)) return { text: String(src) };
    const hit = this._rendered[src];
    if (!hit) return { text: "", pending: true };
    return hit.error ? { text: "", error: hit.error } : { text: hit.text };
  }

  async _renderTemplates() {
    clearTimeout(this._typeTimer);
    const d = this._draft;
    if (!d) return this._render();
    const want = {};
    for (const f of TEMPLATE_FIELDS) {
      const src = d[f];
      if (hasTemplate(src) && !this._rendered[src]) want[f] = src;
    }
    if (Object.keys(want).length) {
      try {
        const res = await this._ws("notification_center/render", { templates: want });
        for (const [f, src] of Object.entries(want)) this._rendered[src] = (res.results || {})[f] || { error: "No result" };
      } catch (e) {
        for (const src of Object.values(want)) this._rendered[src] = { error: (e && e.message) || "Couldn't render" };
      }
    }
    this._render();
  }

  _shows(field, label = "Shows as") {
    const d = this._draft;
    if (!hasTemplate(d[field])) return "";
    const r = this._rText(field);
    if (r.error) return `<p class="hint err" id="shows-${field}"><span class="strong">Template error:</span> ${esc(r.error)}</p>`;
    return `<p class="hint" id="shows-${field}"><span class="ok strong">${label}</span> <span class="fg">${
      r.pending ? "…" : esc(r.text) || "(empty)"
    }</span></p>`;
  }

  _title() {
    const d = this._draft;
    return d.title_template ? this._rText("title_template").text : d.name || "New rule";
  }

  _message() {
    return this._rText("message_template").text;
  }

  // Firing status for the trigger, from live state or the rendered template.
  _nowLine() {
    const d = this._draft;
    if (d.source_type === "template") {
      if (!d.condition_template) return { cls: "muted", text: "Write a template that is true while the problem lasts." };
      const r = this._rText("condition_template");
      if (r.error) return { cls: "err", text: `The template has an error: ${r.error}` };
      if (r.pending) return { cls: "muted", text: "Checking the template…" };
      const on = ["true", "1", "on", "yes"].includes(String(r.text).trim().toLowerCase());
      return { cls: on ? "warnline" : "okline", text: `The template is ${on ? "true" : "false"} right now, so this rule ${on ? "would be firing." : "is not firing."}` };
    }
    if (!d.entity_id) return { cls: "muted", text: "Pick what to watch." };
    const st = this._hass.states[d.entity_id];
    if (!st) return { cls: "err", text: `${d.entity_id} doesn't exist in Home Assistant.` };
    const unit = (st.attributes && st.attributes.unit_of_measurement) || "";
    const on = evalTrigger(d.source_type, d.operator, d.value, st.state);
    return {
      cls: on ? "warnline" : "okline",
      text: `${friendly(this._hass, d.entity_id)} is ${st.state}${unit && d.source_type === "numeric" ? " " + unit : ""} right now, so this rule ${
        on ? "would be firing." : "is not firing."
      }`,
    };
  }

  _refreshLive() {
    const el = this.shadowRoot && this.shadowRoot.getElementById("nowline");
    if (!el || !this._draft) return;
    const n = this._nowLine();
    el.className = `nowline ${n.cls}`;
    const span = el.querySelector("span.t");
    if (span) span.textContent = n.text;
    const chip = this.shadowRoot.getElementById("nowchip");
    const st = this._hass.states[this._draft.entity_id];
    if (chip && st) chip.textContent = `Now: ${st.state}`;
  }

  _refreshTestingBanner() {
    // Called by the 10 s poll while the editor is open.
    if (!this._draft || this._isNew) return;
    const r = this._ruleById(this._editingId);
    const testing = !!(r && r.testing);
    if (testing !== !!this._wasTesting) {
      this._wasTesting = testing;
      this._render();
    }
  }

  _channels() {
    return asList(this._draft.channels);
  }

  _snoozeAllowed() {
    const d = this._draft;
    const follow = d.actions_follow_priority !== false;
    return follow ? (d.priority || "info") === "info" : !!d.snooze;
  }

  _dismissable() {
    const d = this._draft;
    const follow = d.actions_follow_priority !== false;
    return follow ? (d.priority || "info") === "info" : (d.clear_mode || "dismiss") === "dismiss";
  }

  _snoozeMinutes() {
    const v = this._draft.snooze_options;
    const list = Array.isArray(v) ? v : asList(v);
    const nums = list.map(Number).filter((n) => n > 0);
    return nums.length ? nums : (this._meta && this._meta.snooze_default) || [60, 240, 1440];
  }

  _pillText() {
    const d = this._draft;
    if (d.wall_takeover_text) return this._rText("wall_takeover_text").text;
    const status = d.live_activity ? this._rText("critical_text_template").text : "";
    return `${this._title()} ${status}`.trim();
  }

  _renderEditor(ro) {
    if (!this._rules) return `<div class="wrap">${this._skeleton()}</div>`;
    if (!this._draft)
      return `<div class="wrap"><div class="card empty"><p class="strong">This rule doesn't exist anymore.</p>
        <a class="btn" href="#rules" data-act="back">Back to rules</a></div></div>`;
    const d = this._draft;
    const dirty = this._dirty();
    const rule = this._ruleById(this._editingId);
    const testing = !!(rule && rule.testing);
    this._wasTesting = testing;
    const dis = this._readOnly ? 'disabled aria-disabled="true"' : "";
    const head = `<header class="edhead sticky">
      <button type="button" class="iconbtn" data-act="back" aria-label="Back to rules" data-f="back"><ha-icon icon="mdi:arrow-left"></ha-icon></button>
      <div class="namebox"><input type="text" class="nameinput" aria-label="Rule name" placeholder="Name this rule" value="${esc(d.name || "")}"
        data-in="r.name" data-f="r.name" ${dis}></div>
      <span id="status" class="status ${dirty ? "warn" : ""}">${this._isNew ? "Not saved yet" : dirty ? "Unsaved changes" : "Saved"}</span>
      <div class="actions">
        <button type="button" class="btn" data-act="testRule" data-f="testRule"><ha-icon icon="${testing ? "mdi:stop" : "mdi:play"}"></ha-icon>${
      testing ? "Stop test" : "Test"
    }</button>
        <button type="button" class="btn ghost" data-act="back" data-f="cancel">Cancel</button>
        <button type="button" id="save" class="btn primary ${dirty && !this._readOnly ? "" : "dim"}" data-act="save" data-f="save" ${
      this._readOnly ? 'aria-disabled="true"' : ""
    }>Save</button>
      </div></header>`;
    let banners = this._renderBanner();
    if (this._testPrompt)
      banners += `<div class="banner warn" role="alert"><span class="grow">${
        this._isNew
          ? "<strong>This rule hasn't been saved yet.</strong> Save it first so there is something to test."
          : "<strong>You have unsaved changes.</strong> Test runs the saved rule, so these edits would not be included."
      }</span>
        ${this._isNew ? "" : `<button type="button" class="btn" data-act="testSaved">Test the saved version</button>`}
        <button type="button" class="btn primary" data-act="saveAndTest" ${dis}>Save and test</button></div>`;
    if (testing) {
      const names = CHANNELS.filter((c) => this._channels().includes(c.id)).map((c) => c.short).join(", ") || "nowhere";
      banners += `<div class="banner testing" role="status"><span class="grow"><strong class="warn">Testing.</strong> A test alert is showing on ${esc(
        names
      )}, marked TEST. It stays until you stop it, or for 10 minutes.</span>
        <button type="button" class="btn" data-act="stopTest">Stop test</button></div>`;
    }
    return `<div class="wrap edwrap">${head}${ro}${banners}
      <div class="edgrid"><main class="edmain">
        ${this._secWhen()}${this._secUrgency()}${this._secWhere()}${this._secSay()}
        <h2 class="ghead">More options</h2>
        ${this._foldDismiss()}${this._foldLive()}${this._foldTiming()}${this._foldButtons()}${this._foldDigest()}${this._foldExpert()}
      </main><aside class="side" aria-label="Preview">${this._preview()}</aside></div></div>`;
  }

  // --- Section 1: When should it fire? ----------------------------------
  _secWhen() {
    const d = this._draft;
    const ro = this._readOnly;
    const dis = ro ? 'disabled aria-disabled="true"' : "";
    const types = [
      ["state", "A state", "Something is on, open, home…"],
      ["numeric", "A number", "Goes above or below a value"],
      ["template", "A template", "Your own Jinja condition"],
    ];
    const cards = types
      .map(
        ([id, label, sub]) => `<button type="button" class="pick ${d.source_type === id ? "on" : ""}" aria-pressed="${d.source_type === id}"
        data-act="source" data-arg="${id}" data-f="source-${id}" ${dis}><span class="strong">${label}</span><span class="muted small">${sub}</span></button>`
      )
      .join("");
    let body = "";
    if (d.source_type === "template") {
      body = `<div><label class="lbl" for="f-cond">Fires while this template is true</label>
        <textarea id="f-cond" class="mono" rows="3" data-in="r.condition_template" data-f="r.condition_template" ${dis}>${esc(
          d.condition_template || ""
        )}</textarea></div>`;
    } else {
      const st = this._hass.states[d.entity_id];
      const unit = (st && st.attributes && st.attributes.unit_of_measurement) || "";
      body = `${this._entityField("trigger", "Watch this", d.entity_id, true)}`;
      if (d.source_type === "numeric") {
        body += `<div class="two"><div><label class="lbl" for="f-nop">Condition</label>${this._select("r.operator", NUMERIC_OPS, d.operator || ">", {
          id: "f-nop",
          disabled: ro,
        })}</div>
          <div><label class="lbl" for="f-num">Threshold${unit ? ` (${esc(unit)})` : ""}</label>
          <input id="f-num" type="text" inputmode="decimal" value="${esc(d.value ?? "")}" data-in="r.value" data-f="r.value" ${dis}></div></div>`;
      } else {
        const sugg = stateSuggestions(d.entity_id, st);
        const chips = sugg.map((v) => this._chip(v, String(d.value ?? "") === v, "value", v, { disabled: ro })).join("");
        body += `<div class="two"><div><label class="lbl" for="f-op">Condition</label>${this._select("r.operator", STATE_OPS, d.operator || "==", {
          id: "f-op",
          disabled: ro,
        })}</div>
          <div><span class="lbl" id="l-val">Value</span>${
            chips ? `<div class="chips" role="group" aria-labelledby="l-val">${chips}</div>` : ""
          }
          <input type="text" aria-label="Value" placeholder="${sugg.length ? "Or type another value" : "Type the state, e.g. open"}" value="${esc(
            sugg.includes(String(d.value ?? "")) && this._focusKey !== "r.value-typed" ? "" : d.value ?? ""
          )}" data-in="r.value" data-f="r.value-typed" ${dis} class="mt">
          <p class="hint">${sugg.length ? "Suggested from this entity's known states." : "Type the exact state this entity reports."}</p></div></div>`;
      }
    }
    const now = this._nowLine();
    return `<section class="card" aria-labelledby="h-when">
      <div class="rowb"><h2 id="h-when">When should it fire?</h2>
        <div class="inline muted small">Rule is on ${this._switch(d.enabled !== false, "flip", "Rule is on", { arg: "enabled", disabled: ro })}</div></div>
      <div class="picks3" role="group" aria-label="Trigger type">${cards}</div>
      ${body}
      <p id="nowline" class="nowline ${now.cls}"><span class="dot"></span><span class="t">${esc(now.text)}</span></p>
    </section>`;
  }

  // Searchable entity field (fallback for ha-entity-picker, which is not a
  // stable API for custom panels).
  _entityField(key, label, value, showNow, domains) {
    const ro = this._readOnly;
    const st = value ? this._hass.states[value] : null;
    const open = this._ui.picker === key;
    let list = "";
    if (open) {
      const q = (this._ui.pickQ || "").toLowerCase();
      const all = Object.values(this._hass.states)
        .filter((s) => !domains || domains.includes(s.entity_id.split(".")[0]))
        .filter((s) => !q || `${s.attributes.friendly_name || ""} ${s.entity_id}`.toLowerCase().includes(q))
        .sort((a, b) => String(a.attributes.friendly_name || a.entity_id).localeCompare(String(b.attributes.friendly_name || b.entity_id)))
        .slice(0, 60);
      list = `<div class="dropdown" role="listbox" aria-label="Entities">
        <input type="search" aria-label="Search entities" placeholder="Search by name or entity id" value="${esc(this._ui.pickQ || "")}"
          data-in="ui.pickQ" data-f="pickq-${key}">
        ${all
          .map(
            (s) => `<button type="button" role="option" class="opt" data-act="pickEntity" data-arg="${esc(key + "|" + s.entity_id)}" data-f="opt-${esc(
              s.entity_id
            )}"><span class="minw grow"><span class="block">${esc(s.attributes.friendly_name || s.entity_id)}</span>
            <span class="mono muted block">${esc(s.entity_id)}</span></span><span class="muted small">${esc(s.state)}</span></button>`
          )
          .join("") || `<p class="muted small pad">No entities match.</p>`}
      </div>`;
    }
    return `<div class="pickwrap"><span class="lbl" id="l-${key}">${label}</span>
      <button type="button" class="entityfield" aria-labelledby="l-${key}" aria-expanded="${open}" data-act="openPicker" data-arg="${key}" data-f="ef-${key}" ${
      ro ? "disabled" : ""
    }>
        <span class="minw grow">${
          value
            ? `<span class="block strong">${esc(friendly(this._hass, value))}</span><span class="mono muted block">${esc(value)}</span>`
            : `<span class="muted">Choose an entity…</span>`
        }</span>
        ${showNow && st ? `<span class="nowchip" id="nowchip">Now: ${esc(st.state)}</span>` : ""}
        <ha-icon icon="mdi:chevron-down"></ha-icon></button>${list}</div>`;
  }

  // --- Section 2: How urgent is it? ---------------------------------------
  _secUrgency() {
    const d = this._draft;
    const defs = (this._meta && this._meta.priority_defaults) || {};
    const cards = PRIORITIES.map((p) => {
      const on = (d.priority || "info") === p;
      const df = defs[p] || {};
      const cool = df.cooldown ? `every ${df.cooldown} min` : "no cooldown";
      return `<button type="button" class="pick pri ${on ? "on" : ""}" aria-pressed="${on}" data-act="priority" data-arg="${p}" data-f="pri-${p}" ${
        this._readOnly ? "disabled" : ""
      }>
        <span class="inline"><span class="solid" style="background:${PRI[p].solid};color:${PRI[p].onSolid}"><ha-icon icon="${PRI[p].icon}"></ha-icon></span>
        <span class="strong big">${PRI[p].label}</span></span>
        <span class="muted small">${PRI[p].desc}</span>
        <span class="muted xsmall">${PUSH_LABEL[df.push] || ""} · ${cool}</span></button>`;
    }).join("");
    return `<section class="card" aria-labelledby="h-pri"><h2 id="h-pri">How urgent is it?</h2>
      <div class="picks3 wide" role="group" aria-label="Priority">${cards}</div></section>`;
  }

  // --- Section 3: Where does it go? -------------------------------------
  _secWhere() {
    const chans = this._channels();
    const rows = CHANNELS.map((c) => {
      const on = chans.includes(c.id);
      let inner = "";
      if (on && c.id === "mobile") inner = this._mobileBody();
      if (on && c.id === "wall") inner = this._wallBody();
      if (on && c.id === "tts") inner = this._speakerBody();
      return `<div class="chrow ${on ? "on" : ""}"><div class="rowb">
        <div class="inline"><ha-icon icon="${c.icon}" class="${on ? "pfg" : "muted"}"></ha-icon><div><div class="strong">${c.label}</div><div class="muted small">${c.desc}</div></div></div>
        ${this._switch(on, "channel", c.label, { arg: c.id, disabled: this._readOnly })}</div>
        ${inner ? `<div class="chbody">${inner}</div>` : ""}</div>`;
    }).join("");
    return `<section class="card" aria-labelledby="h-where"><h2 id="h-where">Where does it go?</h2>${rows}</section>`;
  }

  _mobileBody() {
    const d = this._draft;
    const people = (this._meta && this._meta.persons) || [];
    const sel = asList(d.recipients);
    const ro = this._readOnly;
    if (!people.length && !sel.length)
      return `<span class="lbl">Who gets it</span><p class="hint m0">Every phone in <a class="link" href="#settings" data-act="tab" data-arg="settings">Settings</a>.
        Add people and their phones there to send a rule to one person.</p>`;
    const chips =
      this._chip("Everyone", !sel.length, "who", "", { disabled: ro }) +
      people.map((p) => this._chip(p.name, sel.includes(p.person), "who", p.person, { disabled: ro })).join("") +
      sel
        .filter((s) => !people.some((p) => p.person === s))
        .map((s) => this._chip(s.startsWith("notify.") ? phoneName(s) : friendly(this._hass, s), true, "who", s, { disabled: ro }))
        .join("");
    return `<span class="lbl" id="l-who">Who gets it</span><div class="chips" role="group" aria-labelledby="l-who">${chips}</div>
      <p class="hint">People and their phones are managed in <a class="link" href="#settings" data-act="tab" data-arg="settings">Settings</a>.</p>`;
  }

  _wallNames(type, current) {
    const m = this._meta || {};
    const names = [...((type === "page" ? m.wall_pages : m.wall_sheets) || [])];
    if (current && !names.includes(current)) names.push(current);
    return names.map((n) => [n, n]);
  }

  _wallSounds(current) {
    const names = [...(((this._meta && this._meta.wall_sounds) || ["chime"]))];
    if (current && !names.includes(current)) names.push(current);
    return names.map((n) => [n, n === "chime" ? "chime (default sound)" : n]);
  }

  _wallBody() {
    const d = this._draft;
    const ro = this._readOnly;
    const w = parseWallAction(d.wall_action);
    const pri = d.priority || "info";
    const canPill = pri === "critical" || pri === "warning";
    const pillOn = canPill && !!d.wall_takeover;
    const max = (this._meta && this._meta.takeover_max_chars) || 28;
    const pill = this._pillText();
    const over = pill.length > max;
    const target = parseTarget(d.wall_takeover_target);
    let react = `<div class="two"><div><label class="lbl" for="f-wt">Open</label>${this._select(
      "fn.wallType",
      [
        ["none", "Nothing"],
        ["sheet", "A sheet"],
        ["page", "A page"],
      ],
      w.type,
      { id: "f-wt", disabled: ro }
    )}</div>${
      w.type !== "none"
        ? `<div><label class="lbl" for="f-wn">Which one</label>${this._select("fn.wallName", [["", "Choose…"], ...this._wallNames(w.type, w.name)], w.name, {
            id: "f-wn",
            disabled: ro,
          })}</div>`
        : ""
    }</div>
      <div class="two mt"><div><label class="lbl" for="f-ws">Play a sound</label>${this._select(
        "fn.wallSound",
        [["", "No sound"], ...this._wallSounds(w.sound)],
        w.sound,
        { id: "f-ws", disabled: ro }
      )}</div></div>
      <p class="hint m0">Your panels decide what each sound is and how loud it plays. Sound names are listed in
        <a class="link" href="#settings" data-act="tab" data-arg="settings">Settings</a> → Advanced.</p>
      <p class="hint m0">${d.wall_action ? `Saved as <span class="mono fg">${esc(d.wall_action)}</span>` : "The panels only list it in their Notifications sheet."}</p>`;
    let pillBody = "";
    if (!canPill)
      pillBody = `<p class="note info mt">Info alerts can't take over the status bar. Set the priority to Warning or Critical to use the pill.</p>`;
    else if (pillOn)
      pillBody = `<div class="stack14 mt">
        <div><div class="rowb"><label class="lbl" for="f-pill">Pill text</label><span class="small strong ${over ? "warn" : "muted"}" id="pillcount">${pill.length} / ${max}</span></div>
          <input id="f-pill" type="text" placeholder="${esc(this._title() + (d.live_activity ? " " + this._rText("critical_text_template").text : ""))} (default)"
            value="${esc(d.wall_takeover_text || "")}" data-in="r.wall_takeover_text" data-f="r.wall_takeover_text" ${ro ? "disabled" : ""}>
          <p class="hint ${over ? "warn" : ""}">${
        over ? "Too long. The panel cuts the pill off after about 28 characters." : "Leave blank to use the title and status text."
      }</p>${this._shows("wall_takeover_text")}</div>
        <div class="two"><div><label class="lbl" for="f-pt">Tapping the pill opens</label>${this._select(
          "fn.pillType",
          [
            ["default", "Notifications sheet (default)"],
            ["sheet", "A sheet"],
            ["page", "A page"],
          ],
          target.type,
          { id: "f-pt", disabled: ro }
        )}</div>${
        target.type !== "default"
          ? `<div><label class="lbl" for="f-pn">Which one</label>${this._select("fn.pillName", [["", "Choose…"], ...this._wallNames(target.type, target.name)], target.name, {
              id: "f-pn",
              disabled: ro,
            })}</div>`
          : ""
      }</div>
        <p class="hint m0">One pill shows at a time. Critical beats warning, then the oldest alert wins.</p></div>`;
    return `<div><h3>When it fires, make the panels react</h3><p class="hint m0 mb">A one-time reaction at the moment the alert starts.</p>${react}</div>
      <div class="divtop"><div class="rowb"><div><h3>While it's active, take over the status bar</h3>
        <p class="hint m0">Replaces the status chips with one coloured pill for as long as the alert lasts. The pill only shows status. It does not chime or open anything; that is the reaction above.</p></div>
        ${canPill ? this._switch(pillOn, "flip", "Take over the status bar", { arg: "wall_takeover", disabled: ro }) : ""}</div>${pillBody}</div>`;
  }

  _speakerBody() {
    const d = this._draft;
    const ro = this._readOnly;
    const sel = asList(d.tts_targets);
    const players = Object.values(this._hass.states)
      .filter((s) => s.entity_id.startsWith("media_player."))
      .sort((a, b) => String(a.attributes.friendly_name || a.entity_id).localeCompare(String(b.attributes.friendly_name || b.entity_id)));
    const ids = players.map((p) => p.entity_id);
    const chips =
      players.map((p) => this._chip(p.attributes.friendly_name || p.entity_id, sel.includes(p.entity_id), "speaker", p.entity_id, { disabled: ro })).join("") +
      sel.filter((s) => !ids.includes(s)).map((s) => this._chip(s, true, "speaker", s, { disabled: ro })).join("");
    return `<div><span class="lbl" id="l-spk">Announce on</span>${
      chips ? `<div class="chips" role="group" aria-labelledby="l-spk">${chips}</div>` : `<p class="muted small">No speakers found in Home Assistant.</p>`
    }
      <p class="hint">${sel.length ? "" : "None picked, so it uses the default speakers. "}Default speakers are set in <a class="link" href="#settings" data-act="tab" data-arg="settings">Settings</a>.</p></div>
      <div><label class="lbl" for="f-tts">What it says out loud</label>
      <textarea id="f-tts" rows="2" placeholder="Leave blank to speak the message" data-in="r.tts_message" data-f="r.tts_message" ${ro ? "disabled" : ""}>${esc(
        d.tts_message || ""
      )}</textarea>${this._shows("tts_message")}</div>`;
  }

  // --- Section 4: What does it say? -------------------------------------
  _secSay() {
    const d = this._draft;
    const ro = this._readOnly;
    const dis = ro ? 'disabled aria-disabled="true"' : "";
    const icon = d.icon || "";
    const tiles = COMMON_ICONS.map(
      (ic) => `<button type="button" class="itile ${icon === ic ? "on" : ""}" aria-pressed="${icon === ic}" aria-label="${esc(
        ic.replace("mdi:", "").replace(/-/g, " ")
      )}" data-act="icon" data-arg="${ic}" data-f="icon-${ic}" ${dis}><ha-icon icon="${ic}"></ha-icon></button>`
    ).join("");
    const pri = d.priority || "info";
    const colors = [...COLORS];
    if (d.color && !colors.some(([v]) => v.toLowerCase() === String(d.color).toLowerCase())) colors.push([d.color, `Custom ${d.color}`]);
    const swatches = colors
      .map(([v, name]) => {
        const on = String(d.color || "").toLowerCase() === v.toLowerCase();
        const hex = v || PRI[pri].solid;
        return `<button type="button" class="swatch ${on ? "on" : ""}" aria-pressed="${on}" aria-label="${esc(name)}" data-act="color" data-arg="${esc(v)}" data-f="color-${esc(
          v || "auto"
        )}" ${dis}><span style="background:${esc(hex)}">${on ? '<ha-icon icon="mdi:check"></ha-icon>' : ""}</span></button>`;
      })
      .join("");
    const phoneOverride = !!d.mobile_navigation_target || this._ui.phonePath;
    const moreIcons = this._ui.moreIcons
      ? `<div id="iconpicker-slot" class="mt"><input type="text" class="mono" aria-label="Icon name" placeholder="mdi:bell" value="${esc(icon)}"
          data-in="r.icon" data-f="r.icon" ${dis}><p class="hint">Any Material Design icon name, like mdi:fire or mdi:door-open.</p></div>`
      : "";
    return `<section class="card" aria-labelledby="h-say"><h2 id="h-say">What does it say?</h2>
      <div><label class="lbl" for="f-title">Title</label><input id="f-title" type="text" placeholder="${esc(d.name || "Uses the rule name")}"
        value="${esc(d.title_template || "")}" data-in="r.title_template" data-f="r.title_template" ${dis}>${this._shows("title_template")}</div>
      <div><div class="rowb"><label class="lbl" for="f-msg">Message</label>
        <button type="button" class="link small" data-act="openPicker" data-arg="insert" data-f="insert" ${dis}>Insert a live value</button></div>
        ${this._ui.picker === "insert" ? this._entityField("insert", "Pick a value to insert", "", false) : ""}
        <textarea id="f-msg" rows="2" data-in="r.message_template" data-f="r.message_template" ${dis}>${esc(d.message_template || "")}</textarea>
        ${this._shows("message_template")}</div>
      <div class="two">
        <div><span class="lbl" id="l-icon">Icon</span><div class="chips tight" role="group" aria-labelledby="l-icon">${tiles}</div>
          <p class="hint"><span class="mono">${esc(icon || PRI[pri].icon + " (priority default)")}</span> ·
          <button type="button" class="link small" data-act="moreIcons" data-f="moreIcons" ${dis}>${this._ui.moreIcons ? "Fewer icons" : "More icons"}</button></p>${moreIcons}</div>
        <div><span class="lbl" id="l-color">Colour</span><div class="chips tight" role="group" aria-labelledby="l-color">${swatches}</div>
          <p class="hint">${d.color ? `Custom colour ${esc(d.color)}. Used on the card and wall panels.` : `Using the ${PRI[pri].label.toLowerCase()} colour.`}</p></div>
      </div>
      <div><label class="lbl" for="f-tap">Tapping it opens</label>
        <input id="f-tap" class="mono" type="text" placeholder="/lovelace/home" value="${esc(d.navigation_target || "")}"
          data-in="r.navigation_target" data-f="r.navigation_target" ${dis}>
        <div class="rowb mt"><span>Open a different page on phones</span>${this._switch(phoneOverride, "phonePath", "Open a different page on phones", {
          disabled: ro,
        })}</div>
        ${
          phoneOverride
            ? `<input class="mono" type="text" aria-label="Page to open on phones" placeholder="/mobile-dash/home" value="${esc(
                d.mobile_navigation_target || ""
              )}" data-in="r.mobile_navigation_target" data-f="r.mobile_navigation_target" ${dis}>`
            : ""
        }</div></section>`;
  }

  _mountIconPicker() {
    // Prefer HA's own icon picker when the frontend has loaded it.
    if (!this._ui.moreIcons || !customElements.get("ha-icon-picker")) return;
    const slot = this.shadowRoot.getElementById("iconpicker-slot");
    if (!slot || this._readOnly) return;
    const picker = document.createElement("ha-icon-picker");
    picker.hass = this._hass;
    picker.value = this._draft.icon || "";
    picker.label = "Icon";
    picker.addEventListener("value-changed", (e) => {
      this._setRule("icon", (e.detail && e.detail.value) || "");
      this._render();
    });
    slot.innerHTML = "";
    slot.appendChild(picker);
  }

  // --- More options (folds) ------------------------------------------------
  _foldDismiss() {
    const d = this._draft;
    const ro = this._readOnly;
    const follow = d.actions_follow_priority !== false;
    const pri = d.priority || "info";
    const allowed = this._snoozeAllowed();
    const mins = this._snoozeMinutes();
    const line = mins.map(durationLabel).join(" · ");
    const sum = `${follow ? "Follows priority" : "Custom"} · ${this._dismissable() ? "can be dismissed" : "stays until resolved"}${
      allowed ? ` · snooze ${line}` : ""
    }`;
    let inner = `<div class="rowb"><div><div>Follow the priority</div><div class="hint m0">${
      pri === "info" ? "Info alerts can be dismissed and snoozed." : `${PRI[pri].label} alerts stay until the condition resolves. Nobody can dismiss them.`
    }</div></div>${this._switch(follow, "flip", "Follow the priority", { arg: "actions_follow_priority", disabled: ro })}</div>`;
    if (!follow) {
      const cm = d.clear_mode || "dismiss";
      inner += `<div class="two" role="group" aria-label="Clearing">${[
        ["locked", "Locked", "Stays until the condition resolves."],
        ["dismiss", "Dismissible", "People can clear it."],
      ]
        .map(
          ([v, l, s]) => `<button type="button" class="pick ${cm === v ? "on" : ""}" aria-pressed="${cm === v}" data-act="clearMode" data-arg="${v}" data-f="cm-${v}" ${
            ro ? "disabled" : ""
          }><span class="strong">${l}</span><span class="muted small">${s}</span></button>`
        )
        .join("")}</div>
        <div class="rowb"><span>Allow snooze</span>${this._switch(!!d.snooze, "flip", "Allow snooze", { arg: "snooze", disabled: ro })}</div>`;
    }
    if (allowed) {
      inner += `<div><span class="lbl" id="l-snz">Snooze choices</span><div class="chips" role="group" aria-labelledby="l-snz">${SNOOZE_CHOICES.map((m) =>
        this._chip(durationLabel(m), mins.includes(m), "snoozeOpt", String(m), { disabled: ro })
      ).join("")}</div>
        <p class="hint">Offered on phones, the card and the wall panels: ${esc(line) || "none picked"}</p></div>`;
    } else {
      inner += `<p class="hint m0">Snooze choices appear here when snoozing is allowed. With the priority defaults that means Info rules.</p>`;
    }
    return this._fold("dismiss", "Dismissing and snoozing", esc(sum), inner);
  }

  _foldLive() {
    const d = this._draft;
    const ro = this._readOnly;
    const dis = ro ? 'disabled aria-disabled="true"' : "";
    const chip = this._rText("critical_text_template").text;
    const sum = d.live_activity ? `On · progress bar${chip ? ` showing ${chip}` : ""}` : "Off";
    let inner = `<div class="rowb"><div><div>Show as a Live Activity</div><div class="hint m0">For ongoing things like a battery draining. Shows a progress bar on phones and the card.</div></div>
      ${this._switch(!!d.live_activity, "flip", "Show as a Live Activity", { arg: "live_activity", disabled: ro })}</div>`;
    if (d.live_activity) {
      const prog = this._rText("progress_template").text;
      const max = this._rText("progress_max_template").text || "100";
      inner += `<div class="two"><div><label class="lbl" for="f-prog">Progress value</label><input id="f-prog" class="mono" type="text" value="${esc(
        d.progress_template || ""
      )}" data-in="r.progress_template" data-f="r.progress_template" ${dis}></div>
        <div><label class="lbl" for="f-max">Out of</label><input id="f-max" class="mono" type="text" placeholder="100" value="${esc(
          d.progress_max_template || ""
        )}" data-in="r.progress_max_template" data-f="r.progress_max_template" ${dis}></div></div>
        ${d.progress_template ? `<p class="hint m0"><span class="ok strong">Shows as</span> <span class="fg">${esc(prog || "…")} of ${esc(max)}</span></p>` : ""}
        <div><label class="lbl" for="f-chip">Status text</label><input id="f-chip" class="mono" type="text" value="${esc(d.critical_text_template || "")}"
          data-in="r.critical_text_template" data-f="r.critical_text_template" ${dis}>
          <p class="hint">Short text beside the title, also used in the wall pill.</p>${this._shows("critical_text_template")}</div>
        <div class="rowb"><span>Show a live countdown</span>${this._switch(!!d.chronometer, "flip", "Show a live countdown", { arg: "chronometer", disabled: ro })}</div>
        ${
          d.chronometer
            ? `<div><label class="lbl" for="f-when">Counts down to</label><input id="f-when" class="mono" type="text" placeholder="A template that gives a time"
            value="${esc(d.when_template || "")}" data-in="r.when_template" data-f="r.when_template" ${dis}></div>`
            : ""
        }
        <div><label class="lbl" for="f-timeout">End the activity after (minutes)</label><input id="f-timeout" type="text" inputmode="numeric"
          placeholder="Only when it resolves (default)" value="${esc(d.activity_timeout ?? "")}" data-in="r.activity_timeout" data-f="r.activity_timeout" ${dis}></div>`;
    }
    return this._fold("live", "Live progress", esc(sum), inner);
  }

  _foldTiming() {
    const d = this._draft;
    const ro = this._readOnly;
    const dis = ro ? 'disabled aria-disabled="true"' : "";
    const pri = d.priority || "info";
    const defs = (this._meta && this._meta.priority_defaults) || {};
    const coolDefault = (defs[pri] || {}).cooldown;
    const coolPh = coolDefault ? `${coolDefault} min (default)` : "No cooldown (default)";
    const qDefault = ((this._meta && this._meta.quiet_defaults) || {})[pri];
    const qKey = d.quiet_hours_behavior || "";
    const qShown = qKey || qDefault || "ignore";
    const qHint = (QUIET.find(([v]) => v === qShown) || [])[2] || "";
    const quietOpts = QUIET.map(([v, l]) => [v, v ? l : `${l} (${(QUIET.find(([x]) => x === qDefault) || [, "Send as normal"])[1].toLowerCase()})`]);
    const pres = d.presence_routing || "all";
    const autoClear = d.auto_clear !== false;
    const sum = `${autoClear ? "Clears when resolved" : "Stays after it resolves"} · ${
      d.cooldown ? `reminds every ${d.cooldown} min` : coolDefault ? `every ${coolDefault} min` : "no cooldown"
    }`;
    const inner = `<div class="rowb"><div><div>Clear it when the problem resolves</div><div class="hint m0">Removes the alert everywhere once the trigger is no longer true.</div></div>
      ${this._switch(autoClear, "flip", "Clear it when the problem resolves", { arg: "auto_clear", disabled: ro })}</div>
      <div class="two"><div><label class="lbl" for="f-quiet">During quiet hours</label>${this._select("r.quiet_hours_behavior", quietOpts, qKey, {
        id: "f-quiet",
        disabled: ro,
      })}<p class="hint">${esc(qHint)}</p>${
        pri === "critical" && qKey && qKey !== "ignore"
          ? `<p class="hint warn">Critical alerts usually come through at night. With this setting this one won't wake anyone.</p>`
          : ""
      }</div>
        <div><label class="lbl" for="f-pres">Who gets it, by presence</label>${this._select(
          "r.presence_routing",
          PRESENCE.map(([v, l]) => [v, l]),
          pres,
          { id: "f-pres", disabled: ro }
        )}<p class="hint">${esc((PRESENCE.find(([v]) => v === pres) || [])[2] || "")}</p></div></div>
      <div class="two"><div><label class="lbl" for="f-cool">Remind again every (minutes)</label><input id="f-cool" type="text" inputmode="numeric" placeholder="${esc(
        coolPh
      )}" value="${esc(d.cooldown ?? "")}" data-in="r.cooldown" data-f="r.cooldown" ${dis}></div>
        <div><label class="lbl" for="f-esc">Escalate if still active after (minutes)</label><input id="f-esc" type="text" inputmode="numeric" placeholder="Never (default)"
          value="${esc(Number(d.escalation_after) === 0 && this._focusKey !== "r.escalation_after" ? "" : d.escalation_after ?? "")}"
          data-in="r.escalation_after" data-f="r.escalation_after" ${dis}><p class="hint">Re-sends it every so many minutes while it lasts. Empty or 0 means never.</p></div></div>`;
    return this._fold("timing", "Timing and who's home", esc(sum), inner);
  }

  _foldButtons() {
    const d = this._draft;
    const ro = this._readOnly;
    const dis = ro ? 'disabled aria-disabled="true"' : "";
    const list = Array.isArray(d.custom_actions) ? d.custom_actions : [];
    const sum = list.length ? `${list.length} button${list.length === 1 ? "" : "s"}` : "None";
    const cards = list
      .map((a, i) => {
        const domain = a.entity ? String(a.entity).split(".")[0] : "";
        const svcs = domain && this._hass.services && this._hass.services[domain] ? Object.keys(this._hass.services[domain]).sort() : [];
        const svc = a.service || "";
        const svcField =
          a.entity && svcs.length
            ? this._select(`r.ca.${i}.service`, [["", "Choose an action…"], ...svcs.map((s) => [`${domain}.${s}`, s.replace(/_/g, " ")]), ...(svc && !svc.startsWith(domain + ".") ? [[svc, svc]] : [])], svc, {
                disabled: ro,
                label: "Does this",
              })
            : `<input class="mono" type="text" aria-label="Does this" placeholder="script.reset_filter" value="${esc(svc)}" data-in="r.ca.${i}.service" data-f="ca-svc-${i}" ${dis}>`;
        return `<div class="subcard">
          <div class="two"><div><label class="lbl" for="ca-l-${i}">Button label</label><input id="ca-l-${i}" type="text" value="${esc(a.label || "")}"
            data-in="r.ca.${i}.label" data-f="ca-l-${i}" ${dis}></div>
            <div><label class="lbl" for="ca-i-${i}">Icon</label><div class="inline"><ha-icon icon="${esc(a.icon || "mdi:gesture-tap")}"></ha-icon>
              <input id="ca-i-${i}" class="mono" type="text" placeholder="mdi:check" value="${esc(a.icon || "")}" data-in="r.ca.${i}.icon" data-f="ca-i-${i}" ${dis}></div></div></div>
          <div class="two"><div>${this._entityField(`ca:${i}`, "Acts on", a.entity || "", false)}
              ${a.entity ? `<button type="button" class="link small" data-act="caNoEntity" data-arg="${i}" ${dis}>Use a script or service instead</button>` : `<p class="hint m0">Or leave it empty and type a script or service.</p>`}</div>
            <div><span class="lbl">Does this</span>${svcField}</div></div>
          <div><label class="lbl" for="ca-c-${i}">Ask first (optional)</label><input id="ca-c-${i}" type="text" placeholder="Close the garage door?" value="${esc(a.confirm || "")}"
            data-in="r.ca.${i}.confirm" data-f="ca-c-${i}" ${dis}></div>
          <div><button type="button" class="link danger-text" data-act="caRemove" data-arg="${i}" ${dis}>Remove button</button></div></div>`;
      })
      .join("");
    const inner = `<p class="hint m0">Let people act from the alert, like Close garage or I replaced it. Running a button clears the alert.</p>${cards}
      <div><button type="button" class="btn" data-act="caAdd" data-f="caAdd" ${dis}><ha-icon icon="mdi:plus"></ha-icon>Add a button</button></div>`;
    return this._fold("buttons", "Buttons on the notification", esc(sum), inner);
  }

  _foldDigest() {
    const d = this._draft;
    const ro = this._readOnly;
    const dis = ro ? 'disabled aria-disabled="true"' : "";
    const sum = d.deliver_as_digest ? `On${d.digest_group ? ` · ${d.digest_group}` : ""}` : "Off, sent on its own";
    let inner = `<div class="rowb"><div><div>Deliver in the daily digest</div><div class="hint m0">Rolls this into one summary instead of sending it on its own. Digest time is set in Settings.</div></div>
      ${this._switch(!!d.deliver_as_digest, "flip", "Deliver in the daily digest", { arg: "deliver_as_digest", disabled: ro })}</div>`;
    if (d.deliver_as_digest)
      inner += `<div><label class="lbl" for="f-dg">Group with</label><input id="f-dg" type="text" placeholder="Maintenance" value="${esc(d.digest_group || "")}"
        data-in="r.digest_group" data-f="r.digest_group" ${dis}></div>
        <div><label class="lbl" for="f-items">List of items (template)</label><textarea id="f-items" class="mono" rows="3" placeholder="A template that returns a list, one row per item"
          data-in="r.items_template" data-f="r.items_template" ${dis}>${esc(d.items_template || "")}</textarea></div>`;
    return this._fold("digest", "Daily digest", esc(sum), inner);
  }

  _foldExpert() {
    const d = this._draft;
    const dis = this._readOnly ? 'disabled aria-disabled="true"' : "";
    const inner = `<div><label class="lbl" for="f-dedup">Dedup tag</label><input id="f-dedup" class="mono" type="text" placeholder="${esc(
      slugify(d.name) || "made_from_the_name"
    )} (automatic)" value="${esc(d.dedup_tag || "")}" data-in="r.dedup_tag" data-f="r.dedup_tag" ${dis}>
      <p class="hint">Made from the rule name automatically. Change it only to make two rules replace each other.</p></div>
      <div><label class="lbl" for="f-wsvc">Also call a service when it fires</label><input id="f-wsvc" class="mono" type="text" placeholder="esphome.mudroom_panel_navigate"
        value="${esc(d.wall_service || "")}" data-in="r.wall_service" data-f="r.wall_service" ${dis}>
        <p class="hint">Called with the alert's tag, wall action, title and priority. Use it to target one specific panel.</p></div>`;
    return this._fold("expert", "Expert", "Internal id and a raw service call. Most rules never need these.", inner);
  }

  // Quiet-hours window as text ("22:00–07:00"), or "" when quiet hours are off.
  _quietNote() {
    const q = (this._meta && this._meta.quiet_hours) || {};
    if (q.enabled === false) return "";
    const a = hhmm(q.start) || "22:00";
    const b = hhmm(q.end) || "07:00";
    return a === b ? "" : `${a}–${b}`;
  }

  // What the phone gets during quiet hours, appended to the push-level note (#64).
  _quietPhoneNote() {
    const d = this._draft;
    const qb = quietBehaviour(d, this._meta);
    if (qb === "ignore") return "";
    const q = (this._meta && this._meta.quiet_hours) || {};
    if (q.enabled === false) return " Quiet hours are off in Settings, so this always applies.";
    const w = this._quietNote();
    const what = {
      downgrade: "arrives silently, and nothing is spoken.",
      suppress: "not sent to phones and nothing is spoken; it still shows on the bell and wall panels.",
      batch: "held and sent as one summary when quiet hours end; nothing is spoken.",
    }[qb];
    return what ? ` During quiet hours (${w}): ${what}` : "";
  }

  // --- Preview column -------------------------------------------------------
  _preview() {
    const d = this._draft;
    const pri = d.priority || "info";
    const chans = this._channels();
    const title = this._title();
    const msg = this._message();
    const accent = d.color || PRI[pri].solid;
    const onAccent = d.color ? "#ffffff" : PRI[pri].onSolid;
    const icon = d.icon || PRI[pri].icon;
    const names = CHANNELS.filter((c) => chans.includes(c.id)).map((c) => c.short);
    let trig;
    if (d.source_type === "template") trig = "your template is true";
    else if (!d.entity_id) trig = "…";
    else {
      const name = friendly(this._hass, d.entity_id);
      const op = d.source_type === "numeric" ? (NUMERIC_OPS.find(([v]) => v === (d.operator || ">")) || [, "goes above"])[1] : d.operator === "!=" ? "is not" : "is";
      trig = `${name} ${op} ${d.value ?? "…"}`;
    }
    const live = !!d.live_activity;
    const prog = parseFloat(this._rText("progress_template").text);
    const max = parseFloat(this._rText("progress_max_template").text) || 100;
    const pct = isNaN(prog) ? 0 : Math.max(0, Math.min(100, (prog / max) * 100));
    const chip = this._rText("critical_text_template").text;
    const bar = live
      ? `<div class="pbar"><span class="track"><span style="width:${pct}%;background:${esc(accent)}"></span></span><span class="small strong">${esc(chip)}</span></div>`
      : "";
    let out = `<p class="card tight sentence">When <strong>${esc(trig)}</strong>, send a <strong class="pri-${pri}">${pri}</strong> alert to <strong>${esc(
      names.join(", ") || "nowhere"
    )}</strong>. ${this._dismissable() ? "People can dismiss it." : "It stays until the condition resolves."}</p>`;
    if (chans.includes("mobile")) {
      const who = asList(d.recipients).length ? this._whoLabel(d).replace(/, ([^,]*)$/, " and $1") : "everyone";
      const btns = (Array.isArray(d.custom_actions) ? d.custom_actions : []).map((a) => a.label || "Button");
      if (this._snoozeAllowed()) btns.push("Snooze");
      if (this._dismissable()) btns.push("Dismiss");
      out += `<div><h3 class="ph">Phone · ${esc(who)}</h3><div class="card tight phone">
        <div class="rowb xsmall muted caps"><span>Home Assistant</span><span>now</span></div>
        <div class="bold">${esc(title)}</div>${msg ? `<div>${esc(msg)}</div>` : ""}${bar}
        ${btns.length ? `<div class="chips tight mt">${btns.map((b) => `<span class="pbtn">${esc(b)}</span>`).join("")}</div>` : ""}</div>
        <p class="hint">${esc(PRI[pri].push)}${this._quietPhoneNote()}</p></div>`;
    }
    if (chans.includes("bell")) {
      out += `<div><h3 class="ph">Dashboard card and bell</h3><div class="card tight">
        <div class="inline atop"><span class="tile" style="background:${esc(accent)};color:${esc(onAccent)}"><ha-icon icon="${esc(icon)}"></ha-icon></span>
        <div class="minw grow"><div class="rowb"><span class="strong">${esc(title)}</span><span class="small muted">now</span></div>
        ${msg ? `<div class="muted small">${esc(msg)}</div>` : ""}</div></div>${bar}</div></div>`;
    }
    if (chans.includes("wall")) {
      const pillOn = (pri === "critical" || pri === "warning") && !!d.wall_takeover;
      const pill = this._pillText();
      const max = (this._meta && this._meta.takeover_max_chars) || 28;
      const shownPill = pill.length > max ? pill.slice(0, max - 1) + "…" : pill;
      const w = parseWallAction(d.wall_action);
      const sound = w.sound ? `play the ${w.sound} sound` : "";
      let note = "When it fires, panels ";
      if (w.type !== "none" && w.name) note += `open the ${w.name} ${w.type}${sound ? ` and ${sound}.` : "."}`;
      else note += sound ? `${sound}.` : "only add it to the Notifications sheet.";
      const qw = this._quietNote();
      if (qw && (w.type !== "none" || w.sound)) {
        const qb = quietBehaviour(d, this._meta);
        if (qb === "suppress" || qb === "batch") note += ` During quiet hours (${qw}) they only list it.`;
        else if (qb === "downgrade" && w.sound) note += ` During quiet hours (${qw}) the sound is marked quiet, so panels can skip it.`;
      }
      if (pillOn) {
        const t = parseTarget(d.wall_takeover_target);
        note += ` The pill stays until it resolves and opens ${t.type === "default" ? "the Notifications sheet." : `the ${t.name} ${t.type}.`}`;
      }
      out += `<div><h3 class="ph">Wall panel</h3><div class="wallprev">
        <div class="wallbar"><span class="wtitle">Home</span><span class="grow"></span>${
          pillOn
            ? `<span class="wpill" style="background:${PRI[pri].pill}"><ha-icon icon="${esc(icon)}"></ha-icon><span>${esc(shownPill)}</span></span>`
            : `<span class="wchips"><span>72°</span><span class="wbell"><ha-icon icon="mdi:bell-outline"></ha-icon>1</span></span>`
        }</div>
        <div class="wallrow"><ha-icon icon="${PRI[pri].icon}" style="color:${PRI[pri].wall}"></ha-icon>
          <div class="minw"><div class="wt" style="color:${PRI[pri].wall}">${esc(title)}</div>${msg ? `<div class="wm">${esc(msg)}</div>` : ""}<div class="ws">Just now</div></div></div>
      </div><p class="hint">${esc(note)}</p></div>`;
    }
    if (chans.includes("tts")) {
      const spk = asList(d.tts_targets).map((s) => friendly(this._hass, s));
      const spoken = d.tts_message ? this._rText("tts_message").text : `${title}${msg ? ". " + msg : ""}`;
      const qb = quietBehaviour(d, this._meta);
      const qw = this._quietNote();
      const quietSpoken = qw && qb !== "ignore" ? `<p class="hint">Not spoken during quiet hours (${esc(qw)}).</p>` : "";
      out += `<div><h3 class="ph">Spoken · ${esc(spk.join(", ") || "default speakers")}</h3>
        <p class="card tight inline atop"><ha-icon icon="mdi:bullhorn-outline" class="muted"></ha-icon><span>${esc(spoken)}</span></p>${quietSpoken}</div>`;
    }
    if (!chans.length) out += `<p class="note warn">No channels are on, so this rule would not notify anyone.</p>`;
    out += `<p class="hint m0">Previews use live values from your home right now.</p>`;
    return out;
  }

  // --- Editor actions --------------------------------------------------------
  _a_back() {
    this._go("#rules");
  }
  _a_flip(field) {
    if (this._readOnly) return;
    const d = this._draft;
    const defaults = { enabled: true, actions_follow_priority: true, auto_clear: true };
    const cur = d[field] === undefined ? !!defaults[field] : d[field] !== false && !!d[field];
    d[field] = !cur;
    this._afterEdit();
  }
  _a_source(id) {
    const d = this._draft;
    if (d.source_type === id) return;
    d.source_type = id;
    if (id === "numeric" && !NUMERIC_OPS.some(([v]) => v === d.operator)) d.operator = ">";
    if (id === "state" && !STATE_OPS.some(([v]) => v === d.operator)) d.operator = "==";
    this._afterEdit();
  }
  _a_value(v) {
    this._draft.value = v;
    this._afterEdit();
  }
  _a_priority(p) {
    this._draft.priority = p;
    this._afterEdit();
  }
  _a_channel(id) {
    const ch = this._channels();
    this._draft.channels = ch.includes(id) ? ch.filter((c) => c !== id) : [...ch, id];
    this._afterEdit();
  }
  _a_who(person) {
    const sel = asList(this._draft.recipients);
    this._draft.recipients = !person ? [] : sel.includes(person) ? sel.filter((x) => x !== person) : [...sel, person];
    this._afterEdit();
  }
  _a_speaker(id) {
    const sel = asList(this._draft.tts_targets);
    this._draft.tts_targets = sel.includes(id) ? sel.filter((x) => x !== id) : [...sel, id];
    this._afterEdit();
  }
  _c_wallSound(v) {
    const w = parseWallAction(this._draft.wall_action);
    w.sound = v;
    this._setWall(w);
  }
  _c_wallType(v) {
    const w = parseWallAction(this._draft.wall_action);
    w.type = v;
    if (v === "none") w.name = "";
    else if (!w.name) w.name = (this._wallNames(v, "")[0] || [""])[0];
    this._setWall(w);
  }
  _c_wallName(v) {
    const w = parseWallAction(this._draft.wall_action);
    w.name = v;
    this._setWall(w);
  }
  _setWall(w) {
    const s = buildWallAction(w);
    this._setRule("wall_action", s);
    this._afterEdit();
  }
  _c_pillType(v) {
    if (v === "default") this._setRule("wall_takeover_target", "");
    else {
      const cur = parseTarget(this._draft.wall_takeover_target);
      const name = cur.type === v && cur.name ? cur.name : (this._wallNames(v, "")[0] || [""])[0];
      this._setRule("wall_takeover_target", `${v}:${name}`);
    }
    this._afterEdit();
  }
  _c_pillName(v) {
    const cur = parseTarget(this._draft.wall_takeover_target);
    this._setRule("wall_takeover_target", cur.type === "default" ? "" : `${cur.type}:${v}`);
    this._afterEdit();
  }
  _a_icon(ic) {
    this._draft.icon = this._draft.icon === ic ? (this._origKeys.has("icon") ? "" : undefined) : ic;
    if (this._draft.icon === undefined) delete this._draft.icon;
    this._afterEdit();
  }
  _a_moreIcons() {
    this._ui.moreIcons = !this._ui.moreIcons;
    this._render();
  }
  _a_color(v) {
    this._setRule("color", v);
    this._afterEdit();
  }
  _a_phonePath() {
    if (this._draft.mobile_navigation_target || this._ui.phonePath) {
      this._ui.phonePath = false;
      this._setRule("mobile_navigation_target", "");
    } else this._ui.phonePath = true;
    this._afterEdit();
  }
  _a_clearMode(v) {
    this._draft.clear_mode = v;
    this._afterEdit();
  }
  _a_snoozeOpt(m) {
    const cur = this._snoozeMinutes();
    const n = Number(m);
    const next = cur.includes(n) ? cur.filter((x) => x !== n) : [...cur, n].sort((a, b) => a - b);
    this._draft.snooze_options = next.length ? next : cur;
    this._afterEdit();
  }
  _a_caAdd() {
    const d = this._draft;
    d.custom_actions = [...(Array.isArray(d.custom_actions) ? d.custom_actions : []), { id: "a" + Math.random().toString(36).slice(2, 8), label: "" }];
    this._ui.folds.buttons = true;
    this._afterEdit();
  }
  _a_caRemove(i) {
    const d = this._draft;
    d.custom_actions = (d.custom_actions || []).filter((_, idx) => idx !== Number(i));
    if (!d.custom_actions.length && !this._origKeys.has("custom_actions")) delete d.custom_actions;
    this._afterEdit();
  }
  _a_caNoEntity(i) {
    const a = (this._draft.custom_actions || [])[Number(i)];
    if (!a) return;
    delete a.entity;
    delete a.target;
    this._afterEdit();
  }
  _a_fold(id) {
    this._ui.folds[id] = !this._ui.folds[id];
    this._render();
  }
  _a_openPicker(key) {
    this._ui.picker = this._ui.picker === key ? null : key;
    this._ui.pickQ = "";
    this._render();
  }
  _a_pickEntity(arg) {
    const [key, entity] = arg.split("|");
    this._ui.picker = null;
    const d = this._draft;
    if (key === "trigger") {
      d.entity_id = entity;
      const st = this._hass.states[entity];
      if (d.source_type === "state") {
        const sugg = stateSuggestions(entity, st);
        if (!sugg.includes(String(d.value ?? ""))) d.value = sugg[0] || "";
      }
    } else if (key === "insert") {
      const snippet = `{{ states('${entity}') }}`;
      const ta = this.shadowRoot.getElementById("f-msg");
      const cur = d.message_template || "";
      const at = ta && ta.selectionStart != null ? ta.selectionStart : cur.length;
      d.message_template = cur.slice(0, at) + snippet + cur.slice(at);
    } else if (key.startsWith("ca:")) {
      const i = Number(key.slice(3));
      const a = (d.custom_actions || [])[i];
      if (a) {
        const oldDomain = a.entity ? String(a.entity).split(".")[0] : "";
        a.entity = entity;
        a.target = { ...(a.target || {}), entity_id: entity };
        const domain = entity.split(".")[0];
        if (domain !== oldDomain) a.service = "";
        if (!a.label) a.label = friendly(this._hass, entity);
      }
    }
    this._afterEdit();
  }
  _afterEdit() {
    this._testPrompt = false;
    this._renderTemplates();
  }

  _buildRule() {
    const rule = clone(this._draft);
    const pri = rule.priority || "info";
    if (rule.wall_takeover && pri !== "critical" && pri !== "warning") rule.wall_takeover = false;
    if (this._isNew && !rule.dedup_tag) {
      const taken = new Set((this._rules || []).map((x) => x.data.dedup_tag || slugify(x.data.name)));
      let tag = slugify(rule.name) || "rule";
      for (let i = 2; taken.has(tag); i++) tag = `${slugify(rule.name) || "rule"}_${i}`;
      rule.dedup_tag = tag;
    }
    if (Array.isArray(rule.custom_actions))
      rule.custom_actions = rule.custom_actions.map((a) => ({ ...a, id: a.id || "a" + Math.random().toString(36).slice(2, 8) }));
    return rule;
  }

  async _a_save() {
    if (this._readOnly || !this._draft) return false;
    if (!String(this._draft.name || "").trim()) {
      this._banner = { kind: "error", text: "Give the rule a name first." };
      this._render();
      return false;
    }
    if (!this._dirty() && !this._isNew) return true;
    const rule = this._buildRule();
    try {
      let res;
      if (this._isNew) res = await this._ws("notification_center/rules/create", { rule });
      else res = await this._ws("notification_center/rules/update", { subentry_id: this._editingId, rule });
      this._draft = rule;
      this._origKeys = new Set(Object.keys(rule));
      this._saved = JSON.stringify(rule);
      this._isNew = false;
      if (res && res.subentry_id) this._editingId = res.subentry_id;
      this._route = { view: "rule", id: this._editingId };
      history.replaceState(null, "", this._hashFor(this._route));
      this._banner = null;
      await this._loadRules(true);
      this._render();
      return true;
    } catch (e) {
      this._banner = { kind: "error", text: (e && e.message) || "Save failed." };
      this._render();
      return false;
    }
  }

  async _a_testRule() {
    const r = this._ruleById(this._editingId);
    if (r && r.testing) return this._a_stopTest();
    if (this._isNew || this._dirty()) {
      this._testPrompt = true;
      this._render();
      return;
    }
    await this._startTest();
  }
  async _a_testSaved() {
    this._testPrompt = false;
    await this._startTest();
  }
  async _a_saveAndTest() {
    this._testPrompt = false;
    if (await this._a_save()) await this._startTest();
  }
  async _startTest() {
    try {
      await this._ws("notification_center/rules/test", { subentry_id: this._editingId, enabled: true });
    } catch (e) {
      this._banner = { kind: "error", text: (e && e.message) || "Test failed." };
    }
    await this._loadRules(true);
    this._render();
  }
  async _a_stopTest() {
    try {
      await this._ws("notification_center/rules/test", { subentry_id: this._editingId, enabled: false });
    } catch (e) {
      /* already stopped */
    }
    await this._loadRules(true);
    this._render();
  }

  // =====================================================================
  // Settings tab
  // =====================================================================
  _personName(person) {
    return friendly(this._hass, person) || String(person).replace(/^person\./, "").replace(/_/g, " ");
  }

  _phoneLabel(svc) {
    return phoneName(svc) || svc;
  }

  _knownPhones() {
    const s = this._sDraft;
    const out = new Set((this._settings && this._settings.available_phones) || []);
    for (const p of s.people || []) for (const ph of p.phones || []) out.add(ph);
    for (const ph of s.other_phones || []) out.add(ph);
    return [...out].sort();
  }

  _assignedPhones() {
    const s = this._sDraft;
    const out = new Set(s.other_phones || []);
    for (const p of s.people || []) for (const ph of p.phones || []) out.add(ph);
    return out;
  }

  _phoneNote(svc) {
    const note = this._phoneNotes[svc];
    if (note) return { cls: note.ok ? "ok" : "warn", text: note.text };
    const st = ((this._settings && this._settings.phone_status) || {})[svc];
    if (st && !st.ok) return { cls: "warn", text: "The last push to this phone failed." };
    const known = ((this._settings && this._settings.available_phones) || []).includes(svc);
    return known ? { cls: "muted", text: "Home Assistant app" } : { cls: "warn", text: "Home Assistant doesn't know this phone right now." };
  }

  _renderSettings() {
    if (this._settingsError && !this._settings) return this._errorBox(this._settingsError, "settings");
    if (!this._settings || !this._sDraft) return this._skeleton();
    return `<div class="stack">${this._healthSection()}${this._peopleSection()}${this._announceSection()}${this._quietSection()}${this._advancedSection()}</div>`;
  }

  _healthSection() {
    const problems = (this._settings.health || []).map((h) => {
      if (h.kind === "no_voice")
        return ["No voice for announcements.", "Rules with Speakers on can't speak until a voice is available.", "Choose a voice", "announce"];
      if (h.kind === "phone_failed")
        return [`${this._phoneLabel(h.phone)} is not receiving alerts.`, "The last push failed. Send a test to check it.", "Go to phone", "people"];
      if (h.kind === "person_no_phone") {
        const name = this._personName(h.person);
        return [`${name} has no phone.`, `Rules sent to ${name} reach nobody.`, "Add a phone", "people"];
      }
      return [h.kind, "", "Open", "people"];
    });
    const body = problems.length
      ? problems
          .map(
            ([title, text, action, to]) => `<div class="problem"><ha-icon icon="mdi:alert-outline" class="warn"></ha-icon>
            <span class="grow"><strong>${esc(title)}</strong> ${esc(text)}</span>
            <button type="button" class="btn" data-act="sJump" data-arg="${to}">${esc(action)}</button></div>`
          )
          .join("")
      : `<p class="healthy"><ha-icon icon="mdi:check"></ha-icon>Everything is working. Phones, voice and speakers all responded.</p>`;
    return `<section aria-labelledby="h-health" class="stack8"><h2 id="h-health" class="ghead">Health</h2>${body}</section>`;
  }

  _peopleSection() {
    const s = this._sDraft;
    const assigned = this._assignedPhones();
    const free = this._knownPhones().filter((p) => !assigned.has(p));
    const phoneOpts = [["", "Choose a phone…"], ...free.map((p) => [p, this._phoneLabel(p)])];
    const cards = (s.people || [])
      .map((pe, i) => {
        const st = this._hass.states[pe.person];
        const pic = st && st.attributes && st.attributes.entity_picture;
        const name = this._personName(pe.person);
        const where = !st ? "Not found in Home Assistant" : st.state === "home" ? "Home" : st.state === "not_home" ? "Away" : st.state;
        const phones = (pe.phones || [])
          .map((ph) => {
            const n = this._phoneNote(ph);
            return `<div class="phonerow"><ha-icon icon="mdi:cellphone" class="muted"></ha-icon>
              <span class="minw grow"><span class="block">${esc(this._phoneLabel(ph))}</span><span class="block small ${n.cls}">${esc(n.text)}</span></span>
              <button type="button" class="btn small" data-act="sTestPhone" data-arg="${esc(ph)}" data-f="test-${esc(ph)}">Send test</button>
              <button type="button" class="iconbtn" aria-label="Remove ${esc(this._phoneLabel(ph))} from ${esc(name)}" data-act="sRemovePhone" data-arg="${i}|${esc(
              ph
            )}"><ha-icon icon="mdi:close"></ha-icon></button></div>`;
          })
          .join("");
        return `<div class="subcard">
          <div class="rowb"><div class="inline minw">${
            pic ? `<img class="avatar" src="${esc(pic)}" alt="">` : `<span class="avatar" aria-hidden="true">${esc(name.charAt(0).toUpperCase())}</span>`
          }
            <div><div class="strong big">${esc(name)}</div><div class="small muted">${esc(where)}</div></div></div>
            <button type="button" class="btn ghost small" data-act="sRemovePerson" data-arg="${i}">Remove</button></div>
          ${phones}
          ${!(pe.phones || []).length ? `<p class="note warn m0">No phone yet, so rules sent to ${esc(name)} reach nobody.</p>` : ""}
          ${
            free.length
              ? `<label class="lbl m0 narrowfield">Add a phone ${this._select("fn.sAddPhone", phoneOpts, "", { label: `Add a phone for ${name}` }).replace(
                  'data-ch="fn.sAddPhone"',
                  `data-ch="fn.sAddPhone" data-arg="${i}"`
                ).replace('data-f="fn.sAddPhone"', `data-f="addphone-${i}"`)}</label>`
              : ""
          }</div>`;
      })
      .join("");
    const have = new Set((s.people || []).map((p) => p.person));
    const avail = Object.keys(this._hass.states)
      .filter((e) => e.startsWith("person.") && !have.has(e))
      .sort();
    const addPerson = avail.length
      ? `<label class="lbl m0 narrowfield">Add a person ${this._select(
          "fn.sAddPerson",
          [["", "Choose from Home Assistant people…"], ...avail.map((e) => [e, this._personName(e)])],
          ""
        )}</label>`
      : (s.people || []).length
      ? ""
      : `<p class="hint m0">Home Assistant has no people yet. Add them under Settings → People, then come back.</p>`;
    const personOpts = [["", "Give to a person…"], ...(s.people || []).map((p, i) => [String(i), this._personName(p.person)])];
    const others = (s.other_phones || [])
      .map((ph) => {
        const n = this._phoneNote(ph);
        return `<div class="phonerow"><ha-icon icon="mdi:cellphone" class="muted"></ha-icon>
          <span class="minw grow"><span class="block">${esc(this._phoneLabel(ph))}</span><span class="block small ${n.cls}">${esc(n.text)}</span></span>
          ${
            (s.people || []).length
              ? this._select("fn.sAssign", personOpts, "", { label: `Give ${this._phoneLabel(ph)} to a person` })
                  .replace('data-ch="fn.sAssign"', `data-ch="fn.sAssign" data-arg="${esc(ph)}"`)
                  .replace('data-f="fn.sAssign"', `data-f="assign-${esc(ph)}"`)
              : ""
          }
          <button type="button" class="btn small" data-act="sTestPhone" data-arg="${esc(ph)}">Send test</button>
          <button type="button" class="iconbtn" aria-label="Remove ${esc(this._phoneLabel(ph))}" data-act="sRemoveOther" data-arg="${esc(ph)}"><ha-icon icon="mdi:close"></ha-icon></button></div>`;
      })
      .join("");
    return `<section class="card" id="sec-people" aria-labelledby="h-people">
      <div><h2 id="h-people">People and phones</h2>
        <p class="hint">A rule sent to Everyone reaches every phone on this page. A rule sent to one person reaches only their phones.</p></div>
      ${cards}${addPerson}
      <div class="divtop stack8"><div><h3>Other phones</h3><p class="hint m0">Not tied to a person, like a shared tablet. They only get rules sent to Everyone.</p></div>
        ${others || `<p class="muted small m0">None.</p>`}
        ${free.length ? `<label class="lbl m0 narrowfield">Add a phone ${this._select("fn.sAddOther", phoneOpts, "")}</label>` : ""}
        ${!this._knownPhones().length ? `<p class="hint m0">No phones found. Install the Home Assistant app on a phone and sign in, then it shows up here.</p>` : ""}
      </div></section>`;
  }

  _announceSection() {
    const s = this._sDraft;
    const engines = Object.keys(this._hass.states)
      .filter((e) => e.startsWith("tts."))
      .sort();
    const voiceOpts = [["", "Automatic (Home Assistant Cloud)"], ...engines.map((e) => [e, friendly(this._hass, e)])];
    if (s.tts_engine && !engines.includes(s.tts_engine)) voiceOpts.push([s.tts_engine, `${s.tts_engine} (not available)`]);
    let hint;
    let hintCls = "";
    if (s.tts_engine && !engines.includes(s.tts_engine)) {
      hint = "This voice isn't available right now.";
      hintCls = "warn";
    } else if (!s.tts_engine && !engines.length) {
      hint = "No voice is installed. Add a text-to-speech integration such as Home Assistant Cloud or Piper.";
      hintCls = "warn";
    } else if (!s.tts_engine) hint = "Uses Home Assistant Cloud when it's set up, otherwise the first voice found.";
    else hint = "Every announcement uses this voice.";
    const players = Object.values(this._hass.states)
      .filter((x) => x.entity_id.startsWith("media_player."))
      .sort((a, b) => String(a.attributes.friendly_name || a.entity_id).localeCompare(String(b.attributes.friendly_name || b.entity_id)));
    const sel = s.default_media_players || [];
    const chips =
      players.map((p) => this._chip(p.attributes.friendly_name || p.entity_id, sel.includes(p.entity_id), "sSpeaker", p.entity_id)).join("") +
      sel.filter((x) => !players.some((p) => p.entity_id === x)).map((x) => this._chip(x, true, "sSpeaker", x)).join("");
    const play = this._playNote;
    return `<section class="card" id="sec-announce" aria-labelledby="h-ann"><h2 id="h-ann">Announcements</h2>
      <div><label class="lbl" for="s-voice">Voice</label>${this._select("fn.sVoice", voiceOpts, s.tts_engine || "", { id: "s-voice" })}
        <p class="hint ${hintCls}">${esc(hint)}</p></div>
      <div><span class="lbl" id="l-dspk">Default speakers</span>${
        chips ? `<div class="chips" role="group" aria-labelledby="l-dspk">${chips}</div>` : `<p class="muted small m0">No speakers found in Home Assistant.</p>`
      }<p class="hint">Used when a rule has Speakers on but doesn't pick its own.</p></div>
      <div class="inline wrapline"><button type="button" class="btn" data-act="sPlayTest" data-f="playtest"><ha-icon icon="mdi:bullhorn-outline"></ha-icon>Play test announcement</button>
        <span role="status" class="small ${play ? (play.ok ? "ok" : "warn") : ""}">${play ? esc(play.text) : ""}</span></div></section>`;
  }

  _quietSection() {
    const s = this._sDraft;
    const on = s.quiet_hours_enabled !== false;
    const start = hhmm(s.quiet_hours_start) || "22:00";
    const end = hhmm(s.quiet_hours_end) || "07:00";
    const segs = quietSegments(start, end)
      .map((g) => `<span style="left:${g.left};width:${g.width}"></span>`)
      .join("");
    const body = on
      ? `<div class="inline wrapline" role="group" aria-label="Quiet hours range">
          <label class="inline">From <input type="time" value="${start}" data-ch="fn.sTime" data-arg="quiet_hours_start" data-f="qs"></label>
          <label class="inline">until <input type="time" value="${end}" data-ch="fn.sTime" data-arg="quiet_hours_end" data-f="qe"></label>
          <span class="muted small">${esc(quietLength(start, end))}</span></div>
        <div aria-hidden="true"><div class="qbar">${segs}</div>
          <div class="rowb xsmall muted"><span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span><span>24:00</span></div></div>
        <div><h3>During quiet hours</h3>
          <div class="qrow"><span class="pri-critical strong">Critical</span><span>Always comes through at full volume, announcements included.</span></div>
          <div class="qrow"><span class="pri-warning strong">Warning</span><span>Arrives silently on phones. Nothing is spoken.</span></div>
          <div class="qrow"><span class="pri-info strong">Info</span><span>Held back and sent as one summary when quiet hours end.</span></div>
          <p class="hint">Any rule can choose differently under Timing and who's home.</p></div>`
      : `<p class="muted m0">Quiet hours are off. Every alert is delivered as soon as it fires.</p>`;
    return `<section class="card" aria-labelledby="h-quiet"><div class="rowb"><h2 id="h-quiet">Quiet hours</h2>
        ${this._switch(on, "sFlip", "Quiet hours", { arg: "quiet_hours_enabled" })}</div>${body}
      <div class="divtop"><label class="inline wrapline"><span class="strong">Daily digest arrives at</span>
        <input type="time" value="${hhmm(s.digest_time) || "08:00"}" data-ch="fn.sTime" data-arg="digest_time" data-f="digest"></label>
        <p class="hint">One summary of the rules set to deliver in the daily digest.</p></div></section>`;
  }

  _advancedSection() {
    const s = this._sDraft;
    const open = this._advOpen;
    const list = (v) => (Array.isArray(v) ? v.join(", ") : v || "");
    const inner = open
      ? `<div class="foldbody grid2">
          <div><label class="lbl" for="s-tts">Speech service</label><input id="s-tts" class="mono" type="text" value="${esc(s.tts_service || "")}" data-in="s.tts_service" data-f="s.tts_service">
            <p class="hint">The Home Assistant action used to speak. Leave as tts.speak unless you use a custom one.</p></div>
          <div><label class="lbl" for="s-deb">Wait before re-checking a rule (ms)</label><input id="s-deb" type="text" inputmode="numeric" value="${esc(s.debounce_ms ?? "")}"
            data-in="s.debounce_ms" data-f="s.debounce_ms"><p class="hint">Stops a flickering sensor from firing the same rule over and over.</p></div>
          <div><label class="lbl" for="s-sheets">Wall panel sheets</label><input id="s-sheets" class="mono" type="text" value="${esc(list(s.wall_sheets))}"
            data-in="s.wall_sheets" data-f="s.wall_sheets"><p class="hint">Sheet names your panels accept, comma-separated. Offered in a rule's Wall panels settings.</p></div>
          <div><label class="lbl" for="s-pages">Wall panel pages</label><input id="s-pages" class="mono" type="text" value="${esc(list(s.wall_pages))}"
            data-in="s.wall_pages" data-f="s.wall_pages"><p class="hint">Page names your panels accept, comma-separated.</p></div>
          <div><label class="lbl" for="s-sounds">Wall panel sounds</label><input id="s-sounds" class="mono" type="text" value="${esc(list(s.wall_sounds))}"
            data-in="s.wall_sounds" data-f="s.wall_sounds"><p class="hint">Sound names your panels can play, comma-separated, like chime, alert, doorbell. Each panel maps a name to its own audio file; "chime" is the default.</p></div></div>`
      : "";
    return `<section class="fold"><button type="button" class="foldhead" aria-expanded="${open}" data-act="sAdv" data-f="sAdv">
      <span class="grow"><span class="foldtitle">Advanced</span><span class="foldsum">Speech service, re-check delay, and wall panel names and sounds. Almost nobody needs to change these.</span></span>
      <ha-icon icon="mdi:chevron-down" class="${open ? "rot" : ""}"></ha-icon></button>${inner}</section>`;
  }

  // Settings actions -----------------------------------------------------------
  _sChanged() {
    this._render();
  }
  _a_sAdv() {
    this._advOpen = !this._advOpen;
    this._render();
  }
  _a_sJump(to) {
    const el = this.shadowRoot.getElementById(`sec-${to}`);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  _a_sFlip(field) {
    this._sDraft[field] = this._sDraft[field] === false;
    this._sChanged();
  }
  _c_sTime(value, el) {
    const field = el.getAttribute("data-arg");
    if (/^\d{2}:\d{2}$/.test(value)) this._sDraft[field] = `${value}:00`;
    this._sChanged();
  }
  _c_sVoice(value) {
    this._sDraft.tts_engine = value;
    this._sChanged();
  }
  _a_sSpeaker(id) {
    const sel = this._sDraft.default_media_players || [];
    this._sDraft.default_media_players = sel.includes(id) ? sel.filter((x) => x !== id) : [...sel, id];
    this._sChanged();
  }
  _c_sAddPerson(value) {
    if (!value) return;
    this._sDraft.people = [...(this._sDraft.people || []), { person: value, phones: [] }];
    this._sChanged();
  }
  _a_sRemovePerson(i) {
    const people = [...(this._sDraft.people || [])];
    const [gone] = people.splice(Number(i), 1);
    this._sDraft.people = people;
    // Their phones stay known: they become "other phones" rather than vanish.
    if (gone && gone.phones && gone.phones.length) this._sDraft.other_phones = [...(this._sDraft.other_phones || []), ...gone.phones];
    this._sChanged();
  }
  _c_sAddPhone(value, el) {
    if (!value) return;
    const i = Number(el.getAttribute("data-arg"));
    const pe = this._sDraft.people[i];
    if (pe) pe.phones = [...(pe.phones || []), value];
    this._sChanged();
  }
  _a_sRemovePhone(arg) {
    const [i, ph] = arg.split("|");
    const pe = this._sDraft.people[Number(i)];
    if (pe) pe.phones = (pe.phones || []).filter((x) => x !== ph);
    this._sChanged();
  }
  _c_sAddOther(value) {
    if (!value) return;
    this._sDraft.other_phones = [...(this._sDraft.other_phones || []), value];
    this._sChanged();
  }
  _a_sRemoveOther(ph) {
    this._sDraft.other_phones = (this._sDraft.other_phones || []).filter((x) => x !== ph);
    this._sChanged();
  }
  _c_sAssign(value, el) {
    if (value === "") return;
    const ph = el.getAttribute("data-arg");
    const pe = this._sDraft.people[Number(value)];
    if (!pe) return;
    this._sDraft.other_phones = (this._sDraft.other_phones || []).filter((x) => x !== ph);
    pe.phones = [...(pe.phones || []), ph];
    this._sChanged();
  }
  async _a_sTestPhone(ph) {
    this._phoneNotes[ph] = { ok: true, text: "Sending…" };
    this._render();
    try {
      const res = await this._ws("notification_center/settings/test_push", { notify_service: ph });
      this._phoneNotes[ph] = res.ok ? { ok: true, text: "Test sent. Check the phone." } : { ok: false, text: res.error || "The test push failed." };
    } catch (e) {
      this._phoneNotes[ph] = { ok: false, text: (e && e.message) || "The test push failed." };
    }
    this._render();
  }
  async _a_sPlayTest() {
    const s = this._sDraft;
    this._playNote = { ok: true, text: "Playing…" };
    this._render();
    try {
      const res = await this._ws("notification_center/settings/test_announcement", {
        engine: s.tts_engine || null,
        media_players: s.default_media_players || [],
      });
      if (res.ok) {
        const names = (s.default_media_players || []).map((x) => friendly(this._hass, x)).join(", ");
        this._playNote = { ok: true, text: `Playing on ${names}.` };
      } else this._playNote = { ok: false, text: `Could not play. ${res.error || ""}`.trim() };
    } catch (e) {
      this._playNote = { ok: false, text: `Could not play. ${(e && e.message) || ""}`.trim() };
    }
    this._render();
  }
  _a_discardSettings() {
    this._sDraft = JSON.parse(this._sSaved);
    this._banner = null;
    this._render();
  }
  async _a_saveSettings() {
    if (!this._sDraft) return false;
    try {
      const res = await this._ws("notification_center/settings/update", { settings: this._sDraft });
      this._settings = res;
      this._sDraft = clone(res.settings);
      this._sSaved = JSON.stringify(res.settings);
      this._banner = null;
      try {
        this._meta = await this._ws("notification_center/meta");
      } catch (_) {
        /* keep the old meta */
      }
      this._render();
      return true;
    } catch (e) {
      this._banner = { kind: "error", text: (e && e.message) || "Save failed." };
      this._render();
      return false;
    }
  }
}

const STYLES = `
:host {
  --bg: var(--primary-background-color, #f3f5f8);
  --card: var(--card-background-color, #ffffff);
  --text: var(--primary-text-color, #1b2330);
  --text2: var(--secondary-text-color, #566072);
  --divider: var(--divider-color, #dde2ea);
  --primary: var(--primary-color, #0b63c5);
  --on-primary: var(--text-primary-color, #ffffff);
  --field: var(--secondary-background-color, #f6f8fb);
  --crit: var(--error-color, #b3261e);
  --warn: var(--warning-color, #b46a00);
  --ok: var(--success-color, #17703a);
  --info: var(--info-color, #3f5a75);
  /* Text versions pulled toward the text colour so they keep contrast on
     the card in both light and dark themes. */
  --crit-fg: color-mix(in srgb, var(--crit) 72%, var(--text));
  --warn-fg: color-mix(in srgb, var(--warn) 62%, var(--text));
  --ok-fg: color-mix(in srgb, var(--ok) 72%, var(--text));
  --info-fg: color-mix(in srgb, var(--info) 72%, var(--text));
  --primary-fg: color-mix(in srgb, var(--primary) 80%, var(--text));
  --crit-soft: color-mix(in srgb, var(--crit) 14%, var(--card));
  --warn-soft: color-mix(in srgb, var(--warn) 16%, var(--card));
  --ok-soft: color-mix(in srgb, var(--ok) 14%, var(--card));
  --info-soft: color-mix(in srgb, var(--info) 14%, var(--card));
  --primary-soft: color-mix(in srgb, var(--primary) 14%, var(--card));
  --off: color-mix(in srgb, var(--text2) 60%, var(--card));
  --faint: color-mix(in srgb, var(--text2) 35%, var(--card));
  --mono: "Roboto Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
  display: block;
  min-height: 100%;
  background: var(--bg);
  color: var(--text);
  font-family: var(--paper-font-body1_-_font-family, Roboto, system-ui, sans-serif);
  font-size: 15px;
  line-height: 1.4;
}
* { box-sizing: border-box; }
.nc { min-height: 100vh; background: var(--bg); }
.wrap { max-width: 1080px; margin: 0 auto; padding: 0 16px 64px; display: flex; flex-direction: column; gap: 20px; }
.wrap.narrowcol { max-width: 880px; }
.wrap.edwrap { max-width: 1180px; gap: 16px; }
h1 { margin: 0; font-size: 28px; font-weight: 500; letter-spacing: -0.2px; }
h2 { margin: 0; font-size: 18px; font-weight: 500; }
h3 { margin: 0 0 4px; font-size: 14px; font-weight: 500; }
p { margin: 0; }
button, input, select, textarea { font: inherit; color: inherit; }
button { cursor: pointer; }
button:disabled, [aria-disabled="true"] { cursor: not-allowed; }
a { color: var(--primary-fg); }
:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }
input[type=text], input[type=search], input[type=time], select, textarea {
  width: 100%; min-height: 44px; padding: 10px 12px; border-radius: 10px;
  border: 1px solid var(--divider); background: var(--field); color: var(--text);
}
input[type=time] { width: auto; }
input:disabled, select:disabled, textarea:disabled { opacity: .7; }
textarea { resize: vertical; line-height: 1.4; }
.mono, textarea.mono, input.mono { font-family: var(--mono); font-size: 13px; }
ha-icon { --mdc-icon-size: 20px; display: inline-flex; flex: none; }

.top { padding-top: 24px; display: flex; flex-direction: column; gap: 12px; }
.sticky { position: sticky; top: 0; z-index: 10; background: var(--bg); }
.titlerow { display: flex; flex-wrap: wrap; align-items: center; gap: 12px 20px; }
.sub { margin-top: 4px; color: var(--text2); }
.grow { flex: 1 1 auto; min-width: 0; }
.minw { min-width: 0; }
.actions { display: flex; flex-wrap: wrap; gap: 8px; margin-left: auto; }
.tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--divider); overflow-x: auto; }
.tab { border: 0; background: none; min-height: 44px; padding: 0 16px; color: var(--text2); font-weight: 500;
  border-bottom: 3px solid transparent; margin-bottom: -1px; }
.tab.on { color: var(--primary-fg); border-bottom-color: var(--primary); }
.status { font-size: 13px; font-weight: 500; color: var(--text2); }
.status.warn, .warn { color: var(--warn-fg); }
.ok { color: var(--ok-fg); }
.err { color: var(--crit-fg); }
.fg { color: var(--text); }
.muted { color: var(--text2); }
.small { font-size: 13px; }
.xsmall { font-size: 12px; }
.strong { font-weight: 500; }
.bold { font-weight: 700; }
.big { font-size: 16px; }
.caps { text-transform: uppercase; letter-spacing: .4px; }
.block { display: block; }
.m0 { margin: 0 !important; }
.mt { margin-top: 8px; }
.mb { margin-bottom: 10px; }
.pad { padding: 8px 10px; }
.inline { display: flex; align-items: center; gap: 10px; }
.inline.atop { align-items: flex-start; }
.card.sentence { display: block; }
.wrapline { flex-wrap: wrap; }
.rowb { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.two { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; align-items: start; }
.grid2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; }
.stack { display: flex; flex-direction: column; gap: 20px; }
.stack8 { display: flex; flex-direction: column; gap: 8px; }
.stack14 { display: flex; flex-direction: column; gap: 14px; }
.divtop { border-top: 1px solid var(--divider); padding-top: 16px; }

.btn { display: inline-flex; align-items: center; gap: 8px; min-height: 44px; padding: 0 16px; border-radius: 22px;
  border: 1px solid var(--divider); background: var(--card); color: var(--text); font-weight: 500; text-decoration: none; white-space: nowrap; }
.btn ha-icon { --mdc-icon-size: 18px; }
.btn.small { padding: 0 14px; }
.btn.primary { background: var(--primary); border-color: var(--primary); color: var(--on-primary); }
.btn.primary.dim { opacity: .45; }
.btn.ghost { background: none; border-color: transparent; color: var(--primary-fg); }
.btn.danger { background: var(--crit); border-color: var(--crit); color: #fff; }
.danger-text { color: var(--crit-fg) !important; }
.btn[aria-disabled="true"] { opacity: .45; pointer-events: none; }
.iconbtn { width: 44px; height: 44px; border-radius: 50%; border: 0; background: none; color: var(--text2);
  display: inline-flex; align-items: center; justify-content: center; flex: none; }
.iconbtn:hover { background: var(--field); }
.link { border: 0; background: none; padding: 0; color: var(--primary-fg); font-weight: 500; text-decoration: underline; text-underline-offset: 2px; }
.rowacts .link { min-height: 44px; display: inline-flex; align-items: center; padding: 0 12px; text-decoration: none; }

.banner { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; padding: 12px 16px; border-radius: 12px; }
.banner.warn { background: var(--warn-soft); color: var(--text); }
.banner.error { background: var(--crit-soft); color: var(--text); }
.banner.info { background: var(--info-soft); color: var(--text); }
.banner.testing { border: 1px dashed var(--warn); color: var(--text); }
.note { padding: 10px 12px; border-radius: 10px; font-size: 14px; }
.note.info { background: var(--info-soft); color: var(--info-fg); }
.note.warn { background: var(--warn-soft); color: var(--text); }
.error { color: var(--crit-fg); }

.card { background: var(--card); border: 1px solid var(--divider); border-radius: 16px; padding: 24px;
  display: flex; flex-direction: column; gap: 18px; }
.card.tight { padding: 14px 16px; gap: 6px; }
.card.tight.inline { flex-direction: row; }
.card.list { padding: 0; gap: 0; }
.card.empty { align-items: center; text-align: center; padding: 40px 24px; gap: 12px; border-style: dashed; }
.errorbox { align-items: flex-start; }
.subcard { border: 1px solid var(--divider); border-radius: 12px; padding: 14px 16px; display: flex; flex-direction: column; gap: 12px; }

.toolbar { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; }
.search { flex: 1 1 260px; display: flex; align-items: center; gap: 10px; min-height: 44px; padding: 0 14px;
  background: var(--card); border: 1px solid var(--divider); border-radius: 22px; color: var(--text2); }
.search input { border: 0; background: none; padding: 0; min-height: 40px; outline: none; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; }
.chips.tight { gap: 6px; }
.chip { display: inline-flex; align-items: center; gap: 6px; min-height: 44px; padding: 0 14px; border-radius: 22px;
  border: 1px solid var(--divider); background: var(--card); color: var(--text); font-weight: 500; }
.chip.on { background: var(--primary); border-color: var(--primary); color: var(--on-primary); }
.chip .ck { --mdc-icon-size: 16px; }
.filenote { display: flex; gap: 10px; align-items: flex-start; color: var(--text2); font-size: 13px; }
.filenote ha-icon { --mdc-icon-size: 16px; margin-top: 1px; }

.group { display: flex; flex-direction: column; gap: 8px; }
.ghead { margin: 0; font-size: 13px; font-weight: 500; letter-spacing: .6px; text-transform: uppercase; color: var(--text2); }
.pri-critical { color: var(--crit-fg); }
.pri-warning { color: var(--warn-fg); }
.pri-info { color: var(--info-fg); }
.row { padding: 12px 16px; display: flex; flex-direction: column; gap: 10px; }
.row + .row { border-top: 1px solid var(--divider); }
.row.dim .ident, .row.dim .badges, .row.dim .chicons, .row.dim .who { opacity: .6; }
.rowmain { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 16px; }
.ident { flex: 999 1 300px; min-width: 0; display: flex; align-items: center; gap: 14px; }
.rname { display: block; color: var(--text); font-size: 16px; font-weight: 500; text-decoration: none; }
.rname:hover { text-decoration: underline; }
/* Rule rows (#62): on wide screens a grid, so the channel icons sit in one
   aligned column on every row and the status badges hug them from the left. */
.badges { display: flex; flex-wrap: wrap; align-items: center; justify-content: flex-end; gap: 8px; }
.who { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chicons { width: 96px; flex: none; }
@media (min-width: 761px) {
  .rulerow .rowmain { display: grid; grid-template-columns: minmax(0, 1fr) auto 96px 110px 236px; align-items: center; column-gap: 16px; }
  .rulerow .rowacts { justify-content: flex-end; }
  .rulerow .ident { min-width: 0; }
}
@media (max-width: 760px) {
  .rulerow .badges { justify-content: flex-start; }
  .rulerow .who { max-width: 60%; }
}
.rowacts { display: flex; align-items: center; gap: 4px; }
.tile { width: 40px; height: 40px; border-radius: 12px; display: flex; align-items: center; justify-content: center; flex: none; }
.tile ha-icon { --mdc-icon-size: 22px; }
.soft-critical { background: var(--crit-soft); color: var(--crit-fg); }
.soft-warning { background: var(--warn-soft); color: var(--warn-fg); }
.soft-info { background: var(--info-soft); color: var(--info-fg); }
.chicons { display: inline-flex; gap: 6px; color: var(--text); }
.chicons ha-icon { --mdc-icon-size: 18px; }
.chicons .faint { color: var(--faint); }
.badge { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 12px; font-size: 13px; font-weight: 500; }
.badge .dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; }
.badge.testing { border: 1px dashed var(--warn); color: var(--warn-fg); }
.menuwrap { position: relative; }
.menu { position: absolute; right: 0; top: 46px; z-index: 5; min-width: 180px; background: var(--card); border: 1px solid var(--divider);
  border-radius: 12px; box-shadow: 0 8px 24px rgba(0,0,0,.18); padding: 6px; display: flex; flex-direction: column; }
.menu button { text-align: left; min-height: 44px; padding: 0 12px; border: 0; border-radius: 8px; background: none; color: var(--text); }
.menu button:hover { background: var(--field); }
.confirm { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; padding: 10px 14px; border-radius: 12px; background: var(--crit-soft); }
.histrow { flex-direction: row; align-items: flex-start; gap: 14px; flex-wrap: wrap; }
.histmeta { display: flex; flex-direction: column; align-items: flex-end; gap: 6px; margin-left: auto; }
.skel { flex-direction: row; align-items: center; gap: 14px; }
.sk { display: block; border-radius: 8px; background: var(--field); animation: pulse 1.2s ease-in-out infinite; }
.sk-icon { width: 40px; height: 40px; }
.sk-line { flex: 1; height: 16px; max-width: 360px; }
@keyframes pulse { 50% { opacity: .5; } }
@media (prefers-reduced-motion: reduce) { .sk { animation: none; } .tgk { transition: none; } }

.tg { border: 0; background: none; padding: 10px 0; flex: none; }
.tgt { display: block; width: 40px; height: 24px; border-radius: 12px; position: relative; background: var(--off); }
.tgt.on { background: var(--primary); }
.tgk { position: absolute; top: 3px; left: 3px; width: 18px; height: 18px; border-radius: 50%; background: #fff; transition: transform .15s; }
.tgt.on .tgk { transform: translateX(16px); }
.tg:disabled { opacity: .5; }

/* Editor */
.edhead { padding: 16px 0 12px; display: flex; flex-wrap: wrap; align-items: center; gap: 10px 16px; border-bottom: 1px solid var(--divider); }
.namebox { flex: 999 1 260px; min-width: 0; }
.nameinput { font-size: 22px !important; font-weight: 500; background: transparent !important; border-color: transparent !important; padding: 6px 8px !important; margin-left: -8px; }
.nameinput:hover, .nameinput:focus { border-color: var(--divider) !important; }
.edgrid { display: flex; flex-wrap: wrap; align-items: flex-start; gap: 24px; }
.edmain { flex: 999 1 520px; min-width: 0; display: flex; flex-direction: column; gap: 16px; }
.side { flex: 1 1 340px; min-width: 0; display: flex; flex-direction: column; gap: 14px; }
@media (min-width: 980px) { .side { position: sticky; top: 88px; } }
.lbl { display: block; font-size: 13px; font-weight: 500; color: var(--text2); margin: 0 0 6px; }
.hint { margin: 6px 0 0; font-size: 13px; color: var(--text2); }
.hint.warn { color: var(--warn-fg); }
.hint.err { color: var(--crit-fg); }
.picks3 { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; }
.picks3.wide { grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); }
.pick { text-align: left; padding: 12px 14px; border-radius: 12px; border: 2px solid var(--divider); background: var(--card);
  color: var(--text); display: flex; flex-direction: column; gap: 4px; }
.pick.on { border-color: var(--primary); background: var(--primary-soft); }
.pick.pri { gap: 8px; padding: 14px; }
.solid { width: 32px; height: 32px; border-radius: 9px; display: flex; align-items: center; justify-content: center; }
.solid ha-icon { --mdc-icon-size: 18px; }
.nowline { display: flex; gap: 8px; align-items: center; padding: 10px 12px; border-radius: 10px; font-size: 14px; margin: 0; }
.nowline .dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; flex: none; }
.nowline.okline { background: var(--ok-soft); color: var(--ok-fg); }
.nowline.warnline { background: var(--warn-soft); color: var(--warn-fg); }
.nowline.err { background: var(--crit-soft); color: var(--crit-fg); }
.nowline.muted { background: var(--field); }
.pickwrap { position: relative; }
.entityfield { width: 100%; text-align: left; min-height: 56px; padding: 8px 12px; border-radius: 10px; border: 1px solid var(--divider);
  background: var(--field); color: var(--text); display: flex; align-items: center; gap: 12px; }
.nowchip { padding: 4px 10px; border-radius: 12px; background: var(--info-soft); color: var(--info-fg); font-size: 13px; font-weight: 500; white-space: nowrap; }
.dropdown { position: absolute; left: 0; right: 0; top: calc(100% + 4px); z-index: 6; background: var(--card); border: 1px solid var(--divider);
  border-radius: 12px; box-shadow: 0 8px 24px rgba(0,0,0,.18); padding: 8px; display: flex; flex-direction: column; gap: 4px; max-height: 360px; overflow-y: auto; }
.opt { text-align: left; min-height: 48px; padding: 6px 10px; border: 0; border-radius: 8px; background: none; color: var(--text);
  display: flex; align-items: center; gap: 12px; }
.opt:hover, .opt:focus-visible { background: var(--field); }
.chrow { border: 1px solid var(--divider); border-radius: 12px; padding: 4px 14px; }
.chrow.on { border-color: var(--primary); }
.chrow ha-icon { --mdc-icon-size: 22px; }
.pfg { color: var(--primary-fg); }
.chbody { border-top: 1px solid var(--divider); padding: 14px 0 12px; display: flex; flex-direction: column; gap: 18px; }
.itile { width: 44px; height: 44px; border-radius: 10px; border: 2px solid var(--divider); background: var(--card); color: var(--text);
  display: flex; align-items: center; justify-content: center; }
.itile.on { border-color: var(--primary); background: var(--primary-soft); }
.swatch { width: 44px; height: 44px; border-radius: 50%; border: 2px solid transparent; background: var(--card); padding: 4px; display: flex; }
.swatch.on { border-color: var(--primary); }
.swatch span { flex: 1; border-radius: 50%; color: #fff; display: flex; align-items: center; justify-content: center; }
.swatch ha-icon { --mdc-icon-size: 16px; }
.fold { background: var(--card); border: 1px solid var(--divider); border-radius: 16px; }
.foldhead { width: 100%; text-align: left; border: 0; background: none; color: var(--text); padding: 16px 24px;
  display: flex; align-items: center; gap: 12px; min-height: 64px; }
.foldtitle { display: block; font-size: 16px; font-weight: 500; }
.foldsum { display: block; font-size: 13px; color: var(--text2); }
.foldhead ha-icon { transition: transform .15s; }
.foldhead ha-icon.rot { transform: rotate(180deg); }
.foldbody { border-top: 1px solid var(--divider); padding: 16px 24px 24px; display: flex; flex-direction: column; gap: 14px; }
.foldbody.grid2 { display: grid; }

/* Preview */
.ph { margin: 0 0 6px; font-size: 13px; font-weight: 500; color: var(--text2); }
.phone { box-shadow: 0 2px 10px rgba(0,0,0,.06); }
.pbtn { padding: 6px 12px; border-radius: 14px; background: var(--primary-soft); color: var(--primary-fg); font-size: 13px; font-weight: 500; }
.pbar { display: flex; align-items: center; gap: 10px; margin-top: 6px; }
.pbar .track { flex: 1; height: 6px; border-radius: 3px; background: var(--divider); overflow: hidden; display: block; }
.pbar .track span { display: block; height: 6px; }
.wallprev { background: #15171b; color: #f2f0ec; border-radius: 16px; padding: 14px 16px; font-family: Barlow, Roboto, sans-serif;
  display: flex; flex-direction: column; gap: 12px; }
.wallbar { display: flex; align-items: center; gap: 10px; min-height: 34px; }
.wtitle { font-size: 18px; }
.wpill { display: inline-flex; align-items: center; gap: 6px; max-width: 232px; padding: 6px 12px; border-radius: 17px; color: #1c1210; font-size: 14px; font-weight: 600; }
.wpill ha-icon { --mdc-icon-size: 15px; }
.wpill span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.wchips { display: inline-flex; align-items: center; gap: 12px; color: #a9acb2; font-size: 14px; }
.wbell { display: inline-flex; align-items: center; gap: 4px; color: #e0a955; }
.wbell ha-icon { --mdc-icon-size: 15px; }
.wallrow { border-top: 1px solid #2a2d33; padding-top: 12px; display: flex; gap: 12px; align-items: flex-start; }
.wt { font-weight: 600; }
.wm { font-size: 14px; color: #d3d5d9; }
.ws { font-size: 12px; color: #a9acb2; }

/* Settings */
.problem { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 14px; padding: 12px 16px; border-radius: 12px; background: var(--warn-soft); }
.healthy { display: flex; align-items: center; gap: 10px; padding: 12px 16px; border-radius: 12px; background: var(--ok-soft); color: var(--ok-fg); font-weight: 500; }
.phonerow { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 12px; padding: 4px 0 4px 12px; border-left: 2px solid var(--divider); }
.phonerow select { width: auto; max-width: 220px; }
.avatar { width: 40px; height: 40px; border-radius: 50%; background: var(--primary-soft); color: var(--primary-fg);
  display: flex; align-items: center; justify-content: center; font-weight: 500; flex: none; object-fit: cover; }
.narrowfield { max-width: 340px; display: flex; flex-direction: column; gap: 6px; }
.qbar { position: relative; height: 12px; border-radius: 6px; background: var(--divider); overflow: hidden; }
.qbar span { position: absolute; top: 0; height: 12px; background: var(--info); }
.qrow { display: flex; gap: 12px; align-items: baseline; margin-top: 8px; }
.qrow > span:first-child { flex: none; width: 72px; }

@media (max-width: 600px) {
  .wrap { padding: 0 12px 48px; }
  h1 { font-size: 24px; }
  .card { padding: 18px 16px; }
  .foldhead, .foldbody { padding-left: 16px; padding-right: 16px; }
  .rowacts { width: 100%; justify-content: flex-end; }
  .histmeta { align-items: flex-start; margin-left: 54px; }
}
`;

customElements.define("notification-center-panel", NotificationCenterPanel);
