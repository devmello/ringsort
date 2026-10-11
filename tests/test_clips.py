"""Tests for recorded-pick clips: reading what a run folder's name says.

Run either way:
    python tests/test_clips.py
    python -m pytest tests -q
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kitcheck.clips import describe_run  # noqa: E402

CONFIG = {"items": {"purple": {"label": "Purple ring"}, "teal": {"label": "Teal ring"}}}


def test_a_model_run_names_its_checkpoint():
    info = describe_run(Path("data/eval/purple_010000_20261010_210212"), CONFIG)
    assert info == {"item": "purple", "label": "Purple ring", "method": "ACT model, step 10,000",
                    "recorded": "2026-10-10T21:02"}


def test_a_replay_run_says_camera_guided_replay():
    info = describe_run(Path("data/eval/teal_replay_20261011_073015_2"), CONFIG)
    assert info["method"] == "Camera-guided replay" and info["label"] == "Teal ring"


def test_a_named_model_version_is_kept():
    assert describe_run(Path("purple_v2_20261011_080000"), CONFIG)["method"] == "ACT model, v2"


def test_other_folders_are_refused():
    try:
        describe_run(Path("data/eval/notes"), CONFIG)
    except ValueError:
        return
    raise AssertionError("expected a ValueError")


if __name__ == "__main__":
    for name, test in list(globals().items()):
        if name.startswith("test_"):
            test()
            print("ok", name)
