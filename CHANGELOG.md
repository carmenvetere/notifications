# Changelog

All notable changes to **Notification Center** are recorded here. Entries are
aggregated toward the first stable **V1** release; each version is published as a
GitHub Release and installable through HACS. Dates are UTC.

The format loosely follows [Keep a Changelog](https://keepachangelog.com/), and
the project aims to follow [Semantic Versioning](https://semver.org/).

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

[v0.3.1]: https://github.com/carmenvetere/notifications/releases/tag/v0.3.1
[v0.3.0]: https://github.com/carmenvetere/notifications/releases/tag/v0.3.0
[v0.2.0]: https://github.com/carmenvetere/notifications/releases/tag/v0.2.0
[v0.1.2]: https://github.com/carmenvetere/notifications/releases/tag/v0.1.2
[v0.1.1]: https://github.com/carmenvetere/notifications/releases/tag/v0.1.1
[v0.1.0]: https://github.com/carmenvetere/notifications/releases/tag/v0.1.0
