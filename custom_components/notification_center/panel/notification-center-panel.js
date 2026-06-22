/*
 * Notification Center — custom setup panel (Deliverable 1).
 *
 * Registered by the integration via panel_custom; served from /panel/. Manages
 * rule subentries through the integration's WebSocket API
 * (notification_center/rules/*), so it can render the designed editor that the
 * stock ha-form config flow can't: trigger/priority/channel cards, conditional
 * reveals, and a live preview. Self-contained (no build step).
 */

const OP_LABEL = {
  "==": "is",
  "!=": "is not",
  ">": "> greater than",
  "<": "< less than",
  ">=": "≥ at or above",
  "<=": "≤ at or below",
  "=": "= equals",
};
const SRC = {
  state: { label: "State", hint: "Matches a value", icon: "mdi:toggle-switch-outline" },
  numeric: { label: "Numeric", hint: "Crosses a threshold", icon: "mdi:numeric" },
  template: { label: "Template", hint: "Custom Jinja", icon: "mdi:code-braces" },
};
const CH = {
  mobile: { label: "Mobile push", hint: "Phones via the HA app", icon: "mdi:cellphone" },
  bell: { label: "Bell / center", hint: "Persistent in-app list", icon: "mdi:bell" },
  wall: { label: "Wall panel", hint: "Dashboard banner", icon: "mdi:monitor-dashboard" },
  tts: { label: "Announce (TTS)", hint: "Spoken on speakers", icon: "mdi:bullhorn" },
  navigate: { label: "Navigate dash", hint: "Force-open a view", icon: "mdi:navigation-variant" },
};
const PRI_DESC = {
  critical: "Breaks through silent mode & Do Not Disturb. Stays in the tray until resolved.",
  warning: "Surfaces above other notifications. Stays in the tray until resolved.",
  info: "Delivered quietly. Can be dismissed or rolled into a digest.",
};
const STEPS = ["Trigger", "Priority", "Channels", "Message", "Advanced"];

function blankRule() {
  return {
    name: "",
    enabled: true,
    source_type: "state",
    entity_id: "",
    operator: "==",
    value: "",
    condition_template: "",
    priority: "info",
    channels: ["bell"],
    icon: "",
    color: "",
    title_template: "",
    message_template: "",
    navigation_target: "",
    tts_message: "",
    tts_targets: "",
    actions_follow_priority: true,
    clear_mode: "dismiss",
    snooze: false,
    deliver_as_digest: false,
    digest_group: "",
    items_template: "",
    auto_clear: true,
    quiet_hours_behavior: "downgrade",
    presence_routing: "all",
    cooldown: "",
    escalation_after: "",
    dedup_tag: "",
  };
}

