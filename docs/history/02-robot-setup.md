# 2. Robot setup

Getting from a powered-off kit to an arm you can teleoperate with the cameras showing. Commands follow the organizers' guide (`QuickStart.md` and `so101_example.md` in their repo). Ports, IDs and cameras are kept in one file, `scripts/settings.env`, so they are typed once.

## Done means

- PyTorch sees the PC's graphics chip.
- `scripts/settings.env` has the right ports and camera setup.
- Both arms are calibrated under the KitCheck IDs.
- Moving the leader arm moves the follower, with the camera views on screen.

## Step 1: check whether the PC is already set up

The organizers may hand you a PC with everything installed. Check before installing anything.

```shell
conda activate lerobot
python3 -c 'import torch; print(torch.cuda.is_available())'
python3 -c "import torch; print(torch.cuda.get_device_name(0))"
pip list | grep lerobot
```

Expected: `True`, then `Radeon 8060S Graphics`, then `lerobot 0.6.2`. If all three match, skip to step 3.

The PC at the event is a Ryzen AI MAX+ 395 (graphics chip gfx1151) with LeRobot 0.6.2 and PyTorch 2.11 for ROCm 7, not the HX370 and v0.4.1 in the guide. ROCm 7 supports this chip directly: **do not set `HSA_OVERRIDE_GFX_VERSION`**, it would make PyTorch treat the chip as the wrong type.

If the first line prints `False`, check `id` lists `render`. Being added to the group takes effect only after logging out and in again (or `newgrp render` in one terminal).

## Step 2: install, only if step 1 failed

The commands below are the guide's, for the HX370 with LeRobot v0.4.1. They do not match the PC at the event (see step 1); ask a mentor rather than running them.

```shell
# ROCm 6.3
sudo apt update
sudo apt install "linux-headers-$(uname -r)"
sudo apt install python3-setuptools python3-wheel
sudo usermod -a -G render,video $LOGNAME
wget https://repo.radeon.com/amdgpu-install/6.3.4/ubuntu/noble/amdgpu-install_6.3.60304-1_all.deb
sudo apt install ./amdgpu-install_6.3.60304-1_all.deb
amdgpu-install -y --usecase=rocm --no-dkms
sudo reboot
```

```shell
# Make the graphics chip usable by PyTorch
echo "export HSA_OVERRIDE_GFX_VERSION=11.0.0" >> ~/.bashrc
source ~/.bashrc

# Python environment (install Miniconda first if it is missing)
conda create -n lerobot python=3.10
conda activate lerobot
pip install torch==2.7.1 torchvision==0.22.1 torchaudio==2.7.1 --index-url https://download.pytorch.org/whl/rocm6.3
conda install ffmpeg=7.1.1 -c conda-forge

# LeRobot v0.4.1 with the SO-101 motor support
git clone https://github.com/huggingface/lerobot.git
cd lerobot
git checkout -b v0.4.1 v0.4.1
pip install -e .
pip install 'lerobot[feetech]'
```

LeRobot v0.4.1 needs a PyTorch version below 2.8, which is why the versions are pinned.

## Step 3: get the project onto the PC and load the settings

Copy the `kitcheck` folder to the PC (from a git repository, a USB stick, or any way the organizers allow). Work from inside it.

```shell
cd kitcheck
hf auth login
export HF_USER=$(hf auth whoami | cut -c 16-)
echo $HF_USER
source scripts/settings.env
```

- You can also type your username into `scripts/settings.env` once, so only the last line is needed.
- **Every new terminal needs `source scripts/settings.env` again.** The commands in these docs use the variables it sets (`$FOLLOWER_PORT`, `$CAMERAS` and so on).
- After editing the file, run the `source` line again.

## Step 4: find the arms

The guide assumes the leader arm is plugged in first and appears as `/dev/ttyACM0`, with the follower second as `/dev/ttyACM1`. The order depends on which you plug in first, so confirm it.

```shell
lerobot-find-port
sudo chmod 666 /dev/ttyACM0
sudo chmod 666 /dev/ttyACM1
```

