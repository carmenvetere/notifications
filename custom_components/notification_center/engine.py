"""Runtime engine: listeners, debounce, active alerts, routing, escalation."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    TrackTemplate,
    async_call_later,
    async_track_state_change_event,
    async_track_template_result,
)
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store
from homeassistant.helpers.template import Template
from homeassistant.util import dt as dt_util, slugify

from .const import (
    CHANNEL_MOBILE,
    CLEAR_DISMISS,
    CONF_DEBOUNCE_MS,
    CONF_DIGEST_TIME,
    CONF_FULLY_KIOSK_DEVICES,
    CONF_MOBILE_TARGETS,
    CONF_PERSONS,
    CONF_QUIET_HOURS_END,
    CONF_QUIET_HOURS_START,
    CONF_TTS_DEFAULT_TARGETS,
    CONF_TTS_SERVICE,
    DEFAULT_DEBOUNCE_MS,
    DEFAULT_DIGEST_TIME,
    DEFAULT_QUIET_HOURS_END,
    DEFAULT_QUIET_HOURS_START,
    DATA_YAML_RULES,
    DEFAULT_TTS_SERVICE,
    DOMAIN,
    MANUAL_TAG_PREFIX,
    PRIORITY_COLORS,
    PRIORITY_ICONS,
    PRIORITY_INFO,
    PRIORITY_ORDER,
    SAVE_DELAY,
    SIGNAL_UPDATE,
    STORAGE_KEY,
    STORAGE_VERSION,
    SUBENTRY_TYPE_RULE,
)
from .quiet_hours import apply_quiet_hours, in_quiet_hours, next_time_after, parse_time
from .router import (
    Person,
    RouterConfig,
    build_live_activity_payload,
    parse_push_action,
    resolve_deliveries,
)
from .rule import Rule, render_items, render_text, template_error

_LOGGER = logging.getLogger(__name__)


HISTORY_LIMIT = 50


def _item_key(item: dict[str, Any]) -> str:
    """Stable key for a digest item (for per-item dismiss)."""
    return item.get("key") or item.get("name") or ""


def _to_int(value: Any) -> int | None:
    """Best-effort int from a rendered template string; None if not numeric."""
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _resolve_action(specs: list[dict[str, Any]], action) -> dict[str, Any] | None:
    """Find a custom-action spec by its stable ``id`` (legacy: list index).

    Matching by a stable id means reordering or deleting a rule's actions can't
    mis-map a live button. Older actions without an id fall back to their index,
    so ``str(action)`` still resolves them.
    """
    key = str(action)
    for i, spec in enumerate(specs):
        if str(spec.get("id") if spec.get("id") is not None else i) == key:
            return spec
    # Fallback: a single-action notification is unambiguous, so run it even if
    # the id doesn't line up (e.g. an older cached card sent a stale/NaN id).
    if len(specs) == 1:
        return specs[0]
    return None


class NotificationEngine:
    """Owns the active-alert state and all listeners for one config entry."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.rules: dict[str, Rule] = {}
        self.entity_to_rules: dict[str, set[str]] = {}
        # tag -> active alert dict
        self.active: dict[str, dict[str, Any]] = {}
        # tag -> datetime until which re-delivery is suppressed
        self._cooldown_until: dict[str, Any] = {}
        # tags the user dismissed; held hidden until the condition resolves
        self._suppressed_until_clear: set[str] = set()
        # tag -> datetime until which a snoozed alert stays hidden
        self._snooze_until: dict[str, Any] = {}
        # tag -> {"reason": batch|digest, "due": datetime} for deferred pushes
        self._held: dict[str, dict[str, Any]] = {}
        self._flush_cancel = None
        # tag -> set of dismissed digest-item keys
        self._dismissed_items: dict[str, set[str]] = {}
        # bounded log of cleared alerts (newest first)
        self._history: list[dict[str, Any]] = []
        # tag -> cancel callback for escalation timer
        self._escalation_cancels: dict[str, Any] = {}
        # tag -> cancel callback for a Live Activity auto-end (activity_timeout)
        self._activity_cancels: dict[str, Any] = {}

        self._unsub_state = None
        self._unsub_push_action = None
        self._template_info = None
        self._template_by_obj: dict[int, str] = {}

        self._dirty: set[str] = set()
        self._debounce_cancel = None

        self._store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY.format(entry.entry_id))

    # --- Lifecycle ----------------------------------------------------------
    async def async_setup(self) -> None:
        self._load_rules()
        # Restore persisted runtime state (active alerts, cooldown/snooze/
        # dismiss-until-resolve) before evaluating, so a restart doesn't drop the
        # tray or re-fire snoozed/dismissed alerts.
        await self._async_restore()
        self._register_listeners()
        # Evaluate everything once at startup so existing active states show.
        self._dirty = set(self.rules)
        await self._process_dirty(None)
        self._reschedule_escalations()
        self._schedule_flush()
        self._schedule_save()
        # Route taps on mobile push action buttons back to the alert.
        self._unsub_push_action = self.hass.bus.async_listen(
            "mobile_app_notification_action", self._handle_push_action
        )

    async def async_unload(self) -> None:
        self._teardown_listeners()
        if self._unsub_push_action:
            self._unsub_push_action()
            self._unsub_push_action = None
        for cancel in list(self._escalation_cancels.values()):
            cancel()
        self._escalation_cancels.clear()
        if self._debounce_cancel:
            self._debounce_cancel()
            self._debounce_cancel = None
        if self._flush_cancel:
            self._flush_cancel()
            self._flush_cancel = None
        # Flush state so a reload/restart restores the latest (delayed saves
        # otherwise only flush on HA final-write, which a reload skips).
        await self._store.async_save(self._data_to_store())

    async def _handle_push_action(self, event) -> None:
        """Handle a tap on a mobile_app notification action button."""
        parsed = parse_push_action(event.data.get("action", ""))
        if not parsed:
            return
        tag, verb, arg = parsed["tag"], parsed["verb"], parsed["arg"]
        if tag not in self.active:
            return  # not one of this engine's alerts
        if verb == "DISMISS":
            self.async_dismiss(tag)
        elif verb == "SNOOZE":
            try:
                minutes = int(arg)
            except (TypeError, ValueError):
                minutes = 60
            self.async_snooze(tag, minutes)
        elif verb == "RUN":
            # arg is the custom action's stable id (legacy: a numeric index).
            await self.async_run_action(tag, arg)

    async def async_reload(self) -> None:
        """Rebuild rules and listeners in place (live reload, no HA restart)."""
        self._teardown_listeners()
        self._load_rules()
        self._register_listeners()
        # Drop active alerts whose rule no longer exists.
        valid_tags = {r.tag for r in self.rules.values()}
        for tag in list(self.active):
            if not self.active[tag].get("manual") and tag not in valid_tags:
                self._cancel_escalation(tag)
                self.active.pop(tag, None)
        # Refresh the *display* of already-active alerts so rule edits (a new
        # custom-action button, a changed title/message/channels) show up
        # immediately without waiting for the alert to clear and re-fire.
        self._refresh_active_presentation()
        self._dirty = set(self.rules)
        await self._process_dirty(None)
        # _process_dirty only publishes when the active set changes; a pure
        # presentation refresh doesn't, so publish unconditionally here.
        self._publish()

    def _refresh_active_presentation(self) -> None:
        """Rebuild presentation fields of active rule-backed alerts from their
        (possibly edited) rule, preserving runtime state and never re-delivering.
        """
        by_tag = {rule.tag: rule for rule in self.rules.values()}
        for tag, alert in list(self.active.items()):
            if alert.get("manual"):
                continue
            rule = by_tag.get(tag)
            if rule is None:
                continue
            fresh = self._build_alert(rule)
            # Keep runtime fields; only the display should change on an edit.
            fresh["created_at"] = alert.get("created_at", fresh["created_at"])
            if "batched" in alert:
                fresh["batched"] = alert["batched"]
            self.active[tag] = fresh

    # --- Rule / listener registration ---------------------------------------
    @property
    def yaml_mode(self) -> bool:
        """True when rules come from YAML (`notification_center: rules:`) —
        the file is the sole source of truth and the panel is read-only."""
        return bool(self.hass.data.get(DATA_YAML_RULES))

    def _load_rules(self) -> None:
        self.rules.clear()
        self.entity_to_rules.clear()
        if self.yaml_mode:
            self._load_yaml_rules()
        else:
            for subentry_id, subentry in self.entry.subentries.items():
                if subentry.subentry_type != SUBENTRY_TYPE_RULE:
                    continue
                self._register_rule(subentry_id, dict(subentry.data))

    def _load_yaml_rules(self) -> None:
        """Build the rule set from the YAML file (sole source of truth, #47).

        Each rule is validated; invalid ones are skipped and surfaced as a
        repair issue so a typo never silently drops the whole file.
        """
        from .websocket_api import _sanitize, _validate_rule  # local: avoid cycle risk

        bad: list[str] = []
        for index, data in enumerate(self.hass.data.get(DATA_YAML_RULES) or []):
            name = str(data.get("name") or f"rule {index + 1}")
            try:
                validated = _validate_rule(_sanitize(dict(data)))
            except vol.Invalid as err:
                bad.append(f"{name}: {err}")
                continue
            tag = validated.get("dedup_tag") or slugify(name)
            self._register_rule(f"yaml_{tag}", validated)
        if bad:
            self._raise_issue(
                "yaml_rules_invalid",
                "yaml_rules_invalid",
                {"errors": "\n".join(f"- {line}" for line in bad)},
            )
        else:
            self._clear_issue("yaml_rules_invalid")

    def _register_rule(self, rule_id: str, data: dict[str, Any]) -> None:
        rule = Rule.from_subentry(rule_id, data)
        self.rules[rule_id] = rule
        for entity_id in rule.tracked_entities:
            self.entity_to_rules.setdefault(entity_id, set()).add(rule_id)
        self._check_rule_templates(rule)

    def _check_rule_templates(self, rule: Rule) -> None:
        """Raise/clear a repair issue for a rule's template syntax errors."""
        err = template_error(self.hass, rule.condition_template) or template_error(
            self.hass, rule.items_template
        )
        issue_id = f"template_{rule.tag}"
        if err:
            self._raise_issue(issue_id, "template_error", {"rule": rule.name, "error": err})
        else:
            self._clear_issue(issue_id)

    # --- Repair issues ------------------------------------------------------
    @callback
    def _raise_issue(self, issue_id: str, translation_key: str, placeholders: dict) -> None:
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=translation_key,
            translation_placeholders=placeholders,
        )

    @callback
    def _clear_issue(self, issue_id: str) -> None:
        ir.async_delete_issue(self.hass, DOMAIN, issue_id)

    def _register_listeners(self) -> None:
        entities = list(self.entity_to_rules)
        if entities:
            self._unsub_state = async_track_state_change_event(
                self.hass, entities, self._handle_state_event
            )

        track: list[TrackTemplate] = []
        self._template_by_obj = {}
        for rule in self.rules.values():
            if rule.is_template and rule.primary_template:
                # Skip templates with syntax errors (a repair issue is raised in
                # _load_rules) so one bad template can't break listener setup.
                if template_error(self.hass, rule.primary_template):
                    continue
                tpl = Template(rule.primary_template, self.hass)
                track.append(TrackTemplate(tpl, None))
                self._template_by_obj[id(tpl)] = rule.rule_id
        if track:
            self._template_info = async_track_template_result(
                self.hass, track, self._handle_template_event
            )

    def _teardown_listeners(self) -> None:
        if self._unsub_state:
            self._unsub_state()
            self._unsub_state = None
        if self._template_info:
            self._template_info.async_remove()
            self._template_info = None

    # --- Event handling (debounced) -----------------------------------------
    @callback
    def _handle_state_event(self, event: Event) -> None:
        entity_id = event.data.get("entity_id")
        self._mark_dirty(self.entity_to_rules.get(entity_id, set()))

    @callback
    def _handle_template_event(self, event, updates) -> None:
        dirty: set[str] = set()
        for update in updates:
            rule_id = self._template_by_obj.get(id(update.template))
            if rule_id:
                dirty.add(rule_id)
        self._mark_dirty(dirty)

    @callback
    def _mark_dirty(self, rule_ids: set[str]) -> None:
        if not rule_ids:
            return
        self._dirty |= set(rule_ids)
        if self._debounce_cancel:
            self._debounce_cancel()
        delay = self._debounce_ms() / 1000
        self._debounce_cancel = async_call_later(self.hass, delay, self._process_dirty)

    async def _process_dirty(self, _now) -> None:
        self._debounce_cancel = None
        dirty = self._dirty
        self._dirty = set()
        changed = False
        for rule_id in dirty:
            rule = self.rules.get(rule_id)
            if rule is None:
                continue
            if await self._evaluate_rule(rule):
                changed = True
        if changed:
            self._publish()

    # --- Core evaluation ----------------------------------------------------
    async def _evaluate_rule(self, rule: Rule) -> bool:
        """Evaluate one rule; route on inactive->active. Returns True if the
        active set changed."""
        active = rule.is_active(self.hass)
        tag = rule.tag
        existing = self.active.get(tag)

        if not active:
            # Condition resolved: lift any user dismiss/snooze holds.
            self._suppressed_until_clear.discard(tag)
            self._snooze_until.pop(tag, None)
            self._dismissed_items.pop(tag, None)
            if self._held.pop(tag, None):
                self._schedule_flush()
            if existing is not None and not existing.get("manual") and rule.auto_clear:
                self._cancel_escalation(tag)
                self._clear_bell(tag)
                self._end_live_activity(existing)
                self._record_history(existing, "resolved")
                self.active.pop(tag, None)
                return True
            return False

        if existing is None:
            # Honor a prior dismiss (sticky until resolve) or active snooze.
            if tag in self._suppressed_until_clear:
                return False
            snooze_until = self._snooze_until.get(tag)
            if snooze_until and dt_util.utcnow() < snooze_until:
                return False
            self._snooze_until.pop(tag, None)
            alert = self._build_alert(rule)
            self.active[tag] = alert
            await self._maybe_deliver(rule, alert)
            self._schedule_escalation(rule, tag)
            return True

        # Already active: keep it, but re-render its dynamic content so template
        # values stay live. Display-only for most channels; a Live Activity gets
        # a silent in-place update pushed to the phone.
        changed = self._refresh_alert_content(rule, existing)
        if changed and existing.get("live_activity"):
            await self._deliver_live_activity(existing)
        return changed

    def _refresh_alert_content(self, rule: Rule, alert: dict[str, Any]) -> bool:
        """Re-render an active alert's templated title/message/items (and Live
        Activity progress/timer) from its rule. Returns True if anything visible
        changed (so callers publish / push a Live Activity update)."""
        if alert.get("manual"):
            return False
        fresh = {
            "title": render_text(self.hass, rule.title_template, rule.name),
            "message": render_text(self.hass, rule.message_template, ""),
            "items": render_items(self.hass, rule.items_template),
            **self._activity_fields(rule),
        }
        if all(alert.get(k) == v for k, v in fresh.items()):
            return False
        alert.update(fresh)
        return True

    def _activity_fields(self, rule: Rule) -> dict[str, Any]:
        """Render the Live Activity progress/timer fields for a rule."""
        if not rule.live_activity:
            return {}
        return {
            "progress": _to_int(render_text(self.hass, rule.progress_template, "")),
            "progress_max": _to_int(
                render_text(self.hass, rule.progress_max_template, "")
            ),
            "critical_text": render_text(self.hass, rule.critical_text_template, "")
            or None,
            "chronometer": rule.chronometer,
            "when": _to_int(render_text(self.hass, rule.when_template, "")),
        }

    def _build_alert(self, rule: Rule) -> dict[str, Any]:
        title = render_text(self.hass, rule.title_template, rule.name)
        message = render_text(self.hass, rule.message_template, "")
        alert = {
            "tag": rule.tag,
            "rule_id": rule.rule_id,
            "name": rule.name,
            "title": title,
            "message": message,
            "priority": rule.priority,
            "icon": rule.effective_icon,
            "color": rule.effective_color,
            "channels": list(rule.channels),
            "navigation_target": rule.navigation_target,
            "mobile_navigation_target": rule.mobile_navigation_target,
            "digest_group": rule.digest_group,
            "digest": rule.deliver_as_digest,
            "items": render_items(self.hass, rule.items_template),
            "created_at": dt_util.utcnow().isoformat(),
            "actions": rule.allowed_actions,
            "buttons": rule.custom_action_buttons,
            "_actions": list(rule.custom_actions),
            "manual": False,
            "live_activity": rule.live_activity,
        }
        alert.update(self._activity_fields(rule))
        return alert

    async def _maybe_deliver(self, rule: Rule, alert: dict[str, Any]) -> None:
        """Apply cooldown + quiet hours, then route the alert."""
        now = dt_util.utcnow()
        tag = alert["tag"]
        suppress = False

        cooldown_until = self._cooldown_until.get(tag)
        if cooldown_until and now < cooldown_until:
            # Within cooldown: alert still shown, but don't re-notify.
            suppress = True

        # Quiet hours.
        local_now = dt_util.now().time()
        is_quiet = in_quiet_hours(local_now, *self._quiet_window())
        priority, qh_suppress, qh_batch = apply_quiet_hours(
            rule.priority, rule.quiet_hours_behavior, is_quiet
        )
        alert["priority"] = priority
        alert["icon"] = rule.icon or PRIORITY_ICONS.get(priority, alert["icon"])
        alert["color"] = rule.color or PRIORITY_COLORS.get(priority, alert["color"])

        # Deferred delivery: quiet-hours "batch" holds until the window ends;
        # digest-delivery holds until the daily digest time. Either way the alert
        # shows in the tray now (bell/wall) but the push is held for the flush.
        hold_reason = None
        if qh_batch:
            hold_reason = "batch"
        elif rule.deliver_as_digest:
            hold_reason = "digest"
        if hold_reason:
            alert["batched"] = True
            self._hold(tag, hold_reason)

        # Diagnostic: a rule wants a mobile push but no notify targets are
        # configured -> the push silently no-ops. Surface it as a repair so
        # "app notifications aren't working" is visible in Settings → Repairs.
        if CHANNEL_MOBILE in alert["channels"]:
            if self._mobile_target_services():
                self._clear_issue("no_mobile_targets")
            else:
                self._raise_issue("no_mobile_targets", "no_mobile_targets", {})

        suppress = suppress or qh_suppress or hold_reason is not None
        await self._route(rule, alert, suppress_push=suppress)

        # Start the Live Activity (the normal mobile push is skipped for it) and
        # arm its optional auto-end timer.
        if not suppress and alert.get("live_activity") and CHANNEL_MOBILE in alert["channels"]:
            await self._deliver_live_activity(alert)
            self._schedule_activity_timeout(rule, tag)

        cooldown = rule.effective_cooldown
        if cooldown:
            self._cooldown_until[tag] = now + timedelta(minutes=cooldown)

    async def _route(
        self, rule: Rule, alert: dict[str, Any], *, suppress_push: bool
    ) -> None:
        actions = resolve_deliveries(
            alert=alert,
            channels=alert["channels"],
            priority=alert["priority"],
            presence_routing=rule.presence_routing,
            tts_targets=rule.tts_targets,
            config=self._router_config(),
            presence=self._presence(),
            suppress_push=suppress_push,
            tts_message=rule.effective_tts_message,
        )
        await self._execute(actions)

    async def _execute(self, actions) -> None:
        for action in actions:
            service = f"{action.domain}.{action.service}"
            issue_id = f"delivery_{service}"
            try:
                await self.hass.services.async_call(
                    action.domain, action.service, action.data, blocking=False
                )
                self._clear_issue(issue_id)
            except Exception as err:  # noqa: BLE001 - never let one delivery break others
                _LOGGER.exception(
                    "notification_center: failed delivering %s", service
                )
                self._raise_issue(
                    issue_id, "delivery_failed", {"service": service, "error": str(err)}
                )

    # --- Escalation ---------------------------------------------------------
    def _schedule_escalation(self, rule: Rule, tag: str) -> None:
        try:
            minutes = int(rule.escalation_after)
        except (TypeError, ValueError):
            return
        if minutes <= 0:
            return
        delay = minutes * 60

        async def _escalate(_now):
            alert = self.active.get(tag)
            if alert is None:
                self._escalation_cancels.pop(tag, None)
                return
            await self._route(rule, alert, suppress_push=False)
            self._escalation_cancels[tag] = async_call_later(
                self.hass, delay, _escalate
            )

        self._escalation_cancels[tag] = async_call_later(self.hass, delay, _escalate)

    def _cancel_escalation(self, tag: str) -> None:
        cancel = self._escalation_cancels.pop(tag, None)
        if cancel:
            cancel()

    # --- Deferred delivery (quiet-hours batch / digest) ---------------------
    def _digest_time(self):
        return parse_time(self._options().get(CONF_DIGEST_TIME, DEFAULT_DIGEST_TIME))

    def _hold(self, tag: str, reason: str) -> None:
        now = dt_util.now()
        if reason == "batch":
            due = next_time_after(now, self._quiet_window()[1])
        else:  # digest
            due = next_time_after(now, self._digest_time())
        self._held[tag] = {"reason": reason, "due": due.isoformat()}
        self._schedule_flush()

    def _schedule_flush(self) -> None:
        if self._flush_cancel:
            self._flush_cancel()
            self._flush_cancel = None
        if not self._held:
            return
        now = dt_util.now()
        dues = [
            d
            for it in self._held.values()
            if (d := dt_util.parse_datetime(it["due"])) is not None
        ]
        if not dues:
            return
        delay = max(1.0, (min(dues) - now).total_seconds())
        self._flush_cancel = async_call_later(self.hass, delay, self._flush)

    async def _flush(self, _now) -> None:
        self._flush_cancel = None
        now = dt_util.now()
        due_tags = [
            tag
            for tag, it in self._held.items()
            if (d := dt_util.parse_datetime(it["due"])) is not None and d <= now
        ]
        for tag in due_tags:
            self._held.pop(tag, None)
        alerts = [self.active[t] for t in due_tags if t in self.active]
        if alerts:
            await self._deliver_batch(alerts)
        self._schedule_flush()
        if due_tags:
            self._schedule_save()

    async def _deliver_batch(self, alerts: list[dict[str, Any]]) -> None:
        """Send a single grouped push for the held (batched/digest) alerts."""
        services = self._mobile_target_services()
        if not services:
            return
        if len(alerts) == 1:
            title = alerts[0].get("title") or alerts[0].get("name") or "Notification"
            message = alerts[0].get("message") or ""
        else:
            title = f"{len(alerts)} notifications"
            message = ", ".join(
                a.get("title") or a.get("name") or "" for a in alerts
            )
        for service in services:
            domain, _, name = service.partition(".")
            try:
                await self.hass.services.async_call(
                    domain or "notify",
                    name or service,
                    {"title": title, "message": message},
                    blocking=False,
                )
            except Exception:  # noqa: BLE001
                _LOGGER.exception(
                    "notification_center: batch delivery via %s failed", service
                )

    def _mobile_target_services(self) -> list[str]:
        cfg = self._router_config()
        if cfg.persons:
            return [p.notify_service for p in cfg.persons if p.notify_service]
        return list(cfg.mobile_targets)

    # --- Live Activity lifecycle --------------------------------------------
    async def _deliver_live_activity(self, alert: dict[str, Any]) -> None:
        """Start or update a Live Activity on every mobile target. Start and
        update use the same payload — re-sending the same tag updates in place."""
        services = self._mobile_target_services()
        if not services:
            return
        payload = build_live_activity_payload(alert)
        for service in services:
            domain, _, name = service.partition(".")
            await self.hass.services.async_call(
                domain or "notify", name or service, payload, blocking=False
            )
        alert["_activity_started"] = True

    @callback
    def _end_live_activity(self, alert: dict[str, Any]) -> None:
        """End a Live Activity (clear_notification). Safe from sync clear paths —
        the notify calls are scheduled fire-and-forget."""
        tag = alert.get("tag")
        cancel = self._activity_cancels.pop(tag, None)
        if cancel:
            cancel()
        if not alert.get("live_activity"):
            return
        services = self._mobile_target_services()
        if not services:
            return
        payload = build_live_activity_payload(alert, ending=True)
        for service in services:
            domain, _, name = service.partition(".")
            self.hass.async_create_task(
                self.hass.services.async_call(
                    domain or "notify", name or service, payload, blocking=False
                )
            )

    def _schedule_activity_timeout(self, rule: Rule, tag: str) -> None:
        """Auto-end a Live Activity after activity_timeout minutes, even if the
        condition is still active (Apple also hard-caps activities at ~8h)."""
        try:
            minutes = int(rule.activity_timeout)
        except (TypeError, ValueError):
            return
        if minutes <= 0:
            return

        @callback
        def _expire(_now):
            self._activity_cancels.pop(tag, None)
            alert = self.active.get(tag)
            if alert is not None and alert.get("live_activity"):
                self._end_live_activity(alert)

        self._activity_cancels[tag] = async_call_later(
            self.hass, minutes * 60, _expire
        )

    async def async_test_push(self) -> None:
        """Send a test push to every configured mobile target, right now.

        Bypasses rules, quiet hours and cooldown so the user can verify their
        app-notification wiring end-to-end. If nothing is configured, raise the
        same repair issue a live mobile rule would, and log why.
        """
        services = self._mobile_target_services()
        if not services:
            self._raise_issue("no_mobile_targets", "no_mobile_targets", {})
            _LOGGER.warning(
                "notification_center: test_push found no mobile targets — set "
                "'Mobile notify services' (or presence-mapped people) in Options"
            )
            return
        self._clear_issue("no_mobile_targets")
        for service in services:
            domain, _, name = service.partition(".")
            await self.hass.services.async_call(
                domain or "notify",
                name or service,
                {
                    "title": "Notification Center",
                    "message": "✅ Test notification — your app notifications are working.",
                    "data": {"tag": "nc_test", "group": "notification_center"},
                },
                blocking=False,
            )

    # --- Public service operations ------------------------------------------
    async def async_send_manual(self, data: dict[str, Any]) -> None:
        """Create a one-off alert not backed by a rule."""
        priority = data.get("priority", PRIORITY_INFO)
        tag = data.get("tag") or f"{MANUAL_TAG_PREFIX}_{dt_util.utcnow().timestamp()}"
        channels = data.get("channels") or []
        alert = {
            "tag": tag,
            "rule_id": None,
            "name": data.get("title", tag),
            "title": data.get("title", "Notification"),
            "message": data.get("message", ""),
            "priority": priority,
            "icon": data.get("icon") or PRIORITY_ICONS.get(priority, "mdi:bell"),
            "color": data.get("color") or PRIORITY_COLORS.get(priority, "#7295B2"),
            "channels": channels,
            "navigation_target": data.get("navigation_target"),
            "mobile_navigation_target": data.get("mobile_navigation_target"),
            "digest_group": data.get("digest_group"),
            "digest": bool(data.get("digest", False)),
            "items": data.get("items", []),
            "created_at": dt_util.utcnow().isoformat(),
            "actions": data.get("actions", [CLEAR_DISMISS]),
            "buttons": [
                {
                    "id": i,
                    "label": a.get("label") or "Run",
                    "icon": a.get("icon"),
                    "confirm": a.get("confirm"),
                }
                for i, a in enumerate(data.get("custom_actions", []))
                if isinstance(a, dict)
            ],
            "_actions": list(data.get("custom_actions", [])),
            "manual": True,
        }
        self.active[tag] = alert
        actions = resolve_deliveries(
            alert=alert,
            channels=channels,
            priority=priority,
            presence_routing=data.get("presence_routing", "all"),
            tts_targets=data.get("tts_targets", []),
            config=self._router_config(),
            presence=self._presence(),
            suppress_push=False,
            tts_message=data.get("tts_message"),
        )
        await self._execute(actions)
        self._publish()

    def _action_allowed(self, tag: str, action: str) -> bool:
        """Whether an action is permitted for an alert's clearing model."""
        alert = self.active.get(tag)
        if alert is None:
            return False
        rule_id = alert.get("rule_id")
        if rule_id is None:  # manual alert: allow what its payload offers
            return action in alert.get("actions", [])
        rule = self.rules.get(rule_id)
        if rule is None:  # rule deleted: permit cleanup
            return True
        if action == "dismiss":
            return rule.effective_clear_mode == CLEAR_DISMISS
        if action == "snooze":
            return rule.snooze_allowed
        return False

    @callback
    def async_dismiss(self, tag: str) -> None:
        if not self._action_allowed(tag, "dismiss"):
            _LOGGER.warning(
                "notification_center: dismiss not permitted for '%s'", tag
            )
            return
        alert = self.active[tag]
        is_rule_backed = alert.get("rule_id") is not None
        self._cancel_escalation(tag)
        self._clear_bell(tag)
        self._end_live_activity(alert)
        self._record_history(alert, "dismissed")
        self.active.pop(tag, None)
        self._held.pop(tag, None)
        self._dismissed_items.pop(tag, None)
        # Rule-backed alerts stay hidden until their condition resolves;
        # manual alerts are simply gone.
        if is_rule_backed:
            self._suppressed_until_clear.add(tag)
        self._publish()

    @callback
    def async_snooze(self, tag: str, minutes: int) -> None:
        if not self._action_allowed(tag, "snooze"):
            _LOGGER.warning(
                "notification_center: snooze not permitted for '%s'", tag
            )
            return
        self._cancel_escalation(tag)
        self._clear_bell(tag)
        self._end_live_activity(self.active[tag])
        self._record_history(self.active[tag], "snoozed")
        self.active.pop(tag, None)
        self._held.pop(tag, None)
        self._dismissed_items.pop(tag, None)
        self._snooze_until[tag] = dt_util.utcnow() + timedelta(minutes=minutes)
        self._cooldown_until[tag] = self._snooze_until[tag]
        self._publish()

    async def async_run_action(self, tag: str, action) -> None:
        """Run a rule-defined custom action (e.g. "I did the chore" → reset).

        Calls the action's service, then clears the alert unless
        ``clear_on_run`` is false. Allowed regardless of clear mode — it's an
        explicit, confirmed user action.
        """
        alert = self.active.get(tag)
        if alert is None:
            return
        specs = alert.get("_actions") or []
        spec = _resolve_action(specs, action)
        if spec is None:
            _LOGGER.warning("notification_center: unknown action '%s' for '%s'", action, tag)
            return

        service = spec.get("service") or spec.get("perform_action")
        ran_ok = True
        if service and "." in service:
            domain, _, name = service.partition(".")
            issue_id = f"action_{domain}.{name}"
            try:
                # blocking so a missing/failing service (e.g. a script that
                # doesn't exist) surfaces here instead of silently no-op'ing.
                await self.hass.services.async_call(
                    domain,
                    name,
                    dict(spec.get("data") or {}),
                    blocking=True,
                    target=spec.get("target") or None,
                )
                self._clear_issue(issue_id)
            except Exception as err:  # noqa: BLE001 - report, don't crash the engine
                ran_ok = False
                _LOGGER.exception(
                    "notification_center: action service %s failed", service
                )
                self._raise_issue(
                    issue_id, "action_failed", {"service": service, "error": str(err)}
                )

        # Only clear the alert if the action actually ran — otherwise a broken
        # script would make the notification vanish while doing nothing.
        if ran_ok and spec.get("clear_on_run", True):
            is_rule_backed = alert.get("rule_id") is not None
            self._cancel_escalation(tag)
            self._clear_bell(tag)
            self._end_live_activity(alert)
            self._record_history(alert, "action")
            self.active.pop(tag, None)
            self._held.pop(tag, None)
            self._dismissed_items.pop(tag, None)
            if is_rule_backed:
                self._suppressed_until_clear.add(tag)
        self._publish()

    def _clear_bell(self, tag: str) -> None:
        # persistent_notification is optional (after_dependencies); skip if absent.
        if not self.hass.services.has_service("persistent_notification", "dismiss"):
            return
        self.hass.async_create_task(
            self.hass.services.async_call(
                "persistent_notification",
                "dismiss",
                {"notification_id": tag},
                blocking=False,
            )
        )

    # --- Publishing ---------------------------------------------------------
    @callback
    def _publish(self) -> None:
        async_dispatcher_send(self.hass, SIGNAL_UPDATE.format(self.entry.entry_id))
        self._schedule_save()

    # --- Persistence --------------------------------------------------------
    @callback
    def _schedule_save(self) -> None:
        self._store.async_delay_save(self._data_to_store, SAVE_DELAY)

    @callback
    def _data_to_store(self) -> dict[str, Any]:
        return {
            "active": self.active,
            "cooldown_until": {
                tag: dt.isoformat() for tag, dt in self._cooldown_until.items()
            },
            "snooze_until": {
                tag: dt.isoformat() for tag, dt in self._snooze_until.items()
            },
            "suppressed_until_clear": sorted(self._suppressed_until_clear),
            "held": self._held,
            "dismissed_items": {
                tag: sorted(keys) for tag, keys in self._dismissed_items.items()
            },
            "history": self._history,
        }

    async def _async_restore(self) -> None:
        """Load persisted state, reconciling against the current rule set."""
        data = await self._store.async_load()
        if not data:
            return
        for tag, alert in (data.get("active") or {}).items():
            # Keep manual alerts and rule-backed alerts whose rule still exists.
            if alert.get("manual") or alert.get("rule_id") in self.rules:
                self.active[tag] = alert
        for tag, raw in (data.get("cooldown_until") or {}).items():
            parsed = dt_util.parse_datetime(raw)
            if parsed:
                self._cooldown_until[tag] = parsed
        for tag, raw in (data.get("snooze_until") or {}).items():
            parsed = dt_util.parse_datetime(raw)
            if parsed:
                self._snooze_until[tag] = parsed
        self._suppressed_until_clear = set(data.get("suppressed_until_clear") or [])
        # Keep only held entries whose alert is still active.
        self._held = {
            tag: it
            for tag, it in (data.get("held") or {}).items()
            if tag in self.active
        }
        self._dismissed_items = {
            tag: set(keys)
            for tag, keys in (data.get("dismissed_items") or {}).items()
            if tag in self.active
        }
        self._history = (data.get("history") or [])[:HISTORY_LIMIT]

    @callback
    def _reschedule_escalations(self) -> None:
        """Re-arm escalation timers for alerts still active after a restart."""
        for tag, alert in self.active.items():
            rule = self.rules.get(alert.get("rule_id"))
            if rule and rule.escalation_after and tag not in self._escalation_cancels:
                self._schedule_escalation(rule, tag)

    # --- Derived views used by sensors --------------------------------------
    def alert_list(self) -> list[dict[str, Any]]:
        now = dt_util.utcnow()
        result = []
        for alert in self.active.values():
            # Drop private keys (manual flag, stored action specs).
            item = {k: v for k, v in alert.items() if not k.startswith("_")}
            item.pop("manual", None)
            created = dt_util.parse_datetime(alert["created_at"])
            item["age_min"] = (
                int((now - created).total_seconds() // 60) if created else 0
            )
            if item.get("items"):
                item["items"] = self._visible_items(alert["tag"], item["items"])
            result.append(item)
        result.sort(
            key=lambda a: (
                -PRIORITY_ORDER.get(a["priority"], 0),
                a.get("created_at", ""),
            )
        )
        return result

    def _visible_items(self, tag: str, items: list) -> list:
        dismissed = self._dismissed_items.get(tag)
        if not dismissed:
            return items
        return [it for it in items if _item_key(it) not in dismissed]

    @callback
    def async_dismiss_item(self, tag: str, key: str) -> None:
        """Hide a single item within a digest alert."""
        if tag not in self.active:
            return
        self._dismissed_items.setdefault(tag, set()).add(key)
        self._publish()

    def _record_history(self, alert: dict[str, Any], reason: str) -> None:
        """Append a cleared alert to the bounded history log (newest first)."""
        self._history.insert(
            0,
            {
                "tag": alert.get("tag"),
                "name": alert.get("name"),
                "title": alert.get("title"),
                "priority": alert.get("priority"),
                "created_at": alert.get("created_at"),
                "cleared_at": dt_util.utcnow().isoformat(),
                "reason": reason,
            },
        )
        del self._history[HISTORY_LIMIT:]

    def history(self) -> list[dict[str, Any]]:
        return list(self._history)

    def count(self) -> int:
        return len(self.active)

    def highest_priority(self) -> str:
        if not self.active:
            return "none"
        return max(
            (a["priority"] for a in self.active.values()),
            key=lambda p: PRIORITY_ORDER.get(p, 0),
        )

    def by_priority(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for alert in self.active.values():
            counts[alert["priority"]] = counts.get(alert["priority"], 0) + 1
        return counts

    # --- Config helpers -----------------------------------------------------
    def _options(self) -> dict[str, Any]:
        return {**self.entry.data, **self.entry.options}

    def _debounce_ms(self) -> int:
        return int(self._options().get(CONF_DEBOUNCE_MS, DEFAULT_DEBOUNCE_MS))

    def _quiet_window(self):
        opts = self._options()
        start = parse_time(opts.get(CONF_QUIET_HOURS_START, DEFAULT_QUIET_HOURS_START))
        end = parse_time(opts.get(CONF_QUIET_HOURS_END, DEFAULT_QUIET_HOURS_END))
        return start, end

    def _router_config(self) -> RouterConfig:
        opts = self._options()
        persons = [
            Person(
                person_entity=p.get("person"),
                notify_service=p.get("notify"),
                media_player=p.get("media_player"),
            )
            for p in opts.get(CONF_PERSONS, [])
            if p.get("notify")
        ]
        return RouterConfig(
            persons=persons,
            mobile_targets=opts.get(CONF_MOBILE_TARGETS, []),
            tts_service=opts.get(CONF_TTS_SERVICE, DEFAULT_TTS_SERVICE),
            tts_default_targets=opts.get(CONF_TTS_DEFAULT_TARGETS, []),
            fully_kiosk_devices=opts.get(CONF_FULLY_KIOSK_DEVICES, []),
        )

    def _presence(self) -> dict[str, str]:
        presence: dict[str, str] = {}
        for person in self._router_config().persons:
            if person.person_entity:
                state = self.hass.states.get(person.person_entity)
                presence[person.person_entity] = state.state if state else "unknown"
        return presence
