# 5. Runner

The runner turns an order into robot runs. It has two jobs: launch one skill, and work through an order item by item, deciding after each run whether to move on, retry or ask for help. It also writes the run log.

| Piece | File | Status |
|---|---|---|
| Try one model by hand | `scripts/try_model.sh` | Written; tested without a robot |
| Launch one skill from code | `kitcheck/skill.py` | Written; tested with a fake run and a real launch on a fake port |
| Order loop, from a terminal | `kitcheck/runner.py` | Written; grasp check, one retry on a miss, asks in the terminal otherwise. No camera check yet |
| Run log | `data/runs.jsonl`, written by `kitcheck/runner.py` | Written; `python -m kitcheck.runner --summary` prints the counts |

From a terminal, with every ring on its spot and the arm at rest:

```shell
python -m kitcheck.runner "Sort all"            # red, purple, teal in turn
python -m kitcheck.runner teal                  # one item
python -m kitcheck.runner red --label 020000    # a downloaded checkpoint
python -m kitcheck.runner --summary             # first-try and after-retry counts
```

## Done means

- `bash scripts/try_model.sh sensor` makes the arm pick one sensor cube, return to rest, and prints what the gripper felt.
- An order of two items runs start to finish from the order page with no typing in a terminal.
- A missed pick is retried once without anyone touching anything.
- Every attempt appears in the run log.

---

## Part A: launching one skill

### By hand

Load the settings (`source scripts/settings.env`), put a cube on its square and the arm in the rest pose, then:

```shell
bash scripts/try_model.sh sensor            # the final model
bash scripts/try_model.sh sensor 020000     # a checkpoint
bash scripts/try_model.sh sensor v2 12      # the v2 model, 12-second time limit
```

It runs the model once, saves the recording under `data/eval/`, prints the grasp check's verdict, adds a line to `data/trials.csv` and shows the running score for that model. This is the tool for the ten-pick tests in doc 4. With voice on (doc 10), it also says the verdict aloud.

### What it runs

Running a trained model is `lerobot-rollout`. The guide's "inference evaluation" command used `lerobot-record` with a model in place of the leader arm, but from LeRobot v0.6 `lerobot-record` refuses a model. The episodic strategy behaves like the old command: it runs the model for a time limit and records the run.

```shell
lerobot-rollout \
  --strategy.type=episodic \
  --robot.type=so101_follower \
  --robot.port=$FOLLOWER_PORT \
  --robot.id=$FOLLOWER_ID \
  --robot.cameras="$CAMERAS" \
  --dataset.single_task="Pick the sensor block and place it in the tray" \
  --dataset.repo_id=local/rollout_kitcheck_red_20261010_153012 \
  --dataset.root=data/eval/sensor_final_20261010_153012 \
  --dataset.episode_time_s=15 \
  --dataset.num_episodes=1 \
  --dataset.push_to_hub=false \
  --policy.path=models/sensor/final/pretrained_model \
  --play_sounds=false
```

### Why each setting is there

| Setting | Reason |
|---|---|
| `--strategy.type=episodic` | Records the run. The `base` strategy records nothing, so the grasp check would have nothing to read. |
| `--dataset.repo_id=local/rollout_...` | `lerobot-rollout` in v0.6.2 refuses a recording name that does not start with `rollout_` (it checks only after connecting the arm). The name must have the form `something/name`. |
| `--dataset.root=...` | Where the run's recording goes. It must be a folder that does not exist yet, so every run needs a new one. A run that fails still leaves its folder behind. |
| `--dataset.episode_time_s=15` | The time limit. The model runs for this long, then the command saves its recording and exits. |
| `--dataset.num_episodes=1` | One pick. With one episode there is no reset pause afterwards. |
| `--dataset.push_to_hub=false` | Uploading is on by default and would stall every pick. |
| `--play_sounds=false` | Spoken prompts are on by default and add delay. |
| `--robot.cameras="$CAMERAS"` | The same camera setup, with the same names, as when recording. A mismatch stops the model loading its inputs. |
| `--robot.id` | Must match the ID used at calibration. |

The recording is not wasted: it holds the gripper's commanded and measured position for every frame, which is what the grasp check reads (doc 6).

### What `skill.py` will do

The same as `try_model.sh`, callable from the runner:

1. Build the command above for the requested item from `config.json` and the loaded settings.
2. Name the output folder with the item and a timestamp.
3. Hold the camera lock so the camera check cannot open a camera during the run.
4. Start the command, wait for it to exit, and save its output to a log file next to the run folder.
5. Return the run folder, or `error` if the command fails or runs well past its time limit.
6. Wait about a second after exit so the cameras are released.

### Things to know about a run

