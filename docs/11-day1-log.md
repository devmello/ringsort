# 11. Day 1 log: what was tried, what worked, what did not

A record of day 1 (10 October 2026), written at 21:05 from the scripts' logs, the run recordings and `data/trials.csv`. Numbers are measured on this setup unless they say otherwise. `history/09-notes.md` holds the decisions worth telling judges; this is the full lab notebook behind them.

## Where things stand at 21:05

| Part | State |
|---|---|
| Task | Pick a colored ring (red, purple, teal) from anywhere in its pick area and drop it in its own cup. One ACT skill per color. |
| Red data | 47 takes, all with a clear grasp signal, on Hugging Face (`varunsatish2017/kitcheck_pick_red`) |
| Purple data | 63 takes (65 recorded, 2 weak ones removed), on Hugging Face (`varunsatish2017/kitcheck_pick_purple`) |
| Teal data | Not recorded |
| Training | Red and purple training in parallel on the cloud GPU, batch size 8, toward 60,000 steps |
| Best result on the robot | Purple step 10,000 at the center of its pick area: 2 placed in the cup out of 23 runs |
| Software | Recording, upload, training, model try-out, runner with grasp check and retry: all working. Order page and camera check: not built. |

## 1. Setup: what was different from the plan

| Plan assumed | Found | What was done |
|---|---|---|
| LeRobot 0.4.1 | LeRobot 0.6.2 (Seeed fork, commit `4aaff99b`), PyTorch 2.11 for ROCm 7, Python 3.12 | Scripts and docs moved to 0.6.2 |
| `lerobot-record --policy.path` runs a model | 0.6.2 refuses that; models run with `lerobot-rollout` | `try_model.sh` and the runner use `lerobot-rollout --strategy.type=episodic` |
| Model runs named `eval_...` | `lerobot-rollout` requires names starting with `rollout_`, checked only after the arm connects | Names changed to `rollout_...` (found when the first real run failed) |
| Ryzen AI HX370, `HSA_OVERRIDE_GFX_VERSION=11.0.0` | Ryzen AI MAX+ 395, Radeon 8060S (gfx1151), about 103 GB GPU memory | The override must not be set; docs corrected |
| GPU usable | The user was added to the `render` group after logging in | Works after logging in again |
| Arms on `/dev/ttyACM0/1`, cameras on `/dev/video0/2` | Numbers change on replug; arm IDs were `follower`/`leader` | `settings.env` uses `/dev/serial/by-id` and `/dev/v4l/by-id` paths and the real IDs; cameras named `front` and `wrist` (MJPG) |
| Packages installed | A LeRobot reinstall at 14:53 removed `datasets`, `pandas`, `av`, `torchcodec`, `pynput`, `wandb`; training also needed `accelerate`, `jsonlines` | Restored the exact versions; nothing else changed |
| Arrow keys need an Xorg session | LeRobot 0.6.2 reads keys from the terminal on Wayland | Works as long as the recording terminal is focused |

## 2. Hardware problems

| Problem | Evidence | What was done |
|---|---|---|
| A motor occasionally misses a reply when a run connects | Seen 6 times on 5 different motors (4; 2 and 3; 6; 6 three times; 2). Every time, all motors answered 20 of 20 pings right after, at 12.3-12.5 V and 40-47 °C | `record.sh`, `try_model.sh` and the runner retry up to 3 times, only when nothing was recorded (the arm had not moved). Suspected cause: both arms and both cameras share one USB 2 hub; moving the follower to its own PC port is the suggested fix |
| Gripper overload flag (status 32) | Appears after long full squeezes | Expected: LeRobot drops the gripper to reduced torque when overloaded. No action |
| A crashed run leaves some motors holding torque | Seen once (elbow, wrist, gripper on after a failed connect) | The next run's connect resets it |

## 3. Recording: what worked and what did not

**Worked**

- **Manual start and stop** (`kitcheck/record.py`, used by `scripts/record.sh`): takes start on the right arrow; they stop on an arrow or after 20 seconds, whichever comes first. The screen always shows WAITING or RECORDING, and a discard returns to WAITING. Tested on LeRobot's mock robot.
- **A full squeeze of the leader handle.** It gives a grasp-check gap of about 13.5 (fully held) in 47 of 47 red takes and 63 of 63 purple takes.
- **Fast, decisive takes.** The final red takes have a median length of 10 s, and motion starts within 0.4 s.
- **Checked upload** (`scripts/push_dataset.sh`): it mirrors the folder to Hugging Face, deletes stale files, and checks the take count, task text and file list.
- **Filtering weak takes** with `lerobot-edit-dataset`. Purple takes 3 (2.5 s idle at the start) and 24 (light squeeze, no hold) were removed. The joint data of the other 63 was checked identical, and the frames match within re-encoding noise.

**Did not work, and was fixed**

- **A light squeeze.** In the first 5 red takes, 4 had a gap of only 1-3, too small to detect. They were re-recorded with a full squeeze.
- **LeRobot's own upload.** It adds a timestamp to a new dataset's name, so takes went to stray repositories (`..._20261010_153921`, `..._162150`, since deleted). It also never deletes old files, so stale takes would have reached training. It was replaced by the checked upload.
- **Changing the layout mid-dataset.** The early takes used "areas", then the layout switched to cups. The old takes were deleted, and the task text now says "drop it in the red cup".

