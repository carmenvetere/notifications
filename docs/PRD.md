# Notification Center — Product & Technical Requirements

Status: **draft** · Scope: the `notification_center` custom Home Assistant
integration in `carmenvetere/notifications`. This documents what exists today,
the requirements it serves, and — most importantly — the **gaps** worth planning
for. Status tags: ✅ implemented · 🟡 partial · ❌ gap.

> **Recently addressed** (since first draft): custom confirm-and-run actions
> (F21), dynamic message templates surfaced + wired (F22), full theme adherence
> (F23), the integration is now **running live** on a real HA instance (G1),
> **CI + a first batch of HA integration tests** landed (G3, now partial), and
> **restart persistence** shipped (G2, done). Top remaining priorities are now
> the P1 design items (digest scheduling, per-item dismiss, actionable push).

---

## 1. Overview

Notification Center is a single custom integration that centralizes home alerts:
one event-driven engine evaluates user-defined **rules**, maintains a set of
**active alerts**, and routes them to **channels** (mobile push, an in-app bell
list, wall panels, TTS, dashboard navigation) according to a **priority** and a
**clearing model**. One JSON attribute (`sensor.notification_center.alerts[]`)
is the single source of truth that every surface renders from.

It replaces duplicated, hand-maintained alert logic (a 50+-trigger template
sensor, alert cards written three times, a broken priority sensor, ~20
automations calling `notify`/`tts`/`fully_kiosk` directly) with one
UI-editable, performant system.

## 2. Goals / non-goals

**Goals**
- UI-editable rules (add/edit from a phone), no YAML or restart required.
- Priority- and channel-aware delivery with sensible per-priority defaults.
- Performant: listen only to referenced entities/templates; evaluate only the
  rules a change touches.
- One render source, many surfaces (mobile pop-up, wall panel, chip).
- Presence-, quiet-hours-, cooldown-, and escalation-aware routing.

