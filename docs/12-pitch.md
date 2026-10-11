# 12. Pitch and demo: how it plays out

The story, the live demo click by click, what to do when something goes wrong, the video, and the judges' questions. The slides are the "RingSort pitch" deck; its speaker notes hold the same script. This replaces the demo parts of `history/08-demo-and-submission.md`, which predate the factory framing.

**The format (from the organizers):** judging starts **sharply at 2:00 PM**. Judges come to each team's table; stay at the table until judging is over. Each pitch is **3 minutes of presentation, then 3 minutes of questions**. Top teams go to the finals and pitch again, so the same 3 minutes has to work twice.

**What the judges score, and where each lands:**

| Criterion | Where it lands in the 3 minutes |
|---|---|
| Technical execution: does it work, how hard, how well built | The live demo, on the real arm; "two ways to pick, measured"; everything runs on the Ryzen AI PC |
| Creativity: original idea or a fresh take | The cell checks itself with the gripper's own position record (no extra sensor) and a camera that knows where each part was taught |
| Impact: would people use it, does it solve a real problem | Trustworthy bins before packing; first-pass yield and yield with retry on screen; a new part type with no code |
| Demo and presentation | A judge starts the order and takes a part away; the cell catches it |

**Winning teams must publish** their full code, training datasets, trained models and demo videos publicly on GitHub. See "Publishing" below.

---

## The story in one breath

> In a factory, mixed parts are sorted into bins before anyone packs kits from them, and a bin is only useful if you can trust it. Robots taught by demonstration fail silently. RingSort is a sorting cell that checks every pick with signals the model doesn't control: the gripper's own position record and a fixed camera. It retries a miss on its own and calls the operator for anything else.

Three things to land, in this order:

1. **The problem is trust, not picking.** "Our first model placed 2 of 23, and nothing told us which 21 failed."
2. **The check is the product.** The gripper's gap needs no extra sensor; the camera knows where each part was taught.
3. **It's measured.** First-pass yield and yield with retry, on screen, from the run log.

---

## Run of show (3:00 exactly)

| Time | Slide or screen | What you do | What you say (short form) |
|---|---|---|---|
| Time | Slide or screen | What you do | What you say (short form) |
|---|---|---|---|
| 0:00 | Cover | Stand beside the table | "This is RingSort: a factory sorting cell that knows when it got a pick wrong." |
| 0:05 | Sorting comes before packing | | Bins must be trustworthy; robots taught by demonstration fail silently; "2 of 23, and nothing told us which 21 failed." |
| 0:20 | When the model gets it wrong | The clip loops by itself | The model carried the ring to the bin and it fell beside it; the gripper check said DROPPED and the camera found it on the table. "Two checks, neither of them the model." |
| 0:32 | RingSort is the sorting cell | | Rings stand in for part types, cups are bins, packing happens later. "Let me show you." |
| 0:40 | The **dashboard** and the arm | Turn to the table | See "The demo, click by click" below (75 s) |
| 1:55 | Every pick is checked… | Back to slides | Gripper record, stand camera, operator only when needed |
| 2:12 | One work order, start to finish | | The 11:08 order plays: red and purple placed, teal missed and caught by the gripper check |
| 2:30 | Consistent data beat more training | | Teal: steady camera, same spot every take, worked at 20k steps; purple's camera moved, needed 50k; red's camera moved after recording, needed 40k |
| 2:45 | Built on AMD | | Trained in AMD Cloud (Radeon AI PRO R9700); the Ryzen AI PC runs the whole cell, no cloud at run time |
| 2:52 | Bins you can trust | | Who uses it; thank you. **Stop at 3:00.** |

The gripper chart, the camera slide and "What building it taught us" come **after** the closing slide, as backups for the 3 minutes of questions.

Rehearse with a timer at least three times. A pick takes about 15 s plus start-up, so keep talking while the arm moves; never wait in silence.

---

## The demo, click by click

**Before it starts** the dashboard is open at http://127.0.0.1:8078, live view on, the arm at rest, purple and teal rings on their marks (both say **ready** in the parts view), bins empty, and the camera badge reads "Camera matches teal's takes".

1. **The cell looks at its table** (15 s)
   - Point at the stand camera view: each ring circled, its taught area drawn, the label **ready**.
   - Say: "Before it moves, the cell looks at its table. It finds every ring and checks it's where the cell was taught to pick it."
2. **A judge starts a work order** (10 s)
   - Hand over the mouse: "Pick a work order." Suggest **What's on the table**, which sorts exactly what the camera sees.
   - The tower light goes green and the camera view goes grey: "Cameras handed to the robot."
   - Say: "Streaming the cameras slowed the model, so during a pick the robot gets them."
