"""One camera-guided replay pick on the arm, recorded like a model run.

kitcheck/skill.py starts this with the usual --robot.* options (the same ones
lerobot-rollout gets) plus the take to play and its base correction; see
kitcheck/replay.py for how the take is chosen.

This module is separate from kitcheck/replay.py because LeRobot's option parser
needs real type annotations here, and it imports LeRobot up front.
"""

import sys
from dataclasses import dataclass
from pathlib import Path

from lerobot.cameras.opencv import OpenCVCameraConfig  # noqa: F401  (registers camera type: opencv)
from lerobot.configs import parser
from lerobot.robots import RobotConfig, make_robot_from_config, so_follower  # noqa: F401  (registers so101_follower)

from kitcheck.replay import corrected, play, source_actions


@dataclass
class ReplayRunConfig:
    robot: RobotConfig
    # The demonstrations folder and the take to play.
    source: str = ""
    episode: int = 0
    # Frames where that take's gripper closed and let go: the correction fades in before and out between them.
    grasp: int = 0
    release: int = 0
    # Degrees added to the base on the way to the ring.
    pan_offset: float = 0.0
    # Where to write the recording, and its task text.
    out: str = ""
    task: str = ""


@parser.wrap()
def replay_run(cfg: ReplayRunConfig):
    actions, names, fps = source_actions(Path(cfg.source), cfg.episode)
    commands = corrected(actions, names, cfg.pan_offset, cfg.grasp, cfg.release, fps)
    print(f"replaying {cfg.source} take {cfg.episode} ({len(commands) / fps:.1f} s), base {cfg.pan_offset:+.2f} deg", flush=True)
    play(make_robot_from_config(cfg.robot), commands, names, Path(cfg.out), cfg.task, fps)
    print(f"recorded {cfg.out}", flush=True)


def main():
    replay_run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