**Non-goals (today)**
- A general automation engine (it's notification-specific).
- Cloud/remote delivery beyond what HA's `notify`/`mobile_app` already provide.
- Replacing HA's native persistent notifications wholesale (it builds on them).

## 3. Personas & primary use cases

- **Homeowner (admin):** defines rules in the panel; wants the right urgency on
  the right device, quiet at night, no nagging duplicates.
- **Household member (non-admin):** receives push; dismisses/snoozes info alerts
  from phone or wall panel; can't edit rules.
- **Wall panel:** always-on surface showing the current tray.

Representative flows: power outage (critical, push + TTS + force-navigate, locked
until resolved); garage left open (warning, push, locked); low batteries (info,
digest of N devices, dismissible); laundry done (info, dismiss + snooze).

## 4. Product requirements (functional)

| # | Requirement | Status | Notes |
|---|---|---|---|
| F1 | Define rules in the UI (add/edit/delete) | ✅ | Custom panel + WS API; config-flow wizard as fallback |
| F2 | Rule triggers: state, numeric threshold, template | ✅ | `condition_template` also an extra gate for state/numeric |
| F3 | Three priorities (critical/warning/info) with defaults | ✅ | color/icon/cooldown/clear-mode/snooze per priority |
| F4 | Channels: mobile, bell, wall, tts, navigate | ✅ | router → `notify.*`, `persistent_notification`, `tts.speak`, `fully_kiosk` |
| F5 | Clearing model: locked vs dismiss (+snooze) | ✅ | critical/warning locked; info dismiss; engine-gated |
| F6 | Auto-clear when condition resolves | ✅ | |
| F7 | Dedup + cooldown (no nagging) | ✅ | dedup by tag; per-priority/override cooldown |
| F8 | Escalation (repeat critical) | 🟡 | timer-based; **lost on restart** (see G2) |
| F9 | Quiet hours (ignore/downgrade/suppress/batch) | 🟡 | single global window; **"batch" doesn't actually defer-and-flush** (see G6) |
| F10 | Presence-aware routing (all / away_only / per_person) | 🟡 | `per_person` not implemented; treated as all |
| F11 | Digest delivery on Info (group + items) | 🟡 | flag + `items_template` + payload; **no scheduled summary window** (see G5) |
| F12 | Snooze with duration | ✅ | service + card duration sheet; "pick a time" not in card |
| F13 | One render source; mobile/wall card | ✅ | container-query-scaled card fills its container |
| F14 | Drop-in priority sensor for the bell icon | ✅ | `sensor.notification_center_priority` |
| F15 | Bulk import existing rules | ✅ | `import_rules` service + packaged `imported_rules.yaml` |
| F16 | Manual one-off send | ✅ | `send` service |
| F17 | Per-item dismiss within a digest | ❌ | items are template-derived/read-only (see G4) |
| F18 | Actionable push (dismiss/snooze from the OS notification) | ✅ | mobile_app action buttons (dismiss/snooze/custom) → `mobile_app_notification_action` routed back |
| F19 | Notification history / audit log | ❌ | only active alerts are kept (see G8) |
| F20 | Native wall-panel firmware (ESP32-S3 / LVGL) | ❌ | design handoff exists; not built (see G9) |
| F21 | Custom actions (run a service from the notification, w/ confirm) | ✅ | per-rule `custom_actions`; `run_action` service; card buttons; clears the alert |
| F22 | Dynamic detail in title/message via templates | ✅ | rendered at fire time; not live while active (see G20) |
| F23 | UI follows the selected HA theme (panel + card) | ✅ | theme variables; priority colors stay fixed as semantic accents |

## 5. Technical requirements & architecture

### 5.1 Components (`custom_components/notification_center/`)
- `engine.py` — listeners (`async_track_state_change_event` over the union of
  referenced entities + `async_track_template_result` per template rule),
  ~300 ms debounce, active-alert dict keyed by dedup tag, cooldown/escalation/
  quiet-hours/presence application, dismiss(sticky)/snooze state.
- `rule.py` — `Rule` dataclass + pure `match_value` and derived properties
  (effective clear mode, snooze, cooldown, color/icon, allowed actions).
- `router.py` — pure channel→service-call resolution (unit-testable).
- `quiet_hours.py` — pure quiet-hours window + behavior.
- `config_flow.py` — parent flow, options flow, 5-step rule subentry wizard.
- `websocket_api.py` — `meta` / `rules.list|create|update|delete` for the panel.
- `sensor.py` / `binary_sensor.py` — exposed entities.
- `panel/` — custom setup panel + the tray card (auto-loaded frontend assets).
- `const.py`, `services.yaml`, `strings.json`, `translations/en.json`.

### 5.2 Data model
- **Rule** (one config subentry): name, enabled, source_type, entity_id,
  operator, value, condition_template, priority, channels[], icon, color,
  title/message templates, navigation_target, dedup_tag, cooldown, auto_clear,
  quiet_hours_behavior, presence_routing, escalation_after, tts_targets,
  tts_message, actions_follow_priority, clear_mode, snooze; Info-only:
  deliver_as_digest, digest_group, items_template.
- **Alert payload** (`alerts[]`): tag, name, title, message, priority, icon,
  color, channels, navigation_target, created_at, age_min, actions[], digest,
  items[].

### 5.3 Interfaces
- **Entities:** `sensor.notification_center` (count + `alerts[]` + `by_priority`),
  `sensor.notification_center_priority`, `binary_sensor.notification_center_active|critical|warning`.
- **Services:** `send`, `dismiss`, `snooze`, `reload`, `import_rules`.
- **WebSocket:** `notification_center/meta|rules/*` (mutations admin-only).
- **Frontend:** custom panel (`/notification-center`) + `custom:notification-center-card`.

### 5.4 Non-functional requirements
| Aspect | Target | Status |
|---|---|---|
| Performance | Re-eval scales with rules touching a change, not all rules | ✅ event-driven + debounce |
| Reliability | Survive restarts without losing alert/snooze/escalation state | ✅ persisted via `Store` + restored (G2) |
| Security | Rule mutations admin-only; no privileged shell-out | ✅ WS `require_admin` |
| Observability | Surfacable failures (bad target, bad template) | 🟡 logged only; no repair issues (G10) |
| Testability | Pure logic unit-tested; HA paths covered | 🟡 51 unit + HA engine/services/WS tests; CI (hassfest+pytest); flow/timing tests remain (G3) |
| i18n | Translatable | 🟡 `en` only |
| Schema evolution | Versioned config with migrations | ❌ entry version=1, no migrations (G11) |

---

## 6. Gaps & risks (prioritized)

### P0 — correctness / trust
- **G1 — 🟡 mostly addressed: no *automated* HA verification.** The integration
  is now confirmed **running live** on a real HA instance (setup, panel, card,
  rule CRUD, custom actions, theming all exercised by hand), so the "does it
  even load" risk is largely retired. What remains is that verification is
  **manual** — there's no regression safety net (rolls into G3). Authoring
  changes still can't be self-verified against HA from CI.
- **G2 — ✅ addressed: runtime state now persists.** Active alerts, cooldown
  and snooze deadlines, and the dismiss-until-resolve set are saved via HA
  `Store` (debounced; flushed on unload) and restored on setup; escalation
  timers are re-armed for still-active alerts. A restart no longer drops the
  tray, re-fires snoozed/dismissed alerts, or resets cooldowns. (Minor: a
  re-armed escalation resumes a full interval from startup rather than the exact
  remaining time.) *Original issue, for history:* active alerts, dismiss-until-resolve,
  snooze windows, cooldown timers, and escalation timers live in RAM and are
  **lost on HA restart**. After a restart a snoozed alert can re-fire, an
  escalation stops, dismissed alerts reappear. Need persistence (Store /
  RestoreEntity) + timer rehydration.
- **G3 — 🟡 partially addressed: CI + first HA tests added.** GitHub Actions now
  runs **hassfest** + **pytest** (pure + HA integration) on every push/PR, with
  `pytest-homeassistant-custom-component` tests covering engine transitions
  (active/auto-clear/sticky-dismiss), the clearing-model service gating,
  `run_action`, manual send, and the WS rule CRUD. Remaining: config/subentry
  **flow** tests, cooldown/escalation timing, presence/quiet-hours paths, and a
  version pin so the suite tracks the HA you run.

### P1 — feature completeness vs. the design
- **G4 — Digest items are read-only.** The design shows per-item dismiss; items
  come from a template (condition-driven) so there's no per-item action. Needs
  a real model (per-item suppression keys, or item-level state) to be dismissible.
- **G5 — ✅ digest scheduling done.** `deliver_as_digest` alerts show in the tray
  immediately but hold their push; a flush at the daily digest time (Options →
  *Daily digest delivery time*) delivers a single grouped summary.
- **G6 — ✅ quiet-hours "batch" defers-and-flushes.** Batch alerts hold their push
  and deliver a grouped summary when quiet hours end. Shared hold/flush engine
  with G5; held state persists across restarts.
- **G7 — ✅ addressed: push is actionable.** Mobile pushes now include
  dismiss/snooze/custom action buttons (tag encoded in each action id); the
  engine listens for `mobile_app_notification_action` and routes taps back to
  `dismiss`/`snooze`/`run_action`. Locked alerts omit dismiss/snooze but keep
  custom actions.
- **G8 — No history / audit trail.** Only active alerts exist; no record of
  past/cleared notifications for review or debugging.
- **G9 — Wall-panel firmware (ESP32-S3 / LVGL) not built.** Deliverable 3 of the
  design. Today "wall" is Lovelace-only (the card) + `fully_kiosk` navigation.
- **G10 — Weak misconfiguration feedback.** Bad notify target, unknown entity,
  or a template error fail quietly (logged). No HA repair issues / config
  validation surfaced to the user.

### P2 — polish / hardening
- **G11 — No config schema versioning/migrations.** If the rule schema changes,
  existing subentries won't migrate.
- **G12 — Two rule editors coexist.** The config-flow wizard (marked temporary)
  duplicates the panel; plan its removal once the panel is proven.
- **G13 — `per_person` presence routing unimplemented** (falls back to all).
- **G14 — Server-side rule validation is thin.** WS stores an arbitrary dict;
  invalid rules can be saved (no schema/voluptuous validation).
- **G15 — Condition-template dependency tracking is partial.** For state/numeric
  rules, a `condition_template` referencing *other* entities won't re-trigger on
  their changes (only the primary entity is tracked). Documented tradeoff.
- **G16 — 🟡 Brand icon: assets done, not submitted.** The icon + generator +
  brands-layout PNGs exist in `brands/`; HA still won't display it until the
  PNGs are merged into `home-assistant/brands`. Remaining work is the upstream PR.
- **G17 — i18n: `en` only.** No other translations.
- **G18 — Card/panel a11y.** Minimal ARIA/keyboard handling; no card config
  editor (`getConfigElement`).
- **G19 — No area/device-level targeting.** Rules are entity-based only.
- **G20 — Templates render at fire time only.** Title/message/items don't
  live-update while an alert stays active (would require re-rendering on each
  re-eval of the tracked entity).
- **G21 — Custom actions identified by list index.** `run_action` takes the
  action's index; editing a rule's `custom_actions` order while an alert is
  active could mis-map a button. Low impact; a stable per-action id would fix it.
- **G22 — Theme edge cases unaudited.** The UI now uses theme variables, but
  only the default light/dark themes are reasoned about; custom themes where,
  e.g., `--secondary-background-color` ≈ `--card-background-color` may be
  low-contrast. Worth a quick pass across a few popular themes.

---

## 7. Proposed plan

**Milestone A — Trust the system (P0).** _(Steps 1 & 3 mostly done.)_
1. 🟡 `pytest-homeassistant-custom-component` tests + GitHub Actions CI
   (hassfest + pytest) — **done** for engine transitions, service gating,
   `run_action`, manual send, and WS CRUD. **Remaining:** config/subentry flow
   tests, cooldown/escalation timing, presence/quiet-hours, and an HA version pin.
2. ~~Persist runtime state with `Store` + rehydrate; reschedule escalation
   timers on startup.~~ ✅ done (active alerts, cooldown/snooze deadlines,
   dismiss-until-resolve; flushed on unload, restored on setup).
3. ~~Smoke-test on a live HA and fix API drift.~~ ✅ confirmed running live.

**Milestone B — Finish the design (P1).**
4. Real digest engine: a scheduled summary window per `digest_group`; deliver
   once/window; implement quiet-hours `batch` as defer-and-flush.
5. Per-item digest model so items are individually dismissible.
6. ~~Actionable push: action buttons + handle `mobile_app` action events.~~ ✅ done.
7. Notification history (a capped log + optional `logbook` entries).
8. Repair issues / validation for bad targets, templates, missing entities.

**Milestone C — Surfaces & polish (P1/P2).**
9. ESP32-S3 ESPHome/LVGL wall-panel package (Deliverable 3).
10. Retire the config-flow wizard once the panel is proven; add schema
    versioning + migrations; implement `per_person`; strengthen WS validation;
    submit the brand icon; add a card config editor + i18n scaffold.

## 8. Open questions
- Should digests deliver on a fixed schedule (e.g., 8 AM) or a rolling window
  per group? Per-rule or global?
- Is acknowledge (seen-but-keep) genuinely gone, or wanted for some warnings?
- For actionable push, which actions per priority (dismiss/snooze/navigate)?
- Wall panel: ESP32-S3/LVGL firmware vs. a kiosk-rendered Lovelace card — commit
  to one before investing in firmware?
- History retention: how long / how many, and surface where (card tab? logbook?).
