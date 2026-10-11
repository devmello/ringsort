# RingSort: spec

**A factory sorting cell: a robot arm sorts mixed parts into one bin per part type, ready to be packed later, and checks every pick itself.** If it picks up nothing, it tries once more. If something else goes wrong, it flags the operator.

This is the whole project in one file. It replaces `PLAN.md` and `docs/` as the scope for day 2. Those files are kept for reference and for judges' questions, but anything this spec cuts is not being built.

**About the name:** RingSort is the project name for the demo, README and submission. Folder names, the Python package (`kitcheck/`), Hugging Face repos (`kitcheck_pick_*`) and model names stay as they are, because renaming them now would break training, downloads and scripts with nothing to show for it.

---

## 1. The story

**Setting: a small factory or assembly shop.** Parts arrive mixed, from a supplier delivery, a disassembly line or a returns pile. Before anyone can pack them into kits or orders, they have to be sorted: each part type into its own bin. Packing then pulls from clean bins.

**RingSort is the sorting cell in that line.** It sorts parts into bins and does not pack. Packing happens downstream, later, from the bins it fills.

**Why the check matters:** sorting is only useful if the bins can be trusted. A part in the wrong bin, or one silently left behind, turns into a wrong kit or a short order downstream, where it costs far more to find. Robots that learn by demonstration fail silently, so RingSort confirms every pick and flags the operator when it can't, the way a line worker pulls the andon cord.

**On the table:**

| In the story | On the table |
|---|---|
| Part types (e.g. O-rings and washers in different sizes) | Colored rings: red, purple, teal |
| Mixed parts waiting to be sorted | Each ring in its pick area |
| One bin per part type | One cup per color |
| Line operator | The person at the terminal |
| Packing station downstream | Not built; mentioned in the pitch only |

## 2. What it does

1. The operator runs one command naming what to sort, for example `Sort all` or `purple`.
2. For each part, the arm runs that part type's trained model: pick the part from its area, drop it in its bin, return to rest.
3. After every pick, RingSort reads the gripper's own position record from that run to decide **placed**, **missed** or **dropped**.
4. On a miss, the part should still be in place, so it retries once.
5. On a drop, a second miss or a failed run, it stops and flags the operator, who chooses retry, placed by hand, skip or cancel.
6. Every attempt goes into a log, and one command prints the cell's success rate.

**Pitch in one sentence:** a factory sorting cell that fills bins for packing and knows when it got a pick wrong, using a signal the model doesn't control, the gripper's measured position, with no extra sensor.

---

## 3. Scope

### In (already built, needs working models)

| Feature | File | State |
|---|---|---|
| One ACT model per color: **purple and teal first**, red last | `models/<color>/<step>/` | Purple trained to 20k, still weak (see section 7). Teal: 45 takes, not trained yet. |
| Run one pick with a model | `kitcheck/skill.py`, `scripts/try_model.sh` | Working on the robot |
| Grasp check: placed / missed / dropped | `kitcheck/grasp.py` | Working; tested on real takes and runs |
| Order loop with one retry and an operator flag | `kitcheck/runner.py` | Working from the terminal |
| Run log and success summary | `data/runs.jsonl`, `runner.py --summary` | Working |
| Camera-guided replay: the stand camera finds the ring; the take of that color whose ring started closest (toward/away from the base) is played back with the base turned to make up the sideways difference; recorded like a model run | `kitcheck/replay.py`, `kitcheck/replay_run.py`, `data/replay.json` (made by `python -m kitcheck.replay learn`) | Built; tested with a fake arm and in rehearsal. Not yet run on the arm. Plain replay of a take has worked on the arm for red. |
| Parts view: while the arm is idle, the stand camera finds each part by color, grades it against where that color sat in its takes (ready / near edge / outside), sees the purple ring in its bin, and checks the camera hasn't moved | `kitcheck/vision.py`, `data/vision.json` (made by `python -m kitcheck.vision learn`) | Built; tested on recorded frames and in the dashboard. Not tried live: the room was dark. |
| Station dashboard: factory view of the line, work orders, operator buttons, live cameras between picks, replay of each pick | `kitcheck/dashboard.py`, `scripts/dashboard.sh` | Built and rehearsed without the robot; not yet run with the arm |
| Camera position check | `kitcheck/camalign.py`, `scripts/align_camera.sh` | Working |
| Recording, upload, training, model download | `scripts/` | Working |

### Stretch (only if a model places 4 of 5 by 09:00)

- **Red**, the third color. It was recorded with the camera in a different position, so it needs about 20 new takes at the locked position and `retrain.sh red v2` before it can join the demo.

### Cut (do not build)

| Cut | Reason |
|---|---|
| Camera check that blocks a pick or confirms every bin | The parts view warns and never blocks. Only the purple bin is in view. |
| Typed or plain-language orders | Kit names from `config.json` are enough |
| Spoken status (ElevenLabs) | Nice to have, not needed |
| Region setup tool, kit-complete watcher, auto re-pack | They depend on the camera check |
| Overnight "organizers' recipe" comparison | Not needed for the demo |
| Run-time model tweaks (ensembling, pan offset, half speed) | Tried on day 1; none helped |
| Second arm, lid, voice input, cloud calls at demo time | Out of scope from the start |

