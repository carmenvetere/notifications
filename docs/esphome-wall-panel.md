# Notification Center → ESPHome / LVGL wall panels

How a wall panel built with ESPHome (LVGL) shows Notification Center alerts
and reacts to them. This is the contract between the integration
(`carmenvetere/notifications`, v0.5.x) and the panel firmware; the firmware
owns all styling.

The integration publishes **one entity** for panels, `sensor.notification_center_wall`,
and accepts **two actions** back from them (`notification_center.dismiss`,
`notification_center.snooze`). Everything the panel needs is attributes on
that entity; Home Assistant pushes attribute changes to ESPHome
`homeassistant` sensors, so there is no polling.

---

## 1. The feed entity: `sensor.notification_center_wall`

| | |
|---|---|
| **state** | number of active alerts (`0` when none) |
| `items` | **the rows**, one string — see §1.1 |
| `rows` | the same rows as a JSON list of objects (for consumers that prefer JSON) |
| `count` | same as the state, as a number |
| `critical_text` | text for a status-bar takeover pill: the top critical alert's title plus its short status, e.g. `Power Outage! 76%`; `""` when no critical alert |
| `testing` | list of alert tags currently in **test mode** |
| `action` | **the most recent wall action**: `tag|action|nonce` — see §2 |
| `action_at` | ISO timestamp of that action, or `null` |

All attributes update together whenever the alert set changes (new alert,
content refresh, dismiss, resolve, test start/stop).

### 1.1 `items` format

Rows separated by `;`, fields by `|`. No JSON parsing needed.

```
tag|level|title|body|when|dismissable|test;tag|level|title|body|when|dismissable|test
```

Example with two alerts:

```
power_outage|critical|Power Outage!|On battery · Powerwall 76% · about 5 h 43 min remaining|3 min ago|0|0;pool_salt_low|info|Pool Salt Level Low|Salt at 2500 ppm (low below 2700)|2 h ago|1|0
```

| Field | Values | Notes |
|---|---|---|
| 0 `tag` | rule's `dedup_tag` | stable id; pass it back to `dismiss` / `snooze` |
| 1 `level` | `critical` · `warning` · `info` | drives colour: red / amber / neutral |
| 2 `title` | text | the rule's rendered title (or its name) |
| 3 `body` | text | the rule's rendered message; may be empty |
| 4 `when` | `Just now` · `N min ago` · `N h ago` · `N d ago` | age since the alert started |
| 5 `dismissable` | `1` / `0` | show the ✕ only when `1`; critical/warning rules are usually locked (`0`) |
| 6 `test` | `1` / `0` | `1` while the rule is in test mode (fired on demand from the panel UI) |

Guarantees:

- **Order:** critical first, then warning, then info; within a level, oldest
  first. Row 0 is always the most important alert.
- **Cap:** at most **6 rows**. `count` / the state may be higher than the
  number of rows.
- **Escaping:** inside title/body/tag, `|` → `/`, `;` → `,`, newlines → space.
  A plain `split` on `;` then `|` is always safe.
