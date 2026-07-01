/*
 * Notification Center card — the notification tray itself (style: "1B").
 *
 * This card IS the content (no bell chip, no modal): drop it into a mobile
 * pop-up (bubble-card / browser_mod) or straight onto a wall panel. It fills
 * its container and scales with the container's width (container-query units),
 * so the same card looks right on a phone sheet and a 480px+ wall panel.
 *
 * 1B "quiet sections": priority is carried only by the muted section header;
 * cards are flat (no tile, no colored bar). Each card shows a single dismiss ✕
 * and, when it has a custom action, one full-width response button. Snooze is
 * off the card face — long-press a row to open the snooze sheet.
 *
 * Colors map to HA theme variables (dark values are only fallbacks) so the card
 * follows the selected theme.
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
  critical: { label: "Critical" },
  warning: { label: "Warning" },
  info: { label: "Info" },
};
const PRIORITY_ORDER = ["critical", "warning", "info"];
// Muted, low-contrast section-label tints (priority lives here, not on cards).
const LABEL_COLOR = { critical: "#cf7b73", warning: "#b89360", info: "#79828f" };

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
  if (m < 1) return "now";
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

  _navigate(path) {
    if (!path) return;
    history.pushState(null, "", path);
    this.dispatchEvent(
      new CustomEvent("location-changed", {
        bubbles: true,
        composed: true,
        detail: { replace: false },
      })
    );
  }

  _render() {
    if (!this._config || !this.shadowRoot) return;
    const count = this._alerts().length;

    const header = this._showHeader
      ? `<div class="head">
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
        const rows = groups[p].map((a) => this._renderAlert(a)).join("");
        return `<div class="group">
            <div class="glabel" style="color:${LABEL_COLOR[p] || "#79828f"}">
              ${PRIORITY_META[p].label}<span class="gcount">${groups[p].length}</span>
            </div>${rows}
          </div>`;
      })
      .join("");
  }

  _renderAlert(a) {
    const color = a.color || "#7295B2";
    const actions = a.actions || [];
    const digestTag = a.digest
      ? `<button class="tag" data-toggle="${esc(a.tag)}">Digest${
          (a.items || []).length ? ` · ${a.items.length}` : ""
        } <ha-icon icon="mdi:chevron-${this._expanded[a.tag] ? "up" : "down"}"></ha-icon></button>`
      : "";
    const dismissBtn = actions.includes("dismiss")
      ? `<button class="dismiss" data-tag="${esc(a.tag)}" title="Dismiss"><ha-icon icon="mdi:close"></ha-icon></button>`
      : "";
    // Each custom action becomes a full-width response button.
    const response = (a.buttons || [])
      .map(
        (b) => `<button class="response" data-run="${esc(a.tag)}" data-action="${esc(b.id)}"${
          b.confirm ? ` data-confirm="${esc(b.confirm)}"` : ""
        }><ha-icon icon="${esc(b.icon || "mdi:check")}"></ha-icon>${esc(b.label)}</button>`
      )
      .join("");
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
                  <button class="idismiss" data-item-tag="${esc(a.tag)}" data-item-key="${esc(
                it.key || it.name
              )}" title="Dismiss"><ha-icon icon="mdi:close"></ha-icon></button>
                </div>`
            )
            .join("")}</div>`
        : "";
    const snoozeAttr = actions.includes("snooze") ? ` data-snooze-tag="${esc(a.tag)}"` : "";
    const navAttr = a.navigation_target ? ` data-nav="${esc(a.navigation_target)}"` : "";

    return `<div class="alert${a.navigation_target ? " tappable" : ""}"${snoozeAttr}${navAttr}>
        <div class="amain">
          <ha-icon class="aicon" icon="${esc(a.icon || "mdi:bell")}"></ha-icon>
          <div class="atext">
            <div class="atitle">
              <span class="aname">${esc(a.title || a.name)}</span>
              <span class="aage">${ageLabel(a.age_min)}</span>
            </div>
            ${a.message ? `<div class="asub">${esc(a.message)}</div>` : ""}
            ${digestTag ? `<div class="ameta">${digestTag}</div>` : ""}
          </div>
          ${dismissBtn}
        </div>
        ${response}
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
    r.querySelectorAll(".dismiss").forEach((btn) => {
      btn.onclick = (e) => {
        e.stopPropagation(); // don't also trigger row navigation
        this._service("dismiss", { tag: e.currentTarget.getAttribute("data-tag") });
      };
    });
    r.querySelectorAll(".response").forEach((btn) => {
      btn.onclick = (e) => {
        e.stopPropagation();
        const el = e.currentTarget;
        const confirm = el.getAttribute("data-confirm");
        if (confirm && !window.confirm(confirm)) return;
        this._service("run_action", {
          tag: el.getAttribute("data-run"),
          action: Number(el.getAttribute("data-action")),
        });
      };
    });
    r.querySelectorAll(".tag[data-toggle]").forEach((t) => {
      t.onclick = (e) => {
        e.stopPropagation();
        const tag = e.currentTarget.getAttribute("data-toggle");
        this._expanded[tag] = !this._expanded[tag];
        this._render();
      };
    });
    r.querySelectorAll(".idismiss").forEach((b) => {
      b.onclick = (e) => {
        e.stopPropagation();
        this._service("dismiss_item", {
          tag: e.currentTarget.getAttribute("data-item-tag"),
          item: e.currentTarget.getAttribute("data-item-key"),
        });
      };
    });
    // Tap a row with a navigation target to open that dashboard path.
    r.querySelectorAll(".alert[data-nav]").forEach((el) => {
      el.addEventListener("click", () => this._navigate(el.getAttribute("data-nav")));
    });
    // Long-press a snoozable row to open the snooze sheet (off the card face).
    r.querySelectorAll("[data-snooze-tag]").forEach((el) => {
      let timer = null;
      const cancel = () => {
        if (timer) { clearTimeout(timer); timer = null; }
      };
      el.addEventListener("pointerdown", () => {
        cancel();
        timer = setTimeout(() => {
          timer = null;
          this._snoozeFor = el.getAttribute("data-snooze-tag");
          this._render();
        }, 500);
      });
      ["pointerup", "pointerleave", "pointercancel"].forEach((ev) =>
        el.addEventListener(ev, cancel)
      );
    });
    r.querySelectorAll(".sopt").forEach((b) => {
      b.onclick = (e) => {
        const opt = SNOOZE_OPTIONS[Number(e.currentTarget.getAttribute("data-snooze"))];
        this._service("snooze", { tag: this._snoozeFor, minutes: opt.minutes() });
        this._snoozeFor = null;
        this._render();
      };
    });
    const cancelBtn = r.querySelector(".scancel");
    if (cancelBtn) cancelBtn.onclick = () => { this._snoozeFor = null; this._render(); };
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
        background: var(--ha-card-background, var(--card-background-color, #20242b));
        color: var(--primary-text-color, #f2f4f8);
        border-radius: var(--ha-card-border-radius, 18px);
        overflow: hidden;
        font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif);
      }
      .head {
        flex: none; display: flex; align-items: center; gap: 2.5cqi;
        padding: clamp(12px, 3.5cqi, 22px);
        border-bottom: 1px solid var(--divider-color, rgba(255,255,255,.06));
        background: transparent;
      }
      .title { font-size: clamp(20px, 5.4cqi, 30px); font-weight: 900; letter-spacing: -.01em;
        color: var(--primary-text-color, #fff); }
      .count { margin-left: auto; text-align: center;
        background: color-mix(in srgb, var(--primary-text-color, #fff) 10%, transparent);
        color: var(--primary-text-color, #cdd3db); border-radius: 999px;
        min-width: clamp(24px, 7cqi, 30px); padding: 0 2.4cqi;
        height: clamp(22px, 6cqi, 28px); line-height: clamp(22px, 6cqi, 28px);
        font-size: clamp(16px, 3.8cqi, 19px); font-weight: 800; }
      .body { flex: 1 1 auto; overflow-y: auto; padding: clamp(8px, 2.5cqi, 16px); }
      .empty { height: 100%; min-height: 120px; display: flex; flex-direction: column;
        align-items: center; justify-content: center; gap: 2cqi;
        color: var(--secondary-text-color, #9aa2ad); }
      .empty ha-icon { --mdc-icon-size: clamp(34px, 12cqi, 64px); opacity: .5; }
      .empty span { font-size: clamp(13px, 3.6cqi, 18px); }
      .group { margin-bottom: clamp(8px, 2.5cqi, 16px); }
      .glabel { font-size: clamp(12px, 3.1cqi, 15px); font-weight: 800; text-transform: uppercase;
        letter-spacing: .1em; margin: 4cqi 1cqi 2cqi; display: flex; gap: 2cqi; align-items: center; }
      .group:first-child .glabel { margin-top: 1.5cqi; }
      .gcount { color: var(--secondary-text-color, #565f6b); font-weight: 800; }
      /* flat cards — no tile, no colored bar, denser */
      .alert { background: color-mix(in srgb, var(--primary-text-color, #fff) 6%, transparent);
        border-radius: clamp(12px, 3.6cqi, 18px); padding: clamp(12px, 3.2cqi, 16px); margin: 2.2cqi 0; }
      .alert.tappable { cursor: pointer; }
      .amain { display: flex; align-items: center; gap: 3cqi; }
      .aicon { flex: none; color: var(--secondary-text-color, #b6bdc7);
        --mdc-icon-size: clamp(22px, 6cqi, 32px); }
      .atext { flex: 1; min-width: 0; }
      .atitle { display: flex; align-items: baseline; gap: 2cqi; }
      .aname { font-size: clamp(16px, 4.6cqi, 22px); font-weight: 700; color: var(--primary-text-color, #fff); }
      .aage { margin-left: auto; font-size: clamp(14px, 3.2cqi, 15px); color: var(--secondary-text-color, #828b97); }
      .asub { font-size: clamp(14px, 3.5cqi, 18px); color: var(--secondary-text-color, #9aa2ad); margin-top: .4cqi; }
      .ameta { display: flex; align-items: center; gap: 2cqi; margin-top: 1.5cqi; }
      .tag { display: inline-flex; align-items: center; gap: .5cqi;
        background: color-mix(in srgb, var(--primary-text-color, #fff) 8%, transparent);
        color: var(--secondary-text-color, #9aa2ad); border: none; border-radius: 999px;
        padding: .6cqi 2cqi; font: inherit; font-size: clamp(11px, 3cqi, 15px); font-weight: 600; cursor: pointer; }
      .tag ha-icon { --mdc-icon-size: clamp(14px, 3.8cqi, 18px); }
      /* single dismiss on the row face */
      .dismiss { flex: none; display: grid; place-items: center; cursor: pointer; border: none;
        width: clamp(38px, 10cqi, 50px); height: clamp(38px, 10cqi, 50px);
        border-radius: clamp(11px, 3cqi, 15px);
        background: color-mix(in srgb, var(--primary-text-color, #fff) 6%, transparent);
        color: var(--secondary-text-color, #8b94a1); }
      .dismiss ha-icon { --mdc-icon-size: clamp(19px, 5cqi, 26px); }
      /* one full-width primary response button below the row */
      .response { display: flex; align-items: center; justify-content: center; gap: 2cqi;
        width: 100%; margin-top: 3cqi; cursor: pointer; border: none;
        border-radius: clamp(11px, 3cqi, 15px); padding: clamp(10px, 2.8cqi, 14px);
        background: color-mix(in srgb, var(--primary-text-color, #fff) 9%, transparent);
        color: var(--primary-text-color, #eef1f5);
        font: inherit; font-size: clamp(14px, 3.8cqi, 18px); font-weight: 700; }
      .response ha-icon { --mdc-icon-size: clamp(18px, 4.6cqi, 22px); }
      .items { margin: 2cqi 0 0 calc(clamp(22px, 6cqi, 32px) + 3cqi);
        display: flex; flex-direction: column; gap: 1.5cqi; }
      .item { display: flex; align-items: center; gap: 2cqi; font-size: clamp(12px, 3.4cqi, 17px); }
      .item ha-icon { --mdc-icon-size: clamp(16px, 4.5cqi, 22px); }
      .iname { flex: 1; min-width: 0; }
      .idetail { font-weight: 600; }
      .idismiss { flex: none; display: grid; place-items: center; cursor: pointer; border: none;
        width: clamp(24px, 6.5cqi, 32px); height: clamp(24px, 6.5cqi, 32px); border-radius: 999px;
        background: transparent; color: var(--secondary-text-color, #8b94a1); }
      .idismiss ha-icon { --mdc-icon-size: clamp(15px, 4cqi, 20px); }
      .idismiss:hover { background: color-mix(in srgb, var(--primary-text-color, #fff) 8%, transparent); }
      /* snooze overlay (scoped to the card so it works embedded) */
      .overlay { position: absolute; inset: 0; z-index: 5; background: rgba(0,0,0,.55);
        display: flex; align-items: flex-end; }
      .sheet { width: 100%; box-sizing: border-box;
        background: var(--ha-card-background, var(--card-background-color, #20242b));
        border-radius: 24px 24px 0 0; padding: clamp(14px, 4cqi, 26px); }
      .shead { font-size: clamp(15px, 4.2cqi, 22px); font-weight: 700; margin-bottom: 1.5cqi; }
      .snote { color: var(--secondary-text-color, #9aa2ad); font-size: clamp(12px, 3.2cqi, 16px); margin-bottom: 3cqi; }
      .sgrid { display: grid; grid-template-columns: 1fr 1fr; gap: 2.5cqi; }
      .sopt { display: flex; flex-direction: column; gap: .5cqi; align-items: flex-start;
        padding: clamp(14px, 4cqi, 22px); border-radius: clamp(12px, 3.5cqi, 18px);
        background: color-mix(in srgb, var(--primary-text-color, #fff) 7%, transparent);
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
    "The notification tray: alerts grouped by priority (quiet sections), flat cards with a single dismiss and one response button. Fills its container — use in a pop-up or on a wall panel.",
});
