# KitCheck

**A parts-kit packing station that checks its own work.** You tap a kit and a robot arm packs it. After every pick the station checks what the gripper felt, and what a fixed camera sees if the kit has one. A missed pick is retried once; anything uncertain goes to a person.

- **Event:** physical AI track, AMD robotics hackathon (SO-101 arms, AMD Ryzen AI PC, AMD MI300X cloud GPU, LeRobot)
- **Team:** solo (add a teammate if one turns up)
- **Hours:** Day 1 10:00–22:00, Day 2 07:00–13:30 (18.5 hours on site, with an overnight gap)
- **AI tools:** Claude Max, ChatGPT Pro
- **Name:** KitCheck is a working name
- **Part docs:** one doc per part of the project is in [`docs/`](docs/README.md)
- **Architecture:** the whole system on one page is [`docs/00-architecture.md`](docs/00-architecture.md)
- **Notes for judges:** decisions and their evidence are in [`docs/09-notes.md`](docs/09-notes.md)
- **Scripts:** training and model try-out tools are in [`scripts/`](scripts/README.md)
- **Optional voice:** spoken status with the ElevenLabs API is in [`docs/10-voice.md`](docs/10-voice.md)

---

## 1. The idea

### Problem

Makerspaces, classes and hackathons hand-pack hundreds of small parts kits. Small online sellers do the same with orders. Robots that learn by demonstration can do the picking, but they fail silently: the model doesn't know when it missed.

### What KitCheck does

1. A person taps a kit button or types an order on a local web page.
2. For each item, it runs that item's trained skill: pick from its square, drop in the tray, return to rest.
3. It then reads the gripper's recorded positions from that run. They show whether the gripper held a cube, whether the cube slipped, and whether the arm let go at the tray.
4. If it picked up nothing, it retries once. If the cube slipped or anything else is uncertain, it pauses and asks for help.
5. A second check uses the kit's fixed camera: is the square stocked before the pick, and did the tray gain a cube after it.
6. When every item is verified it shows "Kit ready" and logs the result.

### Why this idea

- The robot work stays at two simple pick-and-place skills, which is what one person can make reliable in 18.5 hours.
- The distinctive part (check, retry, ask for help) is software, which the AI tools can write while models train.
- The check makes the live demo more reliable. A skill that works 7 times in 10 completes about 9 in 10 with one retry, as long as a miss leaves the item on its spot.
- The grasp check needs no extra hardware or setup, so the self-checking works from the first trained model, before the camera check is built.

### How it maps to the judging criteria

Earlier AMD robotics events scored creativity, difficulty, ease of use and practicality. Tomorrow's rubric is not confirmed, so check it on arrival.

| Criterion | KitCheck's answer |
|---|---|
| Creativity | A learned robot that knows when it got it wrong: check, retry, ask for help |
| Difficulty | Two learned skills plus two independent checks, working together end to end |
| Ease of use | One tap to order. Adding a new part takes about 60 demonstrations and one training run, with no programming |
| Practicality | Kit packing for labs and hackathons; the same station packs small orders for sellers |

---

## 2. Feature set

### Core (must ship)

