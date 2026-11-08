"""Per-rule recipients narrow the push audience (pure unit tests, no HA)."""

import unittest

from custom_components.notification_center.const import CHANNEL_MOBILE
from custom_components.notification_center.router import (
    Person,
    RouterConfig,
    resolve_deliveries,
)

ALEX = Person(person_entity="person.alex", notify_service="notify.mobile_app_phone")
SAM = Person(person_entity="person.sam", notify_service="notify.mobile_app_tablet")


def _push_targets(**kw):
    actions = resolve_deliveries(
        alert={"tag": "t", "title": "T", "message": ""},
        channels=[CHANNEL_MOBILE],
        priority=kw.pop("priority", "warning"),
        presence_routing=kw.pop("presence_routing", "all"),
        tts_targets=[],
        config=kw.pop("config"),
        presence=kw.pop("presence", {}),
        recipients=kw.pop("recipients", None),
    )
    return sorted(f"{a.domain}.{a.service}" for a in actions)


class RecipientsTest(unittest.TestCase):
    def test_no_recipients_means_everyone(self):
        cfg = RouterConfig(persons=[ALEX, SAM])
        self.assertEqual(
            _push_targets(config=cfg), ["notify.mobile_app_phone", "notify.mobile_app_tablet"]
        )

    def test_recipients_filter_persons(self):
        cfg = RouterConfig(persons=[ALEX, SAM])
        self.assertEqual(
            _push_targets(config=cfg, recipients=["person.alex"]), ["notify.mobile_app_phone"]
        )

    def test_recipients_apply_before_presence_routing(self):
        # away_only among the selected people only: alex is home -> would be
        # excluded, but the fallback keeps the alert from being dropped.
        cfg = RouterConfig(persons=[ALEX, SAM])
        presence = {"person.alex": "home", "person.sam": "not_home"}
        self.assertEqual(
            _push_targets(
                config=cfg, recipients=["person.alex"], presence_routing="away_only", presence=presence
            ),
            ["notify.mobile_app_phone"],
        )
        # Both selected, away_only -> only sam.
        self.assertEqual(
            _push_targets(
                config=cfg,
                recipients=["person.alex", "person.sam"],
                presence_routing="away_only",
                presence=presence,
            ),
            ["notify.mobile_app_tablet"],
        )

    def test_recipient_may_be_a_notify_service(self):
        cfg = RouterConfig(persons=[ALEX, SAM])
        self.assertEqual(
            _push_targets(config=cfg, recipients=["notify.mobile_app_tablet"]),
            ["notify.mobile_app_tablet"],
        )

    def test_unmapped_recipient_sends_nothing(self):
        cfg = RouterConfig(persons=[ALEX, SAM])
        self.assertEqual(_push_targets(config=cfg, recipients=["person.nobody"]), [])

    def test_recipients_filter_plain_mobile_targets(self):
        cfg = RouterConfig(mobile_targets=["notify.mobile_app_a", "notify.mobile_app_b"])
        self.assertEqual(
            _push_targets(config=cfg, recipients=["notify.mobile_app_b"]), ["notify.mobile_app_b"]
        )
        self.assertEqual(
            _push_targets(config=cfg), ["notify.mobile_app_a", "notify.mobile_app_b"]
        )


if __name__ == "__main__":
    unittest.main()
