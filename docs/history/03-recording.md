# 3. Recording

Recording the demonstrations each skill learns from. This is the part only you can do, and the quality of these demonstrations decides how well the arm works more than anything else in the project.

Every command here needs the settings loaded in the terminal first: `source scripts/settings.env` (doc 2).

## Done means

- About 60 clean demonstrations per skill, saved locally and uploaded to Hugging Face.
- One recorded demonstration has been replayed on the arm and it picked the item.
- The grasp check can see the hold in the recordings, and its reference file for each item is saved.

## The three skills

The proof of concept sorts three colored rings: each ring starts somewhere in its own pick area and is dropped into its own cup. One skill per color.

| Skill | Dataset | Task text (from `config.json`) |
|---|---|---|
| Red | `${HF_USER}/kitcheck_pick_red` | `Pick the red ring and drop it in the red cup` |
| Purple | `${HF_USER}/kitcheck_pick_purple` | `Pick the purple ring and drop it in the purple cup` |
| Teal | `${HF_USER}/kitcheck_pick_teal` | `Pick the teal ring and drop it in the teal cup` |

Record red first and start its training before recording the next color. Keep all three rings on their spots during every recording (except the one being moved), so each model sees the same scene it will see at run time.

**Grasp the ring across its full width, not by the rim.** Pinching the thin rim lets the gripper close almost fully, and the grasp check then cannot tell a held ring from an empty gripper. Across the full width, the jaws stay clearly open while holding.

## Fix the image settings before the first recording

Camera count and image size are baked into the dataset. They cannot be changed later without re-recording, and they set how long every training run takes (doc 4 has the numbers).

- **The camera setup you chose in doc 1,** unchanged from now on. Two cameras for the model at most; a third adds about 60% to each training run.
- **640×480,** the guide's setting and the one every earlier team's published run used.
- **Short demonstrations.** End each one with the right arrow as soon as the arm has parked. Idle frames lengthen training without teaching anything.

## What one demonstration looks like

1. Start with both arms in the rest pose (see doc 1).
2. Reach to the item's square and grasp the cube the same way every time.
3. **Squeeze the leader's handle fully closed** and keep it closed for the whole carry.
4. Lift, turn to the tray, move over that item's half, lower, then open the handle clearly to release.
5. Return to the rest pose.
6. Hold still for one to two seconds.
7. Press the right arrow to end the demonstration.

Aim for a smooth 10–12 seconds. Slow, hesitant demonstrations teach a slow, hesitant arm.

**Why the full squeeze matters.** The model copies how hard you squeeze, and the grasp check works by seeing that the gripper was told to close further than the cube allowed. In 20 public demonstrations from earlier teams, the one where the operator barely closed the handle was the one the check could not read.

**Why the hold at the end matters.** At demo time the model keeps running until its time limit, and the hold is what teaches it to stay parked after the job is done.

## What to vary and what to keep fixed

The model sees whole camera images, including the tray and the other square. Anything that will differ at demo time has to differ during recording too.

| Vary on purpose | Keep identical |
|---|---|
| The ring's position on its spot (a centimeter or so each way) | Camera positions and lighting |
| Whether the other rings are still on their spots or already in their areas | Grasp style (across the full ring), approach direction and the full squeeze |
| What is already in this ring's cup: nothing, or one or two rings | The rest pose at start and end |
| | The cups: same places, taped or weighted down so a bump cannot move or tip them |
| | The release: open the gripper only once the ring is over the middle of the cup opening, after lifting clear of the rim |

A simple way to cover the variation: during one batch, leave the other two rings on their spots for a few demonstrations, then move them to their areas for a few. Then the model works whichever order the colors run in.

## Command

```shell
bash scripts/record.sh red 5        # first five, then it stops by itself
bash scripts/record.sh red          # more, added to the same dataset, until you press Esc
```

The script fills in everything below from `scripts/settings.env` and `config.json`: the dataset folder (`~/kitcheck_data/pick_<item>`), the task text, and the cameras. It adds to the dataset when the folder already exists; the optional number is the most takes to keep in this session (50 if left out). Takes start and stop only on your keys (`kitcheck/record.py`, a thin wrapper around `lerobot-record`). It starts the camera view (Rerun, in the browser at `http://127.0.0.1:9090`) if one is not running. Run it in a terminal you can type in and keep that terminal focused: on Wayland LeRobot reads the arrow keys from it.

What it runs, for reference:

```shell
lerobot-record \
    --robot.type=so101_follower \
    --robot.port=$FOLLOWER_PORT \
    --robot.id=$FOLLOWER_ID \
    --robot.cameras="$CAMERAS" \
    --teleop.type=so101_leader \
    --teleop.port=$LEADER_PORT \
    --teleop.id=$LEADER_ID \
    --display_data=true \
    --dataset.repo_id=${HF_USER}/kitcheck_pick_red \
    --dataset.num_episodes=60 \
    --dataset.episode_time_s=20 \
    --dataset.reset_time_s=10 \
    --dataset.single_task="Pick the red ring and drop it in the red cup" \
    --dataset.root=${HOME}/kitcheck_data/pick_red
```

