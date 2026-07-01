"""Unit tests for pure rule evaluation (no Home Assistant required)."""

import unittest

from tests.conftest_path import ROOT  # noqa: F401  (ensures sys.path)

from custom_components.notification_center.const import (
    CLEAR_DISMISS,
    CLEAR_LOCKED,
    OP_EQ,
    OP_GE,
    OP_GT,
    OP_LE,
    OP_LT,
    OP_NE,
    PRIORITY_CRITICAL,
    PRIORITY_INFO,
    PRIORITY_WARNING,
    SOURCE_NUMERIC,
    SOURCE_STATE,
)
from custom_components.notification_center.rule import Rule, match_value


class MatchValueState(unittest.TestCase):
    def test_state_equality(self):
        self.assertTrue(match_value(SOURCE_STATE, OP_EQ, "on", "on"))
        self.assertFalse(match_value(SOURCE_STATE, OP_EQ, "on", "off"))

    def test_state_inequality(self):
        self.assertTrue(match_value(SOURCE_STATE, OP_NE, "home", "away"))
        self.assertFalse(match_value(SOURCE_STATE, OP_NE, "home", "home"))

    def test_unavailable_never_matches(self):
        for bad in ("unavailable", "unknown", "", None):
            self.assertFalse(match_value(SOURCE_STATE, OP_EQ, "on", bad))


class MatchValueNumeric(unittest.TestCase):
    def test_operators(self):
        self.assertTrue(match_value(SOURCE_NUMERIC, OP_GT, 20, 25))
        self.assertFalse(match_value(SOURCE_NUMERIC, OP_GT, 20, 15))
        self.assertTrue(match_value(SOURCE_NUMERIC, OP_LT, 20, 15))
        self.assertTrue(match_value(SOURCE_NUMERIC, OP_GE, 20, 20))
        self.assertTrue(match_value(SOURCE_NUMERIC, OP_LE, 20, 20))
        self.assertTrue(match_value(SOURCE_NUMERIC, OP_EQ, 20, 20))
        self.assertTrue(match_value(SOURCE_NUMERIC, OP_NE, 20, 21))

    def test_string_numbers_coerced(self):
        self.assertTrue(match_value(SOURCE_NUMERIC, OP_LT, "20", "15"))

    def test_non_numeric_returns_false(self):
        self.assertFalse(match_value(SOURCE_NUMERIC, OP_GT, 20, "abc"))


class RuleFromSubentry(unittest.TestCase):
    def test_defaults_and_tag(self):
        rule = Rule.from_subentry(
            "sub1",
            {
                "name": "Garage Open",
                "source_type": SOURCE_STATE,
                "entity_id": "binary_sensor.garage",
                "operator": OP_EQ,
                "value": "on",
                "priority": PRIORITY_WARNING,
                "channels": ["mobile", "bell"],
            },
        )
        self.assertEqual(rule.tag, "sub1")  # falls back to rule_id
        self.assertEqual(rule.tracked_entities, ["binary_sensor.garage"])
        self.assertEqual(rule.effective_cooldown, 15)  # warning default
        self.assertEqual(rule.channels, ["mobile", "bell"])

    def test_dedup_tag_used(self):
        rule = Rule.from_subentry("sub1", {"name": "X", "dedup_tag": "garage_open"})
        self.assertEqual(rule.tag, "garage_open")

    def test_channels_from_csv(self):
        rule = Rule.from_subentry("s", {"name": "X", "channels": "mobile, bell ,wall"})
        self.assertEqual(rule.channels, ["mobile", "bell", "wall"])

    def test_effective_color_default_per_priority(self):
        rule = Rule.from_subentry("s", {"name": "X", "priority": PRIORITY_WARNING})
        self.assertEqual(rule.effective_color, "#EF8C00")

    def test_template_rule_tracks_no_entities(self):
        rule = Rule.from_subentry(
            "s",
            {"name": "X", "source_type": "template", "condition_template": "{{ true }}"},
        )
        self.assertTrue(rule.is_template)
        self.assertEqual(rule.tracked_entities, [])
        self.assertEqual(rule.primary_template, "{{ true }}")


