"""Camera-guided replay: pick a part by replaying the demonstration that started
closest to it, with the base turned to make up the difference.

The stand camera says where the ring is. Of that color's demonstrations, the
one whose ring started nearest is played back on the follower, recorded like a
model run, so the grasp check, the retry and the dashboard work unchanged.

Only the base (shoulder_pan) is corrected. Moving the ring sideways around the
arm is a pure base rotation; moving it toward or away from the arm is not, and
needs the other joints, which the demonstrations do not predict well (the same
spot was reached with different elbow and wrist angles). So the take is chosen
mainly by distance toward or away from the base, and the base makes up the
sideways part. The correction fades in on the way to the ring and out again
before the release, so the drop into the bin is the demonstration's own.

    python -m kitcheck.replay learn              -> data/replay.json
    python -m kitcheck.replay plan teal 362 365  which take, how far, what correction

kitcheck/skill.py plays a pick on the arm with kitcheck/replay_run.py.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from kitcheck.skill import ROOT

DATA = ROOT / "data" / "replay.json"
PAN = "shoulder_pan.pos"
GRIPPER = "gripper.pos"
MAX_CORRECTION = 8.0   # degrees of base turn; beyond this the ring is too far from every take
FAR_PX = 25.0          # warn when the chosen take started further than this from the ring (toward/away from the base)


# ---------------------------------------------------------------------------
# Learning the takes


def learn(data_dir: Path, report=print) -> dict:
    """For every color: where each take's ring started, and when the gripper closed and let go."""
    import cv2  # noqa: F401  (vision needs it)

    from kitcheck import grasp, vision

    conf = vision.settings()
    ref = vision.reference_frame(conf)
    items, rows = {}, []
    for item in conf["items"]:
        root = data_dir / f"pick_{item}"
        if not (root / "meta" / "info.json").exists():
            report(f"{item}: no demonstrations at {root}")
            continue
        ref_path = ROOT / "data" / f"grasp_{item}.json"
        reference = grasp.Reference.load(ref_path) if ref_path.exists() else None
        starts, _ = vision.ring_starts(conf, item, root, ref)
        takes = []
        for episode in grasp.load_episodes(root):
            hold = grasp.find_hold(episode)
            verdict = grasp.judge(episode, reference)
            if episode.index not in starts or hold is None or verdict.outcome not in (grasp.PLACED, grasp.HELD):
                continue
            x, y = starts[episode.index]
            takes.append({"episode": episode.index, "x": round(x, 1), "y": round(y, 1),
                          "grasp": int(hold.start), "release": int(hold.end), "frames": len(episode.action)})
            rows.append((x, y, float(episode.action[hold.start, episode.pan])))
        items[item] = takes
        report(f"{item}: {len(takes)} usable takes")
    # How the base angle at the grasp follows the ring's position, over every color's takes.
    xy = np.array([(x, y) for x, y, _ in rows])
    pan = np.array([p for _, _, p in rows])
    coef, *_ = np.linalg.lstsq(np.c_[np.ones(len(xy)), xy], pan, rcond=None)
    fit = np.c_[np.ones(len(xy)), xy] @ coef
    report(f"base turns {coef[1]:.3f} deg per px across and {coef[2]:.3f} deg per px down the image "
           f"(fit to {len(rows)} grasps, typical error {np.median(np.abs(fit - pan)):.1f} deg)")
    return {"pan_per_px": [round(float(coef[1]), 4), round(float(coef[2]), 4)], "items": items}


def load(path: Path = DATA) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing; make it with: python -m kitcheck.replay learn")
    return json.loads(path.read_text())


# ---------------------------------------------------------------------------
# Choosing the take


@dataclass
class Plan:
    item: str
    episode: int
    start: tuple[float, float]   # where that take's ring started (locked camera view)
    target: tuple[float, float]  # where the ring is now
    along_px: float              # distance toward/away from the base: not corrected
    across_px: float             # distance around the base: made up by turning it
    pan_offset: float            # degrees added to the base on the way to the ring

    @property
    def far(self) -> bool:
        return abs(self.along_px) > FAR_PX

    def describe(self) -> str:
        text = f"take {self.episode} (started {np.hypot(self.along_px, self.across_px):.0f} px away), base {self.pan_offset:+.1f} deg"
        return text + (f"; WARNING: {abs(self.along_px):.0f} px nearer or further than any take" if self.far else "")


def plan(item: str, x: float, y: float, data: dict, exclude: tuple[int, ...] = ()) -> Plan:
    takes = [t for t in data["items"].get(item, []) if t["episode"] not in exclude] or data["items"].get(item, [])
    if not takes:
        raise ValueError(f"no usable {item} takes in {DATA.name}; run: python -m kitcheck.replay learn")
    grad = np.array(data["pan_per_px"])
    across = grad / np.linalg.norm(grad)          # the direction turning the base moves the gripper
    along = np.array([-across[1], across[0]])     # toward or away from the base

    def parts(take):
        d = np.array([x - take["x"], y - take["y"]])
        return float(d @ along), float(d @ across), float(grad @ d)

    # Distance along the arm cannot be corrected, distance around it can: weight them so.
    best = min(takes, key=lambda t: parts(t)[0] ** 2 + (0.3 * parts(t)[1]) ** 2)
    a, c, pan = parts(best)
    return Plan(item, int(best["episode"]), (best["x"], best["y"]), (x, y), round(a, 1), round(c, 1),
                round(float(np.clip(pan, -MAX_CORRECTION, MAX_CORRECTION)), 2))


