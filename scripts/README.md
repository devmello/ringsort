# Scripts

Small command-line tools for the teach loop: train, move models, try them on the robot. `docs/history/04-training.md` explains when to use each; `docs/history/09-notes.md` explains the recipe.

Run them with `bash` from the same working folder every time. Each prints its usage when run with no arguments.

| Script | Runs on | Does |
|---|---|---|
| `settings.env` | both | The one place for your username, ports, arm IDs, camera setup and training recipe. Load it with `source scripts/settings.env`. |
| `cloud_setup.sh` | cloud | Once: installs the PC's LeRobot version (0.6.2) without replacing the machine's ROCm PyTorch |
| `train.sh <item> [version]` | cloud | Starts a training run from scratch, in the background |
| `retrain.sh <item> <new version> [from version] [from step]` | cloud | Continues from an existing model on a fresh copy of the dataset |
| `resume.sh <item> <total steps> [version]` | cloud | Runs an existing run for longer |
| `overnight.sh [--baseline <item>] <item>...` | cloud | Queues long runs one after another, optionally followed by the organizers' recipe for comparison |
| `push_checkpoint.sh <item> <step> [version]` | cloud | Uploads one checkpoint to Hugging Face under its own name |
| `train_report.py <log>...` | anywhere | Speed, start-up cost, checkpoints, time left; compares runs when given more than one log |
| `record.sh <item> <episodes>` | PC | Records demonstrations into `~/kitcheck_data/pick_<item>`, adding to it if it exists, then uploads |
| `align_camera.sh [item] [episode]` | PC | Browser page (http://127.0.0.1:8077) that overlays the live stand camera on a recorded demonstration and says how far off it is; frees the camera when you press Done |
| `replay.sh <item> [episode]` | PC | Replays one recorded demonstration on the follower |
| `get_model.sh <item> [label]` | PC | Downloads a model into `models/<item>/<label>/` |
| `try_model.sh <item> [label] [seconds]` | PC | Runs one pick, prints what the gripper felt, keeps score in `data/trials.csv` |
| `_lib.sh` | | Shared helpers; not run directly |

`try_model.sh` also says its verdict aloud when the optional voice is on; see `docs/history/10-voice.md`.

## Folders the scripts create

| Folder | On | Holds |
|---|---|---|
| `outputs/train/<job>/` | cloud | Checkpoints |
| `datasets/<job>/` | cloud | That run's own copy of the dataset |
| `logs/` | cloud | Training logs and process IDs |
| `models/<item>/<label>/` | PC | Downloaded models |
| `data/eval/`, `data/trials.csv` | PC | Recordings and scores of test picks |

## Settings you can override for one command

Put them in front of the command, for example `TRAIN_STEPS=30000 bash scripts/train.sh sensor`.

| Variable | Effect |
|---|---|
| `TRAIN_BATCH_SIZE`, `TRAIN_STEPS`, `TRAIN_SAVE_FREQ`, `RETRAIN_STEPS` | The recipe, for this run only |
| `TRAIN_WANDB=false` | Do not log to Weights & Biases |
| `TRAIN_PUSH=false` | Do not upload the final model |
| `TRAIN_EXTRA_ARGS="..."` | Extra options passed straight to `lerobot-train` |
| `DATASET_REPO=<user>/<name>` | Train on a dataset with a different name |
| `DATASET_ROOT=<folder>` | Train on a dataset already on disk, with no download |
| `MODEL_REPO=<user>/<name>` | Download a model with a different name |
| `RUN_TIME_S=12` | Time limit for `try_model.sh` |
| `KITCHECK_FAKE_RUN=<recorded folder>` | `try_model.sh` uses that recording in place of a real run |

## How they were tested

With LeRobot v0.4.1 on a CPU, against a public SO-101 dataset and a public SO-101 model from teams at an earlier AMD event. Nothing was run on an arm or on the AMD cloud machine. Uploading was checked only up to the upload command.