## 4. Cloud training: problems and fixes

| Problem | Fix |
|---|---|
| The organizers' environment has PyTorch 2.13 (ROCm 10); LeRobot 0.6.2 needs PyTorch 2.7-2.11 and Python 3.12 | `scripts/cloud_setup.sh` makes its own environment (`kc-venv`) with PyTorch 2.7.1 for ROCm 6.3 and LeRobot at the PC's commit |
| Disk full while installing PyTorch | Install goes to the disk with the most free space, with no pip cache |
| The terminal was not using the new environment | The scripts activate it themselves (`~/.kitcheck_venv`), and `train.sh` refuses to run unless LeRobot is 0.6.2 |
| GitHub through the proxy returned 503 | Setup only contacts GitHub if LeRobot is missing |
| `torchcodec` cannot load (no FFmpeg on the cloud machine) | It is removed so that PyAV decodes instead. PyAV decodes these AV1 videos at 0.016 s per frame |
| **Uploads from the cloud to Hugging Face are blocked by the proxy (403)** | Not fixed. Checkpoints come back another way: download through the browser, or the newer Hugging Face upload route if the proxy allows it |
| The setup's GPU check only asked "is a GPU there?" | It now runs a real convolution, a backward pass and a matrix multiply |

**Speeds, measured (step time at batch size 8):**

| Where | Time per step | 10,000 steps |
|---|---|---|
| Cloud, one run | 0.27 s (after warm-up) | 45 min |
| Cloud, red and purple in parallel | about 0.44 s each | about 72 min each, about 25% more total throughput than one at a time |
| This PC's GPU | 0.57-0.78 s | 1.6-2.2 h |
| Other teams' MI300X logs (not ours) | about 0.05 s | 8 min |

The first 200 steps are slow on AMD GPUs (convolution tuning), so judge speed after step 1,000.

## 5. Model results on the robot

All runs used `scripts/try_model.sh`. Placed means held, released over the cup and judged placed by the grasp check. For purple, the front camera also confirmed the ring left the table.

| Model | How it was run | Where the ring was | Placed | Held then dropped | Missed | Runs |
|---|---|---|---|---|---|---|
| Red 10k | Default | Mostly the edge of the pick area, toward the arm | 1 | 1 | 22 | 24 |
| Red 10k | Re-plan every step (temporal ensembling) | Mixed | 0 | 0 | 6 | 6 |
| Red 10k | Base offset −4° | Center | 0 | 0 | 5 | 5 |
| Red 10k | Re-plan every step and offset −4° | Center | 0 | 0 | 5 | 5 |
| Red 20k | Default | Near the center | 0 | 0 | 7 | 7 |
| Purple 10k | Default | Edge of the pick area | 0 | 0 | 10 | 10 |
| **Purple 10k** | **Default** | **Center (blue circle)** | **2** | **2** | **19** | **23** |
| Purple 10k | Half-speed playback (15 per second) | Center | 0 | 0 | 2 | 2 |
| Purple 20k | Default | Center (20-29 px from it) | 0 | 0 | 6 | 6 |

*Correction added on day 2: the one red 10k run counted as placed above wasn't a fair run, so it doesn't count. Red 10k is 0 of 24.*

## 6. What the measurements showed

These come from the joint recordings and from the cameras at the moment the gripper closed, compared with the takes.

- **The models learned the sequence.** In nearly every run: reach toward the pick area, close, swing to the right cup, open.
- **Ring placement matters a lot.** Test placements drifted toward the arm, to the edge of the recorded area: on average 45-90 px from the center in the front camera for red, and the edge cluster for purple. `data/red_pick_map.png` and `data/purple_pick_map.png` show the recorded positions, with a blue circle at their center. All successes were at or near the center.
- **A successful grasp has a clear signature.** At the close, the ring sits in the wrist camera where it sat in the takes. Purple success: (315, 193), 44 px across; takes (304, 186), 45 px. Red takes: (301, 204), 83 px.
- **Misses land on or beside the ring.** For red 10k, the fixed jaw was over the ring's hole (+46 px to the side). For purple 10k, the ring sat about 80 px lower and looked about 40% bigger than in the takes, so the gripper came down onto the ring.
- **The models move about twice as fast as the takes.** Purple 10k closed after 2.5-3 s at 73-107°/s; the takes closed after 5.7 s at 49°/s. The shoulder was 2-5° short of its command at the close, against 0.3° in the takes. Halving the playback speed did not remove that gap, which points to the arm being blocked by the ring rather than lagging.
- **The starting pose was not the cause.** Test runs started inside the range of the takes' starting poses (shoulder lift −105° to −76°).
- **More training is improving the grasp.** Purple 10k to 20k (21:13, 6 runs, none placed yet). The ring's sideways position at the close went from 282-407 to 299-328 px, on target (takes: 304). Its up/down position went from 259-288 to 222-250 (takes: 186). The shoulder's shortfall went from 2-5° to 0.2-1.5°, and speed from 73-107 to 63-92°/s (takes: 49). The remaining error is the gripper coming down about half a ring-width too far forward.
- **The checkpoints are undertrained.** At batch size 8, 10,000-20,000 steps is 80,000-160,000 samples. The organizers' recipe (batch 64, 20,000 steps) is about 1,280,000, and the full 60,000-step run is 480,000.

