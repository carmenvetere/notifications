/*
 * Notification Center card — mobile surface (Deliverable 2).
 *
 * A self-contained custom Lovelace card (no build step required). Drop this
 * file in <config>/www/ and register it as a dashboard resource:
 *
 *   url: /local/notification-center-card.js
 *   type: module
 *
 * Then add to a view:
 *   - type: custom:notification-center-card        # bell chip -> pop-up sheet
 *   - type: custom:notification-center-card        # always-expanded list
 *     mode: inline
 *
 * Data source: sensor.notification_center (attributes.alerts[]) and
 * sensor.notification_center_priority. Renders only the actions each alert
 * permits (alert.actions), groups by priority, and expands digests (alert.items).
 */

const PRIORITY_META = {
  critical: { label: "Critical", color: "#EA4D3D" },
  warning: { label: "Warning", color: "#EF8C00" },
  info: { label: "Info", color: "#7295B2" },
};
const PRIORITY_ORDER = ["critical", "warning", "info"];
const CHANNEL_ICON = {
  mobile: "mdi:cellphone",
  bell: "mdi:bell",
  wall: "mdi:monitor",
  tts: "mdi:bullhorn-variant",
  navigate: "mdi:navigation-variant",
};

const SNOOZE_OPTIONS = [
  { label: "15 minutes", minutes: () => 15 },
  { label: "1 hour", minutes: () => 60 },
  { label: "3 hours", minutes: () => 180 },
  { label: "This evening", minutes: () => minutesUntil(18, 0) },
  { label: "Tomorrow morning", minutes: () => minutesUntil(7, 0, true) },
];

function minutesUntil(hour, minute, tomorrow = false) {
  const now = new Date();
  const t = new Date();
  t.setHours(hour, minute, 0, 0);
  if (tomorrow || t <= now) t.setDate(t.getDate() + (tomorrow ? 1 : 0));
  if (t <= now) t.setDate(t.getDate() + 1);
  return Math.max(1, Math.round((t - now) / 60000));
}

