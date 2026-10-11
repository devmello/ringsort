# 8. Demo and submission

What to show, what to say, what to film and what to hand in. The submission outline follows AMD's project template from earlier events; confirm this event's requirements on arrival and adjust. `09-notes.md` holds the evidence behind each claim and what not to claim.

## Done means

- A 60–90 second video exists by 11:30 on day 2.
- The live demo has been rehearsed three times from a reset table.
- The README, code, dataset links, model links and training log are submitted.

## The pitch

About 30 seconds:

> Hackathons like this one hand-pack hundreds of parts kits. KitCheck is a robot arm that packs a kit when you tap a button, and it checks its own work. After every pick it reads what the gripper felt: if it closed on nothing, it tries again, and if the part slipped, it asks for help. The picking is learned from about 60 demonstrations per part, trained on the MI300X and running locally on this Ryzen AI PC.

Replace "about 60" with the real number. With a fixed camera, add: "A second camera confirms the part is in the tray." With voice on, add: "It tells you what it is doing in a voice made with ElevenLabs."

## Live demo

| Step | What happens | What to say |
|---|---|---|
| 1 | Nothing yet | The pitch |
| 2 | The judge taps "Full kit" | "You place the order." |
| 3 | The arm packs the sensor; the page marks it verified | "After each pick it reads the gripper's own position record." |
| 4 | When the page shows "Picking motor", you take the cube off its square before the arm starts to move | "Now I'll steal the part." |
| 5 | The gripper closes on nothing; the page says "Picked up nothing. Trying again." You put the cube back | "It noticed without a camera, and it retries." |
| 6 | The arm packs the motor; the page shows "Kit ready" | "Both confirmed." |
| 7 | Point at the counts | "Out of N picks today, X were right first time and Y after one retry." |

Each run takes a few seconds to start, which is the moment to take the cube. Keep your hand out of the workspace once the arm is moving.

If a pick misses on its own during the demo, do not apologize. A retry happening live is the feature working.

**With voice on (doc 10),** the station says each of these lines itself. Stop talking and let the judge hear "I picked up nothing. Trying again." Check the volume against the hall before judging starts.

**With a fixed camera,** add after step 6: take a cube back out of the tray. The page shows "Kit incomplete" and the arm re-packs it. Say: "The camera watches the finished kit too."

### Timing

Each pick takes the model's start-up time plus its time limit (doc 5), and this demo has three picks including the stolen one. Measure it end to end and write it here: `__ seconds`. If it is much over a minute and a half, order a one-item kit and steal that cube.

### Reset before every demo

- [ ] One cube on each square, spares within reach
- [ ] Tray empty
- [ ] Arm in its rest pose
- [ ] Page showing "Choose a kit", no fake-robot banner
- [ ] Cameras not bumped: compare each view with the photo

### If it goes wrong

Work down this list and stop at the first one that works:

1. Full kit, live, with the stolen cube
2. One-item kit, live, with the stolen cube
3. Replay mode for the picks (cube exactly on its mark); there is no grasp check in replay mode, so say so
4. The video

## Video

Film something on the evening of day 1 as soon as an order works end to end. Replace it with a better take on day 2 if there is one.

| Shot | Length | Content |
|---|---|---|
| 1 | 5–10 s | The problem in one sentence, over a shot of the workcell |
| 2 | 30–40 s | A full kit, with the arm and the page both in frame |
| 3 | 15–20 s | Stealing a cube, the page saying it picked up nothing, the retry |
| 4 | 10 s | A real miss and retry, if one was caught on camera |
| 5 | 5–10 s | The counts on the page |

- Phone on a stand, landscape, arm and screen both readable.
- One continuous take for shot 2, so it is clearly not edited together.
- Say in the caption that the cube in shot 3 was removed on purpose.

## Numbers

Quote counts, not just percentages: "17 of 20" tells a judge how much to trust it.