3. **A good pick** (25 s)
   - The arm sorts the first ring, the cell shows **PLACED**, the bin count goes up, and the cell plays back its own recording of the pick.
   - Say: "That's the cell's own recording, not mine. It checked the pick from the gripper's position record."
4. **A caught failure** (25 s)
   - As the arm sets off for the second ring, lift that ring off the table.
   - The gripper closes on nothing: **MISSED**, amber light, and the event log says it's retrying.
   - The light goes red and the operator buttons appear (one attempt per part). Put the ring back on its mark and tap **Retry pick**.
   - Say: "It doesn't count a pick it can't confirm. It stops and asks me."
5. **The numbers** (15 s)
   - Point at Shift numbers: first-pass yield vs yield with retry.
   - Tap **Send bins to packing**: "These bins are ready for the packing station."

**Let a judge do steps 2 and 4** if they're willing. A judge who takes the ring away themselves can see it isn't staged.

### If something goes wrong

| What happens | What you do |
|---|---|
| A pick misses for real | That *is* the demo. "Watch: it noticed." Let it retry. On an operator call, press **Retry pick** once, then **Placed by hand** if it misses again. |
| The cell flags DROPPED | "It held the ring and lost it, so it won't pretend the bin has it." Press **Placed by hand** after putting the ring in its cup. |
| The parts view says a ring is "outside taught area" | Move the ring onto its mark and wait for **ready**. "It won't pick from somewhere it was never taught." |
| The camera badge says the camera moved | Don't touch it mid-pitch; say what it caught. Before the slot: `scripts/align_camera.sh teal 20` (or `purple 30` if purple is the demo color). |
| The arm won't connect ("no status packet") | The runner retries 3 times on its own. If it still fails: unplug and replug the arm's power, then click the work order again. |
| The dashboard hangs | Ctrl+C it, run `scripts/dashboard.sh` again (5 s). Or run the same order in a terminal: `python -m kitcheck.runner "Sort all"` with `--label <step>`. |
| Nothing works | Go back to the clip on slide 3, scroll to **Recorded picks** on the dashboard and play the clips, then walk the dashboard in rehearsal mode (below). Say plainly that they're recordings from earlier. |

**Rehearsal mode** (no arm, for practice and as the last fallback):

```bash
KITCHECK_FAKE_RUN=examples/runs/purple_placed scripts/dashboard.sh
```

---

## Checklist, 15 minutes before the slot

