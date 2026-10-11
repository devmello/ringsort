"""Tests for part detection, on drawn images colored like the real table and rings.

Run either way:
    python tests/test_vision.py
    python -m pytest tests -q
"""

import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kitcheck.vision import detect, too_dark  # noqa: E402

# Colors measured on the stand camera (HSV, OpenCV scale), and the ranges config.json uses.
TABLE_HSV = (31, 67, 212)
RING_HSV = {"red": (3, 200, 211), "purple": (137, 115, 119), "teal": (85, 156, 202)}
CONF = {
    "items": {
        "red": {"hsv": [[[0, 120, 90], [8, 255, 255]], [[172, 120, 90], [180, 255, 255]]]},
        "purple": {"hsv": [[[118, 50, 50], [165, 255, 255]]]},
        "teal": {"hsv": [[[74, 90, 80], [98, 255, 255]]]},
    },
    "bins": {"purple": (388, 92, 62)},
}
AREAS = {"purple": {"x": 333, "y": 284, "r_center": 49, "r_edge": 92}}


def bgr(hsv):
    return tuple(int(v) for v in cv2.cvtColor(np.uint8([[hsv]]), cv2.COLOR_HSV2BGR)[0, 0])


def scene(rings=(), specks=()):
    img = np.full((480, 640, 3), bgr(TABLE_HSV), np.uint8)
    for item, (x, y), size in rings:
        cv2.circle(img, (x, y), size, bgr(RING_HSV[item]), -1)
        cv2.circle(img, (x, y), size // 3, bgr(TABLE_HSV), -1)  # the hole
    for item, (x, y) in specks:
        cv2.circle(img, (x, y), 3, bgr(RING_HSV[item]), -1)
    return img


def found(parts):
    return sorted((p.item, p.where, p.bin, p.spot) for p in parts)


def test_finds_each_ring_on_the_table():
    img = scene([("red", (285, 260), 15), ("purple", (375, 262), 15), ("teal", (292, 342), 15)])
    assert found(detect(img, CONF)) == [("purple", "table", "", ""), ("red", "table", "", ""), ("teal", "table", "", "")]


def test_ignores_specks_like_status_leds():
    img = scene(specks=[("purple", (180, 300)), ("teal", (10, 10))])
    assert detect(img, CONF) == []


def test_small_ring_inside_a_cup_counts_as_in_that_bin():
    img = scene([("purple", (395, 125), 7)])
    assert found(detect(img, CONF)) == [("purple", "bin", "purple", "")]


def test_wrong_part_in_a_bin_is_reported_with_the_bin_it_is_in():
    img = scene([("teal", (380, 110), 7)])
    assert found(detect(img, CONF)) == [("teal", "bin", "purple", "")]


def test_grades_the_spot_against_where_it_was_taught():
    for (x, y), spot in (((340, 290), "center"), ((333, 360), "edge"), ((480, 420), "outside")):
        parts = detect(scene([("purple", (x, y), 15)]), CONF, AREAS)
        assert [p.spot for p in parts] == [spot], (x, y)


def test_a_dark_room_is_reported_as_too_dark():
    assert too_dark(np.zeros((480, 640, 3), np.uint8))
    assert not too_dark(scene())


if __name__ == "__main__":
    for name, test in list(globals().items()):
        if name.startswith("test_"):
            test()
            print("ok", name)
