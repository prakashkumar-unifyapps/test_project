"""Reads input timing and lock state from macOS. Needs pyobjc-framework-Quartz.

CGEventSourceSecondsSinceLastEventType needs no Accessibility or Input Monitoring
permission: it only reports *when* the last event of a type happened, never its content.
"""
from __future__ import annotations

import Quartz

_STATE = Quartz.kCGEventSourceStateHIDSystemState

# The inputs Sensei counts as activity: clicks, key presses, scrolls.
_INPUT_TYPES = (
    Quartz.kCGEventKeyDown,
    Quartz.kCGEventLeftMouseDown,
    Quartz.kCGEventRightMouseDown,
    Quartz.kCGEventOtherMouseDown,
    Quartz.kCGEventScrollWheel,
)

_MOUSE_MOVE_TYPES = (
    Quartz.kCGEventMouseMoved,
    Quartz.kCGEventLeftMouseDragged,
    Quartz.kCGEventRightMouseDragged,
)


def _since(types) -> float:
    return min(Quartz.CGEventSourceSecondsSinceLastEventType(_STATE, t) for t in types)


def seconds_since_input() -> float:
    return _since(_INPUT_TYPES)


def seconds_since_mouse_move() -> float:
    return _since(_MOUSE_MOVE_TYPES)


def screen_locked() -> bool:
    session = Quartz.CGSessionCopyCurrentDictionary() or {}
    if session.get("CGSSessionScreenIsLocked"):
        return True
    # Display asleep counts as away too.
    return not Quartz.CGDisplayIsActive(Quartz.CGMainDisplayID()) or bool(
        Quartz.CGDisplayIsAsleep(Quartz.CGMainDisplayID())
    )
