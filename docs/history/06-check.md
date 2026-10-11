# 6. Check

How KitCheck finds out what happened after each pick, using signals the model does not control. There are two, and they are independent:

| | A. Grasp check | B. Camera check |
|---|---|---|
| Reads | The gripper's commanded and measured position in the run's recording | A fixed camera looking at the squares and tray |
| Needs | Nothing extra | A camera that does not move with the arm (setups A and C in doc 1) |
| Answers | Did it pick the cube up? Did it slip? Did it let go at the tray? | Is the square stocked? Did the tray gain a cube? Is the kit complete? |
| Status | Written and tested on recordings: `kitcheck/grasp.py` | Design only: `kitcheck/check.py` |

The grasp check is the base and always runs. Build the camera check second; it uses the kit's stand camera (`front`).

---

## Part A: grasp check

### Done means

- `python -m kitcheck.grasp inspect` on your first five demonstrations ends with "Usable".
- Each item has a reference file, `data/grasp_<item>.json`.
- In ten test picks, the verdict never says "placed" for a cube that was not picked up.

### How it works

LeRobot records two numbers for the gripper on every frame: where it was told to go, and where it actually was. Both are on a scale from 0 (closed) to 100 (open).

- **Closing on a cube:** the gripper cannot reach the commanded position, so the measured value stays above it for as long as the cube is held. That stretch is a "hold".
- **Closing on nothing:** the two values agree. No hold.
- **The cube slips out:** the gap vanishes while the gripper is still told to stay closed.
- **Letting go on purpose:** the gripper is told to open. The base joint's angle at that moment says which way the arm was pointing, and the demonstrations say which way the tray is.

### Verdicts

| Verdict | Meaning | What the runner does |
|---|---|---|
| `placed` | Held the cube, then let go on purpose at the tray | Verified (or cross-checked by the camera) |
| `missed` | Never held anything | Retry once, then ask |
| `dropped` | Held it, then it slipped, or it was released somewhere else, or it was still held when time ran out | Ask |
| `held` | Held and released, but no reference file exists to say where the tray is | Treated as placed; make the reference file |

### Commands

```shell
# After the first five demonstrations: is the signal there?
python -m kitcheck.grasp inspect ~/kitcheck_data/pick_sensor

# After the last demonstration: save what a good pick looks like
python -m kitcheck.grasp learn ~/kitcheck_data/pick_sensor --out data/grasp_sensor.json

# Judge one run by hand (scripts/try_model.sh does this for you)
python -m kitcheck.grasp check data/eval/<run folder> --ref data/grasp_sensor.json
```

Run them from the project folder. They need the Python environment LeRobot is installed in.

### Reading `inspect`

```
episode    held    gap  picked at  let go at  ended by
      0    3.5s   11.4       -7.4      -30.2  opening the gripper
      1    3.9s   13.7       -6.6      -33.5  opening the gripper
```

- **held:** how long the cube was in the gripper.
- **gap:** how far the measured position stayed above the commanded one. Bigger is clearer.
- **picked at / let go at:** the base joint's angle at each end of the hold. These two columns should be clearly different from each other, and each should be nearly the same from one demonstration to the next.
- **ended by:** every demonstration should say "opening the gripper".

### What makes it work

| Requirement | Why | Where it is handled |
|---|---|---|
| Squeeze the leader's handle fully closed in every demonstration | If the gripper is only told to close to about the cube's width, there is no gap to see | Doc 3 |
| A firm cube | A very soft cube squashes until the gap is small | Doc 1 |
| Pickup squares well to the side of the tray | The arm's direction is how "at the tray" is told from "somewhere else" | Doc 1 |
| Open the handle clearly to release | A deliberate release is recognized by the gripper being told to open | Doc 3 |

### Evidence so far

Checked before the event on 20 public demonstrations from two teams at AMD's Tokyo hackathon (real SO-101 arms):

