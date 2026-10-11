"""Part detection on the stand camera: which parts are on the table, whether each
sits where the cell was taught to pick it, and which parts are already in a bin.

Plain color thresholds on the fixed stand camera; nothing is learned. Each item
in config.json lists its color as HSV ranges ("hsv"), and config.json's
"vision" section says where the bins are in the locked camera view.

"Where it was taught" comes from the demonstrations: `learn` finds each part in
the first frame of every take, maps it into the locked camera view (takes made
with the camera elsewhere are corrected with the alignment from
kitcheck/align.py), and keeps the middle of those positions and how far they
spread. A part near that middle is where the models have succeeded; one far
outside it is a part the model has never seen picked from there.

    python -m kitcheck.vision learn             -> data/vision.json
    python -m kitcheck.vision check <image>     -> <image>_parts.jpg with what was found drawn on it

The dashboard (kitcheck/dashboard.py) runs the same detection on the live stand
camera whenever the arm is idle.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np

from kitcheck.skill import ROOT, load_config

W, H = 640, 480
TABLE_AREA = (300, 1800)  # pixels a ring covers lying on the table (measured 560-750)
TABLE_FILL = 0.65         # area / enclosing circle: rings measure 0.83-0.93, specks and LEDs below 0.6
BIN_AREA = (40, 1500)     # a ring at the bottom of a cup shows only partly (measured 60-130)
DARK_V = 40               # mean brightness below this: too dark to judge colors


@dataclass
class Part:
    item: str
    x: int
    y: int
    r: int
    area: int
    where: str               # "table" or "bin"
    bin: str = ""            # whose bin it is in
    spot: str = ""           # on the table: "center", "edge" or "outside" the taught area
    off_px: int | None = None  # distance from the taught center, in the locked camera view


def settings(config: dict | None = None) -> dict:
    config = config or load_config()
    vision = config.get("vision", {})
    items = {item: spec for item, spec in config["items"].items() if spec.get("hsv")}
    return {
        "items": items,
        "bins": {item: tuple(circle) for item, circle in vision.get("bins", {}).items()},
        "reference": ROOT / vision.get("reference", "data/camera_ref_purple_30.png"),
        "areas": ROOT / vision.get("areas", "data/vision.json"),
    }


def load_areas(path: Path) -> dict:
    return json.loads(path.read_text())["items"] if path.exists() else {}


def _mask(hsv: np.ndarray, ranges) -> np.ndarray:
    mask = np.zeros(hsv.shape[:2], np.uint8)
    for low, high in ranges:
        mask |= cv2.inRange(hsv, np.array(low), np.array(high))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))


def too_dark(img: np.ndarray) -> bool:
    return float(cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[..., 2].mean()) < DARK_V


def detect(img: np.ndarray, conf: dict, areas: dict | None = None, to_ref: np.ndarray | None = None) -> list[Part]:
    """Every part visible in one stand-camera frame (BGR, 640x480).

    to_ref maps live pixels into the locked camera view (the inverse of
    align.measure's warp); without it the camera is taken to be where it was locked.
    """
    if img.shape[:2] != (H, W):
        img = cv2.resize(img, (W, H))
    hsv = cv2.cvtColor(cv2.GaussianBlur(img, (5, 5), 0), cv2.COLOR_BGR2HSV)
    parts = []
    for item, spec in conf["items"].items():
        contours, _ = cv2.findContours(_mask(hsv, spec["hsv"]), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < BIN_AREA[0]:
                continue
            (x, y), r = cv2.minEnclosingCircle(contour)
            rx, ry = (to_ref[:, :2] @ (x, y) + to_ref[:, 2]) if to_ref is not None else (x, y)
            inside = [owner for owner, (bx, by, br) in conf["bins"].items() if np.hypot(rx - bx, ry - by) <= br]
            if inside:
                if area <= BIN_AREA[1]:
                    parts.append(Part(item, int(x), int(y), int(r), int(area), "bin", bin=inside[0]))
                continue
            fill = area / (np.pi * r * r) if r else 0
            if not (TABLE_AREA[0] <= area <= TABLE_AREA[1] and fill >= TABLE_FILL):
                continue
            part = Part(item, int(x), int(y), int(r), int(area), "table")
            taught = (areas or {}).get(item)
            if taught:
                off = float(np.hypot(rx - taught["x"], ry - taught["y"]))
                part.off_px = round(off)
                part.spot = "center" if off <= taught["r_center"] else "edge" if off <= taught["r_edge"] else "outside"
            parts.append(part)
    return parts


SPOT_TEXT = {"center": "ready", "edge": "near edge", "outside": "outside taught area", "": "seen"}


def _bgr(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return (int(color[4:6], 16), int(color[2:4], 16), int(color[0:2], 16)) if len(color) == 6 else (200, 200, 200)


def draw(img: np.ndarray, parts: list[Part], conf: dict, areas: dict, to_live: np.ndarray | None = None) -> np.ndarray:
    """The frame with taught pick areas, bins and found parts drawn on it."""
    out = img.copy()
    warp = to_live if to_live is not None else np.eye(2, 3, dtype=np.float32)

    def live(x, y):
        return tuple(int(v) for v in warp[:, :2] @ (x, y) + warp[:, 2])

    # Taught areas only for parts seen on the table (all of them when none is), so they don't pile up.
    on_table = {part.item for part in parts if part.where == "table"}
    areas = {item: taught for item, taught in areas.items() if item in conf["items"] and (not on_table or item in on_table)}
    overlay = out.copy()
    for item, taught in areas.items():
        color = _bgr(conf["items"][item].get("color", "#cccccc"))
        cv2.circle(overlay, live(taught["x"], taught["y"]), int(taught["r_edge"]), color, -1)
    out = cv2.addWeighted(overlay, 0.12, out, 0.88, 0)
    for item, taught in areas.items():
        color = _bgr(conf["items"][item].get("color", "#cccccc"))
        centre = live(taught["x"], taught["y"])
        cv2.circle(out, centre, int(taught["r_edge"]), color, 1, cv2.LINE_AA)
        cv2.circle(out, centre, int(taught["r_center"]), color, 1, cv2.LINE_AA)
        cv2.drawMarker(out, centre, color, cv2.MARKER_CROSS, 10, 1)
    for owner, (bx, by, br) in conf["bins"].items():
        color = _bgr(conf["items"].get(owner, {}).get("color", "#cccccc"))
        cv2.circle(out, live(bx, by), int(br), color, 1, cv2.LINE_AA)
        cv2.putText(out, f"{owner} bin", (live(bx, by)[0] - 30, live(bx, by)[1] - int(br) - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
    taken = [(p.x - p.r - 6, p.y - p.r - 6, 2 * p.r + 12, 2 * p.r + 12) for p in parts]  # labels avoid the parts too
    for part in parts:
        color = _bgr(conf["items"][part.item].get("color", "#cccccc"))
        cv2.circle(out, (part.x, part.y), part.r + 6, (255, 255, 255), 3, cv2.LINE_AA)
        cv2.circle(out, (part.x, part.y), part.r + 6, color, 2, cv2.LINE_AA)
        if part.where == "bin":
            text = f"{part.item}: in {part.bin} bin" if part.bin == part.item else f"{part.item}: WRONG BIN ({part.bin})"
        else:
            text = f"{part.item}: {SPOT_TEXT[part.spot]}"
        _label(out, text, part, color, taken)
    return out


def _label(out: np.ndarray, text: str, part: Part, color, taken: list) -> None:
    """A boxed label beside the part: right, left, below or above, whichever is free."""
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
    w, h, gap = tw + 10, th + 10, part.r + 10
    spots = [(part.x + gap, part.y - h // 2), (part.x - gap - w, part.y - h // 2),
             (part.x - w // 2, part.y + gap), (part.x - w // 2, part.y - gap - h)]
    for x, y in spots:
        x, y = min(max(x, 0), W - w), min(max(y, 0), H - h)
        if all(x + w <= a or a + c <= x or y + h <= b or b + d <= y for a, b, c, d in taken):
            break
    taken.append((x, y, w, h))
    cv2.rectangle(out, (x, y), (x + w, y + h), (20, 20, 20), -1)
    cv2.rectangle(out, (x, y), (x + w, y + h), color, 1)
    cv2.putText(out, text, (x + 5, y + h - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)


# ---------------------------------------------------------------------------
# Learning where each part was taught


def reference_frame(conf: dict) -> np.ndarray:
    ref = cv2.imread(str(conf["reference"]))
    if ref is None:
        raise SystemExit(f"no reference frame at {conf['reference']}; make one with scripts/align_camera.sh")
    return ref


def ring_starts(conf: dict, item: str, root: Path, ref: np.ndarray) -> tuple[dict[int, tuple[float, float]], list[int]]:
    """Where the item's ring sat at the start of each take, in the locked camera view; and the takes skipped."""
    from kitcheck import align  # needs PyAV and pandas, which the dashboard does not

    starts, skipped = {}, []
    for episode in range(align.episode_count(root)):
        frame = align.first_frame(root, episode)
        try:
            warp, cc = align.measure(ref, frame, None)
        except cv2.error:
            warp, cc = None, 0.0
        if warp is None or cc < 0.5:
            skipped.append(episode)
            continue
        mine = [p for p in detect(frame, {**conf, "bins": {}}, None) if p.item == item and p.where == "table"]
        if len(mine) != 1:
            skipped.append(episode)
            continue
        to_ref = cv2.invertAffineTransform(warp)
        x, y = to_ref[:, :2] @ (mine[0].x, mine[0].y) + to_ref[:, 2]
        starts[episode] = (float(x), float(y))
    return starts, skipped


def locate(parts: list[Part], item: str, areas: dict, to_ref: np.ndarray | None = None) -> tuple[float, float] | None:
    """The item's ring on the table, in the locked camera view; the one nearest its taught center if several."""
    mine = [p for p in parts if p.item == item and p.where == "table"]
    if not mine:
        return None
    pts = [tuple(to_ref[:, :2] @ (p.x, p.y) + to_ref[:, 2]) if to_ref is not None else (p.x, p.y) for p in mine]
    taught = areas.get(item)
    if taught:
        pts.sort(key=lambda q: np.hypot(q[0] - taught["x"], q[1] - taught["y"]))
    return float(pts[0][0]), float(pts[0][1])


def snapshot(device: str, settle_s: float = 1.2) -> np.ndarray | None:
    """One stand-camera frame, after letting its exposure settle. The camera must be free."""
    import time

    dev = os.path.realpath(device)
    cap = cv2.VideoCapture(int(dev.removeprefix("/dev/video")) if dev.startswith("/dev/video") else dev, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, H)
    img, until = None, time.monotonic() + settle_s
    while cap.isOpened() and time.monotonic() < until:
        ok, frame = cap.read()
        img = frame if ok else img
    cap.release()
    return None if img is None else cv2.resize(img, (W, H))


def where_is(item: str, img: np.ndarray, conf: dict | None = None) -> tuple[float, float] | None:
    """Find the item's ring in a stand-camera frame, corrected for camera movement, in the locked view."""
    from kitcheck import align

    conf = conf or settings()
    ref = reference_frame(conf)
    try:
        warp, cc = align.measure(ref, img, None)
        to_ref = cv2.invertAffineTransform(warp) if cc > 0.5 else None
    except cv2.error:
        to_ref = None
    areas = load_areas(conf["areas"])
    return locate(detect(img, conf, areas, to_ref), item, areas, to_ref)


def learn(conf: dict, data_dir: Path, report=print) -> dict:
    ref = reference_frame(conf)
    found = {}
    for item in conf["items"]:
        root = data_dir / f"pick_{item}"
        if not (root / "meta" / "info.json").exists():
            report(f"{item}: no demonstrations at {root}")
            continue
        starts, skipped = ring_starts(conf, item, root, ref)
        points = list(starts.values())
        if len(points) < 5:
            report(f"{item}: only {len(points)} usable takes; skipped")
            continue
        pts = np.array(points)
        centre = np.median(pts, axis=0)
        dist = np.hypot(*(pts - centre).T)
        found[item] = {
            "x": round(float(centre[0]), 1), "y": round(float(centre[1]), 1),
            # Half the takes started within r_center of the middle, 95% within r_edge.
            "r_center": round(max(15.0, float(np.percentile(dist, 50))), 1),
            "r_edge": round(max(30.0, float(np.percentile(dist, 95))), 1),
            "takes": len(points), "skipped": skipped,
            "points": [[round(float(x)), round(float(y))] for x, y in pts],
        }
        f = found[item]
        report(f"{item}: {len(points)} takes; taught center ({f['x']:.0f}, {f['y']:.0f}), half within {f['r_center']:.0f} px, "
               f"95% within {f['r_edge']:.0f} px" + (f"; skipped takes {skipped}" if skipped else ""))
    return found


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    learn_p = sub.add_parser("learn", help="where each part sat at the start of its takes")
    learn_p.add_argument("--data-dir", type=Path, default=Path(os.environ.get("DATA_DIR", Path.home() / "kitcheck_data")))
    check_p = sub.add_parser("check", help="find the parts in a saved stand-camera image")
    check_p.add_argument("image", type=Path)
    args = parser.parse_args(argv)

    conf = settings()
    if args.command == "learn":
        items = learn(conf, args.data_dir)
        conf["areas"].parent.mkdir(parents=True, exist_ok=True)
        conf["areas"].write_text(json.dumps({"reference": str(conf["reference"].relative_to(ROOT)), "items": items}, indent=1) + "\n")
        print(f"wrote {conf['areas'].relative_to(ROOT)}")
        return 0

    img = cv2.imread(str(args.image))
    if img is None:
        parser.error(f"cannot read {args.image}")
    img = cv2.resize(img, (W, H))
    areas = load_areas(conf["areas"])
    if too_dark(img):
        print("too dark to judge colors")
    parts = detect(img, conf, areas)
    for part in parts:
        print(json.dumps(asdict(part)))
    out = args.image.with_name(args.image.stem + "_parts.jpg")
    cv2.imwrite(str(out), draw(img, parts, conf, areas))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
