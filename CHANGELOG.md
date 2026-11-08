# Changelog

All notable changes to **Notification Center** are recorded here. Entries are
aggregated toward the first stable **V1** release; each version is published as a
GitHub Release and installable through HACS. Dates are UTC.

The format loosely follows [Keep a Changelog](https://keepachangelog.com/), and
the project aims to follow [Semantic Versioning](https://semver.org/).

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

[v0.4.0]: https://github.com/carmenvetere/notifications/releases/tag/v0.4.0
[v0.3.2]: https://github.com/carmenvetere/notifications/releases/tag/v0.3.2
[v0.3.1]: https://github.com/carmenvetere/notifications/releases/tag/v0.3.1
[v0.3.0]: https://github.com/carmenvetere/notifications/releases/tag/v0.3.0
[v0.2.0]: https://github.com/carmenvetere/notifications/releases/tag/v0.2.0
[v0.1.2]: https://github.com/carmenvetere/notifications/releases/tag/v0.1.2
[v0.1.1]: https://github.com/carmenvetere/notifications/releases/tag/v0.1.1
[v0.1.0]: https://github.com/carmenvetere/notifications/releases/tag/v0.1.0