- **The arm goes limp between runs.** LeRobot switches the motors off briefly on connect and again on disconnect. The arm must start and end in the stable rest pose from doc 1.
- **The model does not know it has finished.** It keeps running until the time limit. That is why each demonstration ends with a hold at the rest pose (doc 3), and why the time limit should be a few seconds longer than a normal pick.
- **Start-up time is unknown.** Each run loads the model and reconnects the arm and cameras. Measure the time from launch to first movement and from launch to exit, and write both here: `first movement: __ s, total: __ s`.
- **Arrow keys and Esc are live during a run.** LeRobot listens for them anywhere on the PC. The right arrow ends a run early, which is handy once the arm has parked, but an accidental press will cut a pick short.

### Setting the time limit

Start with 15 seconds. Watch ten runs. Set the limit to the slowest successful pick plus about three seconds. Too short cuts picks off; too long makes the demo drag.

### Fallback: replay

If a model is unreliable at demo time, a recorded demonstration can be replayed. It only works with the cube exactly where it was in that recording.

```shell
lerobot-replay \
  --robot.type=so101_follower \
  --robot.port=$FOLLOWER_PORT \
  --robot.id=$FOLLOWER_ID \
  --dataset.repo_id=${HF_USER}/kitcheck_pick_sensor \
  --dataset.root=${HOME}/kitcheck_data/pick_sensor \
  --dataset.episode=0 \
  --play_sounds=false
```

`skill.py` should support this as a per-item option in `config.json` (`"mode": "replay"` with an episode number), so the rest of the system does not change. A replay leaves no recording, so there is no grasp check for it.

---

## Part B: the order loop

### Inputs and outputs

- **Input:** a list of item names from the order parser, for example `["sensor", "motor"]`.
- **Output:** a state object the order page polls, and one run-log line per attempt.
- **One order at a time.** A new order while one is running is refused with "Busy".

### Packing one item

The grasp check always runs. The lines marked *camera* only run when a fixed camera is set up (doc 6).

```
attempts = 0
repeat:
    camera: wait until the item's square is stocked      (state: awaiting_restock)
    camera: before = how much of this item's color is in the tray
    attempts += 1
    run the skill                                        (state: picking)
    grasp = what the gripper felt in that run            (state: checking)
            placed, missed or dropped
    camera: after = tray reading; gained = after - before is at least half a cube
    write a run-log line

    if the run failed:                 -> "error":       ask for help
    if grasp is missed, first time:    -> "missed":      retry automatically
    if grasp is missed, second time:   -> "missed":      ask for help
    if grasp is dropped:               -> "dropped":     ask for help
    if grasp is placed:
        no camera:                     -> verified
        camera and the tray gained:    -> verified
        camera and no gain:            -> "unconfirmed": ask for help
```

**Why a miss is retried and a drop is not.** After a miss the cube is still on its square, so trying again is safe. After a drop the cube is somewhere on the table or still in the gripper, and another pick would not find it.

**Why "unconfirmed" goes to a person.** The gripper says it let go at the tray but the camera sees no new cube. It may have bounced out, or landed on another cube where the camera cannot count it. Retrying could pack one too many.

### Asking for help

The order pauses and the page shows what happened and four buttons:

| Button | Effect |
|---|---|
| Retry | Start this item again |
| Mark as placed | A person put it in the tray; continue. Logged as manual. |
| Skip | Leave this item out; continue |
| Cancel order | Stop the order |

### After the last item

- **Without a fixed camera:** the order is `done` when every item is verified, and the page shows "Kit ready".
- **With a fixed camera:** run the kit check first (does the tray hold at least the ordered number of each item type?). If it fails, the order is `incomplete` and the page lists what is missing.

### Watching a finished kit (fixed camera only)

While an order is `done`, the runner looks at the tray every couple of seconds:

- **Everything gone:** the kit was collected. Go back to idle.
- **Some items gone:** the order becomes `incomplete`. If `auto_repack` is on, the missing items are packed again.

### States

| Item state | Meaning |
|---|---|
| `waiting` | Not started |
| `awaiting_restock` | Its square is empty; waiting for a person (fixed camera only) |
| `picking` | The skill is running |
| `checking` | The run ended; reading the gripper record and the tray |
| `verified` | Confirmed |
| `needs_help` | Paused for a person |
| `skipped` | Left out by a person |

| Order state | Meaning |
|---|---|
| `idle` | No order |
| `running` | Working through items |
| `needs_help` | Paused on one item |
| `done` | Kit ready |
| `incomplete` | Kit check failed, or an item was removed |
| `cancelled` | Stopped by a person |

### Speaking (optional)

With voice on, the runner says each step aloud from saved clips (doc 10). One call per state change:

