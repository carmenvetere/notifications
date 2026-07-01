# Notification Center

<img src="brands/custom_integrations/notification_center/icon.png" alt="Notification Center icon" width="96" align="right">

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
- **Priority + channel aware** per rule: `critical` / `warning` / `info`
  (three levels), routed to `mobile` / `bell` / `wall` / `tts` / `navigate`.
  *Digest* is a delivery option on Info, not a priority.
- **Performant**: listens only to the entities/templates actually referenced.
  A changed entity re-evaluates only the rules touching it, debounced (~300 ms).
  Cost scales with rules touching the change, not the whole rule set. Push
  model — `should_poll = False`.
- **One source of truth** for rendering: `sensor.notification_center`'s
  `alerts` JSON attribute, iterated by **one** card on every surface.

## Entities

| Entity | What it provides |
|---|---|
| `sensor.notification_center` | state = active alert count; attrs: `priority`, `alerts[]` (tag/name/title/message/priority/icon/color/channels/navigation_target/created_at/age_min/`actions`/`digest`/`items`), `by_priority`, `history[]` (last 50 cleared: tag/title/priority/created_at/cleared_at/reason) |
| `sensor.notification_center_priority` | state = highest active priority; attrs: `critical`, `warning`, `color`, `count`, `icon` — **drop-in replacement** for the never-defined `sensor.notification_icon_priority` |
| `binary_sensor.notification_center_active` | on when any alert is active |
| `binary_sensor.notification_center_critical` / `_warning` | on when a critical/warning alert is active |

## Services

| Service | Purpose |
|---|---|
| `notification_center.send` | Create a one-off alert (tag/title/message/priority/channels/…) |
| `notification_center.snooze` | Dismiss + suppress for N minutes (Info rules only) |
| `notification_center.dismiss` | Remove an alert and clear its bell notification |
| `notification_center.run_action` | Run a rule's custom action (e.g. a reset script) and clear the alert |
| `notification_center.reload` | Rebuild rules + listeners with no HA restart |

## Priority → channel matrix (per-rule overridable)

| Priority | Mobile (iOS level) | Bell | Wall | TTS | Force-nav | Quiet hrs | Cooldown | Color |
|---|---|---|---|---|---|---|---|---|
| critical | Yes (critical, bypass DND) | Yes | Yes | Yes | Yes | ignored | none | `#EA4D3D` |
| warning | Yes (time-sensitive) | Yes | Yes | opt | opt | downgrade | 15 min | `#EF8C00` |
| info | passive | Yes | Yes | No | No | suppress | 60 min | `#7295B2` |

These are defaults; every rule can override priority, channels, color, icon,
cooldown, quiet-hours behavior, presence routing and escalation. **Info** rules
can additionally be **delivered as a digest** (`deliver_as_digest`): the alert
shows in the tray immediately but its push is **held and sent as a grouped
summary at the daily digest time** (Options → *Daily digest delivery time*,
default 08:00). It still lists its individual items (via `items_template`), and
each item can be **dismissed individually** (a ✕ on the card / the
`notification_center.dismiss_item` service) — the item hides until the digest
next clears.

## Adding a rule

### Custom setup panel (recommended)
The integration registers a **Notifications** panel in the HA sidebar
(`mdi:bell-cog`, admin-only). It's a custom UI — list your rules, add/edit them
in the 5-step wizard with a **live preview** (plain-English summary + a mobile
tray mock), and delete them. It manages rule subentries directly through the
integration's WebSocket API (`notification_center/rules/*`), so it can render
the preset/channel cards and preview that the stock config flow can't.

The panel is served from the integration (`/notification_center_frontend/…`)
and the sidebar entry is registered automatically on setup — no resource
registration needed. Both the panel and the card **follow your selected HA
theme** (light/dark/custom) via theme variables; the priority colors
(`#EA4D3D`/`#EF8C00`/`#7295B2`) stay fixed as semantic accents.