## 6b. The front camera moved during the day (found at 21:35)

Measured by matching the fixed parts of the front-camera image (cups, coasters, table edge, black disk) against red take 0. Shifts are in pixels on a 640×480 image:

| When | Camera shift (x, y) |
|---|---|
| Red takes, all 47 | (0, 0), the reference |
| Purple takes 0-8 / 9-20 / 21-62 | (0, +2) / (+5, −8) / (−28, +13) |
| Red 10k tests 18:48-19:17 | (−29, +14): **not where red was trained** |
| Red tests 19:21-20:03 (10k, ensemble, offset, 20k) | (0, +6): close to red's training |
| Purple 10k tests 20:15-20:48 (both successes) | (−29, +17): where most purple takes were recorded |
| Purple tests from 20:52, and teal takes 0-7 | (−18, +8) |
| 21:40, live | rotated about 12°: moved again |

What this changes:

- The first red test batch was run with the camera 29 px from where red was trained. The "placed toward the arm" reading for those tests is partly the camera, not the ring.
- The red 20k tests ran close to red's camera position (0, +6), so the camera does not explain those misses.
- Both purple successes happened while the camera matched most of purple's takes.

**Decision (21:40):** lock the camera to purple's position (purple take 30), using `python -m kitcheck.camalign`, then tape it. After that:

- Teal is restarted at the locked position (its 8 takes were 12 px off).
- Red gets about 20 new takes at the locked position, then `retrain.sh red v2`, so it learns this view.

From now on, check the camera before every session: `python -m kitcheck.camalign --once`.

## 7. Run-time fixes tried

| Fix | Idea | Result |
|---|---|---|
| Re-plan every step (`POLICY_ARGS="--policy.n_action_steps=1 --policy.temporal_ensemble_coeff=0.01"`) | The default plays 3.3 s of motion without looking; re-planning uses fresh camera images. One re-plan takes 17 ms on the PC's GPU | Red 10k: 0 of 6, and the gripper ended further off to the side (+59 px) |
| Fixed base offset (`ACTION_OFFSET="shoulder_pan.pos=-4"`, `kitcheck/rollout.py`) | Cancel the measured sideways miss (46 px at 11.4 px per degree) | Worse. The model steers from the cameras and compensated: still +62 px to the side and now too high (ring −65 px, size −18). Do not use it with a camera-driven model |
| Half-speed playback (`POLICY_ARGS="--fps=15 --dataset.fps=15"`, a 30 s limit) | Give the arm time to finish coming down | 0 of 2. The shoulder was still 2-5° short of its command |

All three remain available as settings in `scripts/settings.env` and are recorded in the score labels (`010000_ensemble`, `010000_pan-4`, `010000_fps15`), but none is recommended.

## 8. Plan for day 2

1. **Overnight:** red and purple continue to 60,000 steps. Red is then continued to 150,000 (`resume.sh red 150000`, chained on the cloud machine). If time allows, add about 20 precise red takes at the center and run `retrain.sh red v2`.
2. **07:00:** test the latest red and purple checkpoints at the blue circle, 5 runs each, default settings. Build the demo on any model that places 4 or more out of 5.
3. **Teal:** record it only if red or purple works by mid-morning.
4. **Fallback by 09:00:** replay a good recorded take (`scripts/replay.sh`), with the check-and-retry system around it.
5. **Hardware:** move the follower arm (and ideally the front camera) off the shared USB hub.
6. **Before leaving tonight:** photograph the setup, and tape the cups, camera stand and pick areas.

## 9. Files added or changed today

| File | What |
|---|---|
| `scripts/settings.env` | Real ports, IDs and cameras (by-id); recording limits; `POLICY_ARGS`, `ACTION_OFFSET` |
| `scripts/record.sh`, `kitcheck/record.py` | Recording with manual start and stop, a 20 s cap, connection retries and the checked upload |
| `scripts/replay.sh` | Replay one take |
| `scripts/push_dataset.sh` | Checked mirror upload to Hugging Face |
| `scripts/try_model.sh` | `lerobot-rollout`, `rollout_` names, retries, run modes in the score labels |
| `scripts/cloud_setup.sh` | Cloud environment matching the PC, disk choice, GPU and decoding checks |
| `scripts/_lib.sh` | Shared helpers, automatic use of the cloud environment, LeRobot version check |
| `scripts/train_report.py` | Reads LeRobot 0.6 logs |
| `kitcheck/grasp.py` (+ test) | A two-stage release counts as a release, not a slip |
| `kitcheck/skill.py`, `kitcheck/runner.py`, `kitcheck/rollout.py` | Run one skill; the order loop with check and retry; the optional command offset |
| `config.json` | Items red, purple and teal; cup task text; kits |
