# 7. Order page

The web page a person uses to order a kit and watch it being packed. It also shows the run log and, when a fixed camera is in use, holds the setup page for the camera check. This is what judges look at while the arm moves, so it should be readable from a couple of meters away.

Files: `kitcheck/app.py` (server), `kitcheck/orders.py` (parser), `kitcheck/templates/` and `kitcheck/static/` (pages). None of this code exists yet; this doc is the design.

## Done means

- Tapping "Full kit" starts an order with no terminal involved.
- Each item's state updates on the page within a second of changing.
- Help prompts appear with the right buttons.
- The success counts are visible on the same screen, with the latest camera-check image when a fixed camera is in use.

## How it is built

- One Python program using Flask, started with `python -m kitcheck.app` after loading the settings (`source scripts/settings.env`). It serves the pages and runs the order loop in a background thread.
- Plain HTML, CSS and JavaScript. No build step and no outside services.
- The page asks the server for the current state twice a second and redraws.
- It opens at `http://localhost:5000` on the PC. A phone on the same network can open it at the PC's address if the venue network allows that; do not depend on it.

## Order view

Top to bottom:

1. **Kit buttons.** One large button per kit in `config.json`: "Sensor kit", "Motor kit", "Full kit".
2. **Typed order.** A text box with the hint `2 sensors, 1 motor` and a "Pack" button.
3. **Current order.** One tile per item showing its name and state, in order. The item being worked on is highlighted.
4. **Message line.** One sentence saying what is happening or what is needed.
5. **Action buttons.** Shown only when a person must act (see below).
6. **Counts and recent attempts.** The three success numbers and the last ten or so log lines, each with what the gripper felt.
7. **Camera-check image** (fixed camera only). The latest image with the rectangles and readings drawn on it.

Rules:

- Show state with words as well as color.
- Disable the kit buttons and the text box while an order is running.
- Show a clear banner when fake robot mode is on or the check is off, so a test is never mistaken for a real run.

## Messages

| Situation | Message |
|---|---|
| Nothing running | Choose a kit |
| Skill running | Picking sensor (attempt 1) |
| After a run | Checking the pick |
| Missed, first time | Picked up nothing. Trying again. |
| Missed, second time | Picked up nothing twice. Is there a sensor on its square? |
| Dropped: slipped | The sensor slipped out of the gripper on the way. |
| Dropped: wrong place | The gripper let go away from the tray. |
| Dropped: time ran out | The arm was still holding the sensor when time ran out. |
| Robot error | The robot run failed. |
| All verified | Kit ready |

With a fixed camera, four more:

| Situation | Message |
|---|---|
| Square empty | Put a sensor on its square |
| Unconfirmed | The gripper let go at the tray, but I can't see a new sensor in it. |
| Item removed or kit check failed | Kit incomplete: missing 1 sensor |
| Tray emptied after "Kit ready" | Kit collected |

## Sound (optional)

With voice on (doc 10), each message above has a spoken version. By default the PC plays it. If the sound should come from the device showing the page, the page can play the same files:

- The state object carries `"say": {"id": 7, "file": "picking-sensor.mp3"}` for the latest line.
- The page plays `/voice/<file>` once for each new `id`.
- Browsers only allow sound after the person has tapped something, and the first kit button does that.
- Give the page a mute button, and play each line in one place only: the PC or the page.

## Action buttons

| When | Buttons |
|---|---|
| Waiting for a restock (fixed camera only) | Cancel order |
| Needs help | Retry, Mark as placed, Skip, Cancel order |
| Running | Cancel order |
| Kit ready or incomplete | New order |

## Order parser

Turns typed text into a list of item names for the runner.

### Rules

1. Lowercase the text.
2. If the whole text is a kit name, use that kit.
3. Otherwise split on commas, semicolons, `+` and the word "and".
4. Each piece is an optional count followed by an item word, or an item word followed by `x2`.
5. Counts can be digits or the words one to four. "a" and "an" mean one. No count means one.
6. Item words come from each item's `words` list in `config.json`.
7. Expand counts in the order written.
8. Apply the limits in `config.json`: at most two of one item and four items in total.

