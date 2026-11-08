# Changelog

All notable changes to **Notification Center** are recorded here. Entries are
aggregated toward the first stable **V1** release; each version is published as a
GitHub Release and installable through HACS. Dates are UTC.

The format loosely follows [Keep a Changelog](https://keepachangelog.com/), and
the project aims to follow [Semantic Versioning](https://semver.org/).

## [v0.5.1] — 2026-11-08

### Fixed
- **"Who gets it" showed no choices without presence-mapped people.** The
  recipients chips on the Channels step now fall back to the configured
  *Mobile notify services* when no people are mapped, with a hint explaining
  the Everyone default and how presence routing combines with it.

## [v0.5.0] — 2026-11-08

### Added
- **Save bar in the rule editor (#55).** Save / Cancel on every step, an
  "Unsaved changes" indicator, a confirm when leaving with unsaved edits,
  a toast on save (naming the rules file in `rules_file` mode), inline
  validation errors that jump to the offending step, and Ctrl/Cmd+S.
  Previously the only save was the last wizard step's button, so edits on
  earlier steps were silently lost when leaving.
- **Per-rule recipients (#56).** `recipients: [person.…]` chooses which
  people get a rule's push / Live Activity (chips on the Channels step).
  Applied before presence routing; empty = everyone. A recipient nobody is
  mapped to raises a `recipient_unmapped` repair.
- **Wall-panel actions for ESP32 / LVGL panels (#57).** `wall_action`
  (`sheet:outage`, `page:security`, `chime`, comma-separated) is published
  in `sensor.notification_center_wall`'s new `action` attribute as
  `tag|action|nonce` (+ `action_at`) on new alerts, escalations and Test —
  not on silent refreshes or when quiet hours suppress the push. Optional
  `wall_service` calls an action (e.g. an ESPHome `api: actions:` entry)
  with `tag`/`action`/`title`/`priority`. `notification_center.send`
  accepts `recipients` and `wall_action` too.

### Removed
- The Fully Kiosk **`navigate` channel** and the *Fully Kiosk device IDs*
  option. Rules that still list `navigate` load fine — the channel is
  dropped with a log line. `navigation_target` / `mobile_navigation_target`
  are unchanged (mobile dashboard paths for push and card taps).

## [v0.4.1] — 2026-11-08

### Added
- **Test mode.** Every rule has a **Test** button in the panel (and a
  `notification_center.test_rule` action): it fires the alert exactly as
  designed through every channel it uses — push or Live Activity, TTS, bell,
  wall feed / card, navigate — regardless of its condition, cooldown or quiet
  hours, so each element can be verified end to end. It leaves no trace (no
  cooldown, history or persistence), ignores the real condition while active,
  auto-stops after 10 minutes, and a custom-action button on a test alert ends
  the test instead of running the real script.
- **Wall-panel feed: `sensor.notification_center_wall`.** A compact feed for
  ESPHome/LVGL panels that style on-device: `items` is one splittable string
  (`tag|level|title|body|when|dismissable|test;…`, up to 6 rows), plus
  `rows[]`, `critical_text` for a status-bar takeover pill, and `testing[]`.
  Replaces the per-install template sensor such panels needed.
- The card shows a **TEST** chip on test alerts.

### Removed
- The card's `style: panel` option (added in 0.4.0). Wall panels in practice
  are ESPHome/LVGL devices that style on-device and read
  `sensor.notification_center_wall`; the card keeps one theme-following look.

## [v0.4.0] — 2026-11-08

### Added
- **Rules file mode — edit in the panel *and* in YAML (#47).**
  `notification_center: rules_file: notification_center/rules.yaml` makes
  that file the single source of truth while the Notifications panel stays a
  full editor: panel saves are written back to the file, and edits made to the
  file (git pull, an editor, Claude Code) are picked up automatically within
  ~15 s — no reload call needed. A file that fails to parse keeps the last-good
  rules and raises a repair. Inline `rules:` keeps its read-only behavior.
- **Wall-panel look for the card.** New card option `style: panel` (chosen
  automatically for `surface: wall`) renders the tray in the Mudroom wall
  panel's design: warm taupe palette v4, Red Hat Display + Barlow, 18 px
  surface cards with a round icon well coloured by level, a round dismiss
  button, long-form times, no section headers, and a red takeover pill for
  the top critical alert in the header. `style: default` keeps the
  theme-following look.

### Fixed
- **A failing push can no longer hide an alert.** If starting a Live Activity
  failed (for example a notify service that no longer exists), the exception
  aborted the evaluation pass before the tray was published — the alert
  existed but showed nowhere, and the normal push is skipped for Live
  Activity rules, so nothing reached the phone either. Live Activity sends
  are now guarded (a `delivery_failed` repair names the service) and one
  rule's failure never blocks publishing the rest.

## [v0.3.2] — 2026-11-07

### Fixed
- **Spoken (TTS) announcements never played.** `tts.speak` is an entity action
  whose target is the TTS *engine*, but Notification Center only sent the
  speakers and the message — so Home Assistant ran it on no engine, and with no
  error or log. Every announcement now names its engine: the new **TTS engine**
  option (Configure → Routing & timing), or automatically Home Assistant Cloud's
  (`tts.home_assistant_cloud`), else the first engine found. Legacy
  `tts.<platform>_say` services now target the speakers correctly too.
- **No more silent TTS failures.** When a rule wants to speak but no engine is
  available, a *"Spoken announcements have no voice engine"* repair appears.

## [v0.3.1] — 2026-07-16

### Fixed
- **YAML rules file shape is now forgiving (#47).** A rules file that wraps the
  list in its own `rules:` key (double nesting with
  `notification_center: rules: !include …`), or a pasted `export_rules`
  response (`count`/`rules`/`yaml`), is unwrapped automatically instead of
  loading as one junk rule. The panel's read-only list now shows only rules
  that actually validated (invalid ones are already covered by the
  `yaml_rules_invalid` repair issue), so it always matches what the engine
  loaded.

## [v0.3.0] — 2026-07-16

### Added
- **YAML-managed rules (#47).** Configure `notification_center: rules:`
  (typically an `!include` of a git-tracked file) and that file becomes the
  **sole source of truth**: nothing is stored in `.storage`, the panel becomes a
  read-only viewer with a banner, and `notification_center.reload` re-reads the
  file so edits apply without a restart. Invalid rules are skipped and surfaced
  as a repair issue; a file that fails to parse keeps the last-good rules.
- **`notification_center.export_rules`.** Returns every configured rule as data
  plus a ready-to-save YAML string — for backups, or to seed the YAML rules file
  when migrating from panel-managed rules.

## [v0.2.0] — 2026-07-12

### Added
- **Live Activities / Live Updates (#25).** A rule with `live_activity: true`
  delivers an iOS Live Activity / Android Live Update on the mobile channel — a
  persistent lock-screen / Dynamic Island item with a progress bar and/or a live
  countdown (`chronometer`), started on fire, updated silently in place, and
  ended when the condition resolves. A new `activity_timeout` auto-ends it after
  N minutes even if still active. Configurable in the rule editor's Delivery
  step; the card renders a matching progress bar.
- **Surface-aware tap targets (#45).** New `mobile_navigation_target` alongside
  `navigation_target`: a mobile push (and a card set to the `mobile` surface)
  opens the mobile path, while a wall-panel card and the Fully Kiosk Navigate
  channel open the wall path. Each falls back to the other. The card gained a
  `surface: wall | mobile` config option.

### Changed
- **Minimum Home Assistant is now 2026.7.0** (required by Live Activities).

## [v0.1.2] — 2026-07-12

### Added
- **Friendlier first-run options flow (#36).** Routing options are now a menu
  (Routing & timing / Presence-mapped people / Save & close). Presence-mapped
  people are configured with a person picker + a notify-service dropdown +
  optional media player instead of hand-written JSON; mobile targets remain a
  validated picker of the notify services that actually exist. Existing options
  load unchanged.

### Changed
- `hacs.json` minimum Home Assistant version corrected to `2026.2.0` — the
  version the test suite pins and validates (#31).

### Tests
- Engine-level presence-routing coverage for `per_person` and `all`, completing
  the routing test matrix alongside the existing `away_only` path (#20).

## [v0.1.1] — 2026-07-12

### Fixed
- **Card no longer shows a sticky "Configuration error" after a Home Assistant
  restart (#30).** `setConfig` now only stores config — it never throws and does
  no DOM work — so a card whose module hasn't loaded yet auto-recovers once it
  does, instead of painting a hard error that survives until a manual resource
  reload. Combined with serving the frontend assets early and cached (with `?v=`
  cache-busting on upgrades), the card renders on first dashboard load. Bumped
  `PANEL_VERSION` to `0.4.3`.
- **Mobile-push preview now matches the real push (#32).** The panel's
  "Phone push" preview showed the rule's icon/color in the notification header,
  implying the push icon could be styled per rule. It can't: iOS fixes the icon
  to the Home Assistant app icon at the OS level, and on Android we deliberately
  keep the recognizable HA logo. The preview now shows the HA logo, with a
  caption (plus README and code notes) clarifying that a rule's `icon`/`color`
  style the **card / wall** row, not the push.

## [v0.1.0] — 2026-07-12

Initial public release.

### Added
- Priority-based notification engine (critical / warning / info) with per-rule
  overrides.
- Multi-channel routing: mobile push · bell (persistent notification) · wall
  card · TTS announce · force-navigate (Fully Kiosk).
- Quiet hours (ignore / downgrade / suppress / batch), per-priority cooldown,
  daily digests, and deferred delivery.
- Actionable push (dismiss / snooze / custom-action buttons) routed back through
  the engine.
- The Notifications panel (5-step rule wizard with a live preview) and the
  `notification-center-card` Lovelace card.
- Restart persistence, repair issues for common misconfigurations, and cleared
  alert history.

[v0.5.1]: https://github.com/carmenvetere/notifications/releases/tag/v0.5.1
[v0.5.0]: https://github.com/carmenvetere/notifications/releases/tag/v0.5.0
[v0.4.1]: https://github.com/carmenvetere/notifications/releases/tag/v0.4.1
[v0.4.0]: https://github.com/carmenvetere/notifications/releases/tag/v0.4.0
[v0.3.2]: https://github.com/carmenvetere/notifications/releases/tag/v0.3.2
[v0.3.1]: https://github.com/carmenvetere/notifications/releases/tag/v0.3.1
[v0.3.0]: https://github.com/carmenvetere/notifications/releases/tag/v0.3.0
[v0.2.0]: https://github.com/carmenvetere/notifications/releases/tag/v0.2.0
[v0.1.2]: https://github.com/carmenvetere/notifications/releases/tag/v0.1.2
[v0.1.1]: https://github.com/carmenvetere/notifications/releases/tag/v0.1.1
[v0.1.0]: https://github.com/carmenvetere/notifications/releases/tag/v0.1.0
