"""lerobot-rollout with an optional fixed correction added to the model's joint commands.

    ACTION_OFFSET="shoulder_pan.pos=-4" python -m kitcheck.rollout <the usual lerobot-rollout options>

scripts/try_model.sh and kitcheck/skill.py run this; set ACTION_OFFSET in
scripts/settings.env (or in front of a command) rather than calling it directly.

Why: a model can be consistently off in one direction. The step-10,000 red model
closed with the ring 46 px to the right of where the demonstrations had it in the
wrist camera (the fixed jaw over the ring's hole), with height and the other axis
right. Turning the base moves the ring sideways in that image by about 11.4 px per
degree, so -4 degrees on shoulder_pan cancels the bias. The offset is added to
every command sent to the follower, so the whole motion shifts by the same small
angle (about 1.5 cm at the cup).

The recording keeps the model's own commands, so the grasp check, which compares
the commanded and measured gripper, is unaffected; no offset is applied to the gripper.
"""

from __future__ import annotations

import os
import sys

from lerobot.robots.so_follower.so_follower import SOFollower
from lerobot.scripts import lerobot_rollout


def parse_offsets(text: str) -> dict[str, float]:
    """'shoulder_pan.pos=-4, wrist_flex.pos=1.5' -> {'shoulder_pan.pos': -4.0, 'wrist_flex.pos': 1.5}"""
    offsets = {}
    for part in text.replace(";", ",").split(","):
        if not part.strip():
            continue
        name, _, value = part.partition("=")
        name = name.strip()
        if not name.endswith(".pos"):
            name += ".pos"
        if name.startswith("gripper"):
            raise SystemExit("ACTION_OFFSET: the gripper is not offset (the grasp check reads its commands)")
        offsets[name] = float(value)
    return offsets


def main():
    offsets = parse_offsets(os.environ.get("ACTION_OFFSET", ""))
    if offsets:
        original = SOFollower.send_action

        def send_action(self, action):
            action = dict(action)
            for name, delta in offsets.items():
                if name in action:
                    action[name] = action[name] + delta
            return original(self, action)

        SOFollower.send_action = send_action
        print(f"kitcheck: adding {offsets} to every command sent to the follower", flush=True)
    sys.argv = ["lerobot-rollout", *sys.argv[1:]]
    lerobot_rollout.main()


if __name__ == "__main__":
    main()
