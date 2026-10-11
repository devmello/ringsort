"""Tests for camera-guided replay: choosing the take, the base correction, and
that a played-back pick is recorded so the grasp check can read it.

Run either way:
    python tests/test_replay.py
    python -m pytest tests -q
"""

import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kitcheck import grasp  # noqa: E402
from kitcheck.replay import correction_weights, corrected, plan, play  # noqa: E402

NAMES = ["shoulder_pan.pos", "shoulder_lift.pos", "elbow_flex.pos", "wrist_flex.pos", "wrist_roll.pos", "gripper.pos"]
# Base gradient like the real one: turning the base moves the gripper diagonally across the image.
DATA = {
    "pan_per_px": [0.177, 0.180],
    "items": {"teal": [
        {"episode": 1, "x": 300.0, "y": 300.0, "grasp": 60, "release": 150, "frames": 200},
        {"episode": 2, "x": 330.0, "y": 270.0, "grasp": 60, "release": 150, "frames": 200},  # 42 px away, along the arm
        {"episode": 3, "x": 310.0, "y": 290.0, "grasp": 60, "release": 150, "frames": 200},  # 14 px away, around the arm
    ]},
}


def test_plan_prefers_a_take_around_the_base_over_one_along_the_arm():
    # Ring at (320, 310): take 3 is 14 px away but sideways (fixable by turning the base);
    # take 2 is a similar distance along the arm, which turning cannot fix.
    p = plan("teal", 320.0, 310.0, DATA)
    assert p.episode in (1, 3)
    assert abs(p.along_px) < abs(p.across_px) or p.episode == 1


def test_plan_corrects_the_base_by_the_gradient():
    p = plan("teal", 310.0, 310.0, DATA)
    take = next(t for t in DATA["items"]["teal"] if t["episode"] == p.episode)
    expected = 0.177 * (310 - take["x"]) + 0.180 * (310 - take["y"])
    assert abs(p.pan_offset - expected) < 0.01


def test_a_ring_far_from_every_take_is_flagged():
    assert plan("teal", 300.0, 380.0, DATA).far


def test_correction_is_zero_at_rest_full_at_the_grasp_and_gone_before_release():
    w = correction_weights(200, grasp=60, release=150, fps=30)
    assert w[0] == 0.0
    assert w[60] == 1.0 and w[70] == 1.0
    assert w[150] == 0.0 and w[199] == 0.0
    assert np.all(np.abs(np.diff(w)) < 0.15)  # no jumps


def test_only_the_base_is_corrected():
    actions = np.zeros((200, len(NAMES)))
    out = corrected(actions, NAMES, 3.0, 60, 150, 30)
    assert out[60, 0] == 3.0
    assert np.all(out[:, 1:] == 0.0)


def make_take(frames=90, grasp_at=30, release_at=65):
    """Commands and measurements shaped like a real pick: close on a ring, carry, open."""
    t = np.arange(frames)
    act = np.zeros((frames, len(NAMES)))
    act[:, 0] = np.interp(t, [0, grasp_at, release_at - 10, frames], [0, 40, 2, 2])  # pick at 40, drop at 2
    act[:, 5] = np.where((t >= grasp_at) & (t < release_at), 2.0, 30.0)               # gripper closed between
    state = act.copy()
    state[(t >= grasp_at) & (t < release_at), 5] = 15.0                               # the ring holds it open
    return act, state


class FakeArm:
    """An SO-101 follower that reports what the take's own run measured, frame by frame."""

    name = "so101_follower"

    def __init__(self, state, camera=True):
        self.state, self.k, self.sent = state, 0, []
        self.cameras = {"front": None} if camera else {}

    @property
    def action_features(self):
        return {name: float for name in NAMES}

    @property
    def observation_features(self):
        return {**{name: float for name in NAMES}, **({"front": (96, 128, 3)} if self.cameras else {})}

    def connect(self):
        pass

    def disconnect(self):
        pass

    def get_observation(self):
        row = self.state[min(self.k, len(self.state) - 1)]
        obs = {name: float(v) for name, v in zip(NAMES, row)}
        if self.cameras:
            obs["front"] = np.full((96, 128, 3), 120, np.uint8)
        return obs

    def send_action(self, action):
        self.sent.append(action)
        self.k += 1
        return action


def test_a_played_back_pick_is_recorded_and_reads_as_held():
    act, state = make_take()
    arm = FakeArm(state)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "teal_replay_test"
        play(arm, corrected(act, NAMES, 2.0, 30, 65, 30), NAMES, out, "Pick the teal ring", fps=30, log=lambda *_: None)
        verdict = grasp.judge_folder(out)
        recorded = grasp.load_episodes(out)[-1]
        assert verdict.outcome == grasp.HELD, verdict
        assert abs(recorded.action[30, 0] - (act[30, 0] + 2.0)) < 1e-4  # the corrected command is what was recorded
        assert len(sent := arm.sent) == len(act) and sent[0]["gripper.pos"] == 30.0
        assert (out / "videos" / "observation.images.front" / "chunk-000" / "file-000.mp4").exists()


def test_a_run_starting_away_from_the_take_eases_in_first():
    act, state = make_take()
    state = state + np.array([0, 0, 0, 25.0, 0, 0])  # wrist 25 degrees off the take's first pose
    arm = FakeArm(state, camera=False)
    with tempfile.TemporaryDirectory() as tmp:
        lead = play(arm, act, NAMES, Path(tmp) / "run", "task", fps=60, log=lambda *_: None)
    assert lead > 0
    assert abs(arm.sent[0]["wrist_flex.pos"] - 25.0) < 3.0  # starts from where the arm is


if __name__ == "__main__":
    for name, test in list(globals().items()):
        if name.startswith("test_"):
            test()
            print("ok", name)