For another color, change `red` in the dataset name, task text and folder.

On the event PC the camera view has been run through a separate Rerun server, viewed in a browser at `http://127.0.0.1:9090`. Start it in its own terminal first, then add three options to the command above:

```shell
rerun --serve-web --bind 127.0.0.1 --port 9876 --web-viewer-port 9090 --server-memory-limit 128MB
```

```shell
    --display_ip=127.0.0.1 --display_port=9876 --display_compressed_images=true
```

If the follower reports failed reads, `--robot.num_read_retries=10` makes it try again instead of stopping.

- "Episode" is LeRobot's word for one demonstration.
- `episode_time_s` is the longest one demonstration may run. The right arrow ends it early.
- `reset_time_s` is the pause for putting the next cube on the square.
- The dataset uploads to Hugging Face when recording finishes. That is the default; leave it on.
- The dataset name must not start with `eval_`. LeRobot reserves that prefix for runs driven by a model.

## Keys during recording

Takes start only on your key press. A take stops on your key press or after 20 seconds (`REC_EPISODE_S` in `scripts/settings.env`), whichever comes first, and a take stopped by the limit is kept: press left next if you don't want it. Waiting between takes has no limit. The screen always shows **WAITING (not recording)** or **RECORDING**. The follower copies the leader in both states, so you can set up the scene with the arm while waiting.

| State | Key | Effect |
|---|---|---|
| WAITING | Right arrow | Start the next take (this keeps the take before it) |
| WAITING | Left arrow | Throw away the take you just finished, then wait again |
| WAITING | Esc | Save and finish |
| RECORDING | Right arrow | Stop the take and keep it |
| RECORDING | Left arrow | Stop the take and throw it away |
| RECORDING | Esc | Stop, keep this take, save and finish |

`n`, `r` and `q` work like right, left and Esc. A session starts in WAITING. After you press right to start a take, it can take a few seconds to save the previous one; recording begins when the screen says RECORDING.

Use the left arrow freely. A fumbled grasp, a dropped cube or a pause to think is a bad demonstration.

Stop with Esc, not Ctrl+C. Interrupting while a video is being written can corrupt it, and a corrupt video breaks training later.

## First five, then check

Do not record 60 before knowing the pipeline works.

1. Record 5 demonstrations (`--dataset.num_episodes=5`).
2. Put the ring where it was in the first one and replay it with `bash scripts/replay.sh red 0`. The script runs:

```shell
lerobot-replay \
    --robot.type=so101_follower \
    --robot.port=$FOLLOWER_PORT \
    --robot.id=$FOLLOWER_ID \
    --dataset.repo_id=${HF_USER}/kitcheck_pick_red \
    --dataset.root=${HOME}/kitcheck_data/pick_red \
    --dataset.episode=0
```

3. Check that the grasp check can see the hold:

```shell
python -m kitcheck.grasp inspect ${HOME}/kitcheck_data/pick_red
```

It lists each demonstration with how long the cube was held and how large the gap was, and ends with "Usable" or "Weak signal". With a weak signal, use a firmer cube or squeeze harder, and record the five again. Doc 6 explains the numbers.

4. If the arm repeated your motion and the hold shows up, carry on to 60 (next section). If not, fix calibration, ports or the grip before recording more.

## Adding more demonstrations

Run `bash scripts/record.sh red` again. It sees the existing dataset and adds to it; press Esc when you have enough. (By hand this is `--resume=true`, with `--dataset.num_episodes` as the number to add, not the new total.)

## After the last demonstration: save the grasp reference

```shell
python -m kitcheck.grasp learn ${HOME}/kitcheck_data/pick_red --out data/grasp_red.json
```

This records what a good pick of this item looks like to the gripper: how long the cube is held, how large the gap is, and which way the arm points when it lets go. The runner and `scripts/try_model.sh` use it to judge every pick. Run it again after adding demonstrations.

## Removing a bad demonstration afterwards

LeRobot has a dataset editing tool that can delete episodes by number. Check its options with `lerobot-edit-dataset --help` before using it, and prefer the left arrow at recording time.

## Fixing a weak skill

When testing shows where the arm fails (for example, cubes at the back of the square), record 15–20 more demonstrations at exactly those positions, then retrain (doc 4). More data where it fails beats more data everywhere.

## Time budget

About 60 demonstrations at roughly 12 seconds each plus a 10-second reset comes to 20–25 minutes of recording per skill, plus re-dos. Take a short break halfway; tired demonstrations get sloppy.

## Common problems

| Symptom | Cause and fix |
|---|---|
| Arrow keys do nothing | See the `pynput` fix in doc 2 |
| "File exists" when starting | That dataset folder already exists. Use `--resume=true` to add to it, or delete the folder to start over |
| Training later fails with "Could not push packet to decoder" | A video file is corrupt, usually from an interrupted recording. Find it with `ffmpeg -v error -i <file>.mp4 -f null -` |
| Upload is slow or fails | The data is still saved locally under `--dataset.root`. Upload again later, or copy it to the cloud machine as a tar archive |
| `kitcheck.grasp` says "No module named kitcheck" | Run it from inside the `kitcheck` project folder |
