"""Channel routing decisions.

Pure, dependency-free logic: given an alert, the rule's routing settings, the
parent configuration and current presence, decide which HA service calls to
make. Delivery (actually calling the services) happens in the engine. Keeping
the decision here makes it straightforward to unit-test.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .const import (
    CHANNEL_BELL,
    CHANNEL_MOBILE,
    CHANNEL_NAVIGATE,
    CHANNEL_TTS,
    PRESENCE_ALL,
    PRESENCE_AWAY_ONLY,
    PRESENCE_PER_PERSON,
    PRIORITY_INTERRUPTION_LEVEL,
)


@dataclass
class Person:
    """A push target tied to a presence entity."""

    person_entity: str | None
    notify_service: str  # e.g. "notify.mobile_app_carmen"
    media_player: str | None = None


@dataclass
class RouterConfig:
    """Parent-level routing configuration."""

    persons: list[Person] = field(default_factory=list)
    # Fallback list of notify services when no presence-mapped persons exist.
    mobile_targets: list[str] = field(default_factory=list)
    tts_service: str = "tts.speak"
    tts_default_targets: list[str] = field(default_factory=list)
    fully_kiosk_devices: list[str] = field(default_factory=list)


@dataclass
class DeliveryAction:
    """A single resolved HA service call."""

    domain: str
    service: str
    data: dict[str, Any]


def _person_is_home(person_entity: str | None, presence: dict[str, str]) -> bool:
    if not person_entity:
        return False
    return presence.get(person_entity, "not_home") == "home"


def _interruption_level(priority: str) -> str:
    return PRIORITY_INTERRUPTION_LEVEL.get(priority, "active")


def resolve_deliveries(
    *,
    alert: dict[str, Any],
    channels: list[str],
    priority: str,
    presence_routing: str,
    tts_targets: list[str],
    config: RouterConfig,
    presence: dict[str, str] | None = None,
    suppress_push: bool = False,
    tts_message: str | None = None,
) -> list[DeliveryAction]:
    """Resolve an alert into a list of service calls to make."""
    presence = presence or {}
    actions: list[DeliveryAction] = []
    tag = alert.get("tag")
    title = alert.get("title") or alert.get("name") or "Notification"
    message = alert.get("message") or ""

    # --- Mobile push --------------------------------------------------------
    if CHANNEL_MOBILE in channels and not suppress_push:
        level = _interruption_level(priority)
        push_data: dict[str, Any] = {
            "push": {"interruption-level": level},
        }
        if level == "critical":
            # iOS critical alerts bypass Do-Not-Disturb / ringer.
            push_data["push"] = {"sound": {"name": "default", "critical": 1, "volume": 1.0}}
        if alert.get("navigation_target"):
            push_data["url"] = alert["navigation_target"]
        push_data["tag"] = tag
        push_data["group"] = alert.get("digest_group") or priority

        targets = _mobile_targets(presence_routing, config, presence)
        for service in targets:
            domain, _, name = service.partition(".")
            actions.append(
                DeliveryAction(
                    domain=domain or "notify",
                    service=name or service,
                    data={"title": title, "message": message, "data": push_data},
                )
            )

    # --- Bell (persistent_notification) -------------------------------------
    if CHANNEL_BELL in channels:
        actions.append(
            DeliveryAction(
                domain="persistent_notification",
                service="create",
                data={
                    "notification_id": tag,
                    "title": title,
                    "message": message,
                },
            )
        )

    # --- TTS ----------------------------------------------------------------
    if CHANNEL_TTS in channels and not suppress_push:
        media_targets = tts_targets or config.tts_default_targets
        if media_targets:
            domain, _, name = config.tts_service.partition(".")
            spoken = tts_message or (f"{title}. {message}" if message else title)
            actions.append(
                DeliveryAction(
                    domain=domain or "tts",
                    service=name or "speak",
                    data={
                        "media_player_entity_id": media_targets,
                        "message": spoken,
                    },
                )
            )

    # --- Force navigate (Fully Kiosk) ---------------------------------------
    if CHANNEL_NAVIGATE in channels and alert.get("navigation_target"):
        for device_id in config.fully_kiosk_devices:
            actions.append(
                DeliveryAction(
                    domain="fully_kiosk",
                    service="load_url",
                    data={
                        "device_id": device_id,
                        "url": alert["navigation_target"],
                    },
                )
            )

    # Note: CHANNEL_WALL is rendered from the sensor attribute; no call needed.
    return actions


def _mobile_targets(
    presence_routing: str,
    config: RouterConfig,
    presence: dict[str, str],
) -> list[str]:
    """Pick which notify services to call given the presence routing mode."""
    if config.persons:
        if presence_routing == PRESENCE_AWAY_ONLY:
            targets = [
                p.notify_service
                for p in config.persons
                if not _person_is_home(p.person_entity, presence)
            ]
            # If everyone is home, fall back to notifying all so nothing is lost.
            if not targets:
                return [p.notify_service for p in config.persons]
            return targets
        # PRESENCE_ALL and PRESENCE_PER_PERSON both currently notify everyone;
        # per-person filtering is reserved for future per-rule target lists.
        return [p.notify_service for p in config.persons]

    return list(config.mobile_targets)
