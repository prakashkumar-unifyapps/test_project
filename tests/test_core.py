import datetime as dt
import unittest

from idle_nudge.core import Config, Event, State, Tracker, fmt_duration

DAY = dt.date(2026, 11, 25)


class Sim:
    """Drives a Tracker one second at a time with a fake input clock."""

    def __init__(self, **cfg):
        self.t = Tracker(Config(**cfg))
        self.now = 1_000_000.0
        self.last_input = self.now
        self.last_mouse = self.now - 999
        self.locked = False
        self.day = DAY

    def step(self, seconds=1):
        events, tick = [], None
        for _ in range(int(seconds)):
            self.now += 1
            tick = self.t.tick(self.now, self.now - self.last_input,
                               self.now - self.last_mouse, self.locked, self.day)
            events += tick.events
        return events, tick

    def click(self):
        self.last_input = self.now


class TrackerTests(unittest.TestCase):
    def test_warns_before_threshold_then_saved_by_input(self):
        s = Sim()
        ev, tick = s.step(239)
        self.assertEqual(ev, [])
        ev, tick = s.step(1)  # 240 s = 300 - 60
        self.assertEqual(ev, [Event.WARN])
        self.assertEqual(tick.state, State.WARNED)
        self.assertAlmostEqual(tick.seconds_left, 60)
        s.click()
        ev, tick = s.step(1)
        self.assertEqual(ev, [Event.SAVED])
        self.assertEqual(tick.state, State.ACTIVE)
        self.assertEqual(s.t.stats.saves, 1)
        self.assertEqual(s.t.stats.idle_seconds, 0)

    def test_warns_only_once_per_gap(self):
        s = Sim()
        ev, _ = s.step(290)
        self.assertEqual(ev.count(Event.WARN), 1)

    def test_idle_gap_counted_from_last_input(self):
        s = Sim()
        ev, tick = s.step(300)
        self.assertIn(Event.IDLE_STARTED, ev)
        self.assertEqual(tick.state, State.IDLE)
        s.step(420)  # away 12 min total
        s.click()
        ev, tick = s.step(1)
        self.assertEqual(ev, [Event.IDLE_ENDED])
        self.assertEqual(tick.idle_gap, 720)
        self.assertEqual(s.t.stats.idle_seconds, 720)
        self.assertEqual(s.t.stats.idle_gaps, 1)

    def test_lock_ends_gap_and_lock_time_is_not_idle(self):
        s = Sim()
        s.step(400)
        s.locked = True
        ev, tick = s.step(1)
        self.assertEqual(tick.state, State.AWAY)
        self.assertEqual(s.t.stats.idle_seconds, 400)
        s.step(3600)
        s.locked = False
        s.click()
        ev, tick = s.step(1)
        self.assertEqual(tick.state, State.ACTIVE)
        self.assertEqual(s.t.stats.idle_seconds, 400)

    def test_locking_during_warning_avoids_idle(self):
        s = Sim()
        s.step(250)
        s.locked = True
        s.step(600)
        s.locked = False
        s.click()
        s.step(1)
        self.assertEqual(s.t.stats.idle_seconds, 0)

    def test_sleep_detected_by_clock_jump(self):
        s = Sim()
        s.step(100)
        s.now += 3600  # Mac slept for an hour; polling stopped
        _, tick = s.step(1)
        self.assertEqual(tick.state, State.AWAY)
        s.click()
        _, tick = s.step(1)
        self.assertEqual(tick.state, State.ACTIVE)
        self.assertEqual(s.t.stats.idle_seconds, 0)

    def test_snooze_suppresses_nudges_until_it_ends(self):
        s = Sim()
        s.t.snooze(s.now, 600)
        ev, tick = s.step(500)
        self.assertNotIn(Event.WARN, ev)
        self.assertEqual(tick.state, State.SNOOZED)
        s.click()
        s.step(150)  # snooze expires at 600
        self.assertEqual(s.t.state, State.ACTIVE)
        ev, _ = s.step(240)
        self.assertIn(Event.WARN, ev)

    def test_mouse_only_hint(self):
        s = Sim()
        s.step(250)
        s.last_mouse = s.now
        _, tick = s.step(1)
        self.assertTrue(tick.mouse_only)
        self.assertEqual(tick.state, State.WARNED)  # movement did not save the gap

    def test_stats_reset_on_new_day(self):
        s = Sim()
        s.step(400)
        s.click()
        s.step(1)
        self.assertEqual(s.t.stats.idle_gaps, 1)
        s.day = DAY + dt.timedelta(days=1)
        s.step(1)
        self.assertEqual(s.t.stats.idle_gaps, 0)
        self.assertEqual(s.t.stats.day, s.day)

    def test_custom_threshold(self):
        s = Sim(idle_seconds=120, warn_lead=30)
        ev, _ = s.step(90)
        self.assertEqual(ev, [Event.WARN])


class FormatTests(unittest.TestCase):
    def test_fmt(self):
        self.assertEqual(fmt_duration(42), "42s")
        self.assertEqual(fmt_duration(65), "1m 05s")
        self.assertEqual(fmt_duration(720), "12m")
        self.assertEqual(fmt_duration(3725), "1h 02m")


if __name__ == "__main__":
    unittest.main()