function esc(s) {
  return String(s == null ? "" : s).replace(
    /[&<>"]/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])
  );
}

class NotificationCenterPanel extends HTMLElement {
  constructor() {
    super();
    this._view = "list";
    this._rules = [];
    this._meta = null;
    this._editing = null;
    this._editingId = null;
    this._step = 0;
    this._loaded = false;
    this.attachShadow({ mode: "open" });
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._loaded) {
      this._loaded = true;
      this._load();
    }
  }

  async _ws(type, extra) {
    return this._hass.connection.sendMessagePromise({ type, ...(extra || {}) });
  }

  async _load() {
    try {
      this._meta = await this._ws("notification_center/meta");
      await this._reloadRules();
    } catch (e) {
      this._error = (e && e.message) || "Failed to load";
      this._render();
    }
  }

  async _reloadRules() {
    const res = await this._ws("notification_center/rules/list");
    this._rules = res.rules || [];
    this._render();
  }

  // --- effective (mirror Rule properties) --------------------------------
  _eff(r) {
    const d = this._meta.priority_defaults[r.priority] || {};
    const clear = r.actions_follow_priority ? d.clear_mode : r.clear_mode;
    const snooze = r.actions_follow_priority ? d.snooze : !!r.snooze;
    const actions = [];
    if (clear === "dismiss") actions.push("dismiss");
    if (snooze) actions.push("snooze");
    return {
      clear,
      snooze,
      actions,
      color: r.color || d.color,
      icon: r.icon || d.icon,
      cooldown: r.cooldown !== "" && r.cooldown != null ? r.cooldown : d.cooldown,
    };
  }

  // --- navigation ---------------------------------------------------------
  _new() {
    this._editing = blankRule();
    this._editingId = null;
    this._step = 0;
    this._view = "edit";
    this._render();
  }

  _edit(rule) {
    this._editing = { ...blankRule(), ...rule.data };
    this._editingId = rule.subentry_id;
    this._step = 0;
    this._view = "edit";
    this._render();
  }

  async _delete(rule) {
    if (!confirm(`Delete "${rule.data.name || rule.subentry_id}"?`)) return;
    await this._ws("notification_center/rules/delete", { subentry_id: rule.subentry_id });
    await this._reloadRules();
  }

  async _save() {
    const rule = { ...this._editing };
    // Don't persist info-only fields on non-info rules.
    if (rule.priority !== "info") {
      rule.deliver_as_digest = false;
    }
    try {
      if (this._editingId) {
        await this._ws("notification_center/rules/update", {
          subentry_id: this._editingId,
          rule,
        });
      } else {
        await this._ws("notification_center/rules/create", { rule });
      }
      this._view = "list";
      this._editing = null;
      await this._reloadRules();
    } catch (e) {
      alert((e && e.message) || "Save failed");
    }
  }

  _set(key, val) {
    this._editing[key] = val;
  }

  _toggleChannel(id) {
    const ch = this._editing.channels || [];
    this._editing.channels = ch.includes(id)
      ? ch.filter((c) => c !== id)
      : [...ch, id];
    this._render();
  }

  // --- render -------------------------------------------------------------
  _render() {
    if (!this.shadowRoot) return;
    if (!this._meta) {
      this.shadowRoot.innerHTML = `${this._styles()}<div class="loading">Loading…${
        this._error ? ` — ${esc(this._error)}` : ""
      }</div>`;
      return;
    }
    this.shadowRoot.innerHTML =
      this._styles() +
      (this._view === "list" ? this._renderList() : this._renderEdit());
    this._wire();
  }

  _renderList() {
    const rows = this._rules
      .map((r) => {
        const d = r.data;
        const color = r.effective.color;
        const trig =
          d.source_type === "template"
            ? "template"
            : `${esc(d.entity_id || "?")} ${esc(OP_LABEL[d.operator] || d.operator || "")} ${esc(
                d.value || ""
              )}`;
        return `<div class="rule-card">
          <span class="dot" style="background:${d.enabled === false ? "#c4ccd6" : "#2ecc71"}"></span>
          <ha-icon icon="${esc(r.effective.icon)}" style="color:${color}"></ha-icon>
          <div class="rule-text">
            <div class="rule-name">${esc(d.name || r.subentry_id)}</div>
            <div class="rule-sub">${trig}</div>
          </div>
          <span class="pri-pill" style="background:${color}1f;color:${color}">${esc(d.priority)}</span>
          ${d.deliver_as_digest ? `<span class="pri-pill digest">digest</span>` : ""}
          <button class="link" data-edit="${esc(r.subentry_id)}">Edit</button>
          <button class="link danger" data-del="${esc(r.subentry_id)}">Delete</button>
        </div>`;
      })
      .join("");
    return `<div class="page">
      <div class="topbar">
        <h1>Notifications</h1>
        <button class="primary" id="add">+ Add notification rule</button>
      </div>
      ${
        this._rules.length
          ? `<div class="list">${rows}</div>`
          : `<div class="empty">No rules yet. Add your first notification rule.</div>`
      }
    </div>`;
  }

  _renderEdit() {
    const r = this._editing;
    const rail = STEPS.map(
      (s, i) =>
        `<button class="rail-step ${i === this._step ? "on" : ""}" data-step="${i}">
           <span class="rail-num">${i + 1}</span>${s}
         </button>`
    ).join("");
    const last = this._step === STEPS.length - 1;
    return `<div class="page edit">
      <div class="topbar">
        <button class="link" id="back-list">← All rules</button>
        <h1>${this._editingId ? "Edit rule" : "New rule"}</h1>
      </div>
      <div class="edit-grid">
        <div class="rail">${rail}</div>
        <div class="form">${this._renderStep()}</div>
        <div class="preview" id="preview">${this._renderPreview()}</div>
      </div>
      <div class="footer">
        <button class="link" id="prev" ${this._step === 0 ? "disabled" : ""}>Back</button>
        <button class="primary" id="next">${last ? "Save rule" : "Continue"}</button>
      </div>
    </div>`;
  }

  _renderStep() {
    const r = this._editing;
    switch (this._step) {
      case 0:
        return this._stepTrigger(r);
      case 1:
        return this._stepPriority(r);
      case 2:
        return this._stepChannels(r);
      case 3:
        return this._stepMessage(r);
      default:
        return this._stepAdvanced(r);
    }
  }

  _field(label, inner, hint) {
    return `<label class="field"><span class="flabel">${label}</span>${inner}${
      hint ? `<span class="fhint">${hint}</span>` : ""
    }</label>`;
  }

  _text(key, opts = {}) {
    const v = this._editing[key] == null ? "" : this._editing[key];
    const mono = opts.mono ? "mono" : "";
    if (opts.area)
      return `<textarea class="inp ${mono}" data-k="${key}" rows="${opts.rows || 3}">${esc(v)}</textarea>`;
    return `<input class="inp ${mono}" data-k="${key}" type="${opts.type || "text"}" value="${esc(v)}" placeholder="${esc(opts.ph || "")}">`;
  }

  _select(key, options) {
    const cur = this._editing[key];
    const opts = options
      .map(
        (o) =>
          `<option value="${esc(o.v)}" ${o.v === cur ? "selected" : ""}>${esc(o.l)}</option>`
      )
      .join("");
    return `<select class="inp" data-k="${key}">${opts}</select>`;
  }

  _toggle(key, label) {
    const on = !!this._editing[key];
    return `<label class="toggle-row"><span>${label}</span>
      <button class="toggle ${on ? "on" : ""}" data-toggle="${key}"><span class="knob"></span></button></label>`;
  }

  _stepTrigger(r) {
    const cards = Object.keys(SRC)
      .map((id) => {
        const m = SRC[id];
        const on = r.source_type === id;
        return `<button class="pick ${on ? "on" : ""}" data-src="${id}">
          <ha-icon icon="${m.icon}"></ha-icon><b>${m.label}</b><span>${m.hint}</span></button>`;
      })
      .join("");
    let reveal = "";
    if (r.source_type === "template") {
      reveal = this._field(
        "Condition template",
        this._text("condition_template", { area: true, mono: true, rows: 4 }),
        "Fires whenever the template renders truthy."
      );
    } else {
      const ops = (this._meta.operators[r.source_type] || []).map((v) => ({
        v,
        l: OP_LABEL[v] || v,
      }));
      reveal =
        this._field("Entity", this._text("entity_id", { mono: true, ph: "binary_sensor.front_door" })) +
        this._field("Operator", this._select("operator", ops)) +
        this._field("Value / threshold", this._text("value"));
    }
    return `<h2>When should this fire?</h2>
      ${this._field("Rule name", this._text("name", { ph: "Front door left open" }))}
      ${this._toggle("enabled", "Enabled")}
      <div class="flabel">Trigger type</div>
      <div class="picks three">${cards}</div>
      ${reveal}`;
  }

  _stepPriority(r) {
    const cards = this._meta.priorities
      .map((id) => {
        const d = this._meta.priority_defaults[id];
        const on = r.priority === id;
        return `<button class="pri-card ${on ? "on" : ""}" data-pri="${id}" style="--c:${d.color}">
          <div class="pri-ic" style="background:${d.color}"><ha-icon icon="${d.icon}"></ha-icon></div>
          <b style="text-transform:capitalize">${id}</b>
          <span>${PRI_DESC[id] || ""}</span>
          <div class="pri-pills"><span>${d.push}</span><span>${
            d.cooldown ? `Every ${d.cooldown} min` : "No cooldown"
          }</span></div>
        </button>`;
      })
      .join("");
    return `<h2>How important is it?</h2>
      <p class="muted">Priority sets the push level, icon, color, cooldown and clearing behavior — all overridable later.</p>
      <div class="pri-grid">${cards}</div>`;
  }

  _stepChannels(r) {
    const rows = this._meta.channels
      .map((id) => {
        const m = CH[id];
        const on = (r.channels || []).includes(id);
        return `<button class="ch-row ${on ? "on" : ""}" data-ch="${id}">
          <ha-icon icon="${m.icon}"></ha-icon>
          <div class="ch-text"><b>${m.label}</b><span>${m.hint}</span></div>
          <span class="toggle ${on ? "on" : ""}"><span class="knob"></span></span>
        </button>`;
      })
      .join("");
    let reveal = "";
    if ((r.channels || []).includes("tts")) {
      reveal +=
        this._field(
          "Spoken announcement",
          this._text("tts_message", { area: true, rows: 2 }),
          "Leave blank to speak the message. Write a full sentence."
        ) + this._field("Announce on", this._text("tts_targets", { mono: true, ph: "media_player.kitchen, media_player.office" }));
    }
    if ((r.channels || []).includes("navigate")) {
      reveal += this._field("Navigate dashboards to", this._text("navigation_target", { mono: true, ph: "/lovelace/security" }));
    }
    const note =
      (r.channels || []).includes("wall") || (r.channels || []).includes("navigate")
        ? `<div class="note">⚠️ Wall banner & navigation drive Lovelace surfaces only (Fully Kiosk / browser_mod). A native LVGL / NSPanel needs an ESPHome or MQTT action instead.</div>`
        : "";
    return `<h2>Where should it go?</h2>
      <div class="ch-list">${rows}</div>${note}${reveal}`;
  }

  _stepMessage(r) {
    return `<h2>What does it say?</h2>
      <p class="muted">Title and message accept <b>Jinja templates</b>, so you can pull in
        live details. e.g. <code>{{ state_attr('sensor.nws_alerts_alerts','event') }}</code> or
        <code>{{ states('sensor.bayberry_charge') }}%</code>. Rendered when the alert fires.</p>
      ${this._field("Title", this._text("title_template"))}
      ${this._field(
        "Message",
        this._text("message_template", { area: true }),
        "Plain text or a template — include any entity state/attribute here."
      )}
      <div class="two">
        ${this._field("Icon", this._text("icon", { mono: true, ph: "mdi:alert" }))}
        ${this._field("Color", this._text("color", { mono: true, ph: "#EF8C00" }))}
      </div>`;
  }

  _renderCustomActions(r) {
    const list = r.custom_actions || [];
    const rows = list
      .map(
        (a, i) => `<div class="ca-row">
          <div class="two">
            <input class="inp" data-ca="${i}" data-caf="label" placeholder="Button label" value="${esc(a.label || "")}">
            <input class="inp mono" data-ca="${i}" data-caf="service" placeholder="script.reset_filter" value="${esc(a.service || "")}">
          </div>
          <input class="inp" data-ca="${i}" data-caf="confirm" placeholder="Confirmation text (optional)" value="${esc(a.confirm || "")}">
          <div class="ca-foot">
            <input class="inp mono" data-ca="${i}" data-caf="icon" placeholder="mdi:check (optional)" value="${esc(a.icon || "")}">
            <button class="link danger" data-ca-del="${i}">Remove</button>
          </div>
        </div>`
      )
      .join("");
    return `<div class="flabel">Custom actions — run a service from the notification</div>
      <p class="muted">e.g. "Mark replaced" → <code>script.reset_upper_floors_filter_runtime</code>.
        Runs the service (after the optional confirmation) and clears the alert.</p>
      ${rows}
      <button class="link" data-ca-add="1">+ Add action</button>`;
  }

  _stepAdvanced(r) {
    let clearing = "";
    if (!r.actions_follow_priority) {
      const cards = this._meta.clear_modes
        .map((m) => {
          const on = r.clear_mode === m;
          const label = m === "locked" ? "Stays in tray" : "Dismiss";
          const desc = m === "locked" ? "No manual clearing" : "User can clear it";
          return `<button class="pick ${on ? "on" : ""}" data-clear="${m}">
            <b>${label}</b><span>${desc}</span></button>`;
        })
        .join("");
      clearing = `<div class="flabel">When it can be cleared</div>
        <div class="picks two">${cards}</div>${this._toggle("snooze", "Allow snooze")}`;
    } else {
      const eff = this._eff(r);
      clearing = `<div class="chips">${
        eff.actions.length
          ? eff.actions.map((a) => `<span class="chip">${a}</span>`).join("")
          : `<span class="chip muted">Stays in tray (no manual clearing)</span>`
      }</div>`;
    }
    let digest = "";
    if (r.priority === "info") {
      digest =
        this._toggle("deliver_as_digest", "Deliver as a digest") +
        (r.deliver_as_digest
          ? this._field("Digest group", this._text("digest_group", { mono: true })) +
            this._field(
              "Digest items template",
              this._text("items_template", { area: true, mono: true, rows: 3 }),
              "Render a list of {name, detail, icon, color} dicts."
            )
          : "");
    }
    return `<h2>Delivery behavior</h2>
      <p class="muted">Sensible defaults are applied from the priority. Tune only what you need.</p>
      ${this._toggle("actions_follow_priority", "Actions follow priority")}
      ${clearing}
      ${digest}
      ${this._toggle("auto_clear", "Auto-clear when resolved")}
      <div class="two">
        ${this._field("Quiet hours", this._select("quiet_hours_behavior", this._meta.quiet_hours_behaviors.map((v) => ({ v, l: v }))))}
        ${this._field("Presence routing", this._select("presence_routing", this._meta.presence_routing.map((v) => ({ v, l: v }))))}
      </div>
      <div class="two">
        ${this._field("Cooldown override (min)", this._text("cooldown", { type: "number" }))}
        ${this._field("Escalate after (min)", this._text("escalation_after", { type: "number" }))}
      </div>
      ${this._field("Dedup tag", this._text("dedup_tag", { mono: true }))}
      ${this._renderCustomActions(r)}`;
  }

  _renderPreview() {
    const r = this._editing;
    const eff = this._eff(r);
    const chans = (r.channels || []).join(", ") || "no channels";
    const trig =
      r.source_type === "template"
        ? "a template matches"
        : `${r.entity_id || "an entity"} ${OP_LABEL[r.operator] || r.operator} ${r.value || "…"}`;
    const clearTxt =
      eff.clear === "locked"
        ? "It stays in the tray until the condition resolves."
        : "It can be dismissed" + (eff.snooze ? " or snoozed." : ".");
    const actionChips = eff.actions.length
      ? eff.actions
          .map(
            (a) =>
              `<span class="mini-act" style="${
                a === "dismiss" ? `color:${eff.color};border-color:${eff.color}55` : ""
              }">${a}</span>`
          )
          .join("")
      : "";
    return `<div class="pv-summary">
        When <b>${esc(trig)}</b>, send a <b style="color:${eff.color}">${esc(r.priority)}</b>
        notification to <b>${esc(chans)}</b>. ${esc(clearTxt)}
      </div>
      <div class="pv-label">Notification tray</div>
      <div class="pv-tray">
        <div class="pv-ic" style="background:${eff.color}28"><ha-icon icon="${esc(eff.icon)}" style="color:${eff.color}"></ha-icon></div>
        <div class="pv-text">
          <div class="pv-title">${esc(r.title_template || r.name || "Notification")}</div>
          <div class="pv-sub">${esc(r.message_template || "")}</div>
          ${r.deliver_as_digest ? `<span class="pv-tag">Digest</span>` : ""}
        </div>
        ${actionChips ? `<div class="pv-actions">${actionChips}</div>` : ""}
      </div>`;
  }

  _updatePreview() {
    const el = this.shadowRoot.getElementById("preview");
    if (el) el.innerHTML = this._renderPreview();
  }

  // --- events -------------------------------------------------------------
  _wire() {
    const root = this.shadowRoot;
    const add = root.getElementById("add");
    if (add) add.onclick = () => this._new();
    root.querySelectorAll("[data-edit]").forEach((b) => {
      b.onclick = () =>
        this._edit(this._rules.find((x) => x.subentry_id === b.getAttribute("data-edit")));
    });
    root.querySelectorAll("[data-del]").forEach((b) => {
      b.onclick = () =>
        this._delete(this._rules.find((x) => x.subentry_id === b.getAttribute("data-del")));
    });

    const backList = root.getElementById("back-list");
    if (backList) backList.onclick = () => { this._view = "list"; this._render(); };
    const prev = root.getElementById("prev");
    if (prev) prev.onclick = () => { if (this._step > 0) { this._step--; this._render(); } };
    const next = root.getElementById("next");
    if (next)
      next.onclick = () => {
        if (this._step < STEPS.length - 1) { this._step++; this._render(); }
        else this._save();
      };

    root.querySelectorAll("[data-step]").forEach((b) => {
      b.onclick = () => { this._step = Number(b.getAttribute("data-step")); this._render(); };
    });

    // Text inputs: update state + live preview without a full re-render.
    root.querySelectorAll("[data-k]").forEach((el) => {
      el.oninput = () => { this._set(el.getAttribute("data-k"), el.value); this._updatePreview(); };
    });

    // Custom-action editor (nested list).
    root.querySelectorAll("[data-ca]").forEach((el) => {
      el.oninput = () => {
        const i = Number(el.getAttribute("data-ca"));
        const field = el.getAttribute("data-caf");
        this._editing.custom_actions = this._editing.custom_actions || [];
        (this._editing.custom_actions[i] = this._editing.custom_actions[i] || {})[field] =
          el.value;
      };
    });
    const caAdd = root.querySelector("[data-ca-add]");
    if (caAdd)
      caAdd.onclick = () => {
        this._editing.custom_actions = [...(this._editing.custom_actions || []), {}];
        this._render();
      };
    root.querySelectorAll("[data-ca-del]").forEach((b) => {
      b.onclick = () => {
        const i = Number(b.getAttribute("data-ca-del"));
        this._editing.custom_actions = (this._editing.custom_actions || []).filter(
          (_, idx) => idx !== i
        );
        this._render();
      };
    });

    // Source / priority / channel / clear cards.
    root.querySelectorAll("[data-src]").forEach((b) => {
      b.onclick = () => {
        const id = b.getAttribute("data-src");
        this._editing.source_type = id;
        this._editing.operator = id === "numeric" ? ">" : "==";
        this._render();
      };
    });
    root.querySelectorAll("[data-pri]").forEach((b) => {
      b.onclick = () => { this._editing.priority = b.getAttribute("data-pri"); this._render(); };
    });
    root.querySelectorAll("[data-ch]").forEach((b) => {
      b.onclick = () => this._toggleChannel(b.getAttribute("data-ch"));
    });
    root.querySelectorAll("[data-clear]").forEach((b) => {
      b.onclick = () => { this._editing.clear_mode = b.getAttribute("data-clear"); this._render(); };
    });
    root.querySelectorAll("[data-toggle]").forEach((b) => {
      b.onclick = () => {
        const k = b.getAttribute("data-toggle");
        this._editing[k] = !this._editing[k];
        this._render();
      };
    });
  }

  _styles() {
    return `<style>
      /* Theme-derived tokens (fall back to the original light palette). */
      :host {
        --nc-page: var(--primary-background-color, #eef1f5);
        --nc-surface: var(--card-background-color, #fff);
        --nc-inset: var(--secondary-background-color, #f8fafc);
        --nc-text: var(--primary-text-color, #1f2733);
        --nc-muted: var(--secondary-text-color, #5a6573);
        --nc-border: var(--divider-color, #e6ebf2);
        --nc-accent: var(--primary-color, #1f6fdd);
        --nc-on-accent: var(--text-primary-color, #fff);
        --nc-danger: var(--error-color, #EA4D3D);
        --nc-warning: var(--warning-color, #EF8C00);
        --nc-tint: color-mix(in srgb, var(--nc-accent) 14%, transparent);
        display: block; min-height: 100%; background: var(--nc-page);
        font-family: var(--paper-font-body1_-_font-family, "Figtree", Roboto, sans-serif);
        color: var(--nc-text);
      }
      .loading { padding: 40px; color: var(--nc-muted); }
      .page { max-width: 1120px; margin: 0 auto; padding: 20px; }
      .topbar { display: flex; align-items: center; gap: 14px; margin-bottom: 18px; }
      h1 { font-size: 22px; font-weight: 700; margin: 0; }
      h2 { font-size: 19px; font-weight: 700; margin: 0 0 12px; }
      .muted { color: var(--nc-muted); font-size: 14px; margin: 0 0 14px; }
      .primary { margin-left: auto; background: var(--nc-accent); color: var(--nc-on-accent); border: none;
        border-radius: 10px; padding: 10px 16px; font: inherit; font-weight: 600; cursor: pointer; }
      .link { background: none; border: none; color: var(--nc-accent); font: inherit; font-weight: 600; cursor: pointer; padding: 6px; }
      .link.danger { color: var(--nc-danger); }
      .empty { background: var(--nc-surface); border: 1px solid var(--nc-border); border-radius: 14px;
        padding: 40px; text-align: center; color: var(--nc-muted); }
      .list { display: flex; flex-direction: column; gap: 10px; }
      .rule-card { display: flex; align-items: center; gap: 12px; background: var(--nc-surface);
        border: 1px solid var(--nc-border); border-radius: 14px; padding: 12px 14px; }
      .rule-card ha-icon { --mdc-icon-size: 22px; }
      .dot { width: 8px; height: 8px; border-radius: 50%; flex: none; }
      .rule-text { flex: 1; min-width: 0; }
      .rule-name { font-weight: 600; }
      .rule-sub { font-size: 12.5px; color: var(--nc-muted); font-family: "JetBrains Mono", monospace; }
      .pri-pill { border-radius: 999px; padding: 2px 10px; font-size: 12px; font-weight: 700; text-transform: capitalize; }
      .pri-pill.digest { background: var(--nc-inset); color: var(--nc-muted); }
      .edit-grid { display: grid; grid-template-columns: 160px 1fr 340px; gap: 22px; align-items: start; }
      .rail { display: flex; flex-direction: column; gap: 4px; position: sticky; top: 12px; }
      .rail-step { display: flex; align-items: center; gap: 10px; background: none; border: none;
        font: inherit; color: var(--nc-muted); padding: 10px; border-radius: 10px; cursor: pointer; text-align: left; }
      .rail-step.on { background: var(--nc-tint); color: var(--nc-accent); font-weight: 600; }
      .rail-num { width: 22px; height: 22px; border-radius: 50%; background: var(--nc-inset); color: var(--nc-muted);
        display: grid; place-items: center; font-size: 12px; font-weight: 700; }
      .rail-step.on .rail-num { background: var(--nc-accent); color: var(--nc-on-accent); }
      .form { background: var(--nc-surface); border: 1px solid var(--nc-border); border-radius: 16px; padding: 20px;
        box-shadow: 0 1px 2px rgba(16,24,40,.04), 0 12px 32px rgba(16,24,40,.05); }
      .field { display: block; margin-bottom: 14px; }
      .flabel { display: block; font-size: 12px; font-weight: 600; text-transform: uppercase;
        letter-spacing: .03em; color: var(--nc-muted); margin-bottom: 6px; }
      .fhint { display: block; font-size: 12px; color: var(--nc-muted); margin-top: 4px; }
      .inp { width: 100%; box-sizing: border-box; border: 1px solid var(--nc-border); border-radius: 10px;
        padding: 9px 11px; font: inherit; background: var(--nc-inset); color: var(--nc-text); }
      .inp::placeholder { color: var(--nc-muted); opacity: .8; }
      .inp:focus { outline: none; border-color: var(--nc-accent);
        box-shadow: 0 0 0 3px color-mix(in srgb, var(--nc-accent) 22%, transparent); background: var(--nc-surface); }
      .inp.mono, textarea.mono { font-family: "JetBrains Mono", monospace; font-size: 13px; }
      .two { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
      code { font-family: "JetBrains Mono", monospace; font-size: 12px; background: var(--nc-inset);
        border: 1px solid var(--nc-border); border-radius: 5px; padding: 1px 5px; }
      .ca-row { border: 1px solid var(--nc-border); border-radius: 12px; padding: 12px; margin-bottom: 10px;
        display: flex; flex-direction: column; gap: 8px; background: var(--nc-inset); }
      .ca-foot { display: flex; gap: 10px; align-items: center; }
      .ca-foot .inp { flex: 1; }
      .picks { display: grid; gap: 10px; margin-bottom: 14px; }
      .picks.three { grid-template-columns: 1fr 1fr 1fr; }
      .picks.two { grid-template-columns: 1fr 1fr; }
      .pick { text-align: left; display: flex; flex-direction: column; gap: 3px; padding: 13px;
        border-radius: 12px; border: 1.5px solid var(--nc-border); background: var(--nc-inset); cursor: pointer; font: inherit; color: var(--nc-text); }
      .pick.on { background: var(--nc-tint); border-color: var(--nc-accent); }
      .pick ha-icon { --mdc-icon-size: 22px; color: var(--nc-muted); }
      .pick.on ha-icon { color: var(--nc-accent); }
      .pick span { font-size: 12px; color: var(--nc-muted); }
      .pri-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
      .pri-card { text-align: left; background: var(--nc-surface); border: 2px solid var(--nc-border); border-radius: 14px;
        padding: 15px; cursor: pointer; font: inherit; color: var(--nc-text); display: flex; flex-direction: column; gap: 6px; }
      .pri-card.on { border-color: var(--c); box-shadow: 0 4px 14px color-mix(in srgb, var(--c) 25%, transparent); }
      .pri-ic { width: 34px; height: 34px; border-radius: 9px; display: grid; place-items: center; }
      .pri-ic ha-icon { --mdc-icon-size: 20px; color: #fff; }
      .pri-card span { font-size: 12.5px; color: var(--nc-muted); }
      .pri-pills { display: flex; gap: 6px; margin-top: 4px; }
      .pri-pills span { background: var(--nc-inset); border-radius: 999px; padding: 2px 8px; font-size: 11px; color: var(--nc-muted); }
      .ch-list { display: flex; flex-direction: column; gap: 10px; margin-bottom: 12px; }
      .ch-row { display: flex; align-items: center; gap: 12px; padding: 12px 14px; border-radius: 13px;
        border: 1.5px solid var(--nc-border); background: var(--nc-inset); cursor: pointer; font: inherit; color: var(--nc-text); }
      .ch-row.on { background: var(--nc-tint); border-color: var(--nc-accent); }
      .ch-row ha-icon { --mdc-icon-size: 22px; color: var(--nc-muted); }
      .ch-row.on ha-icon { color: var(--nc-accent); }
      .ch-text { flex: 1; text-align: left; }
      .ch-text b { display: block; }
      .ch-text span { font-size: 12px; color: var(--nc-muted); }
      .toggle-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; font-size: 14px; }
      .toggle { width: 42px; height: 24px; border-radius: 999px; border: none;
        background: color-mix(in srgb, var(--nc-muted) 35%, transparent);
        padding: 2px; cursor: pointer; flex: none; }
      .toggle.on { background: var(--nc-accent); }
      .toggle .knob { display: block; width: 20px; height: 20px; border-radius: 50%; background: #fff;
        transition: transform .15s; }
      .toggle.on .knob { transform: translateX(18px); }
      .note { background: color-mix(in srgb, var(--nc-warning) 12%, transparent);
        border: 1px solid color-mix(in srgb, var(--nc-warning) 35%, transparent); color: var(--nc-text);
        border-radius: 10px; padding: 10px 12px; font-size: 13px; margin-bottom: 14px; }
      .chips { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 14px; }
      .chip { background: var(--nc-tint); color: var(--nc-accent); border-radius: 999px; padding: 4px 12px; font-size: 13px;
        font-weight: 600; text-transform: capitalize; }
      .chip.muted { background: var(--nc-inset); color: var(--nc-muted); text-transform: none; }
      .footer { display: flex; align-items: center; justify-content: space-between; margin-top: 18px;
        max-width: 100%; }
      .footer .primary { margin-left: auto; }
      /* preview — mirrors the (theme-following) tray card */
      .preview { position: sticky; top: 12px; display: flex; flex-direction: column; gap: 14px; }
      .pv-summary { background: var(--nc-inset); color: var(--nc-text); border: 1px solid var(--nc-border);
        border-radius: 14px; padding: 16px; font-size: 14px; line-height: 1.5; }
      .pv-label { font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: .03em; color: var(--nc-muted); }
      .pv-tray { background: var(--nc-surface); border: 1px solid var(--nc-border); border-radius: 16px; padding: 12px;
        display: flex; gap: 12px; align-items: flex-start; box-shadow: 0 6px 18px rgba(16,24,40,.07); }
      .pv-ic { width: 38px; height: 38px; border-radius: 11px; display: grid; place-items: center; flex: none; }
      .pv-ic ha-icon { --mdc-icon-size: 22px; }
      .pv-text { flex: 1; min-width: 0; color: var(--nc-text); }
      .pv-title { font-weight: 600; font-size: 14px; }
      .pv-sub { font-size: 12.5px; color: var(--nc-muted); margin-top: 1px; }
      .pv-tag { display: inline-block; margin-top: 6px; background: var(--nc-inset); color: var(--nc-muted);
        border-radius: 999px; padding: 1px 8px; font-size: 11px; font-weight: 600; }
      .pv-actions { display: flex; flex-direction: column; gap: 6px; }
      .mini-act { font-size: 11.5px; font-weight: 700; border-radius: 8px; padding: 5px 10px;
        border: 1px solid transparent; background: var(--nc-inset); color: var(--nc-muted); text-transform: capitalize; }
      @media (max-width: 900px) {
        .edit-grid { grid-template-columns: 1fr; }
        .rail { flex-direction: row; flex-wrap: wrap; position: static; }
        .preview { position: static; }
      }
    </style>`;
  }
}

customElements.define("notification-center-panel", NotificationCenterPanel);
