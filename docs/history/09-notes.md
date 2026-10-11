# Notes

A record of the decisions that are worth explaining to a judge: what was changed, why, what the evidence is, and what still has to be measured. Add to it during the event. Each entry ends with a way to say it in half a minute and a list of what not to claim.

## Before quoting anything here

- **Numbers marked "from other teams' logs" are not yours.** Say where they come from. Replace them with your own as soon as you have them; the blank tables are for that.
- **Ask at check-in whether code prepared before the start may be used.** The scripts and the grasp check were written the night before. If the rules say all code must be written during the event, treat them as reference and rewrite them on site (they are short), and say so if asked.
- **"Tested" in these notes means tested on recordings or on a CPU.** Nothing was run on the arm or on the AMD machines before the event.

### What was prepared before the event

| Prepared beforehand | Done at the event |
|---|---|
| The plan and these docs | The workcell |
| Analysis of other teams' public training logs | Every demonstration |
| Training scripts and the training report tool | Every training run and model |
| The grasp check and its tests | All testing on the robot |
| The voice tool (no clips) | The voice clips themselves |
| | The runner, order page and camera check |

---

## 1. Training time: batch size 8 with frequent checkpoints

**Decision.** Train ACT with batch size 8, a checkpoint every 10,000 steps and a 60,000-step budget, and test checkpoints on the robot as they arrive. The organizers' example uses batch size 64 for 20,000 steps.

**Why.** With 18.5 hours in total, the number of train-and-test cycles decides how good the skills get. The example recipe gives the first usable result after hours; this one gives it after minutes.

**Evidence, from other teams' logs.** Three ACT training logs published by teams at AMD's Tokyo hackathon in December 2025. All ran at 640×480 on the same kind of cloud machine (MI300X VF, 160 processor cores, default data-loading settings).

| Run | Cameras | Batch | Steps | Total time | Per step once warmed up |
|---|---|---|---|---|---|
| Greate Akihabara, warm-up task | 2 | 8 | 20,000 | 21 min | 0.044 s |
| RoboTAI, warm-up task | 3 | 64 | 20,000 | 2 h 50 min | 0.37 s + 0.12 s waiting for data |
| RoboTAI, drawer project | 3 | 64 | 40,000 | 4 h 40 min | 0.38 s |

What the logs show:

- **The GPU step is the bottleneck.** Waiting for data was about 5% of each step once the dataset was a realistic size. More data-loading workers would not help.
- **A big batch does not pay for itself.** A batch-64 step took 8.6 times as long as a batch-8 step (about 5 times after allowing for the third camera) and moved the training loss about twice as far.
- **Time to the same training loss**, the two warm-up-task runs, 10 demonstrations each:

| Training loss reached | Batch 64, three cameras | Batch 8, two cameras |
|---|---|---|
| 0.2 | 28 min | 10 min |
| 0.1 | 51 min | 16 min |

Allowing for the extra camera and that run's data waits, batch 8 reached each level in a bit over half the time. That adjustment is my estimate, from two runs on different data.

- **Every run has a slow start.** The first 200 steps took 3, 5 and 9.5 minutes in the three logs, with a second slow patch of 2–3 minutes at the end of the first pass over the data.

To reproduce these tables: clone the two repositories under Sources and run `python scripts/train_report.py` on their `output.log` files.

**What was tested.** The training, continue-from-a-model and resume scripts were run with LeRobot v0.4.1 on a CPU, on one of those teams' public datasets (real SO-101 data, two cameras, 640×480), for a few steps each. They work. Speed on the AMD GPU was not measured.

**My own numbers.** Fill in from `python scripts/train_report.py logs/<job>.log`.

| Run | Demonstrations | Batch | Steps | First checkpoint after | Total time | Seconds per step | Robot success |
|---|---|---|---|---|---|---|---|
| sensor | | 8 | | | | | / 10 |
| motor | | 8 | | | | | / 10 |
| sensor, organizers' recipe (optional) | | 64 | 20,000 | | | | / 10 |

**A fair comparison of my own, for free.** Overnight, `scripts/overnight.sh --baseline sensor sensor motor` runs the long batch-8 runs and then the organizers' recipe on the same sensor data. The two see almost the same number of samples (150,000 × 8 against 20,000 × 64), so the comparison is like for like. In the morning:

```shell
python scripts/train_report.py --md logs/kitcheck_act_sensor_long.log logs/kitcheck_act_sensor_guide.log
```

Paste the table here, then give each model ten picks on the robot and record both scores.

**Say it in half a minute.**

> The organizers' example trains with batch size 64 for 20,000 steps. Logs that teams published from last year's Tokyo event show that recipe taking close to three hours on this cloud machine, with the GPU step as the bottleneck. I switched to batch size 8 with a checkpoint every 10,000 steps. My first testable model arrived after __ minutes and a full run took __ minutes, so I ran __ train-and-test cycles in a day.

**Do not claim.**

- That batch size 8 gives a better model. The claim is a testable model sooner.
- The Tokyo teams' timings as your own.
- That lower training loss means higher success on the robot.

---

## 2. A fresh copy of the dataset for every training run

**Decision.** Each training run downloads its own copy of the dataset into `datasets/<job>`.

**Why.** LeRobot v0.4.1 uses a local copy of a dataset if one exists and does not check Hugging Face for new demonstrations. After recording fix-up demonstrations, a retrain on the same machine would silently train on the old data and waste a full cycle.

**Evidence.** Read in the LeRobot v0.4.1 source (`lerobot_dataset.py`: the metadata and data are loaded from the local folder first, and the download only happens if that fails). Confirmed in the script test: each run reported the dataset it loaded.

**How to check during the event.** The first lines of every training log show `dataset.num_episodes=`. The scripts print it after starting a run.

**Say it.** "I found that LeRobot reuses a cached dataset without checking for new episodes, so my scripts give every run a fresh copy and print the episode count."

---

## 3. Continue from the existing model after adding demonstrations

**Decision.** After recording fix-up demonstrations, start the next run from the trained weights (`scripts/retrain.sh`) for 20,000 steps, not from scratch.

**Why.** The model already knows most of the task. A fix then costs about 20 minutes.

**Evidence.** Tested on a CPU with real data: the continued run loaded the saved weights and its first training-loss value was 31, against 82 for a run started from scratch on the same data. Whether 20,000 steps is the right amount is untested.

**My own numbers.**

| Retrain | Added demonstrations | Steps | Time | Robot success before | After |
|---|---|---|---|---|---|
| | | | | / 10 | / 10 |

**Do not claim** that this always works. If a continued model is no better, a fresh run on all the data is the fallback.

---

## 4. Two cameras at 640×480

**Decision.** Give the model two cameras at 640×480, even if the kit has three.

**Why.** Camera count and image size are fixed at recording time and set the cost of every training run.

**Evidence.** I timed one training step of LeRobot's ACT model on a CPU for different setups. Relative work per step:

| Setup | Work per step |
|---|---|
| 1 camera at 640×480 | 0.5 |
| 2 cameras at 640×480 | 1.0 |
| 3 cameras at 640×480 | 1.6 |
| 2 cameras at 320×240 | 0.3 |

These are CPU timings. The camera-count ratio should carry over to the GPU; the gain from smaller images will be smaller there.

**Why not 320×240.** It would cut training time further, but it shows the model less detail, every published run from earlier teams used 640×480, and it cannot be undone without re-recording. Not worth the risk on day 1.

---

## 5. Grasp check: reading the gripper's own record

**Decision.** After every pick, decide what happened from the gripper's commanded and measured positions, which LeRobot records on every frame anyway. This is the base check; a fixed camera adds a second one when the kit has it.

**Why.** The gripper's record needs no extra hardware and no setup, and it catches the commonest failure, a missed grasp, more directly than a camera does. It was added while the kit's cameras were still unconfirmed, so that the self-checking would not depend on them. The listing has since shown two cameras, one on the gripper and one on a stand, so the camera check is available too and the two cross-check each other.

**How it works.** When the gripper closes on an object it cannot reach the commanded position, so the measured value stays above the commanded one for as long as the object is held. Closing on nothing leaves no gap. If the gap vanishes while the gripper is still told to stay closed, the object slipped. If the gripper is told to open, the arm let go on purpose, and the base joint's angle says whether that was at the tray.

**Evidence.** Checked before the event on 20 public demonstrations from the two Tokyo teams (real SO-101 arms):

