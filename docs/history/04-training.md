# 4. Training

Turning each dataset into a model on the AMD MI300X cloud GPU, and getting that model back to the PC. The scripts in `scripts/` wrap the organizers' `lerobot-train` command with one deliberate change: a smaller batch size and frequent checkpoints, so a model can be tested minutes after training starts. `09-notes.md` records the reasoning for judges.

## Done means

- One trained ACT model per skill, on Hugging Face and downloaded to the PC.
- The Weights & Biases run for each final model is saved for the submission.
- Your own timings are written into `09-notes.md`.

## One-time setup on the cloud machine

The organizers give each team a cloud machine that opens as a Jupyter notebook. Run their notebook's setup cells in order:

1. Confirm the GPU. Expected device name: `AMD Instinct MI300X VF`.
2. Install ffmpeg 7.
3. Clone LeRobot and install it.
4. Log in to Weights & Biases and Hugging Face with your tokens.

**Check the LeRobot version.** The cloud machine must run the same LeRobot as the PC, or a model trained there may not load on the PC. The PC at the event has **v0.6.2**, installed from source (commit `4aaff99b`), not the v0.4.1 the organizers' notebook checks out. Match the PC, not the notebook:

```shell
cd lerobot && git fetch && git checkout 4aaff99b && pip install -e '.[dataset]'
python -c "import lerobot; print(lerobot.__version__)"    # expect 0.6.2
```

Check on the PC with `pip list | grep lerobot` if in doubt. v0.6.2 needs Python 3.12; if the notebook's environment is older, ask a mentor before installing.

**Get the scripts onto the cloud machine.** Upload the project's `scripts` folder with Jupyter's upload button, or clone your repository there. Then open a terminal (File → New Launcher → Other → Terminal) and work from the folder that contains `scripts`:

```shell
export HF_USER=<your Hugging Face username>
```

Always start the scripts from this same folder. They keep their runs, logs and dataset copies in sub-folders of it.

## The commands

| To do this | Run this on the cloud machine |
|---|---|
| Train a skill from scratch | `bash scripts/train.sh sensor` |
| See speed, checkpoints and time left | `python scripts/train_report.py logs/kitcheck_act_sensor.log` |
| Send a checkpoint to Hugging Face for testing | `bash scripts/push_checkpoint.sh sensor 20000` |
| Retrain after adding demonstrations | `bash scripts/retrain.sh sensor v2` |
| Run an existing run for longer | `bash scripts/resume.sh sensor 100000` |
| Queue the overnight runs | `bash scripts/overnight.sh sensor motor` |

| To do this | Run this on the PC |
|---|---|
| Download the finished model | `bash scripts/get_model.sh sensor` |
| Download a checkpoint you sent | `bash scripts/get_model.sh sensor 020000` |
| Try a model on the robot and keep score | `bash scripts/try_model.sh sensor 020000` |

For the motor skill, use `motor` in place of `sensor`. Each script prints its usage when run with no arguments, and stops with a plain message when something is missing.

Training runs in the background and survives a closed browser tab. Each start prints how to follow the log, how to stop the run, and how many demonstrations it loaded.

## What `train.sh` runs

```shell
nohup lerobot-train \
  --dataset.repo_id=${HF_USER}/kitcheck_pick_sensor \
  --dataset.root=datasets/kitcheck_act_sensor \
  --policy.type=act \
  --batch_size=8 \
  --steps=60000 \
  --save_freq=10000 \
  --output_dir=outputs/train/kitcheck_act_sensor \
  --job_name=kitcheck_act_sensor \
  --policy.device=cuda \
  --policy.push_to_hub=true \
  --policy.repo_id=${HF_USER}/kitcheck_act_sensor \
  --wandb.enable=true \
  --wandb.disable_artifact=true \
  > logs/kitcheck_act_sensor.log 2>&1 &
```

| Setting | Why |
|---|---|
| `--batch_size=8` | LeRobot's default for ACT, and the fastest route to a testable model on this machine (evidence below). The organizers' example uses 64. |
| `--steps=60000` | About 55 minutes at the measured speed. The final model uploads itself when the run ends. |
| `--save_freq=10000` | A checkpoint about every 8 minutes, so there is something to test long before the run ends. |
| `--dataset.root=datasets/<job>` | A fresh copy of the dataset for this run. LeRobot reuses an old local copy without checking for new demonstrations. |
| `--wandb.disable_artifact=true` | Without it, every checkpoint's 200 MB model file is also uploaded to Weights & Biases. The loss curve is still logged. |
| `--policy.device=cuda` | Correct on AMD hardware too. |

The numbers live in `scripts/settings.env`. Change them there, not in the scripts.

## What to expect on the clock

These figures come from three training logs that teams at AMD's Tokyo hackathon published in December 2025. All three ran ACT at 640×480 on the same kind of machine you will get (MI300X VF, 160 processor cores).

