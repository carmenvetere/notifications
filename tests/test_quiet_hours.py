"""Unit tests for quiet-hours logic."""

import unittest
from datetime import datetime, time

from tests.conftest_path import ROOT  # noqa: F401

from custom_components.notification_center.const import (
    PRIORITY_CRITICAL,
    PRIORITY_INFO,
    PRIORITY_WARNING,
    QH_BATCH,
    QH_DOWNGRADE,
    QH_IGNORE,
    QH_SUPPRESS,
)
from custom_components.notification_center.quiet_hours import (
    apply_quiet_hours,
    in_quiet_hours,
    next_time_after,
    parse_time,
)


class NextTimeAfter(unittest.TestCase):
    def test_later_today(self):
        self.assertEqual(
            next_time_after(datetime(2026, 1, 1, 6, 0), time(8, 0)),
            datetime(2026, 1, 1, 8, 0),
        )

    def test_already_passed_rolls_to_tomorrow(self):
        self.assertEqual(
            next_time_after(datetime(2026, 1, 1, 10, 0), time(8, 0)),
            datetime(2026, 1, 2, 8, 0),
        )

    def test_exactly_now_rolls_to_tomorrow(self):
        self.assertEqual(
            next_time_after(datetime(2026, 1, 1, 8, 0), time(8, 0)),
            datetime(2026, 1, 2, 8, 0),
        )


class InQuietHours(unittest.TestCase):
    def test_wrap_midnight(self):
        start, end = time(22, 0), time(7, 0)
        self.assertTrue(in_quiet_hours(time(23, 0), start, end))
        self.assertTrue(in_quiet_hours(time(3, 0), start, end))
        self.assertFalse(in_quiet_hours(time(12, 0), start, end))

    def test_same_day_window(self):
        start, end = time(9, 0), time(17, 0)
        self.assertTrue(in_quiet_hours(time(12, 0), start, end))
        self.assertFalse(in_quiet_hours(time(8, 0), start, end))

    def test_equal_start_end_never_quiet(self):
        self.assertFalse(in_quiet_hours(time(12, 0), time(0, 0), time(0, 0)))

    def test_parse_time(self):
        self.assertEqual(parse_time("22:30"), time(22, 30))
        self.assertEqual(parse_time("07:05:09"), time(7, 5, 9))


class ApplyQuietHours(unittest.TestCase):
    def test_not_quiet_passthrough(self):
        self.assertEqual(
            apply_quiet_hours(PRIORITY_WARNING, QH_SUPPRESS, False),
            (PRIORITY_WARNING, False, False),
        )

    def test_ignore_keeps_critical(self):
        self.assertEqual(
            apply_quiet_hours(PRIORITY_CRITICAL, QH_IGNORE, True),
            (PRIORITY_CRITICAL, False, False),
        )

    def test_downgrade(self):
        prio, suppress, batch = apply_quiet_hours(PRIORITY_WARNING, QH_DOWNGRADE, True)
        self.assertEqual(prio, PRIORITY_INFO)
        self.assertFalse(suppress)
        self.assertFalse(batch)

    def test_suppress(self):
        self.assertEqual(
            apply_quiet_hours(PRIORITY_INFO, QH_SUPPRESS, True),
            (PRIORITY_INFO, True, False),
        )

    def test_batch(self):
        self.assertEqual(
            apply_quiet_hours(PRIORITY_INFO, QH_BATCH, True),
            (PRIORITY_INFO, False, True),
        )


if __name__ == "__main__":
    unittest.main()
