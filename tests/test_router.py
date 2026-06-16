"""Unit tests for channel routing resolution."""

import unittest

from tests.conftest_path import ROOT  # noqa: F401

from custom_components.notification_center.const import (
    CHANNEL_BELL,
    CHANNEL_MOBILE,
    CHANNEL_NAVIGATE,
    CHANNEL_TTS,
    CHANNEL_WALL,
    PRIORITY_CRITICAL,
    PRIORITY_INFO,
    PRIORITY_WARNING,
)
from custom_components.notification_center.router import (
    Person,
    RouterConfig,
    resolve_deliveries,
)

ALERT = {
    "tag": "garage_open",
    "title": "Garage open",
    "message": "10 minutes",
    "navigation_target": "/lovelace/security",
    "digest_group": None,
}


def _resolve(channels, priority="warning", **kw):
    cfg = kw.pop("config", RouterConfig(mobile_targets=["notify.mobile_app_carmen"]))
    return resolve_deliveries(
        alert=ALERT,
        channels=channels,
        priority=priority,
        presence_routing=kw.pop("presence_routing", "all"),
        tts_targets=kw.pop("tts_targets", []),
        config=cfg,
        presence=kw.pop("presence", {}),
        suppress_push=kw.pop("suppress_push", False),
    )


class MobileChannel(unittest.TestCase):
    def test_basic_push(self):
        actions = _resolve([CHANNEL_MOBILE])
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].domain, "notify")
        self.assertEqual(actions[0].service, "mobile_app_carmen")
        self.assertEqual(actions[0].data["title"], "Garage open")

    def test_critical_uses_critical_sound(self):
        actions = _resolve([CHANNEL_MOBILE], priority=PRIORITY_CRITICAL)
        push = actions[0].data["data"]["push"]
        self.assertEqual(push["sound"]["critical"], 1)

    def test_warning_time_sensitive(self):
        actions = _resolve([CHANNEL_MOBILE], priority=PRIORITY_WARNING)
        self.assertEqual(
            actions[0].data["data"]["push"]["interruption-level"], "time-sensitive"
        )

    def test_suppress_push_skips_mobile(self):
        actions = _resolve([CHANNEL_MOBILE], suppress_push=True)
        self.assertEqual(actions, [])

    def test_navigation_target_added_to_push(self):
        actions = _resolve([CHANNEL_MOBILE])
        self.assertEqual(actions[0].data["data"]["url"], "/lovelace/security")


class PresenceRouting(unittest.TestCase):
    def _cfg(self):
        return RouterConfig(
            persons=[
                Person("person.carmen", "notify.mobile_app_carmen"),
                Person("person.brian", "notify.mobile_app_brian"),
            ]
        )

    def test_all_notifies_everyone(self):
        actions = _resolve([CHANNEL_MOBILE], config=self._cfg(), presence_routing="all")
        services = {a.service for a in actions}
        self.assertEqual(services, {"mobile_app_carmen", "mobile_app_brian"})

    def test_away_only_filters_home_people(self):
        actions = _resolve(
            [CHANNEL_MOBILE],
            config=self._cfg(),
            presence_routing="away_only",
            presence={"person.carmen": "home", "person.brian": "not_home"},
        )
        services = {a.service for a in actions}
        self.assertEqual(services, {"mobile_app_brian"})

    def test_away_only_all_home_falls_back_to_all(self):
        actions = _resolve(
            [CHANNEL_MOBILE],
            config=self._cfg(),
            presence_routing="away_only",
            presence={"person.carmen": "home", "person.brian": "home"},
        )
        services = {a.service for a in actions}
        self.assertEqual(services, {"mobile_app_carmen", "mobile_app_brian"})


class OtherChannels(unittest.TestCase):
    def test_bell_uses_tag_as_notification_id(self):
        actions = _resolve([CHANNEL_BELL])
        self.assertEqual(actions[0].domain, "persistent_notification")
        self.assertEqual(actions[0].data["notification_id"], "garage_open")

    def test_wall_produces_no_action(self):
        self.assertEqual(_resolve([CHANNEL_WALL]), [])

    def test_tts_uses_targets(self):
        cfg = RouterConfig(tts_service="tts.speak")
        actions = _resolve(
            [CHANNEL_TTS], config=cfg, tts_targets=["media_player.kitchen"]
        )
        self.assertEqual(actions[0].domain, "tts")
        self.assertEqual(actions[0].service, "speak")
        self.assertEqual(
            actions[0].data["media_player_entity_id"], ["media_player.kitchen"]
        )

    def test_tts_without_targets_noop(self):
        self.assertEqual(_resolve([CHANNEL_TTS], config=RouterConfig()), [])

    def test_navigate_to_fully_kiosk_devices(self):
        cfg = RouterConfig(fully_kiosk_devices=["dev1", "dev2"])
        actions = _resolve([CHANNEL_NAVIGATE], config=cfg)
        self.assertEqual(len(actions), 2)
        self.assertTrue(all(a.domain == "fully_kiosk" for a in actions))
        self.assertEqual(actions[0].data["url"], "/lovelace/security")


if __name__ == "__main__":
    unittest.main()