---

## 4. Hardware and workcell

| Thing | Spec |
|---|---|
| Arms | SO-101 follower (`follower`, serial ...5C4C124442) and leader (`leader`, serial ...5C4C123870) |
| PC | AMD Ryzen AI MAX+ 395, Radeon 8060S (gfx1151), Ubuntu 24.04. Do not set `HSA_OVERRIDE_GFX_VERSION`. |
| Training | AMD Cloud, AMD Radeon AI PRO R9700; `kc-venv` made by `scripts/cloud_setup.sh` |
| Cameras | `front` on the stand (looks down at the pick areas and bins) and `wrist` on the gripper (MJPG). 640×480 at 30 fps. Addressed by `/dev/v4l/by-id` paths. |
| Parts | Three ring types, by color: red, purple, teal (standing in for O-rings or washers) |
| Layout | Each color has a pick area with a blue circle at its center and its own bin (a cup). Everything is taped down. |
| Camera position | Locked to purple take 30. Check it before every session with `python -m kitcheck.camalign --once`. |
| Rest pose | The same pose at the start and end of every take and run, one the arm can hold with motors off |

**Known hardware issue:** both arms and both cameras share one USB 2 hub, and a motor sometimes misses a reply when a run connects. The scripts retry up to 3 times. The fix is to move the follower to its own PC port.

---

## 5. How it works

```
python -m kitcheck.runner "Sort all"
        |
        |  for each color in the order
        v
  run_skill(color)            lerobot-rollout, the color's model, 15 s, fresh output folder
        |
        v
  grasp.judge_folder(run)     reads gripper commanded vs measured position, per frame
        |
   +----+--------------+------------------+
   |                   |                  |
 placed             missed             dropped / error
   |                   |                  |
 next part      retry once, then      flag the operator:
                flag the operator     retry / placed by hand /
                                      skip / cancel
        |
        v
  one line per attempt in data/runs.jsonl
```

### The grasp check

- LeRobot records, on every frame, where the gripper was told to go (the action) and where it got to (the observation), from 0 (closed) to 100 (open).
- **Holding something:** the gripper can't close all the way, so measured minus commanded stays above 4 for at least 0.5 s while the gripper is still. In good takes the gap is about 13.5.
- **Missed:** no hold at all.
- **Dropped:** the gap disappeared while the gripper was still told to stay closed (it slipped), the arm was still holding when the run ended, or it let go too far from the bin's direction.
- **Placed:** it was told to open, and the base joint (`shoulder_pan`) was within tolerance of where the takes let go. The reference comes from `data/grasp_<color>.json`, made with `python -m kitcheck.grasp learn`.
- **What it can't tell you:** whether the part stayed in the bin after it was released.

### Config (`config.json`)

| Key | Meaning |
|---|---|
| `items.<color>.model` | Model used by default (`models/<color>/final/pretrained_model`), or override with `--label <step>` |
| `items.<color>.grasp_reference` | `data/grasp_<color>.json` |
| `items.<color>.run_time_s` | Time limit for one pick (15) |
| `kits` | `Sort all` (purple, teal; add red only if it gets retrained at the locked camera), `Purple`, `Teal`, `Red` |
| `limits.auto_retries` | 1 |
| `camera_check`, `voice` | Off. Cut from scope. |

---

## 6. Commands

All run on the PC from `~/kitcheck`, with `source scripts/settings.env`.

| Task | Command |
|---|---|
| Check the camera hasn't moved | `python -m kitcheck.camalign --once` |
| Fix the camera position | `scripts/align_camera.sh purple 30` → http://127.0.0.1:8077 |
| Download a checkpoint | `scripts/get_model.sh <color> <label>` |
| Test a model with one scored pick | `scripts/try_model.sh <color> <label>` (scores go to `data/trials.csv`) |
| Run the station from the browser | `scripts/dashboard.sh` → http://127.0.0.1:8078 (press "Pause live view" before using `record.sh` or `try_model.sh`) |
| Sort parts into bins from the terminal | `python -m kitcheck.runner "Sort all" --label 060000` (needs `--label` until a model is copied to `models/<color>/final/`) |
| Success rate | `python -m kitcheck.runner --summary` |
| Record more takes | `scripts/record.sh <color> <count>` |
| Fallback: replay a good take | `scripts/replay.sh <color> <episode>` |

On the cloud machine: `scripts/train.sh`, `retrain.sh <color> v2`, `resume.sh <color> <steps>`, `train_report.py logs/<job>.log`. Uploads from the cloud to Hugging Face are blocked by the proxy, so bring checkpoints back through the browser.

---

## 7. Where things stand (end of day 1)

