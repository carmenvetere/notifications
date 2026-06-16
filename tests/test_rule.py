"""Unit tests for pure rule evaluation (no Home Assistant required)."""

import unittest

from tests.conftest_path import ROOT  # noqa: F401  (ensures sys.path)

from custom_components.notification_center.const import (
    OP_EQ,
    OP_GE,
    OP_GT,
    OP_LE,
    OP_LT,
    OP_NE,
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


if __name__ == "__main__":
    unittest.main()