def correction_weights(frames: int, grasp: int, release: int, fps: float) -> np.ndarray:
    """How much of the base correction applies at each frame: 0 at rest, 1 from the approach
    through the lift, back to 0 just before the gripper opens over the bin."""
    k = np.arange(frames, dtype=float)
    full_from = max(1.0, 0.6 * grasp)
    fade_from = min(grasp + 0.5 * fps, release - 1)
    fade_to = max(fade_from + 1, release - 0.2 * fps)
    rise = np.clip(k / full_from, 0, 1)
    fall = np.clip((fade_to - k) / (fade_to - fade_from), 0, 1)
    w = np.minimum(rise, fall)
    return 0.5 - 0.5 * np.cos(np.pi * w)  # smooth ends, no jerk


def corrected(actions: np.ndarray, names: list[str], pan_offset: float, grasp: int, release: int, fps: float) -> np.ndarray:
    out = actions.astype(float).copy()
    if pan_offset:
        out[:, names.index(PAN)] += pan_offset * correction_weights(len(out), grasp, release, fps)
    return out


# ---------------------------------------------------------------------------
# Playing it back on the arm, recorded like a model run


def play(robot, actions: np.ndarray, names: list[str], out: Path, task: str, fps: int, log=print) -> int:
    """Send the commands at fps, recording observations and commands into a LeRobot dataset at out."""
    from lerobot.datasets import LeRobotDataset, aggregate_pipeline_dataset_features, create_initial_features
    from lerobot.processor import make_default_processors
    from lerobot.utils.constants import ACTION, OBS_STR
    from lerobot.utils.feature_utils import build_dataset_frame, combine_feature_dicts

    teleop_proc, action_proc, obs_proc = make_default_processors()
    features = combine_feature_dicts(
        aggregate_pipeline_dataset_features(pipeline=teleop_proc, initial_features=create_initial_features(action=robot.action_features), use_videos=True),
        aggregate_pipeline_dataset_features(pipeline=obs_proc, initial_features=create_initial_features(observation=robot.observation_features), use_videos=True),
    )
    cameras = len(getattr(robot, "cameras", {}) or {})
    dataset = LeRobotDataset.create(f"local/{out.name}", fps, features=features, root=out, robot_type=robot.name,
                                    use_videos=True, image_writer_threads=4 * cameras)
    robot.connect()
    try:
        # Ease from wherever the arm is to the take's first pose, so a run never starts with a jump.
        current = robot.get_observation()
        now = np.array([float(current[name]) for name in names])
        gap = float(np.max(np.abs(now - actions[0])))
        lead = int(fps * min(2.0, max(0.0, gap / 30.0))) if gap > 3.0 else 0
        if lead:
            log(f"easing {gap:.0f} deg into the take's starting pose over {lead / fps:.1f} s")
            ramp = (0.5 - 0.5 * np.cos(np.pi * np.linspace(0, 1, lead)))[:, None]
            actions = np.vstack([now + ramp * (actions[0] - now), actions])
        period = 1.0 / fps
        started = time.perf_counter()
        for k, row in enumerate(actions):
            obs = robot.get_observation()
            obs_frame = build_dataset_frame(dataset.features, obs_proc(obs), prefix=OBS_STR)
            action = {name: float(value) for name, value in zip(names, row)}
            robot.send_action(action_proc((action, obs)))
            dataset.add_frame({**obs_frame, **build_dataset_frame(dataset.features, action, prefix=ACTION), "task": task})
            delay = started + (k + 1) * period - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
        slow = (time.perf_counter() - started) / (len(actions) * period)
        if slow > 1.1:
            log(f"warning: playback ran {slow:.2f}x slower than recorded")
    finally:
        # A motor that misses its "torque off" reply at disconnect (the shared USB hub, day 1) must not
        # lose a run that already happened: say so and still save it. The next connect resets the motors.
        try:
            robot.disconnect()
        except Exception as error:  # noqa: BLE001
            log(f"warning: disconnect failed after the run ({error}); the run is saved anyway")
    dataset.save_episode()
    dataset.finalize()
    return lead


def source_actions(root: Path, episode: int) -> tuple[np.ndarray, list[str], int]:
    """A take's commanded joint positions, the joint names, and its frame rate."""
    from kitcheck import grasp

    info = json.loads((root / "meta" / "info.json").read_text())
    names = list(info["features"]["action"]["names"])
    take = next((e for e in grasp.load_episodes(root) if e.index == episode), None)
    if take is None:
        raise SystemExit(f"{root} has no episode {episode}")
    return take.action, names, int(round(take.fps))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    learn_p = sub.add_parser("learn", help="index every color's takes -> data/replay.json")
    learn_p.add_argument("--data-dir", type=Path, default=Path(os.environ.get("DATA_DIR", Path.home() / "kitcheck_data")))
    plan_p = sub.add_parser("plan", help="which take would be replayed for a ring at x, y (locked camera view)")
    plan_p.add_argument("item")
    plan_p.add_argument("x", type=float)
    plan_p.add_argument("y", type=float)
    args = parser.parse_args(argv)
    if args.command == "learn":
        data = learn(args.data_dir)
        DATA.parent.mkdir(parents=True, exist_ok=True)
        DATA.write_text(json.dumps(data, indent=1) + "\n")
        print(f"wrote {DATA.relative_to(ROOT)}")
    elif args.command == "plan":
        print(plan(args.item, args.x, args.y, load()).describe())
    return 0


if __name__ == "__main__":
    sys.exit(main())
