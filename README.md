# Notification Center

<img src="brands/custom_integrations/notification_center/icon.png" alt="Notification Center icon" width="96" align="right">

**One place to define, route, and see every Home Assistant notification.**

Notification Center turns scattered `notify` / `tts` automations into a single
**event-driven engine** with **UI-editable rules** — priority-aware routing
(mobile · bell · wall · TTS), quiet hours, digests, actionable
buttons, persistence across restarts, and **one card** that renders your whole
notification tray on any surface (phone pop-up, wall panel, dashboard).

![Tests](https://github.com/carmenvetere/notifications/actions/workflows/test.yml/badge.svg)
![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)

## Highlights

- **UI-editable rules** via config *subentries* — add/edit a notification from
  Settings → Devices & Services → Notification Center → *Add notification rule*
  (works from a phone). No YAML, no restart.
- **Priority + channel aware** per rule: `critical` / `warning` / `info`
  (three levels), routed to `mobile` / `bell` / `wall` / `tts`.
  *Digest* is a delivery option on Info, not a priority.
- **Performant**: listens only to the entities/templates actually referenced.
  A changed entity re-evaluates only the rules touching it, debounced (~300 ms).
  Cost scales with rules touching the change, not the whole rule set. Push
  model — `should_poll = False`.
- **One source of truth** for rendering: `sensor.notification_center`'s
  `alerts` JSON attribute, iterated by **one** card on every surface.

## Screenshots

> **To add:** capture these with the packaged **example rules** (import
> `example_rules.yaml` — generic placeholder entities) on the current build so
> no personal entity/home names appear, then drop the PNGs in `docs/images/`.
> They'll render here and in HACS (`render_readme`).

<!--
| Rule editor + live preview | Notification card |
|---|---|
| ![Rule editor](docs/images/panel-edit.png) | ![Card](docs/images/card.png) |

![Rule list](docs/images/panel-rules.png)
![Phone push](docs/images/push.png)
-->

Suggested shot list: the **rule list** (`panel-rules.png`), a **rule in the
editor** showing the live card + phone-push preview (`panel-edit.png`), the
**card** on a dashboard in light and dark (`card.png`), and a **phone push**
(`push.png`).

## Install

**Requires Home Assistant 2026.7.0+.**

**Via HACS (recommended).** Until this is in the default HACS list, add it as a
**custom repository**:

1. HACS → ⋮ (top right) → **Custom repositories**.
2. Repository: `https://github.com/carmenvetere/notifications`, Type: **Integration** → **Add**.
3. Find **Notification Center** in HACS, **Download**, then **restart Home Assistant**.
4. Settings → Devices & Services → **Add Integration** → *Notification Center*.

**Beta / pre-release testing.** To try a pre-release build: in HACS open
**Notification Center** → ⋮ → **Redownload** → enable **Show beta versions**, then
pick the `-beta` version. Betas are published as GitHub pre-releases; stable
versions are normal releases.

**Manual.** Copy `custom_components/notification_center/` into your HA
`config/custom_components/` and restart.

After install, the sidebar **Notifications** panel and the
`custom:notification-center-card` are available with no extra resource setup.

## Entities

| Entity | What it provides |
|---|---|
| `sensor.notification_center` | state = active alert count; attrs: `priority`, `alerts[]` (tag/name/title/message/priority/icon/color/channels/navigation_target/created_at/age_min/`actions`/`digest`/`items`), `by_priority`, `history[]` (last 50 cleared: tag/title/priority/created_at/cleared_at/reason) |
| `sensor.notification_center_wall` | **Wall-panel feed** for ESPHome/LVGL panels (styled on-device): state = count; attrs `items` (one splittable string: `tag\|level\|title\|body\|when\|dismissable\|test;…`, up to 6 rows), `rows[]`, `critical_text` (takeover-pill text), `testing[]` |
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
| `notification_center.reload` | Rebuild rules + listeners with no HA restart (re-reads YAML rules) |
| `notification_center.export_rules` | Return all rules as data + a ready-to-save YAML string (backup / migrate to YAML mode) |
| `notification_center.test_rule` | Fire a rule now, as designed, through every channel (`tag`, `enabled`); auto-stops after 10 min |
| `notification_center.import_rules` | Bulk-create rules from a list (or the packaged examples) |

## Priority → channel matrix (per-rule overridable)

| Priority | Mobile (iOS level) | Bell | Wall | TTS | Quiet hrs | Cooldown | Color |
|---|---|---|---|---|---|---|---|
| critical | Yes (critical, bypass DND) | Yes | Yes | Yes | ignored | none | `#EA4D3D` |
| warning | Yes (time-sensitive) | Yes | Yes | opt | downgrade | 15 min | `#EF8C00` |
| info | passive | Yes | Yes | No | suppress | 60 min | `#7295B2` |

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

### The Notifications panel
The integration adds a **Notifications** panel to the sidebar (admin-only). It
has three tabs and follows your Home Assistant theme (light, dark or custom):

- **Rules**: every rule grouped by priority, with a plain-English summary
  ("When Garage door is open"), the channels it uses, who gets it, and live
  badges (*Active 3 min*, *Testing*, *Digest*). Search, filter (All, Active now,
  Critical, Warning, Info), turn rules on and off, **Test** them, and duplicate
  or delete them from the ⋮ menu (delete asks first).
- **Recent**: the last 50 cleared alerts by day: what fired, how long it lasted,
  where it went, and how it ended (resolved, dismissed by someone, snoozed, a
  button press, or a test).
- **Settings**: people and their phones, voice and speakers, quiet hours and
  the daily digest, plus a **Health** list of anything that isn't working, each
  with a link to the fix. See [Settings](#settings).

The **rule editor** is one page: *When should it fire?* (pick an entity from a
searchable list, with its current state and whether the rule would fire right
now), *How urgent is it?*, *Where does it go?* (each channel with its own
settings) and *What does it say?*, then folded **More options** (dismissing and
snoozing, live progress, timing and presence, buttons, daily digest, expert).
A preview column shows the alert on a phone, the dashboard card, the wall panel
and the spoken sentence, using **rendered** templates with live values. Save
and Cancel stay at the top; leaving with unsaved changes asks first, and
**Test** offers *Save and test* when there are unsaved edits.

The panel and card are served by the integration (`/notification_center_frontend/…`)
and registered automatically, so there's nothing to add to your resources. Rules
are created and edited only through the panel (or your YAML rules file, below).

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

### Test mode — see every element fire, then switch it off

Each rule in the panel has a **Test** button (also `notification_center.test_rule`
with the rule's `tag`). It fires the alert **exactly as designed** through every
channel the rule uses — push or Live Activity, spoken announcement, bell, the
wall feed / card, wall-panel action — regardless of the rule's condition, cooldown
or quiet hours, so you can check titles, templates, icons, buttons and voice
end to end. While testing, the row shows **TESTING** and the alert carries a
`test` flag (the card shows a TEST chip; the wall feed's 7th field is `1`).

Test mode leaves almost no trace: no cooldown, nothing persisted across a
restart, and the real condition is ignored for that rule until the test ends.
The test is listed on the Recent tab, marked as a test. Press **Stop test**, dismiss the alert, or wait — it **auto-stops after 10
minutes** — and the rule is re-evaluated for real. A custom-action button on a
test alert ends the test instead of running the real script (so a test can't
close your garage door).

## YAML-managed rules (git workflow)

Prefer rules as a file you can keep in **git** and edit with any editor (or
Claude Code)? Point the integration at one:

```yaml
# configuration.yaml
notification_center:
  rules_file: notification_center/rules.yaml   # relative to your config dir
```
```yaml
# notification_center/rules.yaml — a BARE LIST of rules (same fields as the
# panel). The first line is `- name: …` — do NOT repeat a `rules:` key here.
- name: Garage door left open
  dedup_tag: garage_open
  source_type: state
  entity_id: binary_sensor.garage_door
  operator: "=="
  value: "on"
  priority: warning
  channels: [mobile, bell, wall]
```

With `rules_file:` that file is the **single source of truth** — nothing is
stored in `.storage` — and you get **both** editors:

- **The file.** Edit it, commit it, pull it onto the HA box: changes are picked
  up **automatically within ~15 s** (or run `notification_center.reload`).
- **The panel.** The Notifications panel stays a full editor; every save is
  written back to the file (a banner names the file). Panel saves rewrite the
  file, so keep notes in commit messages rather than YAML comments.

Rules are validated on load: invalid ones are skipped and listed in a
**repair issue** (never a silent wipe), and a file that fails to parse keeps the
last-good rules and raises its own repair.

**Migrating from panel-managed rules:** run **`notification_center.export_rules`**
(Developer Tools → Actions; it returns a response) and save its `yaml` field as
your rules file, add the `notification_center:` block, and restart once. Remove
the block (and restart) to go back to panel-only rules — your old subentry
rules are untouched while YAML mode is active.

<details>
<summary>Read-only alternative: inline <code>rules:</code></summary>

```yaml
notification_center:
  rules: !include notification_center/rules.yaml
```
Here the rules are part of `configuration.yaml`, which the integration never
rewrites, so the panel is a **read-only viewer**; apply edits with
`notification_center.reload`. Prefer `rules_file:` unless you specifically want
the panel locked.
</details>

## Delivery behavior reference

The Advanced step's knobs, and exactly what each does at runtime:

| Setting | What it does |
|---|---|
| **Cooldown** | Throttles *re-delivery* of the same alert. Per-priority default (critical 0, warning 15 min, info 60 min) unless overridden. After firing, a re-trigger within the window still **shows** in the tray but the push/TTS are suppressed (no nagging). A continuously-active alert never re-fires; cooldown only matters for flapping conditions. |
| **Quiet-hours behavior** | What happens to an alert that fires inside the quiet-hours window (Settings → Quiet hours, default 22:00–07:00 local): **ignore** = *Send as normal*; **downgrade** = *Send quietly*: drops one level in the tray, the push arrives silently (passive) and nothing is spoken; **suppress** = *Don't send*: keep on bell/wall but skip phones and speakers; **batch** = *Hold until quiet hours end*: show it now, but hold the push and send a grouped summary when quiet hours end. A rule that doesn't choose follows its priority: critical → ignore, warning → downgrade, info → batch. Quiet hours can be switched off entirely in Settings. |
| **Escalate after (min)** | While an alert stays active, re-deliver it every N minutes until it clears. Re-armed after a restart. |
| **Auto-clear** | When the trigger condition resolves, the alert leaves the tray automatically (default on). |
| **Presence routing** | Which mobile targets get the push: **all**; **away_only** (notify only people who are *away* — skip anyone home); **per_person** (notify only people who are *home* — ping whoever's actually there). away_only and per_person each fall back to notifying everyone if the filter would exclude all people, so nothing is missed. Applies to people from Settings; phones not tied to a person only get rules sent to everyone with presence routing *all*. A rule's **recipients** narrow the audience first. |
| **Dedup tag** | Alerts sharing a tag collapse into one; a re-trigger replaces rather than stacks. Defaults to a slug of the name. |
| **Cooldown / quiet hours interaction with snooze** | Snooze hides an alert now and re-shows it after the chosen duration; it also sets a cooldown for that window. |

Global settings live on the panel's **Settings** tab: people and phones,
voice and default speakers, the quiet-hours window and the daily digest time,
plus the re-evaluation **debounce** (default 300 ms: a burst of entity changes
becomes one evaluation).

These values persist across restarts: active alerts, cooldown/snooze deadlines,
and dismiss-until-resolve are restored on startup.

## Actionable push

Mobile pushes carry **action buttons** so you can act from the lock screen /
notification shade without opening the app: **Dismiss** and up to three
**Snooze** durations (the rule's snooze choices) when the alert permits them, plus one button per custom action (e.g. "I replaced
it"). Each button's id encodes the alert tag; when tapped, the companion app
fires `mobile_app_notification_action`, which the engine routes back to
`dismiss` / `snooze` / `run_action` for that alert. Locked (critical/warning)
alerts get no dismiss/snooze button but still show custom actions. Tapping the
notification body follows the rule's `navigation_target` (if set).

> **Push icon:** mobile pushes always show the **Home Assistant app icon** — this
> is fixed by the OS on iOS, and on Android we keep the recognizable HA logo
> rather than overriding it. A rule's `icon`/`color` style the **card / wall**
> row (and the panel preview of it), not the push. The push priority is conveyed
> by the iOS interruption level (passive / time-sensitive / critical), not the icon.

### Troubleshooting: app notifications not arriving
A mobile push only goes out if the integration knows **which** notify service
to call. Add phones on the panel's **Settings** tab (under a person, or under
*Other phones*) and press **Send test** next to each one. If a rule with the `mobile` channel fires while no
targets are configured, the push silently no-ops and a **repair issue**
("No mobile notify targets configured") is raised so it's visible. To verify
end-to-end, call the **`notification_center.test_push`** service (Developer
Tools → Actions) — it sends a test push to every configured target right now,
bypassing rules, quiet hours and cooldown. Other reasons a push may be held:
quiet-hours *suppress*/*batch*, digest delivery, or an active cooldown window.

## Live Activities (ongoing progress on the phone)

A rule with `live_activity: true` delivers an **iOS Live Activity / Android
Live Update** on the `mobile` channel instead of a one-shot push: a persistent
lock-screen / Dynamic Island item with a **progress bar** and/or a **live
countdown**. The engine **starts** it when the rule fires, pushes a **silent
in-place update** whenever the templated fields change, and **ends** it
(`clear_notification`) when it's over.

Requires **HA Core 2026.7.0+** and, on iOS, the **17.2+ companion app with Live
Activities enabled (Labs)**. Live Activities support **tap-to-open only** (via
`mobile_navigation_target`/`navigation_target`) — no action buttons, so any
pause/stop buttons live on the card.

**When it ends** — whichever comes first:
- the rule's **condition resolves** (e.g. trigger = "grid power off" → power
  returns → the activity clears), or
- an optional **`activity_timeout`** (minutes) elapses, even if still active.
- Apple also hard-caps activities at ~8 hours.

Rule fields (in addition to the trigger + `channels: [mobile]`):

| Field | Meaning |
|---|---|
| `live_activity: true` | Deliver the mobile channel as a Live Activity/Update. |
| `progress_template` | Renders to a number → the progress value (a bar shows with a max). |
| `progress_max_template` | Renders to the max (default 100). |
| `critical_text_template` | Short chip text (Dynamic Island / status bar). |
| `chronometer: true` + `when_template` | Live count-up/down timer; `when_template` renders to seconds-from-now. |
| `activity_timeout` | Minutes after which the activity auto-ends, regardless of the condition. |

```yaml
- name: Power outage
  dedup_tag: power_outage
  source_type: state
  entity_id: binary_sensor.grid_status
  operator: "=="
  value: "off"
  priority: warning
  channels: [mobile]
  live_activity: true
  progress_template: "{{ states('sensor.powerwall_charge') }}"
  critical_text_template: "{{ states('sensor.powerwall_charge') }}%"
  # ends automatically when grid_status returns to "on" (condition resolves)
```

Prefer `chronometer`/`when` for countdowns so the timer runs on-device without a
push every second; only meaningful field changes push an update (iOS throttles
frequent updates).

## Custom actions ("I did the chore")

A rule can define **custom actions** — buttons on the notification that run a
service after an optional confirmation, then clear the alert. This is how the
chore reminders work: e.g. "Attic HVAC filter due" shows an **I replaced it**
button that runs `script.reset_filter` (which resets the
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
{{ state_attr('sensor.weather_alerts', 'event')
   or state_attr('sensor.weather_alerts', 'title') or 'Active weather alert' }}
```

(adjust the attribute name to your NWS integration). Any entity state/attribute
works: `{{ states('sensor.home_battery_charge') }}%`, `{{ now() }}`, etc. Templates
render at fire time and then **re-render live** while the alert stays active
whenever the rule's tracked entities change — so a message like
`Temp is {{ states('sensor.attic') }}` stays current. (Only entities the rule
already watches for its trigger drive the refresh; a message referencing a
different entity won't update — see G15.)

## Rule data model (one subentry per rule)

`name`, `enabled`, `source_type` (`state` | `numeric` | `template`),
`entity_id`, `operator`, `value`/threshold, `condition_template`, `priority`,
`channels[]`, `icon`, `color`, `title_template`, `message_template`,
`navigation_target` (wall/dashboard tap path), `mobile_navigation_target`
(push/mobile tap path — falls back to `navigation_target`), `dedup_tag`,
`cooldown`, `auto_clear`,
`quiet_hours_behavior`, `presence_routing`, `recipients[]` (people who get the
push / Live Activity; empty = everyone), `escalation_after`, `tts_targets`,
`tts_message`, `actions_follow_priority`, `clear_mode`, `snooze`,
`custom_actions[]`, `wall_action` / `wall_service` and `wall_takeover` /
`wall_takeover_text` / `wall_takeover_target` (ESP32 wall panels, see below),
`snooze_options` (minutes offered when snoozing is allowed; default
`[60, 240, 1440]`), and for Info: `deliver_as_digest`, `digest_group`,
`items_template`.

Each condition (a door left open, a temperature threshold, a template) becomes
one subentry whose thresholds are editable fields. Many similar items — e.g. a
set of low batteries — can collapse into **one** Info rule with
`deliver_as_digest: true`, `digest_group: batteries`, and an `items_template`
listing each low device. See `example_rules.yaml` for a starter set you can
import (`notification_center.import_rules`) and adapt.

For state/numeric rules, `condition_template` (if set) is an extra gate. For
`source_type = template`, `condition_template` *is* the source.

## Settings

Everything global is on the panel's **Settings** tab, saved with one **Save**
(and **Discard** to undo). *Send test* and *Play test announcement* work on
what's on screen without saving.

- **Health**: anything not working, in plain language: no voice for
  announcements, a phone whose last push failed, or a person with no phone
  (so rules sent to them reach nobody). Each has a button that takes you to the
  fix. When all is well: *Everything is working.*
- **People and phones**: each person (picture and Home/Away from their
  `person` entity) with **one or more phones** (`notify.mobile_app_*`), and
  *Other phones* not tied to anyone, like a shared tablet. A rule sent to
  **Everyone** reaches every phone; a rule sent to one person reaches only
  theirs. Phones can move between people and *Other phones* without re-adding.
- **Announcements**: the **voice** (Automatic picks Home Assistant Cloud, else
  the first text-to-speech engine) and the **default speakers** used when a rule
  has Speakers on but doesn't pick its own.
- **Quiet hours**: on/off, *From … until …* (overnight is fine), and the daily
  digest time. During quiet hours, by default: critical always comes through,
  warning arrives silently with nothing spoken, info is held and sent as one
  summary when quiet hours end. Any rule can choose differently.
- **Advanced**: the speech action (`tts.speak`), the re-check delay, and the
  sheet, page and sound names your ESP32 wall panels accept (offered in a
  rule's wall panel settings). Sounds default to `chime`; each panel's
  firmware decides what a name sounds like and how loud it plays.

The rule editor's preview follows quiet hours too: with *Send quietly*, *Don't
interrupt* or *Hold until morning* chosen, the phone, wall and spoken previews
say what changes between your quiet-hours times.

The integration's **Configure** dialog (Settings → Devices & Services) now just
links here. Settings are stored in the config entry's options; upgrading from
0.5 or earlier migrates them automatically (each person gets a phone list, and
the old per-person speaker is dropped: announcements use a rule's speakers or
the default speakers).

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
It ships a **visual config editor** (the dashboard's *Edit card* UI — title,
sensor/priority entities, surface, show-header) so you don't have to hand-write YAML, and
is keyboard-navigable with ARIA labels on its controls. Use it however you
surface it:

```yaml
# Directly on a wall-panel view (give it height via a panel/grid layout):
- type: custom:notification-center-card
  surface: wall   # rows open the rule's wall path (#45)

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

### ESPHome / LVGL wall panels
> Full contract for firmware authors (fields, ordering, `action` semantics,
> ESPHome wiring, migration): [`docs/esphome-wall-panel.md`](docs/esphome-wall-panel.md).

A microcontroller panel can't run the card, and it styles everything on the
device anyway — so the integration publishes a **ready-made feed** instead:
`sensor.notification_center_wall`. Its `items` attribute is one string the
firmware can split without JSON — rows separated by `;`, fields by `|`:

```
tag|level|title|body|when|dismissable|test;tag|level|…
power_outage|critical|Power Outage!|On battery · Powerwall 76%|3 min ago|0|0
```
`level` is `critical` / `warning` / `info`; `when` is `Just now`, `N min ago`,
`N h ago` or `N d ago`; `dismissable` and `test` are `1`/`0`. `|`, `;` and
newlines inside text are replaced. `critical_text` holds the text for a
status-bar takeover pill (the top critical alert's title plus its short status),
and `rows[]` carries the same data as a list for anything that prefers JSON.

```yaml
# ESPHome
text_sensor:
  - platform: homeassistant
    id: ts_notifs
    entity_id: sensor.notification_center_wall
    attribute: items
    on_value: [script.execute: render_notifs]
```
Dismiss from the panel with `notification_center.dismiss` (`tag`), and
"Clear all" by dismissing every row whose `dismissable` is `1`.

#### Make the panel react: `wall_action`
A rule can also tell the panels to *do* something when it fires — open a
sheet or page, or play a sound. Set **`wall_action`** on the rule (Channels
step → *Wall panel*), e.g. `sheet:outage`, `page:security`, `sound:alarm`,
`chime` (the default sound), or several comma-separated:
`sheet:outage,sound:alarm`. The names are yours (list sounds in Settings →
Advanced): the integration just publishes the string; the firmware decides
what each means.

It appears in the feed's **`action`** attribute as `tag|action|nonce|quiet`
(plus `action_at`). The nonce changes on every fire, so a panel reacts once
per alert — on new alerts, escalation re-fires and **Test**, never on silent
content refreshes, and not when quiet hours suppress the push. `quiet` is `1`
when the rule fired during quiet hours with *Send quietly*: open the sheet but
skip the sound.

```yaml
# ESPHome
text_sensor:
  - platform: homeassistant
    id: ts_nc_action
    entity_id: sensor.notification_center_wall
    attribute: action
    on_value:
      - lambda: |-
          // "power_outage|sheet:outage,sound:alarm|17|0"
          auto f = split(x, '|');
          if (f.size() < 2) return;
          bool quiet = f.size() > 3 && f[3] == "1";
          for (auto &a : split(f[1], ',')) {
            if (a.rfind("sheet:", 0) == 0) id(open_sheet).execute(a.substr(6));
            else if (a.rfind("page:", 0) == 0) id(open_page_by_name).execute(a.substr(5));
            else if (quiet) continue;
            else if (a == "chime") id(play_sound).execute("chime");
            else if (a.rfind("sound:", 0) == 0) id(play_sound).execute(a.substr(6));
          }
```

To drive **one specific panel**, or use an action the panel declares with
ESPHome's `api: actions:`, set **`wall_service`** (e.g.
`esphome.mudroom_panel_navigate`): it is called on each fire with `tag`,
`action`, `title` and `priority`. A failing call shows up as a repair.

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

## License

Released under the [MIT License](LICENSE).
