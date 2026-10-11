# 1. Workcell

The physical scene: the items, the tray, the pickup squares, the cameras and the arm's rest pose. Everything the models learn is tied to this scene, so it is built once and then not moved.

## What it has to achieve

- The arm can reach both pickup squares and the tray comfortably.
- The pickup squares are well to either side of the tray, so the arm clearly turns between picking and placing.
- If there is a fixed camera, it sees both pickup squares and the whole tray, with the arm out of the way when it is resting.
- Nothing in view changes between recording, testing and the demo except the items themselves.

## Parts

| Part | Requirement |
|---|---|
| Items | 3–4 cm cubes in two colors, labelled "SENSOR" and "MOTOR". At least three of each. Firm foam is better than soft sponge: the grasp check needs the cube to hold the gripper open (doc 6). |
| Item colors | Bright, clearly different from each other, from the tray and from the surface. The follower arm is white and the leader and camera stand are black, so avoid white, black and grey. Avoid red for the camera check (doc 6). |
| Surface | A plain matte sheet under everything. Tape its corners down. |
| Tray | Shallow, matte, a different color from both items. Large enough that the biggest kit lies flat without stacking. |
| Pickup squares | One taped square per item type, a little larger than a cube. |
| Cameras | The kit's two: one on the gripper, one on a stand. See "Camera setups". |

## Camera setups

**Expect setup A.** The kit linked for this event is the Advanced Kit, and its listing shows two cameras: one mounted on the follower's gripper and one on a jointed stand with a weighted base. Check the kit on the table matches before you start; the other rows are there in case it does not.

Set the matching row in `scripts/settings.env` (setup A is already the default), and do not change it after the first recording.

| Setup | What you have | Camera names | Where they go | Checks you can run |
|---|---|---|---|---|
| **A (the kit at the event)** | Gripper camera + the camera on the stand | `front`, `wrist` | Stand camera looks down on both squares and the tray | Grasp and camera |
| B | Gripper camera only | `wrist` | On the gripper | Grasp only |
| C | Two fixed cameras, none on the gripper | `top`, `side` | `top` looks down on the squares and tray; `side` sees the arm from the side | Grasp and camera |

- **Three cameras:** still give the model two (the gripper camera and the overhead one). A third adds about 60% to every training run. Use it for filming.
- **Setup B:** if the stand camera is missing or broken, everything still works. You lose the stock check and the "take an item out of the tray" step of the demo; the grasp check and its retry remain (doc 6). Any USB webcam fixed above the table turns B back into A.

### Mounting

- **The stand is jointed, so it can sag or be knocked.** Set it so the camera looks straight down over the squares and tray, tighten every joint, and tape the base to the table.
- **Plug each camera into its own USB port on the PC.** The kit includes a USB hub; if you run short of ports, put the two arms on the hub and keep the cameras off it.
- Leave the gripper camera as the kit mounted it.
- The guide uses 640×480 at 30 frames per second.
- Check the fixed camera's view with the arm at rest: both squares and the full tray visible, no part of the arm over them.
- If a camera has automatic exposure or white balance and a way to lock it, lock it.

## Layout

1. Clamp the arm to the table.
2. Teleoperate before taping anything. Find three spots the gripper reaches easily without stretching to the edge of its range: left square, tray, right square.
3. Put the tray straight ahead and the two squares well to the left and right. The grasp check uses the direction the arm is pointing to tell "let go at the tray" from "let go somewhere else", so the directions must be clearly different.
4. Give each item type its own half of the tray (sensor on the left, motor on the right). It keeps cubes from landing on each other.
5. Tape the squares, the tray outline and the camera positions.

## Rest pose

LeRobot switches the follower's motors off for a moment when it connects, and off again when it disconnects (the default since v0.4.1). Each skill run is a separate connection, so between runs the arm is limp.

- Choose a rest pose the arm stays in with the motors off: folded, with the gripper resting on the base or on a small soft pad.
- With a fixed camera, the rest pose must be out of its view of the squares and the tray.
- Every demonstration starts in this pose and ends in it.
- Mark where the gripper rests so you can tell if the arm has slumped somewhere else.

`--robot.disable_torque_on_disconnect=false` keeps the motors on after a run. It does not remove the brief switch-off at the next connect, so the rest pose still has to be stable.

## Lighting and surroundings

- Constant light. Avoid a spot next to a window or under a light people will walk in front of.
- Keep people, bags and laptops out of every camera view. Tape off the table edge if needed.
- Do not change what is in the background after recording starts.

## Checklist before the first recording

- [ ] Camera setup chosen and written in `scripts/settings.env`
- [ ] Arm clamped; leader arm within easy reach
- [ ] Surface taped; tray outline and both squares taped
- [ ] Rest pose chosen and stable with motors off
- [ ] Fixed camera (if any) shows both squares and the tray, arm clear at rest
- [ ] Each camera on its own USB port
- [ ] Items labelled; spares within reach
- [ ] Photos taken of the whole setup from above and from the side

## After recording starts

These must not change: the camera setup and positions, tray and square positions, surface, lighting, the rest pose, the item colors.

These should vary on purpose during recording (see doc 3): the exact position and rotation of the item in its square, what is already in the tray, and whether the other square is stocked.

## If something moves

1. Put it back using the tape marks and the photos.
2. Run each skill a few times.
3. If a skill has clearly got worse, record 15–20 more demonstrations in the new arrangement and retrain. Do not spend long trying to restore the old position exactly.

## Overnight

- Photograph the setup again before leaving.
- Ask the organizers whether the table can stay untouched.
- First thing on day 2, compare each camera's view with last night's photo before testing models.