| | Purple | Teal | Red |
|---|---|---|---|
| Camera position | **Locked position** | **Locked position** (same as purple) | Different: 29 px off |
| Takes | 63 | 45, all with a clean grasp signal (an earlier 8 at the wrong camera position were thrown away) | 47 |
| Hugging Face dataset | `varunsatish2017/kitcheck_pick_purple` | `..._teal` | `..._red` |
| Grasp reference | `data/grasp_purple.json` | `data/grasp_teal.json` | `data/grasp_red.json` |
| Models on the PC | 10k, 20k | none | 10k, 20k |
| Best result | **2 placed out of 23** (10k, ring at the blue circle) | not trained yet | 1 placed out of 24 (10k) |
| Overnight | Training toward 60k | **Must start tonight** | Training toward 60k; drop its 150k continuation in favor of teal |

**Priority: purple and teal.** They share the locked camera position, and purple is the only color that has placed a ring. Red was trained with the camera elsewhere, so it is last.

**What day 1 showed:**

- The models learned the motion sequence but miss the grasp by about half a ring width, coming down too far forward.
- Every success came with the ring at the center of its pick area.
- 10k to 20k steps moved the grasp point toward the target. The checkpoints are undertrained: 160k samples so far, against 1.28M in the organizers' recipe.
- The front camera moved several times on day 1. It is now locked at purple's position; teal was recorded there too, red was not.

---

## 8. Day 2 plan (07:00–13:30)

| Time | Work |
|---|---|
| Tonight | Start teal training on the cloud (`scripts/train.sh teal`). If the GPU is busy, it takes the slot of red's 150k continuation. |
| 07:00 | `camalign --once`. **Camera replay first:** 5 runs each of `python -m kitcheck.runner teal --label replay` and `purple --label replay`, ring on its mark (the parts view says "ready"). Then download the latest purple and teal checkpoints and do 5 model runs each, for the comparison. |
| 07:45 | Pick the best checkpoint for each. If one is weak, record 15–20 takes where it fails and `retrain.sh <color> v2`. Red only if both purple and teal are already working. |
| 08:00–09:00 | `runner "Sort all"` (purple, then teal) end to end. Log every run. |
| **09:00** | **Decision point** (section 9). Nothing new after this. |
| 09:00–10:00 | Repeat runs for a measured success rate. Film every good run. |
| 10:00–11:30 | Film the demo video. Write the README. |
| 11:30–13:30 | Submit, rehearse the pitch, buffer. |

---

## 9. Decision at 09:00

| If | Then |
|---|---|
| Camera replay places 4+ of 5 | Demo "Sort all" with camera replay. Show the ACT numbers as the comparison: "same check, two ways to pick". |
| Purple and teal both place 4+ of 5 | Demo "Sort all" (purple, then teal) |
| Only one does (most likely purple) | Demo that color alone, with the retry shown live |
| Neither does | Demo the check on real runs: a miss is caught, retried, and then flagged for the operator. Then show `replay.sh` doing a clean pick. Say plainly which is a model and which is a replay. |

**Never cut:** the demo video and the submission.

---

## 10. Done means

- [ ] Purple (and ideally teal) places 4 of 5 at the blue circle
- [ ] A full sorting run goes end to end through the runner, with a retry shown
- [ ] A measured number from `runner --summary` (e.g. "first try 6 of 10; with retry 8 of 10")
- [ ] A 60–90 second video
- [ ] README and submission in

---

## 11. The 90-second demo

1. **Set the scene (one sentence):** "In a factory, mixed parts get sorted into bins before anyone packs kits from them, and a bin is only useful if you can trust it."
2. **Start the cell:** on the dashboard, tap the "Sort all" work order. The tower light turns green, and the live cameras hand over to the robot.
3. **A good pick:** the arm drops the first part in its bin. The dashboard shows **PLACED**, the bin count goes up, and the pick replays from the cell's own recording.
4. **A caught failure:** take the next part off its spot before the arm reaches it. The gripper closes on nothing, the dashboard shows **MISSED**, and the light turns amber. Put the part back and the cell retries on its own. On a second failure the light turns red and the operator buttons appear.
5. **The numbers:** point at the shift numbers (first-pass yield, yield with retry). Tap "Send bins to packing" and close with "These bins are now ready for the packing station."

Have the video ready in case the live run fails.

---

## 12. Submission checklist

- [ ] Team, short summary, images or video
- [ ] Mission: a factory sorting cell that fills one bin per part type for packing later, and knows when it got a pick wrong
- [ ] Creativity: self-checking from the gripper's own record, no extra sensor
- [ ] Technical: data capture (110 takes), ACT training on AMD Cloud (Radeon AI PRO R9700; batch 8, frequent checkpoints), running models on the Ryzen AI PC
- [ ] Ease of use: one command per sorting run; adding a new part type means about 50 demonstrations and one training run, with no programming
- [ ] Links: video, Hugging Face datasets, Hugging Face models, W&B run
- [ ] Code in the repo

---

## 13. Pitfalls to remember

- Model runs must be named `rollout_...`. The scripts already do this.
- Each run needs a fresh output folder. The scripts already do this.
- Camera names (`front`, `wrist`) must match between recording and running.
- Don't stop a recording with Ctrl+C mid-write, or a video file can be corrupted.
- The first 200 training steps on AMD GPUs are slow, so judge speed after step 1,000.
- GPU access on the PC needs the `render` group, which takes effect after logging in again (or use `sg render -c ...`).