- Give the first-try number and the after-retry number separately.
- Say how many picks needed a person.
- Use only runs from the final models. Start a fresh log before the judged session (doc 7).
- Fill in the "My own numbers" tables in `09-notes.md` first, and quote from there.

## README outline

Fill each section in. The headings match AMD's template.

**Team information.** Name, team number if assigned, one-paragraph summary, one photo or the video link.

**Mission description.** The real-world problem: hand-packing parts kits and small orders. Who has it. What KitCheck does about it in two sentences.

**Creativity.** A learned robot that knows when it got it wrong. Every pick is checked with signals the model does not control: the gripper's own position record, which needs no extra hardware, and a fixed camera when one is available. Retry for a miss, a person for anything uncertain.

**Technical implementation.**

- *Data capture:* how many demonstrations per skill, what was varied, a photo of teleoperation, links to both datasets.
- *Training:* model type (ACT), batch size, steps, your measured time on the MI300X, the loss curve from Weights & Biases, links to both models. The training-time decision and its evidence are in `09-notes.md`.
- *Inference:* runs on the Ryzen AI PC with no cloud calls; the measured success counts; the video.
- *Checks:* how the grasp check reads the recording; your own figures for how often it agreed with what you saw.
- *System:* the two diagrams from `00-architecture.md`.
- *Voice, if used:* the station's lines are made ahead of time with the ElevenLabs text-to-speech API and played from files, so the demo needs no connection.

**Ease of use.** One tap to order. Adding a part takes one set of demonstrations, one training run, one grasp reference and one entry in `config.json`. No code changes.

**Limits.** Fixed pickup positions, two item types, a start-up delay on every pick, and a grasp check that cannot see whether the cube stayed in the tray. Listing these yourself reads better than a judge finding them.

**What was prepared beforehand.** Say it plainly; the table is in `09-notes.md`.

**Links.** Video, datasets, models, this repository.

## What to hand in

Based on the earlier template:

- [ ] README with the sections above
- [ ] Code and scripts in the repository
- [ ] The Weights & Biases run folder for each final model. On the cloud machine, `wandb/latest-run` is a shortcut; copy the folder it points to.
- [ ] Links to the Hugging Face datasets and models, set to public
- [ ] The video, uploaded somewhere judges can open
- [ ] A filled-in copy of the model table from doc 4

## Questions a judge may ask

| Question | Answer |
|---|---|
| Why two models and not one? | ACT cannot be told which item to pick, so each item gets its own model. Each new part is independent of the others. The cost is a start-up delay per pick. |
| How does it know it missed? | When the gripper closes on a cube it cannot reach the commanded position. That gap is in the data LeRobot records anyway. No gap, nothing was picked up. |
| Isn't that check very simple? | Yes, on purpose. It shares nothing with the model's vision, so it fails differently from the model. |
| Does it know the part is in the tray? | Not from the gripper alone: it knows the part was held and released at the tray. A fixed camera confirms the tray when one is set up. |
| How reliable is it? | Give the counts from the page. |
| Why did you change the training recipe? | The half-minute answer in `09-notes.md`, with your own timings. |
| What happens with a new part? | Record demonstrations, train, save a grasp reference, add a config entry. |
| Is the voice generated live? | No. It has a fixed set of lines, made once with the ElevenLabs API and played from files. That is why it works offline. It does not listen. |
| What doesn't work? | The limits listed in the README. |
| How did you use the AMD hardware? | Training on the MI300X, inference on the Ryzen AI PC through ROCm, everything local at demo time. |
| What would you do next? | Keep the models loaded to remove the delay, add a feeder so nobody restocks by hand, try one language-driven model for all parts. |
| Which parts did you build yourself? | Say it as it is: you built the workcell, recorded every demonstration, ran the training and did the testing; the software was written with AI assistance, some of it before the event, and you can explain how each part works. |

Before judging, make sure you can explain three things without notes: how the grasp check tells a hold from an empty grasp (doc 6), how the runner decides between retrying and asking for help (doc 5), and why you trained with a small batch (`09-notes.md`).