class ClearingModel(unittest.TestCase):
    def test_follow_priority_defaults(self):
        crit = Rule.from_subentry("c", {"name": "C", "priority": PRIORITY_CRITICAL})
        warn = Rule.from_subentry("w", {"name": "W", "priority": PRIORITY_WARNING})
        info = Rule.from_subentry("i", {"name": "I", "priority": PRIORITY_INFO})
        # Critical & Warning are both locked now (acknowledge was removed).
        self.assertEqual(crit.effective_clear_mode, CLEAR_LOCKED)
        self.assertFalse(crit.snooze_allowed)
        self.assertEqual(warn.effective_clear_mode, CLEAR_LOCKED)
        self.assertFalse(warn.snooze_allowed)
        self.assertEqual(info.effective_clear_mode, CLEAR_DISMISS)
        self.assertTrue(info.snooze_allowed)

    def test_allowed_actions_per_mode(self):
        crit = Rule.from_subentry("c", {"name": "C", "priority": PRIORITY_CRITICAL})
        warn = Rule.from_subentry("w", {"name": "W", "priority": PRIORITY_WARNING})
        info = Rule.from_subentry("i", {"name": "I", "priority": PRIORITY_INFO})
        self.assertEqual(crit.allowed_actions, [])  # locked, no snooze
        self.assertEqual(warn.allowed_actions, [])  # locked, no snooze
        self.assertEqual(info.allowed_actions, ["dismiss", "snooze"])

    def test_deliver_as_digest_field(self):
        rule = Rule.from_subentry(
            "d",
            {
                "name": "Batteries",
                "priority": PRIORITY_INFO,
                "deliver_as_digest": True,
                "digest_group": "batteries",
            },
        )
        self.assertTrue(rule.deliver_as_digest)
        self.assertEqual(rule.digest_group, "batteries")

    def test_override_when_not_following_priority(self):
        rule = Rule.from_subentry(
            "r",
            {
                "name": "R",
                "priority": PRIORITY_CRITICAL,
                "actions_follow_priority": False,
                "clear_mode": CLEAR_DISMISS,
                "snooze": True,
            },
        )
        self.assertEqual(rule.effective_clear_mode, CLEAR_DISMISS)
        self.assertTrue(rule.snooze_allowed)
        self.assertEqual(rule.allowed_actions, ["dismiss", "snooze"])

    def test_custom_action_buttons(self):
        rule = Rule.from_subentry(
            "r",
            {
                "name": "Filter",
                "priority": PRIORITY_INFO,
                "custom_actions": [
                    {
                        "id": "close",
                        "label": "I replaced it",
                        "icon": "mdi:check",
                        "service": "script.reset_filter",
                        "confirm": "Sure?",
                    },
                    {"service": "script.x"},  # no id/label -> id=index, "Run"
                    "bogus",  # non-dict ignored
                ],
            },
        )
        buttons = rule.custom_action_buttons
        self.assertEqual(len(buttons), 2)
        # Stable id is used when present; otherwise the list index (as a string).
        self.assertEqual(buttons[0]["id"], "close")
        self.assertEqual(buttons[0]["label"], "I replaced it")
        self.assertEqual(buttons[0]["confirm"], "Sure?")
        self.assertEqual(buttons[1]["id"], "1")
        self.assertEqual(buttons[1]["label"], "Run")

    def test_no_custom_actions_default(self):
        rule = Rule.from_subentry("r", {"name": "X"})
        self.assertEqual(rule.custom_actions, [])
        self.assertEqual(rule.custom_action_buttons, [])

    def test_effective_tts_message_falls_back_to_message(self):
        rule = Rule.from_subentry(
            "r", {"name": "R", "message_template": "the body", "tts_message": ""}
        )
        self.assertEqual(rule.effective_tts_message, "the body")
        rule2 = Rule.from_subentry(
            "r", {"name": "R", "message_template": "body", "tts_message": "spoken"}
        )
        self.assertEqual(rule2.effective_tts_message, "spoken")


if __name__ == "__main__":
    unittest.main()
