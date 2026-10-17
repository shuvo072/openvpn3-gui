"""Counter parsing, rate accuracy, gaps, and exact session routing."""

import json
import unittest
from unittest.mock import patch

from openvpn3_gui.backend import Backend, CLIError
from openvpn3_gui.traffic import TrafficHistory, format_bytes, parse_counters


class TrafficTests(unittest.TestCase):
    def test_json_counters_and_bounds(self):
        self.assertEqual(
            parse_counters('{"BYTES_IN": 0, "BYTES_OUT": 18446744073709551615}'),
            (0, 2**64 - 1),
        )
        for value in (-1, True, "5", 1.5, None, 2**64):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_counters(json.dumps({"BYTES_IN": value, "BYTES_OUT": 0}))
        for value in ("null", "[]", "{}", "not json"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_counters(value)

    def test_elapsed_time_rates_and_reset(self):
        history = TrafficHistory()
        history.add(100, (1000, 500))
        self.assertIsNone(history.rates)
        history.add(102.5, (1500, 750))
        self.assertEqual(history.rates, (200, 100))
        history.add(103, (0, 0))
        self.assertIsNone(history.rates)
        history.add(105, (100, 40))
        self.assertEqual(history.rates, (50, 20))
        history.add(105, (9999, 9999))
        self.assertEqual(history.totals, (100, 40))

    def test_failed_poll_and_long_gap_rebase(self):
        history = TrafficHistory()
        history.add(0, (0, 0))
        history.add(2, (100, 100))
        history.interrupt()
        self.assertIsNone(history.rates)
        self.assertEqual(history.totals, (100, 100))
        history.add(4, (400, 400))
        self.assertIsNone(history.rates)
        history.add(20, (1000, 1000))
        self.assertIsNone(history.rates)

    def test_history_is_bounded_by_time_and_count(self):
        history = TrafficHistory()
        for index in range(200):
            history.add(index * 2, (index, index))
        self.assertEqual(len(history.samples), 31)
        self.assertEqual(history.samples[0][0], 338)
        for index in range(1000):
            history.add(400 + index / 100, (1000, 1000))
        self.assertLessEqual(len(history.samples), 90)

    def test_exact_session_argv_and_invalid_output(self):
        backend = Backend(demo=True)
        backend.demo = False
        with patch.object(
            backend, "read", return_value='{"BYTES_IN":12,"BYTES_OUT":34}'
        ) as read:
            self.assertEqual(
                backend.session_stats("/net/openvpn/v3/sessions/exact"), (12, 34)
            )
            read.assert_called_once_with(
                "session-stats", "--path", "/net/openvpn/v3/sessions/exact", "--json"
            )
        with (
            patch.object(backend, "read", return_value="{}"),
            self.assertRaises(CLIError),
        ):
            backend.session_stats("/net/openvpn/v3/sessions/exact")

    def test_formatting(self):
        self.assertEqual(format_bytes(None), "—")
        self.assertEqual(format_bytes(0, True), "0 B/s")
        self.assertEqual(format_bytes(1536, True), "1.5 KiB/s")
        self.assertEqual(format_bytes(2**64 - 1), "16.0 EiB")
