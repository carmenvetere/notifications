"""Validate the packaged imported_rules.yaml maps cleanly to rules."""

import os
import unittest

import yaml

from tests.conftest_path import ROOT

from custom_components.notification_center.const import (
    CHANNELS,
    PRIORITIES,
    PRIORITY_CRITICAL,
    PRIORITY_DIGEST,
    PRIORITY_INFO,
    PRIORITY_WARNING,
    SOURCE_TEMPLATE,
    SOURCE_TYPES,
)
from custom_components.notification_center.rule import Rule

RULES_FILE = os.path.join(
    ROOT, "custom_components", "notification_center", "imported_rules.yaml"
)


def _load():
    with open(RULES_FILE, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


class ImportedRules(unittest.TestCase):
    def setUp(self):
        self.rules = _load()

    def test_expected_count(self):
        self.assertEqual(len(self.rules), 22)

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
        self.assertEqual(counts[PRIORITY_CRITICAL], 3)
        self.assertEqual(counts[PRIORITY_WARNING], 7)
        self.assertEqual(counts[PRIORITY_INFO], 11)
        self.assertEqual(counts[PRIORITY_DIGEST], 1)

    def test_critical_rules_push_and_escalate(self):
        for r in self.rules:
            if r["priority"] == PRIORITY_CRITICAL:
                self.assertIn("mobile", r["channels"])
                self.assertEqual(r["escalation_after"], 5)
                self.assertEqual(r["quiet_hours_behavior"], "ignore")

    def test_info_rules_do_not_push_mobile(self):
        for r in self.rules:
            if r["priority"] == PRIORITY_INFO:
                self.assertNotIn("mobile", r["channels"])

    def test_battery_digest_single_rule_with_29_sensors(self):
        digest = [r for r in self.rules if r["priority"] == PRIORITY_DIGEST]
        self.assertEqual(len(digest), 1)
        batt = digest[0]
        self.assertEqual(batt["source_type"], SOURCE_TEMPLATE)
        self.assertEqual(batt["digest_group"], "batteries")
        self.assertEqual(batt["condition_template"].count("sensor."), 29)
        self.assertEqual(batt["message_template"].count("sensor."), 29)

    def test_two_condition_cards_are_templates(self):
        templated = {r["dedup_tag"] for r in self.rules if r["source_type"] == "template"}
        self.assertIn("powerwall_charge_low", templated)
        self.assertIn("rain_pool_cover_pump", templated)
        self.assertIn("pool_needs_vacuum", templated)

    def test_navigation_targets_preserved(self):
        by_tag = {r["dedup_tag"]: r for r in self.rules}
        self.assertEqual(by_tag["power_outage"]["navigation_target"], "/mobile-dash/energy")
        self.assertEqual(by_tag["alarm_triggered"]["navigation_target"], "/mobile-dash/security")
        self.assertEqual(
            by_tag["nws_weather_alert"]["navigation_target"], "/mobile-dash/weather"
        )


if __name__ == "__main__":
    unittest.main()