| Case | Result |
|---|---|
| Real demonstrations of a successful pick and place | 19 of 20 read as placed |
| The one miss | The operator closed the gripper only to about the object's width, so there was no gap to see |
| Gap while holding | About 8 to 15 on LeRobot's 0–100 gripper scale; an empty closed gripper read about 0.1 to 0.3 |
| Empty grasps, simulated by editing those recordings | 20 of 20 read as missed |
| Slips part-way through the carry, simulated the same way | 75 of 76 read as not placed |

The failures were simulated by editing real recordings, not recorded on a robot. `tests/test_grasp.py` covers the same cases on made-up data.

**Limits.**

- It cannot see the tray. A cube that bounces out after a clean release reads as placed.
- It needs a firm squeeze. Demonstrations must close the gripper fully on the cube.
- A very soft cube may give a small gap. `python -m kitcheck.grasp inspect <dataset>` on the first five demonstrations shows whether the signal is there.

**My own numbers.** From `data/trials.csv`, compared with what you saw.

| Model | Picks | Gripper said placed | Actually in the tray | Gripper wrong |
|---|---|---|---|---|
| | | | | |

**Say it in half a minute.**

> A learned model does not know when it has failed. KitCheck checks every pick with a signal the model does not control: the gripper's own position record. When it closes on a cube it can't reach the commanded position, and that gap is in the data LeRobot already records, so there is no extra sensor. No gap means it picked up nothing, and it retries. A gap that vanishes early means the cube slipped, and it asks for help.

**Do not claim** that it verifies the cube is in the tray. It verifies the grasp, the carry and the release.

---

## 6. Spoken status with ElevenLabs, made ahead of time

**Decision.** Optional. The station says what it is doing in an ElevenLabs voice, and every line is made in advance and played from a file.

**Why.** A person packing kits is looking at the cubes, not the screen, so spoken prompts fit the job, and in a demo the judge hears the self-check happen. Making the lines ahead of time keeps the rule that nothing calls the cloud while the station runs: the set of things it can say is small and fixed (25 lines with two items, about 1,000 characters).

**Evidence.** The tool was tested with stand-ins for the API and the speaker (`tests/test_voice.py`). One real request with a wrong key reached ElevenLabs and was refused as expected. No clip has been made with a valid key yet.

**My own numbers.**

| Clips made | Characters sent | Voice used | Heard clearly at hall volume? |
|---|---|---|---|
| | | | |

**Say it in half a minute.**

> The station speaks its status in a voice from ElevenLabs. Because it only ever says a fixed set of lines, I generate them once with their text-to-speech API and play the files, so the demo needs no connection and the robot's control stays fully local.

**Do not claim** that speech is generated live, that it holds a conversation, or that it listens.

---

## 7. Considered and not done

| Idea | Why not |
|---|---|
| More data-loading workers | The logs show data loading is about 5% of each step |
| Mixed precision | May shorten the GPU step; untested on this hardware; a failed experiment costs a training cycle |
| Recording at 320×240 | See entry 4 |
| One language-driven model for all items (SmolVLA) | A Tokyo team's log shows 80,000 steps taking over four hours on this machine |
| Keeping the model loaded between picks | Removes a start-up delay per pick; needs a custom control loop; not needed for the demo |
| Spoken orders (speech-to-text) | A hackathon hall is loud, and it would be a cloud call while the station runs |
| Speech generated live for each message | Not needed: the lines are fixed. It would make the demo depend on the network |

---

## Sources

- Greate Akihabara team repository and logs: https://github.com/masato-ka/GreateAkihabra_9_AMDOpenRoboticsHackathon
- RoboTAI team repository and logs: https://github.com/Robotawi/RoboTAI_AMD_Robotics_Hackathon_2025
- Public datasets used for testing: `masato-ka/greate-akihabara-misson1` and `abd64bit/record-red-block-test` on Hugging Face
- LeRobot v0.4.1 source: https://github.com/huggingface/lerobot
- Organizers' guide: https://github.com/andrewgschmidt/AMD_Hackathon/tree/main
- ElevenLabs API reference, text to speech: https://elevenlabs.io/docs/api-reference/text-to-speech/convert
- ElevenLabs API reference, list of voices: https://elevenlabs.io/docs/api-reference/voices/search

---

## Template for a new entry

```
## N. Title

**Decision.**
**Why.**
**Evidence.** (say whose numbers they are)
**My own numbers.**
**Say it in half a minute.**
**Do not claim.**
```