- **Skill A:** pick item A from its taped square, drop it in the tray, return to rest
- **Skill B:** the same for item B
- **Order page:** local web page with kit buttons ("Sensor kit", "Motor kit", "Full kit") and a typed order such as `2 sensors, 1 motor`
- **Runner:** works through the order one item at a time and launches the right skill for a fixed time
- **Grasp check:** after each pick, reads the gripper's recorded positions to tell placed, missed or dropped; one retry on a miss; asks for help otherwise
- **Camera check (uses the kit's stand camera):** will not start a pick if the pickup square is empty; confirms the tray gained a cube; watches a finished kit
- **Live status:** each item shows waiting, picking, verified, retrying or needs help
- **Run log:** every attempt is recorded, with first-try and after-retry success counts shown on the page

### Stretch (only if core works by 09:00 on day 2)

- **Spoken status with ElevenLabs:** the station says what it is doing ("I picked up nothing. Trying again."). The lines are made once with the ElevenLabs API and played from files, so the demo still needs no connection. The tool is written and off by default; switching it on takes a key and about five minutes. Do it last. See `docs/10-voice.md`.
- A third item type (a third skill)
- Plain-language orders ("I'm building a line follower") turned into a kit by a small language model running locally

### Cut (do not build)

- Voice input (spoken orders): too noisy in a hackathon hall. Spoken output is the stretch item above.
- A second arm
- Closing a lid
- Any cloud call during the demo (the optional voice is made ahead of time for this reason)

---

## 3. Physical setup

- **Items:** 3–4 cm cubes of firm foam in two bright colors, labelled as boxed parts ("SENSOR", "MOTOR"). Firm matters: the grasp check needs the cube to hold the gripper open. The follower arm is white and the leader is black, so avoid white, black and grey, and choose colors that differ from the table surface. Bring spares.
- **Surface:** a plain matte sheet (poster board or large paper) under everything.
- **Layout:** one taped pickup square per item type, well to the left and right of a shallow tray. Find comfortable positions by teleoperating first, then tape them down.
- **Cameras:** two, going by the kit's listing (Advanced Kit): one on the follower's gripper and one on a jointed stand. Set the stand camera to look straight down on both pickup squares and the tray, tighten its joints and tape its base down. Put each camera on its own USB port; the kit's hub is for the arms.
- **Rest pose:** every demonstration starts and ends in the same pose, clear of any fixed camera's view of the squares and tray.
- **Motors off between runs:** LeRobot switches the follower's motors off when each run connects and disconnects, so the rest pose must be one the arm stays in while limp (folded, gripper resting on the base or a pad).
- **Lighting:** keep it constant. Avoid a spot where people walking past change the light or appear in frame.
- **Before leaving on day 1:** photograph the whole setup and mark every position with tape. A moved camera can break a trained model.

### Props to bring

- Firm foam cubes in two colors (at least three of each)
- A shallow tray or box lid
- Painter's tape
- Plain poster board or large sheet of paper
- A marker for labels
- A phone stand for filming
- Optional: a small speaker, if you want the spoken status and the PC has none

---

## 4. What is learned and what is code

### Learned (the robot)

- Two separate ACT models, one per item type. ACT is the model the organizers' guide uses.
- About 60 demonstrations per skill, recorded by teleoperating the follower arm with the leader arm.
- Trained on the MI300X cloud GPU, then run on the Ryzen AI PC.

### Code (written with AI tools)

- **Order page:** kit buttons, typed order, live status, run log.
- **Order parser:** simple keyword matching (`2 sensors, 1 motor`). No model needed.
- **Runner:** for each item, launches the guide's inference command with that skill's model and a time limit, then waits for it to finish.
- **Grasp check:** reads each run's recording for the gap between where the gripper was told to go and where it got to. Written and tested on recordings (`kitcheck/grasp.py`).
- **Camera check:** plain color thresholds in fixed regions of a fixed camera's image (each pickup square and the tray). Nothing is learned here. Only with a fixed camera.
- **Region setup tool:** marks the pickup squares and tray on the camera image. Only for the camera check.
- **Training scripts:** start, continue, resume and report on training runs (`scripts/`). Written and tested on a CPU.
- **Voice (optional):** makes and plays the station's spoken lines with the ElevenLabs API (`kitcheck/voice.py`). Written and tested with stand-ins; no real clip made yet.

### Implementation notes

- Each inference run needs a fresh output folder. Reusing one causes a "File exists" error, so the runner should name it with a timestamp.
- Run the camera check between robot runs, not during them, so two programs never use a camera at once.
- Camera names must match between recording and inference. They are set once in `scripts/settings.env`. A mismatch causes a "mean is infinity" error.
- Use the same robot ID for calibration, teleoperation, recording and inference.
- Keep everything local so the demo does not depend on venue Wi-Fi.
- If loading the model on every pick is too slow, keeping both models loaded in one process is a later optimization, not a day-1 task.

---

## 5. Data and training plan

- **Demonstrations:** about 60 per skill, each 10–12 seconds and ended with the right arrow. The time limit is 20 seconds with a 10-second reset (the guide's example values).
- **Variation:** shift and rotate the item slightly inside its taped square between demonstrations. Keep the grasp style identical every time, and squeeze the leader's handle fully closed on every grasp.
- **Bad takes:** re-record them (left arrow) instead of keeping them.
- **Training recipe:** ACT with batch size 8, 60,000 steps and a checkpoint every 10,000 steps. This differs from the guide's example (batch size 64, 20,000 steps); `docs/04-training.md` has the reasons and the commands.
- **Time per run:** about 55 minutes, with the first checkpoint about 13 minutes after starting and another every 8 minutes. These figures come from a Tokyo team's published log for the same setup (two cameras, 640×480, batch size 8), not from a run of this project. The guide's recipe took another Tokyo team 2 hours 50 minutes with three cameras.
- **Test early:** try intermediate checkpoints on the robot instead of waiting for a run to finish.
- **Fixing a weak skill:** record 15–20 extra demonstrations at the positions where it fails, then continue training from the existing model (about 20 minutes).
- **Overnight:** queue the long runs before leaving, if the cloud GPU stays up (`scripts/overnight.sh`). Adding the organizers' recipe to the queue gives a like-for-like comparison to show judges.
- **Keep records:** push datasets and models to Hugging Face and log training to Weights & Biases. The submission template asks for the training log.

---

## 6. Schedule

### Day 1

| Time | Work |
|---|---|
| 10:00–12:00 | Set up the PC and the cloud machine, calibrate, teleoperate with cameras. Ask the organizer questions in section 8. |
| 12:00–13:00 | Build the scene and choose the rest pose. Practice. Record 5 demonstrations, replay one, and check the grasp signal. |
| 13:00–13:45 | Record skill A (sensor, about 60 demonstrations), upload, start training. |
| 13:45–14:30 | Record skill B (motor), upload, start training. |
| 14:30–15:15 | Test skill A on the robot using its first checkpoints (`scripts/try_model.sh`). Note where it fails. |
| 15:15–17:00 | Build the runner and order page with Claude against a fake robot. In between: test skill B, record fix-up demonstrations, start retrains. |
| 17:00–19:00 | First end-to-end order on the robot. Then set up the camera check on the stand camera. |
| 19:00–21:30 | End-to-end runs and fixes. Film any run that works. |
| 21:30–22:00 | Start the long overnight runs. Photograph the setup. |

### Day 2

| Time | Work |
|---|---|
| 07:00–08:00 | Test the overnight models and pick the best. |
| 08:00–10:00 | End-to-end runs and fixes. Nothing new after 09:00. |
| 10:00–11:30 | Film the demo and write the README. |
| 11:30–13:30 | Submit, rehearse the pitch, buffer. |

---

## 7. Targets, decision points and cuts

### Done means

- Each skill works 8 times in 10 on the first try.
- A full two-item kit completes 9 times in 10 with retry.
- A 60–90 second demo video exists.
- The README and submission are in.

### Build order

1. Skill A alone (this is already a demo)
2. Skill B
3. Runner with the grasp check and retry, then the order page
4. Live status and run log
5. Camera check with the stand camera
6. Optional and last: spoken status with ElevenLabs

Robot work and software run in parallel, so steps 3–5 happen while models train.

### Decision points

- **17:00 on day 1:** if skill A is not succeeding about 7 times in 10 after one round of fix-up demonstrations, drop skill B and put the remaining robot time into A.
- **09:00 on day 2:** no new features after this. Stretch items only start if core already works.

### If something is failing

- **The camera check is flaky:** drop it; the grasp check still runs.
- **The grasp signal is weak:** use firmer cubes and a full squeeze; if it stays weak, run each skill for a fixed time and rely on the camera check if you have one.
- **Skill B is weak:** drop it and demo one-item kits with the check.
- **A skill is unreliable at demo time:** replaying a good recorded demonstration with the item in its exact spot still gives a working demo.
- **Never cut:** the demo video.

### Rough odds

These are estimates, assuming no prior LeRobot experience.

| Stage | Odds of finishing |
|---|---|
| One skill working from a fixed spot | About 80% |
| Two skills plus the order page and runner | About 50–60% |
| Stretch features on top | About 25–30% |

A teammate to share the recording would raise these more than anything else.

---

## 8. Questions for the organizers at 10:00

- Does the cloud GPU stay up overnight, and can it be reached from home?
- Is 13:30 the submission deadline, or does judging start before then?
- Can the table stay untouched overnight?
- What is the judging rubric, and is there a required submission template?
- Is there a required warm-up task before the freestyle project?
- Is the PC already set up, and may I install software on it?
- Does the kit match its listing: a camera on the gripper and a second one on a stand?
- May code prepared before the event be used?

---

## 9. Who does what

| Who | Work |
|---|---|
| Me | Demonstrations, scene, lighting, camera placement, testing on the robot |
| Claude | Runner, order page, camera check, README. The training scripts and grasp check are already written. |
| ChatGPT | A second window for pasting errors while Claude is busy |
| On-site mentors | Setup, driver and calibration problems. Ask early. |

---

## 10. The 90-second demo

1. State the problem in one sentence.
2. The judge taps "Full kit".
3. The arm packs the first item and the screen ticks it off.
4. Take the second cube off its square before the arm moves. The gripper closes on nothing, the screen says so, and the arm retries once you put it back.
5. If the camera check is built: take an item back out of the tray. The screen flags the kit as incomplete and the arm re-packs it.
6. Show the run log with the measured success rate.

Things that make it land:

- Let the judge place the order, so the run is clearly not staged.
- Quote a measured number, such as 18 out of 20 runs.
- Have the video ready in case the live run fails.

---

## 11. Submission checklist

Based on AMD's project template from earlier events. Confirm against this event's requirements.

- [ ] Team information, a short summary, and images or video
- [ ] Mission description: the real-world application
- [ ] Creativity: what is novel in the approach
- [ ] Technical implementation: data capture, training and inference, with images or video
- [ ] Ease of use: how it generalizes and what interface controls the robot
- [ ] Links: demo video, Hugging Face dataset, Hugging Face model
- [ ] Code and scripts in the repository
- [ ] The Weights & Biases run for the final model

---

## 12. Setup facts from the organizers' guide

- **PC (checked on the day):** AMD Ryzen AI MAX+ 395 with Radeon 8060S, Ubuntu 24.04, PyTorch 2.11 for ROCm 7, LeRobot v0.6.2. The guide assumed an HX370 with LeRobot v0.4.1. In v0.6.2 trained models run with `lerobot-rollout`, not `lerobot-record`.
- **Training:** AMD MI300X cloud GPU through a Jupyter notebook
- **Arm ports:** the guide assumes the leader on `/dev/ttyACM0` and the follower on `/dev/ttyACM1`, but the order depends on which is plugged in first. `scripts/settings.env` uses the `/dev/serial/by-id/` paths instead, which do not change.
- **Cameras:** the guide's examples assume `top` on `/dev/video0` and `side` on `/dev/video2`. This kit's two cameras are on the gripper and on a stand, so the names here are `wrist` and `front`. `scripts/settings.env` addresses them by their `/dev/v4l/by-id/` paths, which survive a replug.
- **Accounts needed:** Hugging Face (with a write token) and Weights & Biases

### Known pitfalls

- A "Lock" error during calibration: unplug and replug the arm's power.
- Shaky video: plug the cameras into different USB ports, not one hub.
- Arrow keys not working during recording on Ubuntu: install `pynput==1.7.7` and log in with "Ubuntu with Xorg".
- Stopping a recording with Ctrl+C mid-write can corrupt a video file, which later breaks training.
- To add demonstrations to an existing dataset, use `--resume=true` and set the episode count to the number of additional ones.
- The guide's inference command has a comment after a line-continuation backslash. Remove the comment or the command breaks.
- Inference output names start with `eval_`, and an existing folder with that name causes a "File exists" error.
- Download from the cloud machine faster by packing files into a tar archive first.
- Check the power supply labels before plugging in. On the Pro version of the Seeed kit the leader arm uses 5 V and the follower 12 V, and the wrong one can damage the motors.

---

## 13. Before the event

- [ ] Create Hugging Face and Weights & Biases accounts and tokens
- [ ] Read the LeRobot imitation-learning tutorial (the organizers' FAQ asks for this)
- [ ] Gather the props in section 3
- [ ] Optional: an ElevenLabs account and API key, if you want the spoken status
- [ ] Get the project folder somewhere the PC and the cloud machine can copy it from
- [ ] Have this plan open on the laptop

---

## 14. Why this can place: evidence from earlier events

- **AMD Open Robotics Hackathon, Tokyo, 1st place:** a donut-order packing robot. It used two arms, 120+ demonstrations, the task split into subtasks with a separately trained lid-closing model, a chatbot for orders, and a USB bell to signal that a task was done.
- **Tokyo, 3rd place:** opening a drawer, placing a toy inside and closing it, with ACT, about 64 demonstrations and three cameras.
- **Paris, two 3rd-place teams:** a robot that anticipates which tool to hand over, and a voice-controlled assistant.
- **StarkHacks 2026, "Best Use of AMD Tech" (ten winners), including:**
  - Sparky: a desk companion running voice, vision and an arm on one laptop with no cloud calls
  - Autonomous Triage Kiosk: replayed about 14 recorded motions behind a voice agent, with no trained model
  - AI Battery Assembler: two first-time hackers whose arm picked and placed a battery cell
  - Cleanfinity: a camera-guided system sorting desk items into bins
- **Finishing matters:** at the Tokyo event 36 teams entered and only 20-odd submitted.

What the winners shared: a real problem stated in one sentence, small learned skills behind a software layer, an explicit "done" signal, everything running on the AMD machine, and a demo that worked live.

---

## 15. Unknowns

- This event's rubric, prize structure and field size are not confirmed.
- Training time on the MI300X comes from other teams' logs, not from a run of this project.
- Whether the kit on the table matches its listing, which shows the Advanced Kit with a camera on the gripper and a second one on a stand.
- Whether code prepared before the event may be used.

---

## 16. Links

- Organizers' guide: https://github.com/andrewgschmidt/AMD_Hackathon/tree/main
- Seeed SO-ARM101 wiki: https://wiki.seeedstudio.com/lerobot_so100m_new/
- LeRobot imitation-learning tutorial: https://huggingface.co/docs/lerobot/main/en/il_robots
- LeRobot SO-101 guide: https://huggingface.co/docs/lerobot/so101
- AMD project template: https://github.com/AlexHe99/AMD_Robotics_Hackathon_2025_ProjectTemplate
- AMD Open Robotics Hackathon recap: https://www.amd.com/en/developer/resources/technical-articles/2025/amd-open-robotics-hackathon-recap.html
- Tokyo 1st place (donut packing): https://github.com/masato-ka/GreateAkihabra_9_AMDOpenRoboticsHackathon
- Tokyo 3rd place (drawer opener): https://github.com/Robotawi/RoboTAI_AMD_Robotics_Hackathon_2025
- StarkHacks winners gallery: https://starkhacks.devpost.com/project-gallery