- [ ] Camera badge: "Camera matches teal's takes" (or purple's); only if it says moved, run `scripts/align_camera.sh teal 20`
- [ ] Lighting as during recording; nobody standing behind the table in the camera's view
- [ ] Rings on their marks, parts view says **ready** for each; bins empty
- [ ] Arm at rest; one test pick done in the last 15 minutes
- [ ] Dashboard open, model menu set to the best checkpoint for each color (teal 020000, purple 050000, red 040000)
- [ ] Shift numbers show real runs from this morning (don't restart the dashboard after them; the shift resets)
- [ ] Deck open on the cover, in a second window; the **[__]** numbers filled in
- [ ] Demo video downloaded locally, ready to play; **Recorded picks** on the dashboard lists the best clips (press "Keep this clip" on good picks during the morning)

---

## Numbers to have before presenting

| Number | Where it comes from | Goes on |
|---|---|---|
| ACT best checkpoint: placed of runs | Same, runs with `--label <step>` | Same |
| First-pass yield and yield with retry for full orders | Dashboard shift numbers | Said live |
| Grasp check agreement on our runs | Compare `data/runs.jsonl` with what you saw | README, Q&A |

Never quote a number you haven't measured today. "We don't have that number" is a fine answer.

---

## The submission video (60–90 s)

**Not needed for judging** (the pitch is live). Winning teams must publish demo videos on GitHub, and the clips in `media/picks/` already show the cell working. The minimum: one unedited phone take of a good full run in the morning, which also backs up the live demo. The shot list below is only for a polished version if there's time.

Film on a phone on a stand, the table and the dashboard both in frame if you can, otherwise cut between them.

1. **0–8 s:** title card, "RingSort: a factory sorting cell that knows when it got a pick wrong."
2. **8–20 s:** the parts view on the dashboard: rings found, **ready**.
3. **20–40 s:** "What's on the table" order: first ring picked, **PLACED**, bin count, the recording plays back.
4. **40–60 s:** a hand lifts the next ring; **MISSED**; the ring goes back; retry; **PLACED**.
5. **60–75 s:** shift numbers; "Send bins to packing".
6. **75–90 s:** end card: AMD Ryzen AI PC + AMD Cloud (Radeon AI PRO R9700), the GitHub link.

Film it as soon as one full run works on day 2, and keep the best take. Don't leave it for last.

---

## Judges' questions

**Why does teal sometimes miss?**
The model is a 20,000-step checkpoint, our least-trained. When it misses, the gripper closes beside the ring, and the gripper check says MISSED instead of counting it. That's the point of the cell: a model that is right most of the time, and a check that catches the rest.

**Why not just use the camera to check everything?**
The camera can't see into the teal and red bins, and it's blocked by the arm during a pick. The gripper record works on every pick with no extra hardware. They cross-check each other.

**What can't it tell?**
A part that bounces out after a clean release reads as placed, and the camera only confirms the purple bin. Fixed color thresholds would need re-measuring under very different light.

**How does it know where a part was taught?**
From the first frame of each of the 155 demonstrations: where the ring started, mapped into one camera view using the fixed parts of the scene. Half the purple takes started within 49 px of the middle, and teal within 15 px.

**Why did ACT do poorly?**
Time. At batch size 8, our day-1 checkpoints had seen 80–160k samples; the organizers' recipe sees 1.28M. Grasps got closer to the target between 10k and 20k steps. The camera moving under trained models also cost us runs.

**How do you add a new part type?**
Record about 50 demonstrations, add its color range and an entry to `config.json`, then train an ACT model and rebuild the references (`python -m kitcheck.grasp learn`, `python -m kitcheck.vision learn`). No new code.

**What runs on AMD?**
Training in AMD Cloud on Radeon AI PRO R9700 GPUs: 0.27 s per step alone, about 0.44 s each with two in parallel. Everything else runs locally on the Ryzen AI MAX+ 395: models, cameras, parts view, dashboard. No cloud at run time.

**What was the biggest lesson?**
Good data matters more than anything. Teal's camera stayed within 3 px across all 45 takes and the ring started in nearly the same spot each time (half within 15 px); its model placed at 20,000 steps. Purple's camera moved three times during recording and it needed 50,000; red's camera moved after recording and it needed 40,000. Teal was also recorded last, when we were most practiced.

**What would you do with another week?**
The packing station downstream, a feeder, keeping the model loaded between picks, and one language-conditioned model (e.g. SmolVLA) for every part type.

**What was prepared before the event?**
The idea, the plan and the design notes, worked out with chatbots. Everything on the robot, every demonstration and model, the dashboard and the camera checks were built here, and the training pipeline was regenerated here for LeRobot 0.6.2. A few small helper scripts and the grasp-check design date from the night before. (See `history/09-notes.md`.)

**How reliable is the gripper check?**
On public SO-101 data: 19 of 20 real picks read as placed, 20 of 20 simulated empty grasps as missed, 75 of 76 simulated slips as not placed. In our own 155 demonstrations the hold shows every time. [Add today's agreement on robot runs.]

---

## Day 2 timeline, working back from 2:00 PM

| Time | Work |
|---|---|
| 07:00 | Camera check. ACT, 5 single-attempt runs each for purple and teal. |
| 09:00 | Decide what picks in the demo (spec, section 9). **Nothing new after this.** |
| 09:00–10:30 | Full sorting runs from the dashboard for the shift numbers. Film the video the first time a full run works. |
| 10:30–12:00 | Fill the deck's `[__]` numbers and the README. Publish to GitHub and Hugging Face (below). |
| 12:00–13:30 | Rehearse the 3 minutes with a timer, at least three times; practice the questions. |
| 13:30–14:00 | The 15-minute checklist; eat something; stay at the table. |

## Publishing (required for winners, do it before judging)

- [ ] **Code:** a public GitHub repo of this folder. It isn't a git repo yet; `.gitignore` already leaves out `data/`, `models/`, logs and keys. Check for secrets before the first push.
- [ ] **Datasets:** `varunsatish2017/kitcheck_pick_purple`, `_teal`, `_red` on Hugging Face (already public).
- [ ] **Models:** the checkpoints you demo, public on Hugging Face (red and purple 10k/20k are; teal and the later ones are not yet).
- [ ] **Demo video:** uploaded (YouTube or the repo's releases) and linked from the README.
- [ ] README links filled: video, datasets, models, W&B.

## If the slot is shorter or longer

- **2 minutes:** cover → problem (one sentence) → dashboard demo steps 2–4 → "Built on AMD" in one sentence → close.
- **Finals, if longer:** add the gripper chart (backup A) after "Every pick is checked", and the camera slide (backup B) after it.
- **Science-fair style (judges walk up):** skip the slides. Start at the dashboard parts view, invite the judge to start an order and take a ring away, then show the numbers. Keep the deck open for the gripper chart.