| Case | Result |
|---|---|
| Real successful picks | 19 of 20 read as placed |
| The one that did not | The operator barely closed the handle; the gap was about 2 |
| Gap while holding | About 8 to 15; an empty closed gripper read 0.1 to 0.3 |
| Empty grasps, simulated by editing those recordings | 20 of 20 read as missed |
| Slips part-way through the carry, simulated the same way | 75 of 76 read as not placed |

The failures were simulated, not recorded on a robot. `tests/test_grasp.py` runs the same cases on made-up recordings: `python tests/test_grasp.py`.

### Limits

- **It cannot see the tray.** A cube that bounces out after a clean release reads as placed. Use a shallow tray with a lip, and release low.
- **It cannot tell an empty square from a missed grasp.** Both read as missed. Without a camera, the runner retries once and then asks.
- **Replayed demonstrations leave no recording,** so there is nothing to check.

### Settings

The defaults in `kitcheck/grasp.py` come from the evidence above. `learn` adapts two of them to your demonstrations and saves them in the reference file.

| Setting | Default | Meaning |
|---|---|---|
| `min_gap` | 4.0, then 40% of your demonstrations' typical gap | How far measured must stay above commanded to count as blocked |
| `min_hold_s` | 0.5 | Holds shorter than this are ignored |
| `pan_tolerance` | At least 6, wider if your demonstrations vary | How far from the tray direction still counts as "at the tray" |

---

## Part B: camera check

Only with a fixed camera. This part is a design; the code does not exist yet.

### Done means

- With a cube on a square, the check says "stocked"; with the square empty, "empty". Ten out of ten each way.
- Putting one cube in the tray reads as a gain of about one cube. Ten out of ten.
- It still gets these right immediately after a robot run.

### The three questions

| Question | Used for | Answer |
|---|---|---|
| Is this item's square stocked? | Before a pick; telling an empty square from a miss | Yes or no |
| How much of this item's color is in the tray? | Compare before and after a pick | A number in cube-areas (1.0 is one cube) |
| Does the tray hold the whole kit? | After the last item; watching a finished kit | Complete, incomplete with a list, or empty |

### How it works

Plain color counting in fixed rectangles. Nothing is learned.

1. Open the fixed camera at the same size LeRobot uses.
2. Read and throw away the first ten frames while the camera's exposure settles.
3. For each of five frames, convert to HSV color and, inside each rectangle, count the pixels that fall in the item's color range. A small clean-up step removes speckle.
4. Take the middle value of the five counts.
5. Divide by the size of one cube in that rectangle to get cube-areas.
6. Save the frame with the rectangles and numbers drawn on it, for the order page.
7. Close the camera so the next robot run can use it.

### Decisions

| Decision | Rule | Setting |
|---|---|---|
| Square is stocked | Item color in its square is at least half a cube | `present_fraction: 0.5` |
| Tray gained a cube | Tray reading rose by at least half a cube of that color | `landed_fraction: 0.5` |
| Kit complete | For each item type, tray holds at least the ordered count minus half a cube | same threshold |
| Tray empty | Under a quarter of a cube of every color | `empty_fraction: 0.25` |

When watching a finished kit, two looks in a row must agree before the order changes state. A hand reaching into the tray would otherwise trigger a false "incomplete".

### Settings

These live in the `camera_check` section of `config.json` and are written by the setup page.

```json
"camera_check": {
  "enabled": true,
  "camera": "front",
  "regions": {
    "tray":          [210, 150, 220, 180],
    "square_sensor": [ 90, 200,  70,  70],
    "square_motor":  [480, 200,  70,  70]
  },
  "colors": {
    "sensor": {"low": [ 95, 80, 60], "high": [125, 255, 255]},
    "motor":  {"low": [ 20, 80, 80], "high": [ 35, 255, 255]}
  },
  "unit_area": {
    "sensor": {"tray": 1450, "square_sensor": 1380},
    "motor":  {"tray": 1500, "square_motor": 1420}
  },
  "present_fraction": 0.5,
  "landed_fraction": 0.5,
  "empty_fraction": 0.25,
  "frames": 5,
  "warmup_frames": 10
}
```

