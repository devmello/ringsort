"""Tests for grasp sensing, on made-up recordings shaped like real ones.

Run either way:
    python tests/test_grasp.py
    python -m pytest tests -q
"""

import json
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kitcheck.grasp import (  # noqa: E402
    DROPPED,
    HELD,
    MISSED,
    PLACED,
    Episode,
    Reference,
    find_hold,
    judge,
    judge_folder,
    learn,
    load_episodes,
)

FPS = 30
NAMES = ["shoulder_pan.pos", "shoulder_lift.pos", "elbow_flex.pos", "wrist_flex.pos", "wrist_roll.pos", "gripper.pos"]
PAN, GRIPPER = 0, 5


def make_episode(
    index=0,
    seconds=10.0,
    close_at=2.0,       # the gripper is told to close
    open_at=6.0,        # the gripper is told to open again
    squeeze_to=0.5,     # commanded position while "closed"
    object_width=12.0,  # where an object stops the gripper; None means nothing is there
    slip_at=None,       # the object falls out at this time
    ease_s=None,        # opens in two stages: eases off to the object's width for this long first
    pick_pan=-25.0,
    tray_pan=0.0,
    swing=(3.0, 5.0),   # the arm turns from the pickup direction to the tray direction
    noise=0.15,
    seed=0,
):
    rng = np.random.default_rng(seed + index)
    n = int(seconds * FPS)
    t = np.arange(n) / FPS

    commanded = np.full(n, 70.0)
    commanded[(t >= close_at) & (t < open_at)] = squeeze_to
    held_until = open_at + 0.2
    if ease_s:
        commanded[(t >= open_at) & (t < open_at + ease_s)] = object_width
        held_until = open_at + ease_s + 0.2

    # The measured gripper follows the command with a short lag, and stops at the
    # object's width while an object is in the way.
    measured = np.empty(n)
    value = 70.0
    for i in range(n):
        value += 0.35 * (commanded[i] - value)
        has_object = object_width is not None and t[i] >= close_at and (slip_at is None or t[i] < slip_at)
        if has_object and t[i] < held_until:
            value = max(value, object_width)
        measured[i] = max(value, 0.8)  # a closed gripper reads slightly above zero
    measured += rng.normal(0, noise, n)

    pan = np.interp(t, [0, swing[0], swing[1], seconds], [pick_pan, pick_pan, tray_pan, tray_pan])
    pan += rng.normal(0, noise, n)

    action = np.zeros((n, 6))
    state = np.zeros((n, 6))
    action[:, GRIPPER], state[:, GRIPPER] = commanded, measured
    action[:, PAN], state[:, PAN] = pan, pan
    return Episode(index=index, fps=FPS, action=action, state=state, gripper=GRIPPER, pan=PAN)


def reference():
    return learn([make_episode(i, open_at=5.5 + 0.2 * i, tray_pan=0.0 + 0.3 * i) for i in range(6)])


def test_good_pick_is_placed():
    episode = make_episode()
    hold = find_hold(episode)
    assert hold is not None and hold.released
    assert 3.0 < hold.seconds < 4.5
    assert 10.0 < hold.gap < 13.0
    assert abs(hold.pan_start - (-25.0)) < 2 and abs(hold.pan_end - 0.0) < 2
    assert judge(episode, reference()).outcome == PLACED


def test_empty_grasp_is_missed():
    episode = make_episode(object_width=None)
    assert find_hold(episode) is None
    assert judge(episode, reference()).outcome == MISSED


def test_two_stage_release_is_placed():
    # Easing the handle off to the object's width, pausing, then opening fully is still a release.
    for ease_s in (0.5, 1.0, 1.5):
        verdict = judge(make_episode(ease_s=ease_s), reference())
        assert verdict.outcome == PLACED, (ease_s, verdict)


