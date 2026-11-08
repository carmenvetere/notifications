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
 *   surface: wall | mobile          # which tap target a row opens (#45)
 *   style: auto | default | panel   # "panel" = the Mudroom wall-panel look
 *                                   # (warm taupe palette, Red Hat Display +
 *                                   # Barlow); "auto" picks it for surface: wall
 */

const PRIORITY_META = {
  critical: { label: "Critical" },
  warning: { label: "Warning" },
  info: { label: "Info" },
};
const PRIORITY_ORDER = ["critical", "warning", "info"];
// Muted, low-contrast section-label tints (priority lives here, not on cards).
const LABEL_COLOR = { critical: "#cf7b73", warning: "#b89360", info: "#79828f" };

// "panel" style: the Mudroom LVGL wall panel's level colours (palette v4) —
// red for critical, amber for warning, secondary text for info.
const PANEL_LEVEL_COLOR = { critical: "#F08A70", warning: "#EDB160", info: "#DED7CB" };

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

// Long-form age for the panel style ("18 minutes ago"), like the wall panel.
function ageLong(min) {
  const m = Number(min) || 0;
  if (m < 1) return "just now";
  if (m < 60) return `${m} minute${m === 1 ? "" : "s"} ago`;
  if (m < 1440) {
    const h = Math.floor(m / 60);
    return `${h} hour${h === 1 ? "" : "s"} ago`;
  }
  const d = Math.floor(m / 1440);
  return `${d} day${d === 1 ? "" : "s"} ago`;
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
    return {
      entity: "sensor.notification_center",
      priority_entity: "sensor.notification_center_priority",
      title: "Notifications",
      show_header: true,
      surface: "mobile",
    };
  }

  // Visual config editor (Lovelace "Edit card" UI), so the card is
  // configurable without hand-writing YAML.
  static getConfigElement() {
    return document.createElement("notification-center-card-editor");
  }

  setConfig(config) {
    // Bulletproof by contract: setConfig must ONLY store config — never throw
    // and never touch the DOM or `hass`. A thrown setConfig paints a *sticky*
    // "Configuration error" that survives until a manual resource reload (the
    // exact restart symptom in #30); an undefined element, by contrast,
    // auto-recovers once the module loads. So we normalize bad input instead of
    // throwing, and defer all rendering to connectedCallback / the hass setter.
    const c = config && typeof config === "object" ? config : {};
    this._config = c;
    this._entity = c.entity || "sensor.notification_center";
    this._priorityEntity =
      c.priority_entity || "sensor.notification_center_priority";
    this._title = c.title || "Notifications";
    this._showHeader = c.show_header !== false;
    // Which surface this card represents, for surface-aware tap targets (#45).
    this._surface = c.surface === "wall" ? "wall" : "mobile";
    // Visual style: "panel" mirrors the Mudroom wall panel; "auto" (default)
    // uses it for wall surfaces and the theme-following default elsewhere.
    this._style =
      c.style === "panel" || (c.style !== "default" && this._surface === "wall")
        ? "panel"
        : "default";
    // Re-render only if we're already connected; otherwise connectedCallback
    // will do it. Keeps setConfig free of first-paint DOM work.
    if (this.isConnected) this._render();
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
    // Never let a transient render error surface as a sticky "configuration
    // error" card — log it and try again on the next hass update.
    try {
      const count = this._alerts().length;
      const panel = this._style === "panel";
      // Panel style: like the wall panel's status bar, a red takeover pill
      // for the top critical alert replaces the bell count.
      const crit = panel ? this._alerts().find((a) => a.priority === "critical") : null;
      const status = crit
        ? `<button type="button" class="pill" data-pill-nav="${esc(this._navFor(crit) || "")}"
             aria-label="${esc(crit.title || crit.name)}"><ha-icon icon="${esc(
             crit.icon || "mdi:alarm-light"
           )}"></ha-icon><span>${esc(crit.title || crit.name)}</span></button>`
        : `<span class="count">${panel ? `<ha-icon icon="mdi:bell-outline"></ha-icon>` : ""}${count}</span>`;
      const header = this._showHeader
        ? `<div class="head">
             <span class="title">${esc(this._title)}</span>
             ${status}
           </div>`
        : "";

      this.shadowRoot.innerHTML = `${this._styles()}
        <div class="card${panel ? " panel" : ""}">
          ${header}
          <div class="body" role="list" aria-label="${esc(this._title)}">${this._renderGroups()}</div>
          ${this._snoozeFor ? this._renderSnooze() : ""}
        </div>`;
      this._wire();
    } catch (e) {
      console.error("notification-center-card: render failed", e);
    }
  }

  // Surface-aware tap target (#45): a card placed on a wall panel opens the
  // wall path; one on a mobile dashboard opens the mobile path. Each falls
  // back to the other so a single URL still works everywhere.
  _navFor(a) {
    return this._surface === "wall"
      ? a.navigation_target || a.mobile_navigation_target
      : a.mobile_navigation_target || a.navigation_target;
  }

  _renderGroups() {
    const groups = this._grouped();
    const sections = PRIORITY_ORDER.filter((p) => groups[p].length);
    const panel = this._style === "panel";
    if (!sections.length) {
      return panel
        ? `<div class="empty">
            <ha-icon icon="mdi:bell-outline"></ha-icon>
            <span>All caught up</span></div>`
        : `<div class="empty">
            <ha-icon icon="mdi:check-circle-outline"></ha-icon>
            <span>You're all caught up.</span></div>`;
    }
    if (panel) {
      // The wall panel has no section headers: one list, critical first,
      // priority carried by the icon colour.
      const rows = sections
        .flatMap((p) => groups[p])
        .map((a) => this._renderAlert(a))
        .join("");
      return `<div class="group">${rows}</div>`;
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
    const expanded = !!this._expanded[a.tag];
    const digestTag = a.digest
      ? `<button type="button" class="tag" data-toggle="${esc(a.tag)}" aria-expanded="${expanded}" aria-label="Toggle digest items">Digest${
          (a.items || []).length ? ` · ${a.items.length}` : ""
        } <ha-icon icon="mdi:chevron-${expanded ? "up" : "down"}"></ha-icon></button>`
      : "";
    const dismissBtn = actions.includes("dismiss")
      ? `<button type="button" class="dismiss" data-tag="${esc(a.tag)}" title="Dismiss" aria-label="Dismiss ${esc(a.title || a.name)}"><ha-icon icon="mdi:close"></ha-icon></button>`
      : "";
    // Each custom action becomes a full-width response button.
    const response = (a.buttons || [])
      .map(
        (b) => `<button type="button" class="response" data-run="${esc(a.tag)}" data-action="${esc(b.id)}"${
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
                  <button type="button" class="idismiss" data-item-tag="${esc(a.tag)}" data-item-key="${esc(
                it.key || it.name
              )}" title="Dismiss" aria-label="Dismiss ${esc(it.name)}"><ha-icon icon="mdi:close"></ha-icon></button>
                </div>`
            )
            .join("")}</div>`
        : "";
    const snoozeAttr = actions.includes("snooze") ? ` data-snooze-tag="${esc(a.tag)}"` : "";
    const nav = this._navFor(a);
    const navAttr = nav ? ` data-nav="${esc(nav)}"` : "";
    // Panel style: icon in a round well, coloured by level; long-form time
    // under the message (mirrors the wall panel's notification rows).
    const panel = this._style === "panel";
    const level = PRIORITY_ORDER.includes(a.priority) ? a.priority : "info";
    const iconEl = panel
      ? `<span class="awell"><ha-icon class="aicon" icon="${esc(a.icon || "mdi:bell")}"
           style="color:${PANEL_LEVEL_COLOR[level]}"></ha-icon></span>`
      : `<ha-icon class="aicon" icon="${esc(a.icon || "mdi:bell")}"></ha-icon>`;
    const ageEl = panel ? "" : `<span class="aage">${ageLabel(a.age_min)}</span>`;
    const timeEl = panel ? `<div class="atime">${ageLong(a.age_min)}</div>` : "";
    const navA11y = nav
      ? ` role="button" tabindex="0" aria-label="${esc(a.title || a.name)} — open ${esc(nav)}"`
      : ` role="listitem"`;
    // Progress bar for activity-style alerts (Live Activity mirror, #25).
    const hasProgress = a.progress != null && a.progress !== "";
    const pct = hasProgress
      ? Math.max(0, Math.min(100, (Number(a.progress) / (Number(a.progress_max) || 100)) * 100))
      : 0;
    const progress = hasProgress
      ? `<div class="aprog"><div class="aprog-track"><span style="width:${pct}%;background:${color}"></span></div>${
          a.critical_text ? `<span class="aprog-txt">${esc(a.critical_text)}</span>` : ""
        }</div>`
      : "";
    return `<div class="alert${nav ? " tappable" : ""}"${snoozeAttr}${navAttr}${navA11y}>
        <div class="amain">
          ${iconEl}
          <div class="atext">
            <div class="atitle">
              <span class="aname">${esc(a.title || a.name)}</span>
              ${a.test ? `<span class="testchip" title="Test mode — fired on demand, ends automatically">TEST</span>` : ""}
              ${ageEl}
            </div>
            ${a.message ? `<div class="asub">${esc(a.message)}</div>` : ""}
            ${timeEl}
            ${digestTag ? `<div class="ameta">${digestTag}</div>` : ""}
          </div>
          ${dismissBtn}
        </div>
        ${progress}
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
          // Stable string id (G21); must NOT be coerced to a Number, or ids
          // like "a3k9x2" become NaN and the action can't be resolved.
          action: el.getAttribute("data-action"),
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
    // Panel style: the critical takeover pill opens that alert's target.
    const pill = r.querySelector(".pill[data-pill-nav]");
    if (pill) pill.onclick = () => this._navigate(pill.getAttribute("data-pill-nav"));
    // Tap (or keyboard-activate) a row with a navigation target.
    r.querySelectorAll(".alert[data-nav]").forEach((el) => {
      const go = () => this._navigate(el.getAttribute("data-nav"));
      el.addEventListener("click", go);
      el.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          go();
        }
      });
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
    // The panel style uses the wall panel's typefaces (Google Fonts, OFL);
    // it falls back to the system font when offline. @import must come first.
    const fonts =
      this._style === "panel"
        ? `@import url('https://fonts.googleapis.com/css2?family=Barlow:wght@400;500;600&family=Red+Hat+Display:wght@400;600&display=swap');`
        : "";
    return `<style>${fonts}
      :host { display: block; height: 100%; }
      /* a11y: a clear keyboard-focus ring on every interactive element. */
      button:focus-visible, .alert[tabindex]:focus-visible {
        outline: 2px solid var(--primary-color, #4ebcff);
        outline-offset: 2px;
        border-radius: 8px;
      }
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
      .testchip { flex: none; border-radius: 999px; padding: 1px 8px; font-size: clamp(10px, 2.6cqi, 12px);
        font-weight: 800; letter-spacing: .08em; background: #EDB16033; color: #EDB160; }
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
      /* activity progress bar (#25) */
      .aprog { display: flex; align-items: center; gap: 2.5cqi; margin-top: 2.5cqi; }
      .aprog-track { flex: 1; height: clamp(6px, 1.6cqi, 9px); border-radius: 999px; overflow: hidden;
        background: color-mix(in srgb, var(--primary-text-color, #fff) 12%, transparent); }
      .aprog-track span { display: block; height: 100%; border-radius: 999px; transition: width .3s ease; }
      .aprog-txt { flex: none; font-size: clamp(12px, 3.2cqi, 15px); font-weight: 700;
        color: var(--secondary-text-color, #9aa2ad); font-variant-numeric: tabular-nums; }
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

      /* ---- "panel" style: the Mudroom wall panel (ESPHome/LVGL, palette v4) ----
         Flat colour steps for depth, no shadows; Red Hat Display titles, Barlow
         body; 18px surface cards with a round 48px icon well coloured by level,
         a round 52px dismiss button, and a red takeover pill for critical. */
      .card.panel {
        --p-bg: #3A3732; --p-surface: #615C55; --p-surface2: #756F67; --p-divider: #76716A;
        --p-dot: #6F6A62; --p-text: #F5F1E8; --p-text2: #DED7CB; --p-text3: #BBB4A8;
        --p-sub: #D6D0C5; --p-dim: #A39D91; --p-chevron: #A7A095; --p-sage: #A9B4A3;
        --p-amber: #EDB160; --p-red: #F08A70; --p-red-fill: #CC624E; --p-on-red: #FBF6EE;
        --p-ink: #34312C; --p-blue: #A9B2B8;
        background: var(--p-bg); color: var(--p-text); border-radius: 22px;
        font-family: "Barlow", var(--paper-font-body1_-_font-family, Roboto, sans-serif);
      }
      .panel button:focus-visible, .panel .alert[tabindex]:focus-visible { outline-color: var(--p-sage); }
      .panel .head { border-bottom: none; gap: 12px;
        padding: clamp(18px, 3.6cqi, 26px) clamp(16px, 4.4cqi, 32px) 10px; }
      .panel .title { font-family: "Red Hat Display", "Barlow", sans-serif; font-weight: 400;
        font-size: clamp(24px, 4.4cqi, 32px); letter-spacing: 0; color: var(--p-text); }
      .panel .count { display: inline-flex; align-items: center; gap: 6px; height: 48px; line-height: 48px;
        padding: 0 16px; border-radius: 24px; background: var(--p-surface); color: var(--p-text2);
        font-size: 19px; font-weight: 500; min-width: 0; }
      .panel .count ha-icon { --mdc-icon-size: 24px; color: var(--p-dim); }
      .pill { margin-left: auto; display: inline-flex; align-items: center; gap: 10px; height: 52px;
        padding: 0 22px 0 18px; border-radius: 26px; border: none; cursor: pointer;
        background: var(--p-red-fill); color: var(--p-on-red);
        font-family: "Red Hat Display", "Barlow", sans-serif; font-weight: 600; font-size: 19px;
        max-width: 70%; }
      .pill span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .pill ha-icon { --mdc-icon-size: 24px; flex: none; }
      .panel .body { padding: 4px clamp(16px, 4.4cqi, 32px) 28px; }
      .panel .empty { color: var(--p-chevron); gap: 12px; }
      .panel .empty ha-icon { --mdc-icon-size: 72px; opacity: 1; }
      .panel .empty span { font-size: 20px; font-weight: 500; }
      .panel .group { margin: 0; display: flex; flex-direction: column; gap: 10px; }
      .panel .alert { background: var(--p-surface); border-radius: 18px; margin: 0;
        padding: 14px 14px 14px 16px; min-height: 92px; box-sizing: border-box;
        display: flex; flex-direction: column; justify-content: center; }
      .panel .amain { gap: 14px; }
      .awell { flex: none; width: 48px; height: 48px; border-radius: 50%; background: var(--p-surface2);
        display: grid; place-items: center; }
      .awell ha-icon { --mdc-icon-size: 26px; }
      .panel .aname { font-family: "Red Hat Display", "Barlow", sans-serif; font-weight: 600;
        font-size: 19px; color: var(--p-text); }
      .panel .asub { font-size: 16px; color: var(--p-sub); margin-top: 2px; }
      .atime { font-size: 14px; font-weight: 500; color: var(--p-text3); margin-top: 2px; }
      .panel .tag { background: var(--p-surface2); color: var(--p-text2); font-size: 14px; }
      .panel .dismiss { width: 52px; height: 52px; border-radius: 26px;
        background: var(--p-surface2); color: var(--p-text2); }
      .panel .dismiss ha-icon { --mdc-icon-size: 24px; }
      .panel .response { border-radius: 26px; padding: 14px 22px; margin-top: 12px;
        background: var(--p-surface2); color: var(--p-text); font-weight: 600; font-size: 16px; }
      .panel .aprog { margin-top: 12px; }
      .panel .aprog-track { background: var(--p-dot); height: 8px; }
      .panel .aprog-txt { color: var(--p-text2); font-size: 14px; }
      .panel .items { margin: 10px 0 0 62px; gap: 8px; }
      .panel .item { font-size: 15px; color: var(--p-sub); }
      .panel .idismiss { color: var(--p-text3); }
      .panel .sheet { background: var(--p-bg); border-radius: 30px 30px 0 0; }
      .panel .shead { font-family: "Red Hat Display", "Barlow", sans-serif; font-weight: 400; font-size: 24px; }
      .panel .snote { color: var(--p-text3); }
      .panel .sopt { background: var(--p-surface); border-color: transparent; color: var(--p-text); border-radius: 18px; }
      .panel .sopt span { color: var(--p-text3); }
      .panel .scancel { border-color: var(--p-divider); color: var(--p-text2); border-radius: 26px; }
    </style>`;
  }
}