### Examples

| Typed | Result |
|---|---|
| `sensor` | `[sensor]` |
| `2 sensors, 1 motor` | `[sensor, sensor, motor]` |
| `a motor and a sensor` | `[motor, sensor]` |
| `motor x2` | `[motor, motor]` |
| `full kit` | `[sensor, motor]` |
| `3 sensors` | Error: "At most 2 of each item per kit." |
| `1 widget` | Error: "I don't know 'widget'. I can pack: sensor, motor." |
| (empty) | Error: "Type an order or choose a kit." |

Errors are shown under the text box. Nothing is sent to the runner until the whole order parses.

## Setup page

At `/setup`. Only needed for the camera check, so build it last and skip it without a fixed camera. It replaces image windows, which the PC's OpenCV build cannot open.

| Control | What it does |
|---|---|
| Take snapshot | Shows a fresh frame from the fixed camera |
| Mark region | Choose tray, sensor square or motor square, then click two opposite corners on the snapshot |
| Sample color | Choose an item, then click a cube of that type |
| Measure cube size | Records each cube's pixel count, once with the cubes in the tray and once on their squares |
| Live readout | Shows stocked or empty for each square and the cube-areas of each color in the tray, updating every second |
| Run one pick | Runs one skill without an order, for testing |
| Start fresh log | Archives the run log and starts a new one |

The setup page must refuse to open the camera while a robot run is in progress.

## Server interface

| Request | Purpose |
|---|---|
| `GET /` | Order view |
| `GET /setup` | Setup page |
| `GET /api/state` | Current state (below) |
| `POST /api/order` with `{"text": "..."}` or `{"kit": "Full kit"}` | Start an order. Returns the parsed list, an error message, or "Busy". |
| `POST /api/help` with `{"action": "retry"}` | Answer a help request: `retry`, `mark_placed`, `skip` or `cancel` |
| `POST /api/cancel` | Cancel the current order |
| `GET /api/check.jpg` | Latest check image |
| `GET /api/log?n=10` | Most recent log lines |
| `GET /api/setup/snapshot.jpg` | Fresh frame from the fixed camera |
| `POST /api/setup/regions`, `/sample`, `/measure` | Save setup values to `config.json` |
| `GET /api/setup/readout` | Current check readings |
| `POST /api/setup/run` with `{"item": "sensor"}` | Run one pick |
| `POST /api/log/reset` | Start a fresh log |

### State object

```json
{
  "order": {
    "id": 12,
    "state": "running",
    "items": [
      {"item": "sensor", "label": "Sensor", "state": "verified", "attempts": 1},
      {"item": "motor", "label": "Motor", "state": "awaiting_restock", "attempts": 0}
    ],
    "message": "Put a motor on its square",
    "needs": "restock"
  },
  "counts": {"attempted": 18, "first_try": 14, "after_retry": 17, "needed_person": 1},
  "fake_robot": false,
  "check_enabled": true
}
```

`needs` is `null`, `"restock"` or `"help"`, and decides which action buttons show. `order` is `null` when idle.

## Building it before the robot is free

With `"fake_robot": true` (doc 5) the whole page can be built and tested on the Mac: start an order, let recorded folders stand in for robot runs, and watch the states change. Build in this order:

1. Parser, with the examples above as tests
2. Order view against a runner that only waits and reports states
3. Help prompts
4. Counts and log display
5. Setup page and restock prompt (fixed camera only)

## Testing

| Test | Pass |
|---|---|
| Every row of the parser examples | Matches |
| Tap a kit while one is running | Refused with "Busy"; buttons are disabled |
| Each message in the table above | Appears in the right situation in fake robot mode |
| Reload the page mid-order | Shows the order in progress, not a blank page |
| Unplug the network | Page and orders still work |

## Cut-down version

If the page is not ready, the runner can be driven from a terminal: `python -m kitcheck.runner "2 sensors, 1 motor"`, printing each state as a line of text. Build this first; it is also the quickest way to test the order loop.
