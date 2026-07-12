# Changelog

All notable changes to **Notification Center** are recorded here. Entries are
aggregated toward the first stable **V1** release; each version is published as a
GitHub Release and installable through HACS. Dates are UTC.

The format loosely follows [Keep a Changelog](https://keepachangelog.com/), and
the project aims to follow [Semantic Versioning](https://semver.org/).

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

[v0.1.1]: https://github.com/carmenvetere/notifications/releases/tag/v0.1.1
[v0.1.0]: https://github.com/carmenvetere/notifications/releases/tag/v0.1.0