customElements.define("notification-center-card", NotificationCenterCard);

// --- Visual config editor ---------------------------------------------------
class NotificationCenterCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
  }

  set hass(hass) {
    this._hass = hass;
  }

  setConfig(config) {
    this._config = { ...config };
    this._render();
  }

  _emit(patch) {
    this._config = { ...this._config, ...patch };
    this.dispatchEvent(
      new CustomEvent("config-changed", {
        detail: { config: this._config },
        bubbles: true,
        composed: true,
      })
    );
  }

  _render() {
    if (!this.shadowRoot) return;
    const c = this._config || {};
    const showHeader = c.show_header !== false;
    this.shadowRoot.innerHTML = `
      <style>
        .form { display: flex; flex-direction: column; gap: 12px; padding: 4px 2px; }
        label { display: flex; flex-direction: column; gap: 4px;
          font-size: 13px; color: var(--secondary-text-color, #8a8a8a); }
        input[type=text] { padding: 8px 10px; font-size: 14px;
          border: 1px solid var(--divider-color, #ccc); border-radius: 8px;
          background: var(--card-background-color, #fff);
          color: var(--primary-text-color, #111); }
        .row { display: flex; align-items: center; gap: 8px; }
        .row label { flex-direction: row; align-items: center;
          color: var(--primary-text-color, #111); font-size: 14px; }
      </style>
      <div class="form">
        <label>Title
          <input type="text" data-k="title" value="${esc(c.title || "Notifications")}">
        </label>
        <label>Sensor entity
          <input type="text" data-k="entity" value="${esc(c.entity || "sensor.notification_center")}">
        </label>
        <label>Priority entity
          <input type="text" data-k="priority_entity" value="${esc(
            c.priority_entity || "sensor.notification_center_priority"
          )}">
        </label>
        <label>Surface (tap target)
          <select data-k="surface">
            <option value="mobile"${c.surface !== "wall" ? " selected" : ""}>Mobile (opens the rule's mobile path)</option>
            <option value="wall"${c.surface === "wall" ? " selected" : ""}>Wall panel (opens the rule's wall path)</option>
          </select>
        </label>
        <label>Style
          <select data-k="style">
            <option value="auto"${!c.style || c.style === "auto" ? " selected" : ""}>Auto (wall panel look on the wall surface)</option>
            <option value="default"${c.style === "default" ? " selected" : ""}>Default (follows the Home Assistant theme)</option>
            <option value="panel"${c.style === "panel" ? " selected" : ""}>Wall panel (warm taupe, matches the Mudroom panel)</option>
          </select>
        </label>
        <div class="row">
          <input type="checkbox" id="nc-show-header" data-k="show_header" ${showHeader ? "checked" : ""}>
          <label for="nc-show-header">Show header</label>
        </div>
      </div>`;
    this.shadowRoot.querySelectorAll("input[type=text]").forEach((el) => {
      el.addEventListener("input", () =>
        this._emit({ [el.getAttribute("data-k")]: el.value })
      );
    });
    this.shadowRoot.querySelectorAll("select[data-k]").forEach((sel) => {
      sel.addEventListener("change", () =>
        this._emit({ [sel.getAttribute("data-k")]: sel.value })
      );
    });
    const cb = this.shadowRoot.querySelector("input[type=checkbox]");
    if (cb)
      cb.addEventListener("change", () => this._emit({ show_header: cb.checked }));
  }
}

customElements.define(
  "notification-center-card-editor",
  NotificationCenterCardEditor
);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "notification-center-card",
  name: "Notification Center",
  description:
    "The notification tray: alerts grouped by priority (quiet sections), flat cards with dismiss and per-action response buttons. Fills its container — use in a pop-up or on a wall panel.",
  preview: true,
  documentationURL:
    "https://github.com/carmenvetere/notifications/blob/main/README.md",
});
