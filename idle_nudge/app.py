"""Idle Nudge menu-bar app for macOS.

Warns you shortly before Sensei would mark the current gap as idle, so a short pause
does not turn into recorded idle time. When you really are leaving, it offers to lock
the screen, which Sensei records as "locked" instead of idle.

It never synthesises clicks or key presses: every saved gap is real input from you.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import subprocess
import time
from pathlib import Path

import rumps

from . import probe
from .core import Config, Event, State, Tracker, fmt_duration

DATA_DIR = Path.home() / ".idle-nudge"
CONFIG_FILE = DATA_DIR / "config.json"
LOG_FILE = DATA_DIR / "idle-gaps.csv"

DEFAULTS = {
    "idleSeconds": 300,     # keep in step with Sensei config.json capture.idleSeconds
    "warnLeadSeconds": 60,
    "sound": "Glass",       # any name in /System/Library/Sounds, or "" for none
    "popup": True,          # modal alert; clicking it is a real click
}


def load_settings() -> dict:
    DATA_DIR.mkdir(exist_ok=True)
    settings = dict(DEFAULTS)
    if CONFIG_FILE.exists():
        try:
            settings.update(json.loads(CONFIG_FILE.read_text()))
        except (ValueError, OSError) as e:
            print(f"Ignoring {CONFIG_FILE}: {e}")
    else:
        CONFIG_FILE.write_text(json.dumps(DEFAULTS, indent=2) + "\n")
    return settings


def log_gap(end: float, seconds: float) -> None:
    new = not LOG_FILE.exists()
    with LOG_FILE.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["start", "end", "seconds"])
        fmt = lambda t: dt.datetime.fromtimestamp(t).isoformat(timespec="seconds")
        w.writerow([fmt(end - seconds), fmt(end), round(seconds)])


def play(sound: str) -> None:
    if sound:
        subprocess.Popen(["afplay", f"/System/Library/Sounds/{sound}.aiff"])


def lock_screen() -> None:
    # Sleeps the display; with "Require password immediately" this locks the Mac.
    subprocess.run(["pmset", "displaysleepnow"], check=False)


class IdleNudgeApp(rumps.App):
    def __init__(self):
        super().__init__("Idle Nudge", title="◉", quit_button=None)
        self.settings = load_settings()
        self.tracker = Tracker(Config(
            idle_seconds=float(self.settings["idleSeconds"]),
            warn_lead=float(self.settings["warnLeadSeconds"]),
        ))
        self.status_item = rumps.MenuItem("Starting…")
        self.today_item = rumps.MenuItem("Idle today: 0s")
        self.saves_item = rumps.MenuItem("Nudges: 0 · saved: 0")
        self.snooze_items = [
            rumps.MenuItem("Away 15 min (no nudges)", callback=lambda _: self.snooze(15)),
            rumps.MenuItem("Away 30 min (no nudges)", callback=lambda _: self.snooze(30)),
            rumps.MenuItem("Away 60 min (no nudges)", callback=lambda _: self.snooze(60)),
        ]
        self.resume_item = rumps.MenuItem("Resume nudges", callback=self.resume)
        self.menu = [
            self.status_item,
            self.today_item,
            self.saves_item,
            None,
            rumps.MenuItem("Leaving now: lock screen", callback=lambda _: lock_screen()),
            *self.snooze_items,
            self.resume_item,
            None,
            rumps.MenuItem("Open idle log", callback=self.open_log),
            rumps.MenuItem("Edit settings", callback=self.open_settings),
            rumps.MenuItem("Quit", callback=rumps.quit_application),
        ]
        for item in (self.status_item, self.today_item, self.saves_item):
            item.set_callback(None)
        self.timer = rumps.Timer(self.on_tick, 1)
        self.timer.start()

    # ── menu actions ──
    def snooze(self, minutes: int):
        now = time.time()
        gap = self.tracker.snooze(now, minutes * 60)
        if gap:
            log_gap(now, gap)

    def resume(self, _):
        self.tracker.cancel_snooze()

    def open_log(self, _):
        if not LOG_FILE.exists():
            rumps.alert("Idle Nudge", "No idle gaps recorded yet.")
            return
        subprocess.run(["open", "-t", str(LOG_FILE)], check=False)

    def open_settings(self, _):
        subprocess.run(["open", "-t", str(CONFIG_FILE)], check=False)
        rumps.alert("Idle Nudge", "Restart Idle Nudge after saving the settings.")

    # ── polling ──
    def on_tick(self, _):
        now = time.time()
        tick = self.tracker.tick(
            now,
            probe.seconds_since_input(),
            probe.seconds_since_mouse_move(),
            probe.screen_locked(),
            dt.date.today(),
        )
        if tick.idle_gap:
            log_gap(now, tick.idle_gap)
        self.render(tick)
        if Event.WARN in tick.events:
            self.nudge(tick)

    def render(self, tick):
        st = tick.state
        stats = self.tracker.stats
        if st is State.WARNED:
            self.title = f"⚠ {int(tick.seconds_left)}s"
            hint = " — moving the mouse doesn't count, click or type" if tick.mouse_only else ""
            self.status_item.title = f"Idle in {int(tick.seconds_left)}s{hint}"
        elif st is State.IDLE:
            self.title = "◌ idle"
            self.status_item.title = "Idle now (Sensei is recording idle time)"
        elif st is State.AWAY:
            self.title = "◉"
            self.status_item.title = "Locked or asleep (not idle)"
        elif st is State.SNOOZED:
            left = (self.tracker.snooze_until or time.time()) - time.time()
            self.title = "☾"
            self.status_item.title = f"Away on purpose, {fmt_duration(left)} left"
        else:
            self.title = "◉"
            self.status_item.title = f"Active · idle in {fmt_duration(tick.seconds_left)} without input"
        self.today_item.title = f"Idle today: {fmt_duration(stats.idle_seconds)} in {stats.idle_gaps} gaps"
        self.saves_item.title = f"Nudges: {stats.nudges} · saved: {stats.saves}"

    def nudge(self, tick):
        play(self.settings.get("sound", ""))
        if not self.settings.get("popup", True):
            return
        lead = int(tick.seconds_left)
        choice = rumps.alert(
            title="Still there?",
            message=(f"Sensei marks this as idle in about {lead}s. "
                     "Click, type or scroll to keep it active.\n\n"
                     "Leaving? Lock the screen so it is recorded as locked, not idle."),
            ok="I'm here",
            cancel="Lock screen",
        )
        if choice == 0:  # cancel button
            lock_screen()


def main():
    IdleNudgeApp().run()


if __name__ == "__main__":
    main()
