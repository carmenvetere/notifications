"""Validate the packaged example_rules.yaml maps cleanly to rules."""

import os
import unittest

import yaml

from tests.conftest_path import ROOT

from custom_components.notification_center.const import (
    CHANNELS,
    PRIORITIES,
    PRIORITY_CRITICAL,
    PRIORITY_INFO,
    PRIORITY_WARNING,
    SOURCE_TEMPLATE,
    SOURCE_TYPES,
)
from custom_components.notification_center.rule import Rule

RULES_FILE = os.path.join(
    ROOT, "custom_components", "notification_center", "example_rules.yaml"
)


def _load():
    with open(RULES_FILE, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


class ExampleRules(unittest.TestCase):
    def setUp(self):
        self.rules = _load()
        self.by_tag = {r["dedup_tag"]: r for r in self.rules}

    def test_expected_count(self):
        self.assertEqual(len(self.rules), 8)

    def test_all_map_to_rule_and_are_valid(self):
        for raw in self.rules:
            rule = Rule.from_subentry(raw["dedup_tag"], raw)
            self.assertIn(rule.source_type, SOURCE_TYPES, rule.name)
            self.assertIn(rule.priority, PRIORITIES, rule.name)
            for ch in rule.channels:
                self.assertIn(ch, CHANNELS, rule.name)
            if rule.is_template:
                self.assertTrue(rule.primary_template, rule.name)
            else:
                self.assertTrue(rule.entity_id, rule.name)
                self.assertTrue(rule.operator, rule.name)

    def test_dedup_tags_unique(self):
        tags = [r["dedup_tag"] for r in self.rules]
        self.assertEqual(len(tags), len(set(tags)))

    def test_priority_distribution(self):
        counts = {}
        for r in self.rules:
            counts[r["priority"]] = counts.get(r["priority"], 0) + 1
        self.assertEqual(counts[PRIORITY_CRITICAL], 2)
        self.assertEqual(counts[PRIORITY_WARNING], 3)
        self.assertEqual(counts[PRIORITY_INFO], 3)
        self.assertNotIn("digest", counts)

    def test_critical_rules_push_and_escalate(self):
        crit = [r for r in self.rules if r["priority"] == PRIORITY_CRITICAL]
        self.assertTrue(crit)
        for r in crit:
            self.assertIn("mobile", r["channels"])
            self.assertEqual(r["escalation_after"], 5)
            self.assertEqual(r["quiet_hours_behavior"], "ignore")

    def test_single_digest_rule_with_items(self):
        digest = [r for r in self.rules if r.get("deliver_as_digest")]
        self.assertEqual(len(digest), 1)
        batt = digest[0]
        self.assertEqual(batt["priority"], PRIORITY_INFO)
        self.assertEqual(batt["source_type"], SOURCE_TEMPLATE)
        self.assertEqual(batt["digest_group"], "batteries")
        self.assertTrue(batt.get("items_template"))

    def test_template_rules_present(self):
        templated = {r["dedup_tag"] for r in self.rules if r["source_type"] == "template"}
        self.assertIn("weather_alert", templated)
        self.assertIn("low_batteries", templated)

    def test_chore_rule_has_confirmed_reset_action(self):
        actions = self.by_tag["hvac_filter"].get("custom_actions") or []
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["service"], "script.reset_filter")
        self.assertTrue(actions[0].get("confirm"))

    def test_entity_action_button_has_target(self):
        actions = self.by_tag["garage_open"].get("custom_actions") or []
        self.assertEqual(actions[0]["service"], "cover.close_cover")
        self.assertEqual(actions[0]["target"], {"entity_id": "cover.garage_door"})

    def test_weather_rule_has_message_template(self):
        self.assertIn(
            "sensor.weather_alerts", self.by_tag["weather_alert"]["message_template"]
        )

    def test_navigation_targets_preserved(self):
        self.assertEqual(self.by_tag["garage_open"]["navigation_target"], "/lovelace/home")
        self.assertEqual(self.by_tag["weather_alert"]["navigation_target"], "/lovelace/weather")


if __name__ == "__main__":
    unittest.main()
