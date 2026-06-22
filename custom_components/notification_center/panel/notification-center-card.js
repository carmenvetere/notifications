/*
 * Notification Center card — the notification tray itself.
 *
 * This card IS the content (no bell chip, no modal): drop it into a mobile
 * pop-up (bubble-card / browser_mod) or straight onto a wall panel. It fills
 * its container and scales with the container's width (container-query units),
 * so the same card looks right on a phone sheet and a 480px+ wall panel.
 *
 * Auto-loaded by the integration, so `custom:notification-center-card` appears
 * in the card picker. Config (all optional):
 *   type: custom:notification-center-card
 *   entity: sensor.notification_center
 *   priority_entity: sensor.notification_center_priority
 *   title: Notifications
 *   show_header: true
 */

const PRIORITY_META = {
  critical: { label: "Critical", color: "#EA4D3D" },
  warning: { label: "Warning", color: "#EF8C00" },
  info: { label: "Info", color: "#7295B2" },
};
const PRIORITY_ORDER = ["critical", "warning", "info"];

const SNOOZE_OPTIONS = [
  { label: "15 minutes", sub: "", minutes: () => 15 },
  { label: "1 hour", sub: "", minutes: () => 60 },
  { label: "3 hours", sub: "", minutes: () => 180 },
  { label: "Tomorrow morning", sub: "7:00", minutes: () => minutesUntil(7, 0, true) },
];

function minutesUntil(hour, minute, tomorrow = false) {
  const now = new Date();
  const t = new Date();
  t.setHours(hour, minute, 0, 0);
  if (tomorrow) t.setDate(t.getDate() + 1);
  if (t <= now) t.setDate(t.getDate() + 1);
  return Math.max(1, Math.round((t - now) / 60000));
}

function ageLabel(min) {
  const m = Number(min) || 0;
  if (m < 1) return "just now";
  if (m < 60) return `${m}m`;
  if (m < 1440) return `${Math.floor(m / 60)}h`;
  return `${Math.floor(m / 1440)}d`;
}

