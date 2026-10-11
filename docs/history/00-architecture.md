# Architecture

The whole of KitCheck on one page: what the parts are, where each runs, how data moves, and which decisions shaped it. The numbered docs go into each part; `09-notes.md` records why the main decisions were made.

## In one paragraph

A person orders a kit on a web page. For each item, a trained model drives the robot arm to pick one cube and put it in the tray. After every pick the system checks the result with signals the model does not control: what the gripper felt, and, if a fixed camera is available, what that camera sees. A missed pick is retried once; anything uncertain goes to the person. The models are taught by demonstration and trained on a cloud GPU in a loop short enough to repeat several times in a day.

## Two loops

KitCheck is two loops that share the robot.

### The teach loop: making a skill

```
   record demonstrations                 PC + arms         docs/03
            |
            v
   upload dataset  ----------------->  Hugging Face
            |
            v
   train (batch 8, checkpoint            cloud GPU         docs/04
   every 10,000 steps)                                     scripts/train.sh
            |
            v
   fetch a checkpoint  <------------   Hugging Face        scripts/push_checkpoint.sh
            |                                              scripts/get_model.sh
            v
   ten test picks, scored                PC + arm          scripts/try_model.sh
            |
     good enough? -- yes --> use it in the pack loop
            |
            no
            v
   record 15-20 demonstrations where it failed
            |
            v
   continue training from the model you have               scripts/retrain.sh
   (about 20 minutes), then fetch and test again
```

One pass takes roughly 45 minutes of recording once, then about 13 minutes to a first checkpoint and 8 minutes per checkpoint after that. Those timings come from another team's published log for the same setup; see `04-training.md`.

### The pack loop: filling an order

```
   order page  -->  runner
                      |
                      |  for each item in the order:
                      v
            (fixed camera only) is the pickup square stocked?  -- no --> ask for a restock
                      |
                      v
            run the item's model for a fixed time            lerobot-rollout + model
                      |
                      v
            grasp check: read the gripper's recorded
            positions from that run                          kitcheck/grasp.py
                      |
        +-------------+----------------+
        |             |                |
     missed        dropped          placed
        |             |                |
   retry once,    ask the      (fixed camera only) did the tray gain a cube?
   then ask       person             |              |
                                    yes             no
                                     |              |
                                 verified     ask the person
                      |
                      v
            every attempt is written to the run log; the page shows the counts

            optional: each of these steps is also spoken, from clips saved in advance
```

## The two check signals

| | Grasp check | Camera check |
|---|---|---|
| What it reads | The gripper's commanded and measured position, recorded by LeRobot on every frame | A fixed camera looking at the pickup squares and tray |
| Needs | Nothing extra. Works with any camera setup | A camera that does not move with the arm |
| Tells you | Picked up nothing; object slipped out; let go in the wrong place; held and let go at the tray | Square is empty; tray gained a cube; kit complete; item removed from a finished kit |
| Cannot tell | Whether the cube stayed in the tray after release | Anything about cubes that are stacked or hidden |
| Status | Written and tested on recordings (`kitcheck/grasp.py`) | Designed, not written (`06-check.md`) |

The grasp check is the base. The camera check uses the kit's stand camera, and the two then cross-check each other.

## Parts

| Part | File | Runs on | Status | Doc |
|---|---|---|---|---|
| Workcell | none (physical) | table | to build | 01 |
| Settings | `scripts/settings.env` | PC and cloud | written | 02 |
| Recording | LeRobot commands | PC | commands checked up to the hardware | 03 |
| Training | `scripts/train.sh`, `retrain.sh`, `resume.sh`, `overnight.sh` | cloud GPU | written, tested on a CPU with real data | 04 |
| Model transfer | `scripts/push_checkpoint.sh`, `scripts/get_model.sh` | cloud, PC | written, download tested | 04 |
| Training report | `scripts/train_report.py` | anywhere | written, tested on real logs | 04 |
| Model try-out | `scripts/try_model.sh` | PC | written, tested without a robot | 05 |
| Grasp check | `kitcheck/grasp.py` | PC | written, tested on real recordings | 06 |
| Camera check | `kitcheck/check.py` | PC | designed | 06 |
| Runner | `kitcheck/runner.py`, `kitcheck/skill.py` | PC | designed | 05 |
| Order page | `kitcheck/app.py`, `kitcheck/orders.py` | PC | designed | 07 |
| Run log | `kitcheck/runlog.py` | PC | designed | 05 |
| Voice (optional) | `kitcheck/voice.py` | PC to play; any online machine to make the clips | written, tested with stand-ins | 10 |

