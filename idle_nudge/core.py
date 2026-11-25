"""Idle-gap state machine. Pure Python, no macOS imports, so it can be unit-tested anywhere.

Mirrors how Sensei records idle time: a gap of `idle_seconds` or more without a click,
key press or scroll is idle, counted from the last input. Mouse movement is not input.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import Enum


class State(Enum):
    ACTIVE = "active"      # recent input
    WARNED = "warned"      # nudge shown, idle threshold not yet reached
    IDLE = "idle"          # past the threshold: Sensei is recording idle time
    AWAY = "away"          # screen locked or Mac asleep: Sensei records "locked"/"asleep"
    SNOOZED = "snoozed"    # user said they are away on purpose; no nudges


class Event(Enum):
    WARN = "warn"            # show the nudge
    SAVED = "saved"          # input arrived after a nudge, before the threshold
    IDLE_STARTED = "idle_started"
    IDLE_ENDED = "idle_ended"


@dataclass
class Config:
    idle_seconds: float = 300.0   # Sensei capture.idleSeconds
    warn_lead: float = 60.0       # nudge this many seconds before the threshold
    mouse_hint_window: float = 10.0  # mouse moved this recently -> "moving the mouse doesn't count"
    sleep_gap: float = 15.0       # wall-clock jump between ticks larger than this = Mac was asleep

    @property
    def warn_at(self) -> float:
        return max(0.0, self.idle_seconds - self.warn_lead)


@dataclass
class DayStats:
    day: dt.date
    idle_seconds: float = 0.0
    idle_gaps: int = 0
    nudges: int = 0
    saves: int = 0


@dataclass
class Tick:
    events: list[Event]
    state: State
    seconds_left: float          # until Sensei marks this gap idle (0 when idle)
    mouse_only: bool             # mouse is moving but no counted input
    idle_gap: float | None = None  # length of a gap that just ended, if any


@dataclass
class Tracker:
    config: Config = field(default_factory=Config)
    state: State = State.ACTIVE
    snooze_until: float | None = None
    _last_now: float | None = None
    _last_age: float = 0.0
    stats: DayStats | None = None

    def snooze(self, now: float, seconds: float) -> float | None:
        """Stop nudging for `seconds`. Returns the length of an idle gap this closed, if any."""
        gap = None
        if self.state is State.IDLE and self.stats is not None:
            gap = self._close_gap([])
        self.snooze_until = now + seconds
        self.state = State.SNOOZED
        return gap

    def cancel_snooze(self) -> None:
        self.snooze_until = None
        if self.state is State.SNOOZED:
            self.state = State.ACTIVE

    def tick(
        self,
        now: float,
        input_age: float,
        mouse_age: float,
        locked: bool,
        today: dt.date,
    ) -> Tick:
        """Advance one poll.

        now        wall-clock seconds (time.time())
        input_age  seconds since the last click, key press or scroll
        mouse_age  seconds since the mouse last moved
        locked     screen is locked or display asleep
        """
        cfg = self.config
        events: list[Event] = []
        gap: float | None = None

        if self.stats is None or self.stats.day != today:
            self.stats = DayStats(day=today)
        stats = self.stats

        slept = self._last_now is not None and now - self._last_now > cfg.sleep_gap
        had_input = input_age + 0.5 < self._last_age or input_age < 1.0

        if self.snooze_until is not None and now >= self.snooze_until:
            self.snooze_until = None
            if self.state is State.SNOOZED:
                self.state = State.ACTIVE

        if locked or slept:
            if self.state is State.IDLE:
                gap = self._close_gap(events)
            self.state = State.AWAY
        elif self.state is State.AWAY:
            # Back from lock/sleep: start fresh, the away time was never idle.
            self.state = State.SNOOZED if self.snooze_until else State.ACTIVE
            if input_age >= cfg.idle_seconds and not self.snooze_until:
                self.state = State.IDLE
                events.append(Event.IDLE_STARTED)
        elif self.state is State.SNOOZED:
            if had_input and self.snooze_until is None:
                self.state = State.ACTIVE
        elif self.state is State.ACTIVE:
            if input_age >= cfg.idle_seconds:
                self.state = State.IDLE
                events.append(Event.IDLE_STARTED)
            elif input_age >= cfg.warn_at:
                self.state = State.WARNED
                stats.nudges += 1
                events.append(Event.WARN)
        elif self.state is State.WARNED:
            if had_input:
                self.state = State.ACTIVE
                stats.saves += 1
                events.append(Event.SAVED)
            elif input_age >= cfg.idle_seconds:
                self.state = State.IDLE
                events.append(Event.IDLE_STARTED)
        elif self.state is State.IDLE:
            if had_input:
                gap = self._close_gap(events)
                self.state = State.ACTIVE

        self._last_now = now
        self._last_age = input_age

        seconds_left = max(0.0, cfg.idle_seconds - input_age)
        if self.state is State.IDLE:
            seconds_left = 0.0
        mouse_only = (
            self.state in (State.WARNED, State.IDLE)
            and mouse_age < cfg.mouse_hint_window
        )
        return Tick(events, self.state, seconds_left, mouse_only, gap)

    def _close_gap(self, events: list[Event]) -> float:
        # The gap runs from the last input to the latest age we saw before input/lock.
        gap = self._last_age
        assert self.stats is not None
        self.stats.idle_seconds += gap
        self.stats.idle_gaps += 1
        events.append(Event.IDLE_ENDED)
        return gap


def fmt_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m"
    if m:
        return f"{m}m {s:02d}s" if m < 10 else f"{m}m"
    return f"{s}s"