- Regions are `[x, y, width, height]` in pixels of the camera image.
- Colors are OpenCV HSV ranges: hue 0–179, saturation and value 0–255.
- `unit_area` is the pixel count of one cube, measured separately in each rectangle, because a camera that looks at an angle sees the same cube at different sizes in different places.
- Every number above is a placeholder. The real values come from the setup steps below.

### Setup, once the camera is fixed

About ten minutes on the setup page:

1. Put the arm in its rest pose and take a snapshot.
2. Mark the three rectangles: the tray and each pickup square. Make the squares' rectangles a little larger than the taped squares.
3. Put one cube of each type in the tray and click each one. The page samples its color and builds a range around it: hue plus or minus 10, and saturation and value from about 60 below the sample up to the maximum. These widths are starting points.
4. Measure cube size: with one cube of each type in the tray, then with one on each square.
5. Watch the live readout while moving cubes between the squares and the tray. Each cube should read close to 1.0 wherever it is, and empty areas close to 0.

Redo steps 3–4 if the lighting changes. Redo step 2 if the camera or the tray moves.

### Choosing item colors

- Pick two colors far apart in hue, such as blue and yellow.
- Avoid red. In OpenCV's hue scale red sits at both ends, so it needs two ranges.
- Avoid any color that appears on the arm, the tray, the surface or the tape.
- Matte beats shiny. Glare reads as white.

### Trust test

Run this before letting the runner rely on the camera check, and again on the morning of day 2.

| Trial | Repeat | Expected |
|---|---|---|
| Cube on its square | 10 times per item, different positions | Stocked |
| Square empty | 10 times per item | Empty |
| Add one cube to the tray, varied tray contents | 10 times per item | Gain between about 0.7 and 1.3 |
| Add nothing | 10 times | Gain near 0 |
| Same trials straight after a robot run | 5 times | Same answers |

If any trial fails, fix the cause using the table below before moving on. A check that is wrong one time in ten will make the demo worse, not better.

### What goes wrong

| Symptom | Likely cause | Fix |
|---|---|---|
| A placed cube reads as no gain | It landed on another cube | Give each item its own tray half; keep kits to two of each type; the runner asks a person |
| Readings jump between looks | Camera exposure still settling, or someone's shadow | Raise `warmup_frames`; keep people out of the light |
| Everything reads low after a while | Lighting changed | Re-sample colors and re-measure cube size |
| A color is found where there is no cube | Something else in view matches it | Tighten the range, or shrink the rectangle, or change the item color |
| The arm is counted | The arm is over a rectangle at rest | Move the rest pose or the rectangles |
| "Camera busy" or no frame | The robot run has not released the camera yet | Wait and try again, up to three times |
| Rectangles are off | The camera or the tray moved | Re-mark the regions |

### What the camera check does not do

- It does not find cubes for the arm. The models do that from the camera images.
- It cannot count cubes that are stacked or hidden.
- It does not recognize objects. Anything of the right color in the right rectangle counts.

---

## If a judge asks why the checks are so simple

They are simple on purpose. A check is only useful if it fails differently from the thing it checks. The gripper's position record and a color count share nothing with the model's vision, so when the model is fooled, they are not.

## Cut-down versions

| If | Then |
|---|---|
| No fixed camera | Grasp check only. No stock check, no kit watching. |
| The camera check is unreliable | Set `"enabled": false`; the grasp check still runs |
| The grasp signal is weak with your cubes | Use firmer cubes; if that fails, rely on the camera check alone |
| Both are unavailable | Picks run for a fixed time with no verification, and the project is two pick-and-place skills behind an order page |
