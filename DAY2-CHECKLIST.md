# Day 2 checklist (Sunday, October 11)

Judging starts at **2:00 PM sharp**, at your table: 3 minutes of pitch, then 3 minutes of questions. Stay at the table until judging is over. The full plan, fallbacks and judge questions are in [docs/12-pitch.md](docs/12-pitch.md); the slides are the "RingSort pitch" deck.

## 1. Before you leave, or on your phone (5 min)

- [ ] Check teal's training on the cloud machine (it should be past step 50,000)
- [ ] Confirm the cloud GPU's name for the deck: `rocm-smi --showproductname`
- [ ] Download the newest purple and teal checkpoints through the browser (uploads from the cloud are blocked); they go in `models/<color>/<step>/` on the PC

## 2. Set up at the table (15 min)

- [ ] Lights on, rings on their marks, arm at rest
- [ ] Terminal: `cd ~/kitcheck && conda activate lerobot && source scripts/settings.env`
- [ ] Camera check: the dashboard badge should say **"Camera matches teal's takes"** (or purple's). The camera is in teal's recorded position, 1.7° turned from purple's; **don't realign it to purple 30** while teal is the demo color. Terminal version: `python -m kitcheck.camalign --once --ref teal:20`
- [ ] Dashboard: `scripts/dashboard.sh`, then open http://127.0.0.1:8078
- [ ] **Parts view under the hall lights: every ring circled and "ready"?** If a ring isn't found, ask Claude to re-measure the colors from a live frame (they were never tried live: the room was dark)

## 3. Test what picks, done by 9:00 AM (about 1 hour)

- [ ] **Camera replay, 5 runs each for teal and purple.** In the dashboard set each color to "camera replay" and run a single-color order. Never run on the arm yet: watch the first run with a hand near the arm's power. Press **Keep this clip** on good picks.
- [ ] **ACT, 5 runs each** with the newest checkpoints
- [ ] **9:00 decision:** whichever places at least 4 of 5 is the demo. **No new features after this.**

## 4. Collect the material (9:00–10:30)

- [ ] Run **Sort all** from the dashboard several times, for the shift numbers. **Don't restart the dashboard afterwards:** the shift numbers reset.
- [ ] **Film one phone take** of a good full run: a ring placed, then you lift the next ring away, the cell says MISSED, put it back, it retries. No editing needed. It's the backup if the live demo fails, and the "demo video" if you win.

## 5. Send Claude these (it updates the deck, README and spec)

- [ ] Results: camera replay X of 5, ACT X of 5 (or the output of `python -m kitcheck.runner --summary`)
- [ ] Team name and your name (deck cover and script)
- [ ] The GPU name from step 1
- [ ] The GitHub account for the public repo
- [ ] Phone videos, if you want them in the README

## 6. Publish (by noon; required only if you win, but easier now)

- [ ] **Code:** public GitHub repo (Claude sets it up and pushes after you confirm)
- [ ] **Models:** make the teal model and the checkpoints you demo public on Hugging Face (datasets already are)
- [ ] **Video:** the phone take, plus the clips already in `media/picks/`; link them from the README

## 7. Rehearse (noon to 1:30)

- [ ] The 3-minute pitch with a timer, **at least three times** (script in the deck's speaker notes)
- [ ] Read the 10 judge questions and answers in docs/12-pitch.md

## 8. 1:30 to 2:00 PM

- [ ] Camera badge "Camera matches teal's takes", rings "ready", bins empty, arm at rest
- [ ] One test pick
- [ ] Deck open on the cover, dashboard in the other window
- [ ] Stay at the table

## Remember

- **The dashboard holds the cameras.** Press **Pause live view** before using `record.sh` or `try_model.sh`.
- **If the live demo fails:** slide 3's clip (the caught drop) and the dashboard's **Recorded picks**, then rehearsal mode:
  `KITCHECK_FAKE_RUN=examples/runs/purple_placed scripts/dashboard.sh`
- **Never quote a number you didn't measure today.** "We don't have that number" is a fine answer.