function esc(s) {
  return String(s == null ? "" : s).replace(
    /[&<>"]/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])
  );
}

class NotificationCenterCard extends HTMLElement {
  constructor() {
    super();
    // Attach the shadow root once, here — never inside setConfig (some HA
    // frontend versions call setConfig in contexts where doing DOM work throws,
    // which surfaces as "Configuration error").
    this.attachShadow({ mode: "open" });
    this._expanded = {};
    this._snoozeFor = null;
  }

  static getStubConfig() {
    return { entity: "sensor.notification_center" };
  }

  setConfig(config) {
    if (!config || typeof config !== "object") {
      throw new Error("Invalid notification-center-card configuration");
    }
    this._config = config;
    this._entity = config.entity || "sensor.notification_center";
    this._priorityEntity =
      config.priority_entity || "sensor.notification_center_priority";
    this._title = config.title || "Notifications";
    this._showHeader = config.show_header !== false;
    this._render();
  }

  connectedCallback() {
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return Math.max(3, this._alerts().length + 1);
  }

  _alerts() {
    const st = this._hass && this._hass.states[this._entity];
    return (st && st.attributes && st.attributes.alerts) || [];
  }

  _grouped() {
    const groups = { critical: [], warning: [], info: [] };
    for (const a of this._alerts()) (groups[a.priority] || groups.info).push(a);
    return groups;
  }

  _service(service, data) {
    if (this._hass) this._hass.callService("notification_center", service, data);
  }

  _render() {
    if (!this._config || !this.shadowRoot) return;
    const alerts = this._alerts();
    const count = alerts.length;
    const prioSt = this._hass && this._hass.states[this._priorityEntity];
    const priority = (prioSt && prioSt.state) || "none";
    const accent =
      (prioSt && prioSt.attributes && prioSt.attributes.color) ||
      (PRIORITY_META[priority] && PRIORITY_META[priority].color) ||
      "#9aa2ad";

    const header = this._showHeader
      ? `<div class="head" style="--accent:${accent}">
           <ha-icon icon="mdi:bell${count ? "-badge" : "-outline"}"></ha-icon>
           <span class="title">${esc(this._title)}</span>
           <span class="count">${count}</span>
         </div>`
      : "";

    this.shadowRoot.innerHTML = `${this._styles()}
      <div class="card">
        ${header}
        <div class="body">${this._renderGroups()}</div>
        ${this._snoozeFor ? this._renderSnooze() : ""}
      </div>`;
    this._wire();
  }

  _renderGroups() {
    const groups = this._grouped();
    const sections = PRIORITY_ORDER.filter((p) => groups[p].length);
    if (!sections.length) {
      return `<div class="empty">
        <ha-icon icon="mdi:check-circle-outline"></ha-icon>
        <span>You're all caught up.</span></div>`;
    }
    return sections
      .map((p) => {
        const meta = PRIORITY_META[p];
        const rows = groups[p].map((a) => this._renderAlert(a)).join("");
        return `<div class="group">
            <div class="glabel" style="color:${meta.color}">
              ${meta.label}<span class="gcount">${groups[p].length}</span>
            </div>${rows}
          </div>`;
      })
      .join("");
  }

  _renderAlert(a) {
    const color = a.color || (PRIORITY_META[a.priority] || {}).color || "#7295B2";
    const actions = a.actions || [];
    const digestTag = a.digest
      ? `<button class="tag" data-toggle="${esc(a.tag)}">Digest${
          (a.items || []).length ? ` · ${a.items.length}` : ""
        } <ha-icon icon="mdi:chevron-${this._expanded[a.tag] ? "up" : "down"}"></ha-icon></button>`
      : "";
    const chips = actions.length
      ? `<div class="acts">
           ${
             actions.includes("snooze")
               ? `<button class="act snooze" data-act="snooze" data-tag="${esc(
                   a.tag
                 )}" title="Snooze"><ha-icon icon="mdi:bell-sleep-outline"></ha-icon></button>`
               : ""
           }
           ${
             actions.includes("dismiss")
               ? `<button class="act dismiss" data-act="dismiss" data-tag="${esc(
                   a.tag
                 )}" style="color:${color};border-color:${color}55" title="Dismiss"><ha-icon icon="mdi:close"></ha-icon></button>`
               : ""
           }
         </div>`
      : "";
    const cbtns = (a.buttons || []).length
      ? `<div class="cbtns">${a.buttons
          .map(
            (b) => `<button class="cbtn" data-run="${esc(a.tag)}" data-action="${esc(
              b.id
            )}"${b.confirm ? ` data-confirm="${esc(b.confirm)}"` : ""}>${
              b.icon ? `<ha-icon icon="${esc(b.icon)}"></ha-icon>` : ""
            }${esc(b.label)}</button>`
          )
          .join("")}</div>`
      : "";
    const items =
      a.digest && this._expanded[a.tag] && (a.items || []).length
        ? `<div class="items">${a.items
            .map(
              (it) => `<div class="item">
                  <ha-icon icon="${esc(it.icon || "mdi:circle-small")}" style="color:${esc(
                it.color || color
              )}"></ha-icon>
                  <span class="iname">${esc(it.name)}</span>
                  <span class="idetail" style="color:${esc(it.color || color)}">${esc(
                it.detail || ""
              )}</span>
                </div>`
            )
            .join("")}</div>`
        : "";

    return `<div class="alert" style="--c:${color}">
        <div class="amain">
          <div class="ichip"><ha-icon icon="${esc(a.icon || "mdi:bell")}"></ha-icon></div>
          <div class="atext">
            <div class="atitle">${esc(a.title || a.name)}</div>
            ${a.message ? `<div class="asub">${esc(a.message)}</div>` : ""}
            <div class="ameta">
              <span>${ageLabel(a.age_min)}${Number(a.age_min) >= 1 ? " ago" : ""}</span>
              ${digestTag}
            </div>
          </div>
          ${chips}
        </div>
        ${cbtns}
        ${items}
      </div>`;
  }

  _renderSnooze() {
    const opts = SNOOZE_OPTIONS.map(
      (o, i) =>
        `<button class="sopt" data-snooze="${i}"><b>${o.label}</b>${
          o.sub ? `<span>${o.sub}</span>` : ""
        }</button>`
    ).join("");
    return `<div class="overlay">
      <div class="sheet">
        <div class="shead">Snooze until…</div>
        <div class="snote">Leaves the tray now, re-alerts at the chosen time.</div>
        <div class="sgrid">${opts}</div>
        <button class="scancel">Cancel</button>
      </div>
    </div>`;
  }

  _wire() {
    const r = this.shadowRoot;
    r.querySelectorAll(".act").forEach((btn) => {
      btn.onclick = (e) => {
        const el = e.currentTarget;
        const tag = el.getAttribute("data-tag");
        if (el.getAttribute("data-act") === "dismiss") this._service("dismiss", { tag });
        else { this._snoozeFor = tag; this._render(); }
      };
    });
    r.querySelectorAll(".tag[data-toggle]").forEach((t) => {
      t.onclick = (e) => {
        const tag = e.currentTarget.getAttribute("data-toggle");
        this._expanded[tag] = !this._expanded[tag];
        this._render();
      };
    });
    r.querySelectorAll(".cbtn").forEach((b) => {
      b.onclick = (e) => {
        const el = e.currentTarget;
        const confirm = el.getAttribute("data-confirm");
        if (confirm && !window.confirm(confirm)) return;
        this._service("run_action", {
          tag: el.getAttribute("data-run"),
          action: Number(el.getAttribute("data-action")),
        });
      };
    });
    r.querySelectorAll(".sopt").forEach((b) => {
      b.onclick = (e) => {
        const opt = SNOOZE_OPTIONS[Number(e.currentTarget.getAttribute("data-snooze"))];
        this._service("snooze", { tag: this._snoozeFor, minutes: opt.minutes() });
        this._snoozeFor = null;
        this._render();
      };
    });
    const cancel = r.querySelector(".scancel");
    if (cancel) cancel.onclick = () => { this._snoozeFor = null; this._render(); };
    const overlay = r.querySelector(".overlay");
    if (overlay)
      overlay.onclick = (e) => {
        if (e.target === overlay) { this._snoozeFor = null; this._render(); }
      };
  }

  _styles() {
    return `<style>
      :host { display: block; height: 100%; }
      .card {
        container-type: inline-size;
        position: relative;
        height: 100%;
        box-sizing: border-box;
        display: flex; flex-direction: column;
        background: var(--ha-card-background, var(--card-background-color, #16191f));
        color: var(--primary-text-color, #f2f4f8);
        border-radius: var(--ha-card-border-radius, 18px);
        overflow: hidden;
        font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif);
      }
      .head {
        flex: none; display: flex; align-items: center; gap: 2.5cqi;
        padding: clamp(12px, 3.5cqi, 22px);
        border-bottom: 1px solid var(--divider-color, rgba(255,255,255,.06));
        background: linear-gradient(180deg, color-mix(in srgb, var(--accent) 10%, transparent), transparent);
      }
      .head ha-icon { --mdc-icon-size: clamp(20px, 5.5cqi, 30px); color: var(--accent); }
      .title { font-size: clamp(16px, 4.6cqi, 26px); font-weight: 700; }
      .count { margin-left: auto; background: var(--secondary-background-color, #232831);
        color: var(--secondary-text-color, #9aa2ad); border-radius: 999px;
        padding: 0.6cqi 3cqi; font-size: clamp(17px, 5cqi, 26px); font-weight: 700; }
      .body { flex: 1 1 auto; overflow-y: auto; padding: clamp(8px, 2.5cqi, 16px); }
      .empty { height: 100%; min-height: 120px; display: flex; flex-direction: column;
        align-items: center; justify-content: center; gap: 2cqi;
        color: var(--secondary-text-color, #9aa2ad); }
      .empty ha-icon { --mdc-icon-size: clamp(34px, 12cqi, 64px); opacity: .5; }
      .empty span { font-size: clamp(13px, 3.6cqi, 18px); }
      .group { margin-bottom: clamp(8px, 2.5cqi, 16px); }
      .glabel { font-size: clamp(13px, 3.7cqi, 19px); font-weight: 700; text-transform: uppercase;
        letter-spacing: .04em; margin: 1.5cqi 1cqi; display: flex; gap: 2cqi; align-items: center; }
      .gcount { color: var(--secondary-text-color, #6b7280); font-weight: 600; }
      .alert { background: color-mix(in srgb, var(--c) 7%, var(--ha-card-background, #1e222a));
        border-left: 3px solid var(--c); border-radius: clamp(10px, 3cqi, 18px);
        padding: clamp(10px, 3cqi, 18px); margin: 2cqi 0; }
      .amain { display: flex; align-items: flex-start; gap: 3cqi; }
      .ichip { flex: none; width: clamp(36px, 11cqi, 60px); height: clamp(36px, 11cqi, 60px);
        border-radius: clamp(9px, 3cqi, 16px); display: grid; place-items: center;
        background: color-mix(in srgb, var(--c) 22%, transparent); }
      .ichip ha-icon { --mdc-icon-size: clamp(20px, 6cqi, 34px); color: var(--c); }
      .atext { flex: 1; min-width: 0; }
      .atitle { font-size: clamp(14px, 4cqi, 22px); font-weight: 600; }
      .asub { font-size: clamp(12px, 3.4cqi, 18px); color: var(--secondary-text-color, #9aa2ad); margin-top: .3cqi; }
      .ameta { display: flex; align-items: center; gap: 2cqi; flex-wrap: wrap;
        font-size: clamp(11px, 3cqi, 15px); color: var(--secondary-text-color, #6b7280); margin-top: 1.5cqi; }
      .tag { display: inline-flex; align-items: center; gap: .5cqi; background: var(--secondary-background-color, #232831);
        color: var(--secondary-text-color, #9aa2ad); border: none; border-radius: 999px;
        padding: .6cqi 2cqi; font: inherit; font-size: clamp(11px, 3cqi, 15px); font-weight: 600; cursor: pointer; }
      .tag ha-icon { --mdc-icon-size: clamp(14px, 3.8cqi, 18px); }
      .acts { display: flex; gap: 2cqi; align-items: center; }
      .act { flex: none; display: grid; place-items: center; cursor: pointer;
        width: clamp(38px, 11cqi, 56px); height: clamp(38px, 11cqi, 56px);
        border-radius: 999px; border: 1px solid transparent;
        background: var(--secondary-background-color, #232831); color: var(--secondary-text-color, #cfd6e0); }
      .act ha-icon { --mdc-icon-size: clamp(20px, 5.5cqi, 30px); }
      .act.dismiss { background: color-mix(in srgb, var(--c) 14%, transparent); }
      .items { margin: 2cqi 0 0 calc(clamp(36px, 11cqi, 60px) + 3cqi);
        display: flex; flex-direction: column; gap: 1.5cqi; }
      .item { display: flex; align-items: center; gap: 2cqi; font-size: clamp(12px, 3.4cqi, 17px); }
      .item ha-icon { --mdc-icon-size: clamp(16px, 4.5cqi, 22px); }
      .iname { flex: 1; min-width: 0; }
      .idetail { font-weight: 600; }
      .cbtns { display: flex; flex-wrap: wrap; gap: 2cqi;
        margin: 2.5cqi 0 0 calc(clamp(36px, 11cqi, 60px) + 3cqi); }
      .cbtn { display: inline-flex; align-items: center; gap: 1.5cqi; cursor: pointer;
        padding: clamp(8px, 2.4cqi, 14px) clamp(12px, 3.4cqi, 20px);
        border-radius: 999px; font: inherit; font-size: clamp(12px, 3.4cqi, 17px); font-weight: 600;
        background: color-mix(in srgb, var(--c) 16%, transparent); color: var(--c);
        border: 1px solid color-mix(in srgb, var(--c) 40%, transparent); }
      .cbtn ha-icon { --mdc-icon-size: clamp(16px, 4.4cqi, 22px); }
      /* snooze overlay (scoped to the card so it works embedded) */
      .overlay { position: absolute; inset: 0; z-index: 5; background: rgba(0,0,0,.55);
        display: flex; align-items: flex-end; }
      .sheet { width: 100%; box-sizing: border-box; background: var(--card-background-color, #16191f);
        border-radius: 24px 24px 0 0; padding: clamp(14px, 4cqi, 26px); }
      .shead { font-size: clamp(15px, 4.2cqi, 22px); font-weight: 700; margin-bottom: 1.5cqi; }
      .snote { color: var(--secondary-text-color, #9aa2ad); font-size: clamp(12px, 3.2cqi, 16px); margin-bottom: 3cqi; }
      .sgrid { display: grid; grid-template-columns: 1fr 1fr; gap: 2.5cqi; }
      .sopt { display: flex; flex-direction: column; gap: .5cqi; align-items: flex-start;
        padding: clamp(14px, 4cqi, 22px); border-radius: clamp(12px, 3.5cqi, 18px);
        background: var(--secondary-background-color, #1a1e25);
        border: 1px solid var(--divider-color, rgba(255,255,255,.06));
        color: var(--primary-text-color, #f2f4f8); font: inherit; cursor: pointer; text-align: left; }
      .sopt b { font-size: clamp(14px, 3.8cqi, 19px); }
      .sopt span { font-size: clamp(11px, 3cqi, 15px); color: var(--secondary-text-color, #9aa2ad); }
      .scancel { width: 100%; margin-top: 2.5cqi; padding: clamp(12px, 3.5cqi, 18px);
        border-radius: clamp(12px, 3.5cqi, 18px); background: transparent;
        border: 1px solid var(--divider-color, rgba(255,255,255,.1));
        color: var(--secondary-text-color, #9aa2ad); font: inherit; font-weight: 600; cursor: pointer; }
    </style>`;
  }
}

customElements.define("notification-center-card", NotificationCenterCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "notification-center-card",
  name: "Notification Center",
  description:
    "The notification tray: active alerts grouped by priority with gated dismiss/snooze and digest expansion. Fills its container — use in a pop-up or on a wall panel.",
});
