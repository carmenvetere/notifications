"""Runtime engine: listeners, debounce, active alerts, routing, escalation."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    TrackTemplate,
    async_call_later,
    async_track_state_change_event,
    async_track_template_result,
)
from homeassistant.helpers.storage import Store
from homeassistant.helpers.template import Template
from homeassistant.util import dt as dt_util

from .const import (
    CLEAR_DISMISS,
    CONF_DEBOUNCE_MS,
    CONF_FULLY_KIOSK_DEVICES,
    CONF_MOBILE_TARGETS,
    CONF_PERSONS,
    CONF_QUIET_HOURS_END,
    CONF_QUIET_HOURS_START,
    CONF_TTS_DEFAULT_TARGETS,
    CONF_TTS_SERVICE,
    DEFAULT_DEBOUNCE_MS,
    DEFAULT_QUIET_HOURS_END,
    DEFAULT_QUIET_HOURS_START,
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
from .quiet_hours import apply_quiet_hours, in_quiet_hours, parse_time
from .router import Person, RouterConfig, resolve_deliveries
from .rule import Rule, render_items, render_text

_LOGGER = logging.getLogger(__name__)


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
        # tag -> cancel callback for escalation timer
        self._escalation_cancels: dict[str, Any] = {}

        self._unsub_state = None
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
        self._schedule_save()

    async def async_unload(self) -> None:
        self._teardown_listeners()
        for cancel in list(self._escalation_cancels.values()):
            cancel()
        self._escalation_cancels.clear()
        if self._debounce_cancel:
            self._debounce_cancel()
            self._debounce_cancel = None
        # Flush state so a reload/restart restores the latest (delayed saves
        # otherwise only flush on HA final-write, which a reload skips).
        await self._store.async_save(self._data_to_store())

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
        self._dirty = set(self.rules)
        await self._process_dirty(None)

    # --- Rule / listener registration ---------------------------------------
    def _load_rules(self) -> None:
        self.rules.clear()
        self.entity_to_rules.clear()
        for subentry_id, subentry in self.entry.subentries.items():
            if subentry.subentry_type != SUBENTRY_TYPE_RULE:
                continue
            rule = Rule.from_subentry(subentry_id, dict(subentry.data))
            self.rules[subentry_id] = rule
            for entity_id in rule.tracked_entities:
                self.entity_to_rules.setdefault(entity_id, set()).add(subentry_id)

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
            if existing is not None and not existing.get("manual") and rule.auto_clear:
                self._cancel_escalation(tag)
                self._clear_bell(tag)
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

        return False

    def _build_alert(self, rule: Rule) -> dict[str, Any]:
        title = render_text(self.hass, rule.title_template, rule.name)
        message = render_text(self.hass, rule.message_template, "")
        return {
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
            "digest_group": rule.digest_group,
            "digest": rule.deliver_as_digest,
            "items": render_items(self.hass, rule.items_template),
            "created_at": dt_util.utcnow().isoformat(),
            "actions": rule.allowed_actions,
            "buttons": rule.custom_action_buttons,
            "_actions": list(rule.custom_actions),
            "manual": False,
        }

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
        if qh_batch:
            alert["batched"] = True
        suppress = suppress or qh_suppress or qh_batch

        await self._route(rule, alert, suppress_push=suppress)

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
            try:
                await self.hass.services.async_call(
                    action.domain, action.service, action.data, blocking=False
                )
            except Exception:  # noqa: BLE001 - never let one delivery break others
                _LOGGER.exception(
                    "notification_center: failed delivering %s.%s",
                    action.domain,
                    action.service,
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
        is_rule_backed = self.active[tag].get("rule_id") is not None
        self._cancel_escalation(tag)
        self._clear_bell(tag)
        self.active.pop(tag, None)
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
        self.active.pop(tag, None)
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
        try:
            spec = specs[int(action)]
        except (TypeError, ValueError, IndexError):
            _LOGGER.warning("notification_center: unknown action '%s' for '%s'", action, tag)
            return

        service = spec.get("service") or spec.get("perform_action")
        if service and "." in service:
            domain, _, name = service.partition(".")
            try:
                await self.hass.services.async_call(
                    domain,
                    name,
                    dict(spec.get("data") or {}),
                    blocking=False,
                    target=spec.get("target") or None,
                )
            except Exception:  # noqa: BLE001 - report, don't crash the engine
                _LOGGER.exception(
                    "notification_center: action service %s failed", service
                )

        if spec.get("clear_on_run", True):
            is_rule_backed = alert.get("rule_id") is not None
            self._cancel_escalation(tag)
            self._clear_bell(tag)
            self.active.pop(tag, None)
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
            result.append(item)
        result.sort(
            key=lambda a: (
                -PRIORITY_ORDER.get(a["priority"], 0),
                a.get("created_at", ""),
            )
        )
        return result

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