- **Extra fields:** new fields are only ever *appended*. Read the fields you
  know by index and ignore the rest, so firmware keeps working across
  integration updates (today's firmware reads 0–5 and ignores 6).
- **Empty:** no alerts → `items` is `""`.

### 1.2 Which rules appear

A rule appears in the feed when its channels include **`wall`**. Everything
else about the rule (priority, templates, dismiss/snooze permissions) flows
through unchanged. Alerts in test mode appear exactly like real ones, with
field 6 = `1`.

---

## 2. Making the panel react: the `action` attribute

A rule can carry a **`wall_action`** string (set in the Notifications panel →
rule → *Channels* step → *Wall panel*, or `wall_action:` in `rules.yaml`).
When that rule fires, the feed's `action` attribute becomes

```
<tag>|<wall_action>|<nonce>
```

e.g. `power_outage|sheet:outage,chime|17`.

- **When it fires:** on a **new** alert (inactive → active), on each
  **escalation** re-fire, on a manual `notification_center.send` with a
  `wall_action`, and on **Test**. It does **not** fire on silent content
  refreshes (e.g. the battery % changing in the message) nor when quiet
  hours / cooldown suppress the push — the alert still shows in `items`, the
  panel just isn't interrupted.
- **Nonce:** increases on every fire, so the string changes even when the
  same rule fires twice in a row. ESPHome's `on_value` only runs on change,
  which is exactly the "react once per fire" behaviour you want.
- **Restart:** the nonce counter resets when Home Assistant restarts and
  `action` is `""` until the next fire. Ignore empty values.
- **Vocabulary:** the integration does not interpret the action; the firmware
  does. Convention used in the panel UI's suggestions:
  - `sheet:<name>` — open a bottom sheet (`sheet:outage`)
  - `page:<name>` — switch to a tab/page (`page:security`)
  - `chime` — play the attention sound
  - several, comma-separated: `sheet:outage,chime`

Rules can additionally set **`wall_service`** (e.g.
`esphome.mudroom_panel_navigate`): the integration then also *calls* that
Home Assistant action on each fire with `tag`, `action`, `title`, `priority`.
Use this only to target **one specific panel** or when the panel declares an
ESPHome `api: actions:` entry; the `action` attribute is the general path and
reaches every panel at once.

---

## 3. Actions the panel sends back

| Action | Data | When allowed |
|---|---|---|
| `notification_center.dismiss` | `tag` | only when the row's `dismissable` is `1` (otherwise the engine logs a warning and ignores it) |
| `notification_center.snooze` | `tag`, `minutes` | info-level rules with snooze enabled |

"**Clear all**" = call `dismiss` for every row whose `dismissable` is `1`.

Dismissing a **test** alert simply ends the test. Dismissing a real
rule-backed alert hides it until its condition resolves.

Note: rule **custom-action buttons** (e.g. "I replaced the filter") are not
in the feed today; they're a phone/card feature.

---

## 4. ESPHome wiring (reference)

### 4.1 Subscriptions

```yaml
text_sensor:
  # The rows.
  - platform: homeassistant
    id: ts_notifs
    entity_id: sensor.notification_center_wall
    attribute: items
    on_value: [script.execute: render_notifs]

  # Status-bar takeover pill text ("" = no critical alert).
  - platform: homeassistant
    id: ts_nc_critical
    entity_id: sensor.notification_center_wall
    attribute: critical_text
    on_value: [script.execute: render_status_bar]

  # Wall actions: "tag|sheet:outage,chime|17".
  - platform: homeassistant
    id: ts_nc_action
    entity_id: sensor.notification_center_wall
    attribute: action
    on_value:
      - lambda: |-
          if (x.empty()) return;                 // startup / no action yet
          auto f = split(x, '|');
          if (f.size() < 2) return;
          for (auto &a : split(f[1], ',')) {
            if (a.rfind("sheet:", 0) == 0)      id(open_sheet).execute(a.substr(6));
            else if (a.rfind("page:", 0) == 0)  id(open_page_by_name).execute(a.substr(5));
            else if (a == "chime")              id(play_chime).execute();
          }

sensor:
  # Bell badge count (hide the bell at 0).
  - platform: homeassistant
    id: nc_count
    entity_id: sensor.notification_center_wall
    on_value: [script.execute: render_status_bar]
```

### 4.2 Parsing rows

```cpp
struct Notif { std::string id, level, title, body, time; bool dismissable, test; };

inline std::vector<Notif> parse_notifs(const std::string &s) {
  std::vector<Notif> out;
  if (!valid(s)) return out;
  for (auto &row : split(s, ';')) {
    if (row.empty()) continue;
    auto f = split(row, '|');
    Notif n;
    n.id          = field(f, 0);
    n.level       = lower(field(f, 1));
    n.title       = field(f, 2);
    n.body        = field(f, 3);
    n.time        = field(f, 4);
    n.dismissable = field(f, 5, "1") != "0";
    n.test        = field(f, 6, "0") == "1";   // new in 0.4.1; default keeps old feeds working
    out.push_back(n);
  }
  return out;
}
```

Rendering conventions (level → colour): `critical` → red, `warning` → amber,
`info` → secondary text. A `test` row can append " · TEST" to the title or
tint the time label amber so a test is never mistaken for a real alert.

### 4.3 Sending actions back

```yaml
# dismiss row n
- homeassistant.action:
    action: notification_center.dismiss
    data:
      tag: !lambda "return panel::state().notifs[n].id;"
```

---

## 5. Testing the whole path

1. In Home Assistant, open the **Notifications** panel, pick a rule with the
   `wall` channel, press **Test**. Within ~1 s the panel's rows include it
   (field 6 = `1`); if the rule has a `wall_action`, the `action` attribute
   changes and the panel reacts (sheet/page/chime).
2. Press **Stop test** (or wait 10 minutes). The row disappears; `action`
   keeps its last value (ignore it — only *changes* matter).
3. Developer Tools → States → `sensor.notification_center_wall` shows every
   attribute live, which is the quickest way to check what the panel is
   receiving.

---

## 6. Migration notes for an existing panel

- Point the existing `ts_notifs` subscription at
  `sensor.notification_center_wall` (`attribute: items`) and delete the
  per-install template sensor that used to build the same string. The string
  format is identical, so `parse_notifs` needs no change (adding field 6 is
  optional).
- The old Fully Kiosk **`navigate`** channel is gone (0.5.0). Rules that still
  list it load fine; the channel is dropped. Use `wall_action` instead.
- `navigation_target` / `mobile_navigation_target` are **mobile dashboard
  paths** for the phone push and the card; they have no meaning for the
  panel.