- The leader is the arm with the handle. The follower has the gripper.
- Check the power supply labels before plugging in. On the Pro version of the Seeed kit the leader takes 5 V and the follower 12 V, and the wrong one can damage the motors. Ask a mentor if the supplies are not labelled.
- The USB cable carries no power. Each arm needs both its power supply and its USB cable.
- If the ports differ from the defaults, change `FOLLOWER_PORT` and `LEADER_PORT` in `scripts/settings.env` and load it again.

## Step 5: calibrate

The arms come assembled. Do not run the motor ID setup.

```shell
lerobot-calibrate \
    --robot.type=so101_follower \
    --robot.port=$FOLLOWER_PORT \
    --robot.id=$FOLLOWER_ID
```

```shell
lerobot-calibrate \
    --teleop.type=so101_leader \
    --teleop.port=$LEADER_PORT \
    --teleop.id=$LEADER_ID
```

For each arm: move every joint to the middle of its range, press Enter, then move each joint through its full range.

The ID names the saved calibration file. Every later command must use the same two IDs, which is why they live in the settings file.

## Step 6: find the cameras and choose the setup

```shell
lerobot-find-cameras opencv
```

1. Expect two: the one on the gripper (`wrist`) and the one on the stand (`front`). Test images are saved under `outputs/captured_images`; use them to tell which index is which.
2. In `scripts/settings.env`, put the right `index_or_path` number on each camera in the setup A line. If the kit is different, switch to the matching setup from doc 1.
3. Load the settings again.

Indexes can change after a reboot or replug. If a camera view looks wrong later, run the find command again.

## Step 7: teleoperate with cameras

```shell
lerobot-teleoperate \
    --robot.type=so101_follower \
    --robot.port=$FOLLOWER_PORT \
    --robot.id=$FOLLOWER_ID \
    --robot.cameras="$CAMERAS" \
    --teleop.type=so101_leader \
    --teleop.port=$LEADER_PORT \
    --teleop.id=$LEADER_ID \
    --display_data=true
```

When this works, build the workcell (doc 1) and practice the pick for 15 minutes before recording anything.

## Step 8: extras KitCheck needs

```shell
pip install flask
```

Flask is only for the order page. OpenCV is already installed with LeRobot; it is the headless build, so `cv2.imshow` windows will not open, and the setup page in doc 7 replaces them.

## Problems and fixes

| Symptom | Fix |
|---|---|
| "Lock" error during calibration | Unplug and replug the arm's power |
| "Could not connect on port" | Run the `chmod` lines again; check which arm is on which port; check the settings were loaded in this terminal |
| A motor is not found, or its light is off | A cable before that motor is loose; power off before reseating it |
| Shaky or dropped video | Put the cameras on different USB ports |
| Camera capture is slow at the chosen size | Add `fourcc: "MJPG"` to that camera in `scripts/settings.env`, then keep it for the whole event |
| Arrow keys do nothing during recording | `pip uninstall pynput && pip install pynput==1.7.7`, then log in with "Ubuntu with Xorg" |
| `torch.cuda.is_available()` is `False` | Check `id` lists `render` (log out and in after being added); make sure `HSA_OVERRIDE_GFX_VERSION` is **not** set; ask a mentor |
| "'datasets' is required but not installed" | A reinstall of LeRobot dropped the dataset extras: `pip install 'datasets==4.8.5' 'pandas<3' 'av==15.1.0' 'torchcodec==0.11.1' pynput wandb` |
| A command complains about an empty port or camera setting | The settings were not loaded in this terminal: `source scripts/settings.env` |

## Questions for the organizers

- Is the PC already set up, and may I install software on it?
- Does the kit match its listing: a camera on the gripper and a second one on a stand?
- May code prepared before the event be used?
- Does the PC stay with my table overnight?

## How this doc was checked

The calibrate, teleoperate, record, replay and model-run commands were run with LeRobot v0.4.1 on a machine with no arm attached. Each one was accepted and stopped only at "Could not connect on port", so the options and the camera settings are valid. They have not been run on an arm.
