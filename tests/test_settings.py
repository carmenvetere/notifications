"""Unit tests for the normalized settings model."""

import unittest

from tests.conftest_path import ROOT  # noqa: F401

from custom_components.notification_center.settings import (
    CONF_WALL_SOUNDS,
    DEFAULT_WALL_SOUNDS,
    normalize,
)


class WallSoundsTest(unittest.TestCase):
    def test_default_is_chime(self):
        self.assertEqual(normalize({})[CONF_WALL_SOUNDS], DEFAULT_WALL_SOUNDS)
        self.assertEqual(normalize(None)[CONF_WALL_SOUNDS], ["chime"])

    def test_list_and_comma_string_are_cleaned(self):
        self.assertEqual(normalize({CONF_WALL_SOUNDS: [" chime ", "", "alarm"]})[CONF_WALL_SOUNDS], ["chime", "alarm"])
        self.assertEqual(normalize({CONF_WALL_SOUNDS: "chime, doorbell"})[CONF_WALL_SOUNDS], ["chime", "doorbell"])

    def test_empty_falls_back_to_default(self):
        self.assertEqual(normalize({CONF_WALL_SOUNDS: []})[CONF_WALL_SOUNDS], ["chime"])

    def test_default_list_is_not_shared(self):
        normalize({})[CONF_WALL_SOUNDS].append("x")
        self.assertEqual(DEFAULT_WALL_SOUNDS, ["chime"])


if __name__ == "__main__":
    unittest.main()