"Tested" never means tested on the arm or on the AMD machines. Nothing has been.

## Where things run

| Machine | Role |
|---|---|
| AMD Ryzen AI PC (Ubuntu) | Arms, cameras, recording, running models, all KitCheck software. No cloud calls at demo time. |
| AMD MI300X cloud GPU | Training only |
| Hugging Face | Datasets and models in transit between the two |
| Weights & Biases | Loss curves for the submission |
| ElevenLabs (optional) | Makes the voice clips once, ahead of time. Not used while the station runs. |
| MacBook | Writing code and docs |

## Data and where it lives

| Thing | Made by | Lives in |
|---|---|---|
| Demonstrations | Recording | `~/kitcheck_data/pick_<item>` on the PC; `<you>/kitcheck_pick_<item>` on Hugging Face |
| Training runs | `scripts/train.sh` | `outputs/train/<job>` and `logs/<job>.log` on the cloud machine |
| Dataset copy per run | `scripts/train.sh` | `datasets/<job>` on the cloud machine |
| Models | Training | `<you>/kitcheck_act_<item>...` on Hugging Face; `models/<item>/<label>/` on the PC |
| What a good pick feels like | `python -m kitcheck.grasp learn` | `data/grasp_<item>.json` on the PC |
| Test picks | `scripts/try_model.sh` | `data/eval/` and `data/trials.csv` on the PC |
| Orders and attempts | Runner | `data/runs.jsonl` on the PC |
| Voice clips (optional) | `python -m kitcheck.voice build` | `assets/voice/`, kept in git |
| App settings | You | `config.json` |
| Ports, IDs, cameras, training recipe | You | `scripts/settings.env` |

## Camera setups

The kit's listing shows a camera on the gripper and a second one on a stand, which is setup A. The design also works with the other two, in case the kit on the table differs. `01-workcell.md` has the details.

| Setup | Cameras | Model sees | Checks available |
|---|---|---|---|
| **A (the kit at the event)** | Gripper camera + the camera on the stand | `front`, `wrist` | Grasp and camera |
| B | Gripper camera only | `wrist` | Grasp only |
| C | Two fixed cameras | `top`, `side` | Grasp and camera |

With a third camera, still give the model only two: each extra camera adds about 60% to every training run.

## Names that must match everywhere

| Thing | Name |
|---|---|
| Items | `sensor`, `motor` |
| Arm IDs | `follower`, `leader` (the names they were calibrated under) |
| Camera names | From the chosen setup; identical in recording and at run time |
| Datasets | `<you>/kitcheck_pick_<item>` |
| Training jobs and models | `kitcheck_act_<item>`, then `kitcheck_act_<item>_v2`, ... |
| Task text | `Pick the <item> block and place it in the tray` |

## Decisions that shaped it

Each has an entry in `09-notes.md` with the evidence.

1. **Two small skills, not one large one.** ACT cannot be told which item to pick, and each skill can be taught and fixed independently.
2. **Checks the model does not control.** A learned model fails silently; the gripper's position and a fixed camera are separate evidence.
3. **Grasp check as the base.** It needs no extra hardware and no setup, and it catches a missed grasp directly. The camera check is built on top of it.
4. **Batch size 8 with frequent checkpoints.** A testable model in minutes, where the organizers' example recipe takes hours.
5. **A fresh copy of the dataset for every training run.** LeRobot silently reuses an old local copy otherwise.
6. **Continue from the existing model after adding demonstrations.** A fix costs about 20 minutes, not a full run.
7. **One process per pick.** Simple and robust; it costs a start-up delay on each pick.
8. **Everything local at demo time.** The demo does not depend on venue Wi-Fi. The optional voice keeps to this: its lines are made in advance with the ElevenLabs API and played from files.

## What is not built yet

The runner, the order page, the camera check and the run log are designs. The build order is in `README.md`.
