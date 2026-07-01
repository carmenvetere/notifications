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
    build_push_actions,
    parse_push_action,
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

    def test_per_person_notifies_only_home_people(self):
        actions = _resolve(
            [CHANNEL_MOBILE],
            config=self._cfg(),
            presence_routing="per_person",
            presence={"person.carmen": "home", "person.brian": "not_home"},
        )
        services = {a.service for a in actions}
        self.assertEqual(services, {"mobile_app_carmen"})

    def test_per_person_nobody_home_falls_back_to_all(self):
        actions = _resolve(
            [CHANNEL_MOBILE],
            config=self._cfg(),
            presence_routing="per_person",
            presence={"person.carmen": "not_home", "person.brian": "not_home"},
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


class PushActions(unittest.TestCase):
    def test_build_dismiss_snooze_and_custom(self):
        alert = {
            "tag": "batt",
            "actions": ["dismiss", "snooze"],
            "buttons": [{"id": 0, "label": "I did it"}],
        }
        acts = build_push_actions(alert)
        ids = [a["action"] for a in acts]
        self.assertEqual(ids[0], "NC::DISMISS::batt")
        self.assertEqual(ids[1], "NC::SNOOZE::batt::60")
        self.assertEqual(ids[2], "NC::RUN::batt::0")
        self.assertTrue(acts[0]["destructive"])
        self.assertEqual(acts[2]["title"], "I did it")

    def test_locked_alert_has_no_dismiss_snooze_but_keeps_custom(self):
        alert = {"tag": "x", "actions": [], "buttons": [{"id": 0, "label": "Go"}]}
        ids = [a["action"] for a in build_push_actions(alert)]
        self.assertEqual(ids, ["NC::RUN::x::0"])

    def test_no_actions_no_buttons(self):
        self.assertEqual(build_push_actions({"tag": "x", "actions": []}), [])

    def test_actions_attached_to_mobile_push(self):
        alert = {**ALERT, "actions": ["dismiss", "snooze"], "buttons": []}
        acts = resolve_deliveries(
            alert=alert, channels=[CHANNEL_MOBILE], priority="info",
            presence_routing="all", tts_targets=[],
            config=RouterConfig(mobile_targets=["notify.mobile_app_carmen"]),
        )
        push = acts[0].data["data"]
        self.assertIn("actions", push)
        self.assertEqual(push["actions"][0]["action"], "NC::DISMISS::garage_open")

    def test_parse_roundtrip(self):
        self.assertEqual(
            parse_push_action("NC::SNOOZE::garage::60"),
            {"verb": "SNOOZE", "tag": "garage", "arg": "60"},
        )
        self.assertEqual(
            parse_push_action("NC::DISMISS::garage"),
            {"verb": "DISMISS", "tag": "garage", "arg": None},
        )
        self.assertIsNone(parse_push_action("something_else"))
        self.assertIsNone(parse_push_action(""))


if __name__ == "__main__":
    unittest.main()
