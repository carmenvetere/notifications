# Notification Center

A unified, UI-editable, performant notification service for Home Assistant,
packaged as the custom integration `notification_center`.

It replaces hand-duplicated alert logic (one giant template sensor with dozens
of state triggers, alert cards written three times, a referenced-but-never-defined
priority sensor, and ~20 automations calling `notify`/`tts`/`fully_kiosk`
directly) with **one** event-driven engine, **one** rendering source, and
**UI-editable** rules.

## Highlights

- **UI-editable rules** via config *subentries* — add/edit a notification from
  Settings → Devices & Services → Notification Center → *Add notification rule*
  (works from a phone). No YAML, no restart.
- **Priority + channel aware** per rule: `critical` / `warning` / `info` /
  `digest`, routed to `mobile` / `bell` / `wall` / `tts` / `navigate`.
- **Performant**: listens only to the entities/templates actually referenced.
  A changed entity re-evaluates only the rules touching it, debounced (~300 ms).
  Cost scales with rules touching the change, not the whole rule set. Push
  model — `should_poll = False`.
- **One source of truth** for rendering: `sensor.notification_center`'s
  `alerts` JSON attribute, iterated by **one** card on every surface.

## Entities

| Entity | What it provides |
|---|---|
| `sensor.notification_center` | state = active alert count; attrs: `priority`, `alerts[]` (tag/name/title/message/priority/icon/color/channels/navigation_target/created_at/acknowledged/age_min), `by_priority` |
| `sensor.notification_center_priority` | state = highest active priority; attrs: `critical`, `warning`, `color`, `count`, `icon` — **drop-in replacement** for the never-defined `sensor.notification_icon_priority` |
| `binary_sensor.notification_center_active` | on when any alert is active |
| `binary_sensor.notification_center_critical` / `_warning` | on when a critical/warning alert is active |

## Services

| Service | Purpose |
|---|---|
| `notification_center.send` | Create a one-off alert (tag/title/message/priority/channels/…) |
| `notification_center.acknowledge` | Mark an alert acknowledged (stops escalation) |
| `notification_center.snooze` | Dismiss + suppress for N minutes |
| `notification_center.dismiss` | Remove an alert and clear its bell notification |
| `notification_center.reload` | Rebuild rules + listeners with no HA restart |

## Priority → channel matrix (per-rule overridable)

| Priority | Mobile (iOS level) | Bell | Wall | TTS | Force-nav | Quiet hrs | Cooldown | Color |
|---|---|---|---|---|---|---|---|---|
| critical | Yes (critical, bypass DND) | Yes | Yes | Yes | Yes | ignored | none | `#EA4D3D` |
| warning | Yes (time-sensitive) | Yes | Yes | opt | opt | downgrade | 15 min | `#EF8C00` |
| info | passive | Yes | Yes | No | No | suppress | 60 min | `#7295B2` |
| digest | grouped | Grp | Coll | No | No | batch | 12 h | `#9A988F` |

These are defaults; every rule can override priority, channels, color, icon,
cooldown, quiet-hours behavior, presence routing and escalation.

## Adding a rule (5-step wizard)

Settings → Notification Center → **Add notification rule** walks a wizard
(rendered with native `ha-form` selectors), branching via sub-steps:

1. **Trigger** — name, enabled, trigger type → then either entity/operator/value
   (state/numeric) or a condition template.
2. **Priority** — sets push level, icon, color, cooldown and clearing defaults.
3. **Channels** — pick channels; reveals a **spoken announcement** sub-step when
   TTS is on and a navigation-path sub-step when Navigate is on.
4. **Message** — title/message templates, icon, color overrides.
5. **Delivery behavior** — *Actions follow priority* (default on); when off, a
   **clearing model** step appears. Plus auto-clear, quiet hours, presence
   routing, cooldown/escalation overrides, dedup tag, digest group.

### Clearing model (no redundant Acknowledge + Dismiss)
Each rule has exactly one clearing mode, plus optional snooze. By default it
follows the priority:

| Priority | Clear mode | Snooze |
|---|---|---|
| critical | **locked** — only auto-clears when the condition resolves | off |
| warning | **acknowledge** — stops escalation, stays until resolved | off |
| info | **dismiss** — clears immediately | on |
| digest | **dismiss** | off |

The engine **gates** the `acknowledge` / `dismiss` / `snooze` services to the
permitted mode (others log a warning and no-op), and each alert in
`sensor.notification_center.attributes.alerts[]` carries an `actions` list so a
card renders only the buttons that apply. A dismissed rule-backed alert stays
hidden until its condition resolves; a snoozed one reappears after the window.

## Rule data model (one subentry per rule)

`name`, `enabled`, `source_type` (`state` | `numeric` | `template`),
`entity_id`, `operator`, `value`/threshold, `condition_template`, `priority`,
`channels[]`, `icon`, `color`, `title_template`, `message_template`,
`navigation_target`, `dedup_tag`, `cooldown`, `auto_clear`,
`quiet_hours_behavior`, `presence_routing`, `escalation_after`, `tts_targets`,
`tts_message`, `digest_group`, `actions_follow_priority`, `clear_mode`,
`snooze`.

- 21 boolean rules → 21 subentries (thresholds become editable fields).
- 30 battery sensors → **one** template rule, `priority = digest`,
  `digest_group = batteries`.

For state/numeric rules, `condition_template` (if set) is an extra gate. For
`source_type = template`, `condition_template` *is* the source.

## Global configuration (Options)

Settings → Notification Center → **Configure**:

- **Mobile notify services** and/or **presence-mapped people**
  (`[{person, notify, media_player}]`) — drives presence-aware routing
  (`all` / `away_only` / `per_person`).
- **TTS service** + default media players.
- **Fully Kiosk device IDs** for force-navigate.
- **Quiet hours** start/end and re-evaluation **debounce** (ms).

> Routing targets are configuration, not hardcoded — set Carmen's and Brian's
> `notify.mobile_app_*` services and the living-room/mudroom Fully Kiosk device
> IDs here.

## Dashboard

`dashboards/modules/notification-list.yaml` renders the alerts with the
already-installed `config-template-card`, iterating
`sensor.notification_center.attributes.alerts`. Include it once per surface.
The file also contains commented NSPanel (`button-card`) and bell-chip
(`mushroom`) variants that iterate the **same** JSON and point the chip
icon/color/count at the two sensors above.

## Installation

Copy `custom_components/notification_center/` into your HA `config/custom_components/`
(or install via HACS as a custom repository), restart HA, then add **Notification
Center** from Settings → Devices & Services.

## Development / tests

The pure decision logic (rule matching, channel routing, quiet hours) has no
Home Assistant imports and is unit-tested with stdlib `unittest`:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

HA-dependent modules (engine, sensors, config flow) are checked with
`python3 -m py_compile custom_components/notification_center/*.py`. With a full
HA dev environment also run `hass --script check_config` and `hassfest`.

## Migration (in the `mobile` HA repo)

This repo holds the integration, card and tests. The phased migration that
gutting the duplicated YAML (the 1253-line `notifications.yaml`, the 401-line
NSPanel `alerts-view.yaml`, `sensor.notification_alert_counter`, the
auto-navigate automation) happens in the `mobile` repo by adding rules here and
repointing each surface at `sensor.notification_center*`.
