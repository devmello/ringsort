"""Line the front camera up with where it was during a recording.

    python -m kitcheck.camalign                 compare with purple take 30 (the default reference)
    python -m kitcheck.camalign --ref red:0     compare with red take 0
    python -m kitcheck.camalign --once          one reading, then exit

A trained model only works with the camera where it was during recording. This
reads the live front camera about once a second, measures how far the fixed
parts of the scene (cups, coasters, table edge, the black disk) have moved
compared with the reference take, and prints the shift in pixels. It also writes
data/camera_overlay.png: the live view and the reference blended half and half,
so a moved camera shows as doubled edges. Nudge the stand until the shift is
within about 3 px, tighten it, and tape the base. Ctrl+C to stop.

The camera must be free: stop any recording or model run first.
"""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DATA_DIR", Path.home() / "kitcheck_data"))
FRONT_CAM = os.environ.get("FRONT_CAM", "/dev/v4l/by-id/usb-icSpring_icspring_camera-video-index0")

# Parts of the image that never change during takes: the cups, coasters and table
# edge along the top, and the black disk at the bottom right.
STATIC = np.zeros((480, 640), np.uint8)
STATIC[:190, :] = 255
STATIC[330:, 420:] = 255


def reference_frame(spec: str) -> np.ndarray:
    """'purple:30' -> the first front-camera frame of purple take 30 (RGB). Cached as a PNG."""
    item, _, take = spec.partition(":")
    take = int(take or 0)
    cache = ROOT / "data" / f"camera_ref_{item}_{take}.png"
    if cache.exists():
        return cv2.cvtColor(cv2.imread(str(cache)), cv2.COLOR_BGR2RGB)
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    ds = LeRobotDataset(f"local/kitcheck_pick_{item}", root=DATA_DIR / f"pick_{item}")
    index = ds.meta.episodes[take]["dataset_from_index"]
    rgb = np.ascontiguousarray((ds[index]["observation.images.front"].permute(1, 2, 0).numpy() * 255).astype(np.uint8))
    cache.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(cache), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    return rgb


class ShiftMeter:
    def __init__(self, reference_rgb: np.ndarray):
        self.orb = cv2.ORB_create(3000)
        self.matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        self.ref_keys, self.ref_desc = self.orb.detectAndCompute(cv2.cvtColor(reference_rgb, cv2.COLOR_RGB2GRAY), STATIC)

    def measure(self, rgb: np.ndarray):
        """(dx, dy, rotation in degrees, scale, matched features) of this frame against the reference, or None."""
        keys, desc = self.orb.detectAndCompute(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), STATIC)
        if desc is None or len(keys) < 10:
            return None
        matches = sorted(self.matcher.match(self.ref_desc, desc), key=lambda m: m.distance)[:300]
        a = np.float32([self.ref_keys[m.queryIdx].pt for m in matches])
        b = np.float32([keys[m.trainIdx].pt for m in matches])
        affine, inliers = cv2.estimateAffinePartial2D(a, b, method=cv2.RANSAC, ransacReprojThreshold=3.0)
        if affine is None or inliers.sum() < 10:
            return None
        moved = (b - a)[inliers.ravel() == 1]
        angle = float(np.degrees(np.arctan2(affine[1, 0], affine[0, 0])))
        scale = float(np.hypot(affine[0, 0], affine[1, 0]))
        return float(np.median(moved[:, 0])), float(np.median(moved[:, 1])), angle, scale, int(inliers.sum())


def advice(dx: float, dy: float, angle: float, scale: float = 1.0) -> str:
    if abs(dx) <= 3 and abs(dy) <= 3 and abs(angle) <= 0.5 and abs(scale - 1) <= 0.02:
        return "ALIGNED: tighten the stand and tape its base"
    parts = []
    if abs(dx) > 3:
        parts.append(f"scene is {abs(dx):.0f} px too far {'right' if dx > 0 else 'left'} in the image")
    if abs(dy) > 3:
        parts.append(f"{abs(dy):.0f} px too far {'down' if dy > 0 else 'up'}")
    if abs(angle) > 0.5:
        parts.append(f"rotated {angle:+.1f} deg")
    if abs(scale - 1) > 0.02:
        parts.append(f"scene looks {'bigger' if scale > 1 else 'smaller'} by {abs(scale - 1) * 100:.0f}% "
                     f"(camera {'closer to' if scale > 1 else 'further from'} the table than in the reference)")
    return "; ".join(parts)


def open_camera():
    cap = cv2.VideoCapture(FRONT_CAM, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    if not cap.isOpened():
        raise SystemExit(f"cannot open the front camera at {FRONT_CAM}; is a recording or model run using it?")
    for _ in range(5):  # let exposure settle
        cap.read()
    return cap


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ref", default="purple:30", help="item:take whose camera position to match (default purple:30)")
    parser.add_argument("--once", action="store_true", help="take one reading and exit")
    parser.add_argument("--image", help="measure this image file instead of the live camera (for testing)")
    args = parser.parse_args(argv)

    reference = reference_frame(args.ref)
    meter = ShiftMeter(reference)
    overlay = ROOT / "data" / "camera_overlay.png"
    cap = None if args.image else open_camera()
    print(f"matching the camera position of {args.ref}; overlay image: {overlay}")
    try:
        while True:
            if args.image:
                frame = cv2.cvtColor(cv2.imread(args.image), cv2.COLOR_BGR2RGB)
            else:
                ok, bgr = cap.read()
                if not ok:
                    raise SystemExit("the camera stopped giving frames")
                frame = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            result = meter.measure(frame)
            blend = cv2.addWeighted(frame, 0.5, reference, 0.5, 0)
            cv2.imwrite(str(overlay), cv2.cvtColor(blend, cv2.COLOR_RGB2BGR))
            if result is None:
                print("not enough of the cups and table edge in view to measure (is something blocking the camera?)")
            else:
                dx, dy, angle, scale, n = result
                note = "" if n >= 30 else " [few features matched: reading unreliable, the view is very different]"
                print(f"shift x {dx:+5.1f} px, y {dy:+5.1f} px, rotation {angle:+.2f} deg, scale {scale:.3f} ({n} features): "
                      f"{advice(dx, dy, angle, scale)}{note}", flush=True)
            if args.once or args.image:
                break
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        if cap is not None:
            cap.release()


if __name__ == "__main__":
    main()