function ageLabel(min) {
  const m = Number(min) || 0;
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
  setConfig(config) {
    this._config = config || {};
    this._entity = this._config.entity || "sensor.notification_center";
    this._priorityEntity =
      this._config.priority_entity || "sensor.notification_center_priority";
    this._mode = this._config.mode || "chip"; // "chip" | "inline"
    this._open = false;
    this._snoozeFor = null; // tag awaiting a duration choice
    this._expanded = {}; // tag -> bool (digest expansion)
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return this._mode === "inline" ? 4 : 1;
  }

  _alerts() {
    const st = this._hass && this._hass.states[this._entity];
    return (st && st.attributes && st.attributes.alerts) || [];
  }

  _grouped() {
    const groups = { critical: [], warning: [], info: [] };
    for (const a of this._alerts()) {
      (groups[a.priority] || groups.info).push(a);
    }
    return groups;
  }

  _service(service, data) {
    if (!this._hass) return;
    this._hass.callService("notification_center", service, data);
  }

  // --- rendering ----------------------------------------------------------
  _render() {
    if (!this._config) return;
    if (!this._root) {
      this._root = this.attachShadow ? this.attachShadow({ mode: "open" }) : this;
    }
    this.style.display = this._mode === "inline" ? "block" : "inline-block";
    const alerts = this._alerts();
    const count = alerts.length;
    const prioSt = this._hass && this._hass.states[this._priorityEntity];
    const priority = (prioSt && prioSt.state) || "none";
    const color =
      (prioSt && prioSt.attributes && prioSt.attributes.color) ||
      (PRIORITY_META[priority] && PRIORITY_META[priority].color) ||
      "#9aa2ad";

    const chip =
      this._mode === "chip"
        ? `<button class="chip" title="Notifications">
             <ha-icon icon="mdi:bell${count ? "-badge" : "-outline"}" style="color:${color}"></ha-icon>
             ${count ? `<span class="badge" style="background:${color}">${count}</span>` : ""}
           </button>`
        : "";

    const sheet =
      this._mode === "inline" || this._open
        ? `<div class="sheet ${this._mode === "inline" ? "inline" : "modal"}">
             ${this._mode === "chip" ? `<div class="handle"></div>` : ""}
             <div class="sheet-head">
               <ha-icon icon="mdi:bell"></ha-icon>
               <span class="sheet-title">Notifications</span>
               <span class="count-pill">${count}</span>
             </div>
             <div class="sheet-body">${this._renderGroups()}</div>
           </div>`
        : "";

    const backdrop =
      this._mode === "chip" && this._open ? `<div class="backdrop"></div>` : "";
    const snooze = this._snoozeFor ? this._renderSnooze() : "";

    this._root.innerHTML = `${this._styles()}${chip}${backdrop}${sheet}${snooze}`;
    this._wire();
  }

  _renderGroups() {
    const groups = this._grouped();
    const sections = PRIORITY_ORDER.filter((p) => groups[p].length);
    if (!sections.length) {
      return `<div class="empty">You're all caught up.</div>`;
    }
    return sections
      .map((p) => {
        const meta = PRIORITY_META[p];
        const rows = groups[p].map((a) => this._renderAlert(a)).join("");
        return `<div class="group">
            <div class="group-label" style="color:${meta.color}">
              ${meta.label}<span class="group-count">${groups[p].length}</span>
            </div>${rows}
          </div>`;
      })
      .join("");
  }

  _renderAlert(a) {
    const color = a.color || (PRIORITY_META[a.priority] || {}).color || "#7295B2";
    const actions = a.actions || [];
    const channels = (a.channels || [])
      .map(
        (c) =>
          `<ha-icon class="ch" icon="${CHANNEL_ICON[c] || "mdi:bell"}"></ha-icon>`
      )
      .join("");
    const digestTag = a.digest
      ? `<span class="tag" data-toggle="${esc(a.tag)}">Digest${
          (a.items || []).length ? ` · ${a.items.length}` : ""
        }</span>`
      : "";
    const chips = actions.length
      ? `<div class="row-actions">
           ${
             actions.includes("dismiss")
               ? `<button class="act dismiss" data-act="dismiss" data-tag="${esc(
                   a.tag
                 )}" style="color:${color};border-color:${color}55">Dismiss</button>`
               : ""
           }
           ${
             actions.includes("snooze")
               ? `<button class="act snooze" data-act="snooze" data-tag="${esc(
                   a.tag
                 )}">Snooze</button>`
               : ""
           }
         </div>`
      : "";
    const items =
      a.digest && this._expanded[a.tag] && (a.items || []).length
        ? `<div class="items">${a.items
            .map(
              (it) => `<div class="item">
                  <ha-icon icon="${esc(it.icon || "mdi:circle-small")}" style="color:${esc(
                it.color || color
              )}"></ha-icon>
                  <span class="item-name">${esc(it.name)}</span>
                  <span class="item-detail" style="color:${esc(
                    it.color || color
                  )}">${esc(it.detail || "")}</span>
                </div>`
            )
            .join("")}</div>`
        : "";

    return `<div class="alert">
        <div class="alert-main">
          <div class="icon-chip" style="background:${color}28">
            <ha-icon icon="${esc(a.icon || "mdi:bell")}" style="color:${color}"></ha-icon>
          </div>
          <div class="alert-text">
            <div class="alert-title">${esc(a.title || a.name)}</div>
            ${a.message ? `<div class="alert-sub">${esc(a.message)}</div>` : ""}
            <div class="alert-meta">
              <span>${ageLabel(a.age_min)} ago</span>
              ${channels ? `<span class="dot">·</span>${channels}` : ""}
              ${digestTag}
            </div>
          </div>
          ${chips}
        </div>
        ${items}
      </div>`;
  }

  _renderSnooze() {
    const opts = SNOOZE_OPTIONS.map(
      (o, i) =>
        `<button class="snooze-opt" data-snooze="${i}">${o.label}</button>`
    ).join("");
    return `<div class="backdrop snooze-backdrop"></div>
      <div class="sheet modal snooze-sheet">
        <div class="handle"></div>
        <div class="sheet-head"><span class="sheet-title">Snooze until…</span></div>
        <div class="snooze-note">Leaves the tray now, re-alerts at the chosen time.</div>
        <div class="snooze-grid">${opts}</div>
        <button class="snooze-cancel">Cancel</button>
      </div>`;
  }

  // --- events -------------------------------------------------------------
  _wire() {
    const r = this._root;
    const chip = r.querySelector(".chip");
    if (chip) chip.onclick = () => { this._open = true; this._render(); };

    const backdrop = r.querySelector(".backdrop:not(.snooze-backdrop)");
    if (backdrop) backdrop.onclick = () => { this._open = false; this._render(); };

    r.querySelectorAll(".act").forEach((btn) => {
      btn.onclick = (e) => {
        const tag = e.currentTarget.getAttribute("data-tag");
        if (e.currentTarget.getAttribute("data-act") === "dismiss") {
          this._service("dismiss", { tag });
        } else {
          this._snoozeFor = tag;
          this._render();
        }
      };
    });

    r.querySelectorAll(".tag[data-toggle]").forEach((t) => {
      t.onclick = (e) => {
        const tag = e.currentTarget.getAttribute("data-toggle");
        this._expanded[tag] = !this._expanded[tag];
        this._render();
      };
    });

    r.querySelectorAll(".snooze-opt").forEach((b) => {
      b.onclick = (e) => {
        const opt = SNOOZE_OPTIONS[Number(e.currentTarget.getAttribute("data-snooze"))];
        this._service("snooze", { tag: this._snoozeFor, minutes: opt.minutes() });
        this._snoozeFor = null;
        this._render();
      };
    });
    const cancel = r.querySelector(".snooze-cancel");
    if (cancel) cancel.onclick = () => { this._snoozeFor = null; this._render(); };
    const sb = r.querySelector(".snooze-backdrop");
    if (sb) sb.onclick = () => { this._snoozeFor = null; this._render(); };
  }

  _styles() {
    return `<style>
      :host { display: inline-block; }
      .chip {
        display: inline-flex; align-items: center; gap: 6px; position: relative;
        background: var(--card-background-color, #1e222a);
        border: 1px solid var(--divider-color, rgba(255,255,255,.08));
        border-radius: 999px; padding: 6px 12px; cursor: pointer;
        color: var(--primary-text-color, #f2f4f8); font: inherit;
      }
      .chip ha-icon { --mdc-icon-size: 22px; }
      .badge { color: #fff; font-size: 12px; font-weight: 700; border-radius: 999px;
               min-width: 18px; height: 18px; padding: 0 5px; display: inline-grid; place-items: center; }
      .backdrop { position: fixed; inset: 0; background: rgba(0,0,0,.5); z-index: 8; }
      .sheet { background: var(--card-background-color, #16191f); color: var(--primary-text-color, #f2f4f8);
               font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif); }
      .sheet.modal {
        position: fixed; left: 0; right: 0; bottom: 0; z-index: 9;
        border-radius: 30px 30px 0 0; padding: 8px 16px 20px;
        max-height: 80vh; overflow-y: auto;
        box-shadow: 0 -8px 30px rgba(0,0,0,.4);
      }
      .sheet.inline { border-radius: 16px; padding: 12px 14px; }
      .handle { width: 40px; height: 4px; border-radius: 999px;
                background: var(--divider-color, rgba(255,255,255,.18)); margin: 6px auto 10px; }
      .sheet-head { display: flex; align-items: center; gap: 10px; padding: 4px 2px 10px; }
      .sheet-head ha-icon { --mdc-icon-size: 22px; }
      .sheet-title { font-size: 18px; font-weight: 700; }
      .count-pill { margin-left: auto; background: var(--secondary-background-color, #232831);
                    color: var(--secondary-text-color, #9aa2ad); border-radius: 999px;
                    padding: 2px 10px; font-size: 13px; font-weight: 600; }
      .empty { padding: 24px 4px; text-align: center; color: var(--secondary-text-color, #9aa2ad); }
      .group { margin-bottom: 14px; }
      .group-label { font-size: 12px; font-weight: 700; text-transform: uppercase;
                     letter-spacing: .04em; margin: 6px 2px; display: flex; gap: 8px; align-items: center; }
      .group-count { color: var(--secondary-text-color, #6b7280); font-weight: 600; }
      .alert { background: var(--ha-card-background, #1e222a); border-radius: 16px;
               padding: 12px; margin: 8px 0; }
      .alert-main { display: flex; align-items: flex-start; gap: 12px; }
      .icon-chip { flex: none; width: 40px; height: 40px; border-radius: 11px; display: grid; place-items: center; }
      .icon-chip ha-icon { --mdc-icon-size: 22px; }
      .alert-text { flex: 1; min-width: 0; }
      .alert-title { font-size: 15px; font-weight: 600; }
      .alert-sub { font-size: 13px; color: var(--secondary-text-color, #9aa2ad); margin-top: 1px; }
      .alert-meta { display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
                    font-size: 12px; color: var(--secondary-text-color, #6b7280); margin-top: 6px; }
      .alert-meta .ch { --mdc-icon-size: 15px; }
      .alert-meta .dot { opacity: .5; }
      .tag { background: var(--secondary-background-color, #232831); border-radius: 999px;
             padding: 1px 8px; font-weight: 600; cursor: pointer; }
      .row-actions { display: flex; flex-direction: column; gap: 6px; align-items: flex-end; }
      .act { font: inherit; font-size: 12.5px; font-weight: 700; border-radius: 8px;
             padding: 6px 12px; cursor: pointer; border: 1px solid transparent; }
      .act.dismiss { background: transparent; }
      .act.snooze { background: var(--secondary-background-color, #232831);
                    color: var(--secondary-text-color, #cfd6e0); }
      .items { margin: 8px 0 0 52px; display: flex; flex-direction: column; gap: 6px; }
      .item { display: flex; align-items: center; gap: 8px; font-size: 13px; }
      .item ha-icon { --mdc-icon-size: 18px; }
      .item-name { flex: 1; min-width: 0; }
      .item-detail { font-weight: 600; }
      .snooze-sheet { z-index: 11; }
      .snooze-backdrop { z-index: 10; }
      .snooze-note { color: var(--secondary-text-color, #9aa2ad); font-size: 13px; margin: 0 2px 12px; }
      .snooze-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
      .snooze-opt { font: inherit; font-weight: 600; padding: 16px 10px; border-radius: 14px;
                    background: var(--secondary-background-color, #1a1e25);
                    border: 1px solid var(--divider-color, rgba(255,255,255,.06));
                    color: var(--primary-text-color, #f2f4f8); cursor: pointer; }
      .snooze-cancel { width: 100%; margin-top: 12px; padding: 14px; border-radius: 14px;
                       background: transparent; border: 1px solid var(--divider-color, rgba(255,255,255,.1));
                       color: var(--secondary-text-color, #9aa2ad); font: inherit; font-weight: 600; cursor: pointer; }
    </style>`;
  }
}

customElements.define("notification-center-card", NotificationCenterCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "notification-center-card",
  name: "Notification Center",
  description: "Active alerts grouped by priority, with gated dismiss/snooze and digest expansion.",
});