The panel is the **sole** rule editor: rules are created and edited only
through it (over the WebSocket API). There is no native `ha-form` config-flow
wizard — Settings → Notification Center exposes just the global **Options**
(routing, quiet hours, digest time, debounce).

The five steps of the panel wizard:

1. **Trigger** — name, enabled, trigger type → then either entity/operator/value
   (state/numeric) or a condition template.
2. **Priority** — sets push level, icon, color, cooldown and clearing defaults.
3. **Channels** — pick channels; reveals a **spoken announcement** sub-step when
   TTS is on and a navigation-path sub-step when Navigate is on.
4. **Message** — title/message templates, icon, color overrides.
5. **Delivery behavior** — *Actions follow priority* (default on); when off, a
   **clearing model** step appears (Stays in tray / Dismiss + allow snooze).
   For **Info**, a *Deliver as a digest* toggle (+ digest group + items
   template) appears. Plus auto-clear, quiet hours, presence routing,
   cooldown/escalation overrides, dedup tag.

### Clearing model
Acknowledge was removed. Each alert is either **locked** or **dismissable**,
plus optional snooze. By default it follows the priority:

| Priority | Clear mode | Snooze |
|---|---|---|
| critical | **locked** — no manual clearing; auto-clears when the condition resolves | off |
| warning | **locked** — same as critical | off |
| info | **dismiss** — the user can clear it | on |

Because Critical/Warning are locked, there is no "Clear all" affordance. The
engine **gates** the `dismiss` / `snooze` services to the permitted mode (others
log a warning and no-op), and each alert in
`sensor.notification_center.attributes.alerts[]` carries an `actions` list
(`[]` for locked) plus `digest`/`items[]` so a card renders only the buttons and
sub-entries that apply. A dismissed rule-backed alert stays hidden until its
condition resolves; a snoozed one reappears after the window.

## Delivery behavior reference

The Advanced step's knobs, and exactly what each does at runtime:

| Setting | What it does |
|---|---|
| **Cooldown** | Throttles *re-delivery* of the same alert. Per-priority default (critical 0, warning 15 min, info 60 min) unless overridden. After firing, a re-trigger within the window still **shows** in the tray but the push/TTS are suppressed (no nagging). A continuously-active alert never re-fires; cooldown only matters for flapping conditions. |
| **Quiet-hours behavior** | What happens to an alert that fires inside the global quiet-hours window (Options → start/end, default 22:00–07:00 local): **ignore** = deliver normally; **downgrade** = drop one level (critical→warning→info; changes push level/icon/color and the tray priority); **suppress** = keep on bell/wall but skip mobile + TTS; **batch** = show it now, but **hold the push and deliver a grouped summary when quiet hours end**. |
| **Escalate after (min)** | While an alert stays active, re-deliver it every N minutes until it clears. Re-armed after a restart. |
| **Auto-clear** | When the trigger condition resolves, the alert leaves the tray automatically (default on). |
| **Presence routing** | Which mobile targets get the push: **all**; **away_only** (notify only people who are *away* — skip anyone home); **per_person** (notify only people who are *home* — ping whoever's actually there). away_only and per_person each fall back to notifying everyone if the filter would exclude all people, so nothing is missed. Requires presence-mapped people (Options → Persons); with only a flat mobile-targets list, all targets are always notified. |
| **Dedup tag** | Alerts sharing a tag collapse into one; a re-trigger replaces rather than stacks. Defaults to a slug of the name. |
| **Cooldown / quiet hours interaction with snooze** | Snooze hides an alert now and re-shows it after the chosen duration; it also sets a cooldown for that window. |

Global settings live in **Options** (Configure): the quiet-hours window, the
re-evaluation **debounce** (default 300 ms — a burst of entity changes becomes
one evaluation), mobile/TTS targets, presence-mapped people, and Fully Kiosk
device IDs.

These values persist across restarts: active alerts, cooldown/snooze deadlines,
and dismiss-until-resolve are restored on startup.

## Actionable push

Mobile pushes carry **action buttons** so you can act from the lock screen /
notification shade without opening the app: **Dismiss** and **Snooze 60m** when
the alert permits them, plus one button per custom action (e.g. "I replaced
it"). Each button's id encodes the alert tag; when tapped, the companion app
fires `mobile_app_notification_action`, which the engine routes back to
`dismiss` / `snooze` / `run_action` for that alert. Locked (critical/warning)
alerts get no dismiss/snooze button but still show custom actions. Tapping the
notification body follows the rule's `navigation_target` (if set).

### Troubleshooting: app notifications not arriving
A mobile push only goes out if the integration knows **which** notify service
to call. Set **Mobile notify services** (e.g. `notify.mobile_app_yourphone`)
under **Settings → Devices & Services → Notification Center → Configure**, or
add presence-mapped people. If a rule with the `mobile` channel fires while no
targets are configured, the push silently no-ops and a **repair issue**
("No mobile notify targets configured") is raised so it's visible. To verify
end-to-end, call the **`notification_center.test_push`** service (Developer
Tools → Actions) — it sends a test push to every configured target right now,
bypassing rules, quiet hours and cooldown. Other reasons a push may be held:
quiet-hours *suppress*/*batch*, digest delivery, or an active cooldown window.

## Custom actions ("I did the chore")

A rule can define **custom actions** — buttons on the notification that run a
service after an optional confirmation, then clear the alert. This is how the
chore reminders work: e.g. "Attic HVAC filter due" shows an **I replaced it**
button that runs `script.reset_upper_floors_filter_runtime` (which resets the
counter, so the alert also auto-clears). Each action is
`{label, service, data, target, confirm, icon, clear_on_run}`; edit them in the
panel's *Delivery behavior* step or as a list on the rule.

**Pick an entity's action (no YAML).** In the panel's custom-action editor you
can choose a **Home Assistant entity** and one of its available actions from a
dropdown — e.g. select the garage-door cover and pick **Close** — and the
`service` (`cover.close_cover`) and `target` (`entity_id`) are filled in for
you, with the button label defaulted to the entity's name. Leave the entity
blank to type a raw service like `script.reset_filter` for scripts/scenes.

## Dynamic detail in messages

Title and message are **Jinja templates**, rendered when the alert fires — so
you can pull in live data. For example the imported weather rule's message is:

```jinja
{{ state_attr('sensor.nws_alerts_alerts', 'event')
   or state_attr('sensor.nws_alerts_alerts', 'title') or 'Active weather alert' }}
```

(adjust the attribute name to your NWS integration). Any entity state/attribute
works: `{{ states('sensor.bayberry_charge') }}%`, `{{ now() }}`, etc. Templates
render at fire time; they don't live-update while the alert stays active.

## Rule data model (one subentry per rule)

`name`, `enabled`, `source_type` (`state` | `numeric` | `template`),
`entity_id`, `operator`, `value`/threshold, `condition_template`, `priority`,
`channels[]`, `icon`, `color`, `title_template`, `message_template`,
`navigation_target`, `dedup_tag`, `cooldown`, `auto_clear`,
`quiet_hours_behavior`, `presence_routing`, `escalation_after`, `tts_targets`,
`tts_message`, `actions_follow_priority`, `clear_mode`, `snooze`,
`custom_actions[]`, and for Info: `deliver_as_digest`, `digest_group`,
`items_template`.

- 21 boolean rules → 21 subentries (thresholds become editable fields).
- 30 battery sensors → **one** Info rule with `deliver_as_digest: true`,
  `digest_group: batteries`, and an `items_template` listing each low device.

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

### Mobile / wall card (recommended)
The integration **auto-loads** the card, so `custom:notification-center-card`
appears in the dashboard card picker — no resource registration or file copying
needed. (If it doesn't appear, hard-refresh the browser to clear the frontend
cache.)

The card **is** the notification tray — alerts grouped by priority with gated
dismiss/snooze and digest expansion. There's no bell chip; it renders the
content directly and **fills its container**, scaling with the container width
(so it looks right both in a small mobile pop-up and on a 480px+ wall panel).
Use it however you surface it:

```yaml
# Directly on a wall-panel view (give it height via a panel/grid layout):
- type: custom:notification-center-card

# Inside a mobile pop-up (e.g. bubble-card) opened from a bell chip elsewhere:
#   pop-up content:
- type: custom:notification-center-card
  title: Notifications      # optional (default "Notifications")
  show_header: false        # optional — hide the header when the pop-up has its own
```

Options (all optional): `entity` (default `sensor.notification_center`),
`priority_entity`, `title`, `show_header`. The snooze duration picker is an
in-card overlay, so it works embedded. It maps to HA theme vars, falling back
to the dark mock palette.

It reads `sensor.notification_center` + `sensor.notification_center_priority`
and groups alerts by priority into **quiet sections** (priority is shown by the
muted section header; cards themselves are flat). Each card shows the title with
the age inline, the message below, a single **dismiss ✕**, and — when the rule
has a custom action — one **full-width response button** (e.g. "I vacuumed it").
Snooze is off the card face: **long-press a row** to open the snooze duration
sheet. Digests expand into their `items[]`. Styling maps to HA theme variables
so it follows your theme, with dark values as fallbacks.

### Simple fallback
`dashboards/modules/notification-list.yaml` renders a read-only list with the
already-installed `config-template-card` (no dismiss/snooze). Include it where
the custom card isn't wanted; the file also has commented NSPanel/chip variants.

## Installation

Copy `custom_components/notification_center/` into your HA `config/custom_components/`
(or install via HACS as a custom repository), restart HA, then add **Notification
Center** from Settings → Devices & Services.

## Brand icon

The icon lives in `brands/custom_integrations/notification_center/` (`icon.png`
256×256, `icon@2x.png` 512×512) and is generated by `brands/generate_icon.py`
(`python3 brands/generate_icon.py`, needs Pillow) — a rounded blue tile with a
white bell and a red priority badge.

Home Assistant serves integration icons from the
[`home-assistant/brands`](https://github.com/home-assistant/brands) repo, not
from a custom component, so to make it show in Settings → Devices & Services and
HACS, submit these PNGs there under `custom_integrations/notification_center/`
(the folder layout here already mirrors that path — copy it across and open a
PR). Until that's merged the integration shows the default icon; the sidebar
**Notifications** panel uses the built-in `mdi:bell-cog`.

## Development / tests

Two layers of tests:

- **Pure-logic tests** (`tests/test_*.py`) — rule matching, channel routing,
  quiet hours, the imported-rules mapping. No Home Assistant needed:

  ```bash
  python3 -m unittest discover -s tests -p 'test_*.py'
  ```

- **HA integration tests** (`tests/integration_*.py`) — exercise the engine,
  services, and WebSocket API inside a running Home Assistant via
  `pytest-homeassistant-custom-component`:

  ```bash
  pip install -r requirements_test.txt
  python -m pytest          # runs both layers
  ```

CI (`.github/workflows/test.yml`) runs **hassfest** (manifest/structure
validation) and **pytest** (both layers) on every push and PR.

HA-dependent modules also compile-check with
`python3 -m py_compile custom_components/notification_center/*.py`.

## Migration (in the `mobile` HA repo)

This repo holds the integration, card and tests. The phased migration that
gutting the duplicated YAML (the 1253-line `notifications.yaml`, the 401-line
NSPanel `alerts-view.yaml`, `sensor.notification_alert_counter`, the
auto-navigate automation) happens in the `mobile` repo by adding rules here and
repointing each surface at `sensor.notification_center*`.