| Run | Cameras | Batch | Steps | Total time | Per step once warmed up |
|---|---|---|---|---|---|
| Greate Akihabara, warm-up task | 2 | 8 | 20,000 | 21 min | 0.044 s |
| RoboTAI, warm-up task | 3 | 64 | 20,000 | 2 h 50 min | 0.37 s, plus 0.12 s waiting for data |
| RoboTAI, drawer project | 3 | 64 | 40,000 | 4 h 40 min | 0.38 s |

The first row matches the plan when the model has two cameras at 640×480 and batch size 8. From it:

| Milestone | Time after starting |
|---|---|
| Warm-up finished, full speed | about 5 min |
| 10,000-step checkpoint | about 13 min |
| 20,000-step checkpoint | about 21 min |
| Each further 10,000 steps | about 8 min |
| 60,000 steps, run complete | about 55 min |

Expect similar numbers, not identical ones. With one camera (setup B) each step should take roughly half as long. `train_report.py` gives your real figures as soon as the run is past warm-up.

### The first minutes are slow, and that is normal

The GPU library tunes itself the first time it sees each image and batch shape. In the three logs the first 200 steps took 3, 5 and 9.5 minutes; after that the runs went at full speed. There was a second slow patch of 2–3 minutes when the run first reached the end of the dataset.

Do not judge speed, or restart the run, during the first ten minutes.

### Reading a log line

```
step:20K smpl:160K ep:371 epch:37.06 loss:0.071 grdn:9.641 lr:1.0e-05 updt_s:0.046 data_s:0.010
```

`updt_s` is the time the GPU spent on one step. `data_s` is the time spent waiting for the next batch of data. Their sum is the time per step. `train_report.py` reads these for you and works out the time left.

## Why batch size 8

A step at batch 64 takes several times longer than a step at batch 8, but it does not teach the model several times as much. In the logs, a batch-64 step took 8.6 times as long as a batch-8 step (about 5 times after allowing for the third camera), and moved the training loss only about twice as far.

The two warm-up-task logs show the result. Both trained on 10 demonstrations:

| Training loss reached | Batch 64, three cameras | Batch 8, two cameras |
|---|---|---|
| 0.2 | 28 min | 10 min |
| 0.1 | 51 min | 16 min |
| 0.071 | 78 min | 21 min |

This comparison is not exact: the datasets differ, and the three-camera run did more work per step. Allowing for the extra camera and for that run's data waits, the batch-8 run still reached each loss level in a bit over half the time.

Rough estimate for KitCheck, extrapolated from these logs: a first usable model 20–45 minutes after starting with batch 8, against 45–100 minutes with the organizers' recipe. Training loss is only a guide; the robot test decides.

## What changes the time per step

Decided when recording, not when training:

| Setup | Work per step, relative |
|---|---|
| 1 camera at 640×480 | 0.5 |
| 2 cameras at 640×480 | 1.0 |
| 3 cameras at 640×480 | 1.6 |
| 2 cameras at 320×240 | 0.3 |

These ratios were measured by timing LeRobot's ACT model on a CPU. The camera-count ratio should carry over to the GPU. The gain from smaller images will be smaller on the GPU than shown here.

- **Two cameras for the model at most.** A third adds about 60% to every training run.
- **Keep 640×480** unless training time is still the bottleneck after the first cycle. Smaller images train faster but show the model less detail, every earlier team's published run used 640×480, and the choice cannot be changed without re-recording.
- **Keep demonstrations short.** Fewer frames means fewer steps to cover the data the same number of times.

## What does not help

- **More data-loading workers (`--num_workers`).** In the logs the GPU step was about 95% of each step once the dataset was a realistic size. The default of 4 is enough.
- **A bigger batch.** It makes each step proportionally slower.
- **Mixed precision.** LeRobot supports it through `accelerate launch --mixed_precision=...`, and it may shorten the GPU step, but it is untested on this hardware. Not a day-1 experiment.

## Training both skills

Start the second skill's training as soon as its dataset is uploaded; do not wait for the first to finish. Both runs share one GPU, so each slows down while they overlap. Run `train_report.py` on the first run before and after to see by how much.

## Getting a model to the PC

**The final model** uploads to Hugging Face when a run completes. On the PC:

```shell
bash scripts/get_model.sh sensor
```

**A checkpoint, before the run ends.** On the cloud machine, then on the PC:

```shell
bash scripts/push_checkpoint.sh sensor 20000     # cloud machine
bash scripts/get_model.sh sensor 020000          # PC
```

**A run you stopped early** never uploads its final model. Send the checkpoint you want with `push_checkpoint.sh`.

**Without Hugging Face.** Pack the folder on the cloud machine and download it through Jupyter's file browser:

```shell
tar cjvf sensor_020000.tar.bz2 outputs/train/kitcheck_act_sensor/checkpoints/020000/pretrained_model
```

Models land in `models/<item>/<label>/pretrained_model` on the PC, about 200 MB each. The label is `final`, a step number like `020000`, a version like `v2`, or both like `v2_010000`.

## Which model is in use

Fill this in as you go. It is also the record you need for the README.

| Skill | Label | Steps | Demonstrations | First-try success | Notes |
|---|---|---|---|---|---|
| sensor | | | | / 10 | |
| motor | | | | / 10 | |

## Judging a model

The loss curve only tells you training ran. The test that counts is ten picks on the robot, with the cube placed in different spots inside its square and different tray contents:

```shell
bash scripts/try_model.sh sensor 020000
```

Each run prints what the gripper felt (placed, missed or dropped) and a running score for that model. The gripper cannot see the tray, so count a pick as good only if the cube is in it. Write the result in the table above.

| Result | Next step |
|---|---|
| 8 or more out of 10 | Good enough. Move on. |
| 5–7 out of 10 | Try a later checkpoint first. If it is no better, note where it fails, record 15–20 demonstrations there, retrain |
| Under 5, or the arm moves vaguely and never commits | Something is mismatched: check camera names, camera positions and the rest pose before recording more |

## Retraining after adding demonstrations

```shell
bash scripts/retrain.sh sensor v2
```

It does two things:

1. **Downloads a fresh copy of the dataset,** so the new demonstrations are used.
2. **Starts from the model you already have,** so it needs far fewer steps than starting over: 20,000, about 21 minutes. That number is a starting point, not a tested value.

Check the line it prints: `loaded: N demonstrations` must show the new total. If it shows the old number, the upload from the PC did not finish.

The next fix is `bash scripts/retrain.sh sensor v3 v2`, which starts from v2. If a continued model is no better than the one it started from, train from scratch on all the data: `bash scripts/train.sh sensor v3`.

## Running the same run for longer

When the data has not changed and you only want more steps:

```shell
bash scripts/resume.sh sensor 100000
```

The number is the new total, not the number of steps to add.

## Overnight

Time is free overnight, so use it for the long version.

1. Confirm the cloud machine stays up overnight.
2. Queue the runs:

```shell
bash scripts/overnight.sh --baseline sensor sensor motor
```

This trains each skill from scratch for 150,000 steps on the final data, one after the other, about two hours each. With `--baseline sensor` it then runs the organizers' recipe (batch 64, 20,000 steps) on the sensor data. The two sensor runs see almost the same number of samples, so the morning comparison is like for like, and it is your own evidence for the judges. Leave `--baseline sensor` out if you only want the long runs.

3. Check `logs/overnight.log` shows the first run started before you leave.

In the morning:

```shell
python scripts/train_report.py --md logs/kitcheck_act_sensor_long.log logs/kitcheck_act_sensor_guide.log
```

Then test the overnight models against the best ones from day 1 and keep whichever does better on the robot. Longer training is not guaranteed to be better. The step counts above are examples, not tested values.

## Settings to leave alone

ACT's defaults plan 100 actions at a time and run all of them before looking again, which is about three seconds at 30 frames per second. That makes the arm commit to a motion once it starts. Changing this is a possible tuning step, not a day-1 task. The same goes for the learning rate and the model's size.

## Common problems

| Symptom | Fix |
|---|---|
| "The run stopped while starting" with a Weights & Biases message | Log in first (the notebook's login cell), or set `TRAIN_WANDB=false` |
| The first few hundred steps crawl | Normal warm-up; see "The first minutes are slow" |
| "already exists" when starting | Add a version label (`train.sh sensor v2`) or use `resume.sh` |
| `loaded:` shows fewer demonstrations than you recorded | The dataset upload from the PC did not finish. Upload it, then start a new version |
| "Could not push packet to decoder" | A corrupt video in the dataset. See doc 3 |
| Dataset not found | Check the dataset finished uploading and `HF_USER` is right |
| Dataset uploaded by hand is rejected for its version | It needs a version tag. The notebook's last cell shows how: `create_tag(<dataset>, tag="v3.0", revision="main", repo_type="dataset")` |
| Other model types fail to import | Only ACT works without extra installs. SmolVLA and Pi need `pip install -e ".[smolvla]"` or `".[pi]"` |

## How this doc was checked

- Every script was run with LeRobot v0.4.1 on a CPU against a public SO-101 dataset from one of the Tokyo teams (two cameras, 640×480), for a few steps each: training, retraining from a model, resuming, the overnight queue and the report. A real public model was downloaded with `get_model.sh`. Uploading was checked only up to the upload command.
- Nothing was run on the AMD cloud machine. Timings are read from other teams' published logs, not measured for this project.