def test_slip_during_carry_is_dropped():
    for slip_at in (3.0, 4.0, 5.0):
        verdict = judge(make_episode(slip_at=slip_at), reference())
        assert verdict.outcome == DROPPED, (slip_at, verdict)
        assert "slipped" in verdict.reason


def test_letting_go_in_the_wrong_place_is_dropped():
    episode = make_episode(tray_pan=-25.0)  # opens the gripper without ever turning to the tray
    verdict = judge(episode, reference())
    assert verdict.outcome == DROPPED
    assert "away from its bin" in verdict.reason


def test_run_that_ends_while_holding_is_dropped():
    verdict = judge(make_episode(seconds=5.0), reference())
    assert verdict.outcome == DROPPED
    assert "still holding" in verdict.reason


def test_without_a_reference_a_good_pick_is_held():
    assert judge(make_episode()).outcome == HELD


def test_one_noisy_frame_does_not_split_the_hold():
    episode = make_episode()
    episode.state[int(4.0 * FPS), GRIPPER] = 1.0  # a single bad reading mid-carry
    hold = find_hold(episode)
    assert hold is not None and hold.seconds > 3.0
    assert judge(episode, reference()).outcome == PLACED


def test_light_squeeze_is_not_seen():
    # Known limit: if the gripper is only told to close to about the object's
    # width, nothing shows that it is blocked. Demonstrations must squeeze fully.
    episode = make_episode(squeeze_to=10.5, object_width=12.0)
    assert judge(episode, reference()).outcome == MISSED


def test_learn_summarizes_the_demonstrations():
    ref = reference()
    assert ref.episodes == 6 and ref.episodes_with_hold == 6
    assert 2.0 <= ref.min_gap <= 8.0
    assert abs(ref.pick_pan - (-25.0)) < 2
    assert abs(ref.release_pan - 0.75) < 2
    assert ref.pan_tolerance >= 6.0


def test_learn_refuses_demonstrations_with_no_hold():
    try:
        learn([make_episode(object_width=None)])
    except ValueError as error:
        assert "no demonstration" in str(error)
    else:
        raise AssertionError("expected a ValueError")


def test_reference_round_trip_and_reading_a_folder():
    import pandas as pd

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        ref = reference()
        ref.save(tmp / "ref" / "grasp_sensor.json")
        assert Reference.load(tmp / "ref" / "grasp_sensor.json") == ref

        # Write two episodes the way LeRobot lays a folder out.
        episodes = [make_episode(0), make_episode(1, object_width=None)]
        (tmp / "run" / "meta").mkdir(parents=True)
        (tmp / "run" / "data" / "chunk-000").mkdir(parents=True)
        info = {"fps": FPS, "features": {"action": {"names": NAMES}, "observation.state": {"names": NAMES}}}
        (tmp / "run" / "meta" / "info.json").write_text(json.dumps(info))
        rows = []
        for ep in episodes:
            for frame in range(len(ep.state)):
                rows.append(
                    {
                        "action": ep.action[frame].astype(np.float32),
                        "observation.state": ep.state[frame].astype(np.float32),
                        "episode_index": ep.index,
                        "frame_index": frame,
                    }
                )
        pd.DataFrame(rows).to_parquet(tmp / "run" / "data" / "chunk-000" / "file-000.parquet")

        loaded = load_episodes(tmp / "run")
        assert [ep.index for ep in loaded] == [0, 1]
        assert loaded[0].state.shape == episodes[0].state.shape
        assert judge(loaded[0], ref).outcome == PLACED
        assert judge_folder(tmp / "run", ref).outcome == MISSED  # the last episode in the folder


if __name__ == "__main__":
    failures = 0
    for name, test in sorted(globals().items()):
        if name.startswith("test_") and callable(test):
            try:
                test()
                print(f"ok    {name}")
            except Exception as error:  # noqa: BLE001
                failures += 1
                print(f"FAIL  {name}: {error!r}")
    sys.exit(1 if failures else 0)
