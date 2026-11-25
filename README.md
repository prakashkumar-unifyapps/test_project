# Idle Nudge

A macOS menu-bar app that cuts down the idle time Sensei records.

Sensei marks any gap of 5 minutes or more without a click, key press or scroll as idle,
counted from the last input. Moving the mouse does not count. Idle Nudge watches the same
inputs and:

- **Warns you 60 s before the cutoff.** You get a sound, a countdown in the menu bar and a
  "Still there?" pop-up. Clicking **I'm here** is a real click, so the gap stays active.
- **Tells you when only the mouse is moving.** Movement doesn't count, so it asks you to click or type.
- **Locks the screen when you're leaving.** Sensei records a locked screen as "locked",
  not idle. Use the pop-up's **Lock screen** button or **Leaving now: lock screen** in the menu.
- **Has "Away 15/30/60 min".** Turns nudges off for lunch or a meeting away from the desk.
- **Shows your idle time.** The menu has idle time today, the number of gaps, and
  nudges vs saves. Each gap is logged to `~/.idle-nudge/idle-gaps.csv`.

It never fakes input. Every gap it saves comes from you actually clicking, typing or scrolling.

## Run

```bash
python3 -m pip install -r requirements.txt
```

```bash
python3 -m idle_nudge
```

It doesn't need Accessibility or Input Monitoring permission. It only reads *when* the last
input happened (`CGEventSourceSecondsSinceLastEventType`), never what was typed.

## Settings

`~/.idle-nudge/config.json` is created on first run. Restart the app after you edit it.

| Key | Default | Meaning |
|---|---|---|
| `idleSeconds` | 300 | Keep this equal to Sensei's `capture.idleSeconds` |
| `warnLeadSeconds` | 60 | How long before the cutoff to nudge |
| `sound` | `Glass` | A name from `/System/Library/Sounds`, or `""` for no sound |
| `popup` | `true` | Show the "Still there?" pop-up; `false` shows only the sound and the menu-bar countdown |

## Tests

The idle logic (`idle_nudge/core.py`) is plain Python and runs anywhere:

```bash
python3 -m unittest -v
```

## Known limits

- On calls or while watching video with no input, you still get a nudge after 4 minutes.
  Use "Away" mode, or click once. Sensei's longer buffer for calls (AS-62) isn't built yet.
- While the pop-up is open, the menu-bar countdown pauses (it's a modal alert). The idle state
  catches up as soon as the pop-up is dismissed.
- The pop-up briefly takes focus, so Sensei may record a second or two under Python.
- **Lock screen** puts the display to sleep. It locks only if "Require password after screen
  saver begins or display is turned off" is set to *Immediately*.