| When | Phrase |
|---|---|
| Order accepted | `order_started` |
| Skill starts | `picking` |
| Item verified | `verified` |
| Missed, first time | `missed_retry` |
| Missed, second time | `missed_twice` |
| Dropped | `dropped_slipped`, `dropped_wrong_place` or `dropped_timeout`, from the grasp check's reason |
| Run failed | `error` |
| Square empty (camera check) | `restock` |
| Unconfirmed (camera check) | `unconfirmed` |
| Kit ready | `kit_ready` |

`key_for_verdict()` in `kitcheck/voice.py` picks the phrase from a grasp verdict. `Voice.say()` never raises and never waits for the network, so speech cannot hold up or break an order.

### Threads and the camera

- The order loop runs in one background thread inside the web server.
- One lock guards the cameras. The camera check takes it for each look; `skill.py` takes it for a whole run. Nothing else opens a camera.

---

## Part C: the run log

One line of JSON per attempt, appended to `data/runs.jsonl`:

```json
{"time": "2026-10-10T15:30:27", "order": 12, "item": "sensor", "attempt": 1,
 "outcome": "placed", "hold_s": 3.1, "gap": 12.4, "tray_gain": 0.94,
 "run_s": 21.3, "model": "models/sensor/final"}
```

`outcome` is one of `placed`, `missed`, `dropped`, `unconfirmed`, `error`, `manual`, `skipped`. `hold_s` and `gap` come from the grasp check. `tray_gain` is in cube-areas and is only present with a fixed camera.

### Success counts

| Number | Definition |
|---|---|
| First-try success | Items verified on attempt 1, out of all items attempted |
| Success after retry | Items verified on attempt 1 or the automatic retry, out of all items attempted |
| Needed a person | Items that ended as `manual` or `skipped` |

Show all three. Quoting only the after-retry number would overstate the models.

Start a fresh log file before the judged session so the numbers on screen come from the final models.

---

## Settings

Two files, with no overlap.

**`scripts/settings.env`** holds what the machine needs: ports, arm IDs, the camera setup and the training recipe. Load it in the terminal before starting anything (`source scripts/settings.env`); the app reads the same values from the environment.

**`config.json`** holds what the app needs:

```json
{
  "items": {
    "sensor": {
      "label": "Sensor",
      "words": ["sensor", "sensors"],
      "task": "Pick the sensor block and place it in the tray",
      "mode": "model",
      "model": "models/sensor/final/pretrained_model",
      "grasp_reference": "data/grasp_sensor.json",
      "run_time_s": 15
    },
    "motor": {
      "label": "Motor",
      "words": ["motor", "motors"],
      "task": "Pick the motor block and place it in the tray",
      "mode": "model",
      "model": "models/motor/final/pretrained_model",
      "grasp_reference": "data/grasp_motor.json",
      "run_time_s": 15
    }
  },
  "kits": {
    "Sensor kit": ["sensor"],
    "Motor kit": ["motor"],
    "Full kit": ["sensor", "motor"]
  },
  "limits": {"max_items_per_order": 4, "max_per_item": 2, "auto_retries": 1},
  "auto_repack": true,
  "camera_check": {"enabled": false},
  "voice": {"enabled": false, "voice_id": "", "model_id": "eleven_multilingual_v2", "clips": "assets/voice"},
  "fake_robot": false
}
```

This file now exists in the project root with these values.

The `camera_check` section grows once the setup page has been used; doc 6 lists its fields. Leave it off until the camera check is built. The `voice` section is the optional spoken status; doc 10 explains it.

## Working without the robot

- **`scripts/try_model.sh`:** set `KITCHECK_FAKE_RUN=<a recorded LeRobot folder>` and it uses that recording in place of a real run. This is how its scoring was tested.
- **The runner:** with `"fake_robot": true`, `skill.py` waits a few seconds and returns a recorded folder without touching the arm. You move cubes by hand to play the robot's part. This lets the order page and runner be built on the Mac or while the arm is busy.

## Testing

| Test | How | Pass |
|---|---|---|
| One skill by hand | `bash scripts/try_model.sh sensor` | Cube in tray, arm back at rest, verdict "placed" |
| Ten runs | The same, ten times, varying cube position and tray contents | 8 or more in the tray |
| Gripper agrees with you | Compare each verdict with what you saw | No "placed" for a cube that was never picked up |
| Steal the cube | Take the cube off its square just before the gripper closes | Verdict "missed" |
| Order loop, fake robot | Recorded folders stand in for runs | States change as described above |
| Retry | Fake robot returns a "missed" recording | One automatic retry, then a help request |

## Later, only if there is time

Keeping both models loaded in one long-running process would remove the start-up delay on every pick. It means writing a control loop against LeRobot's Python interface. It is not needed for the demo and should not be started on day 1.
