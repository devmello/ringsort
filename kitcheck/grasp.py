"""Grasp sensing: tell from a recording's joint data whether the gripper held
something, and where the arm was when it let go. No camera is involved.

How it works
------------
LeRobot records two numbers for the gripper on every frame: the position it was
told to go to (the action) and the position it actually reached (the
observation), both on a scale from 0 (closed) to 100 (open). When the gripper
closes on an object it cannot reach the commanded position, so the measured
value stays above the commanded one for as long as the object is held. When it
closes on nothing, the two agree.

A "hold" is a stretch of frames where that gap is large and the gripper is not
moving. Two things about the end of the hold tell a good pick from a bad one:

* How it ended. If the gripper was told to open, the arm let go on purpose. If
  the gripper was still told to stay closed and the gap simply vanished, the
  object slipped out.
* Where it ended. The base joint (shoulder_pan) says which way the arm was
  pointing. Comparing it with where the demonstrations let go tells "at the
  tray" from "somewhere else".

Use
---
    python -m kitcheck.grasp inspect <dataset or run folder>
    python -m kitcheck.grasp learn   <demonstration dataset folder> --out data/grasp_sensor.json
    python -m kitcheck.grasp check   <run folder> --ref data/grasp_sensor.json

A folder is anything LeRobot wrote: it contains meta/info.json and data/chunk-*/file-*.parquet.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

GRIPPER_NAME = "gripper.pos"
PAN_NAME = "shoulder_pan.pos"

PLACED = "placed"    # held, then let go on purpose where the demonstrations let go
DROPPED = "dropped"  # held, then slipped out, let go somewhere else, or never let go
MISSED = "missed"    # never held anything
HELD = "held"        # held and let go on purpose; no reference to say where it should be


@dataclass
class Settings:
    """Thresholds. Positions use LeRobot's gripper scale: 0 closed, 100 open."""

    min_gap: float = 4.0          # measured minus commanded gripper position that counts as "blocked"
    min_hold_s: float = 0.5       # a hold shorter than this is ignored
    still_window_s: float = 0.17  # the gripper must be motionless over this window...
    still_tolerance: float = 1.5  # ...to within this much
    bridge_s: float = 0.1         # gaps in a hold shorter than this are filled in
    release_window_s: float = 0.4 # after a hold ends, look this far ahead for the gripper being told to open
    release_margin: float = 3.0   # "told to open" means commanded this far above where the object blocked it


@dataclass
class Hold:
    start: int          # first frame of the hold
    end: int            # one past the last frame
    seconds: float
    gap: float          # median measured-minus-commanded gripper position during the hold
    pan_start: float    # base joint position when the hold began (where it picked)
    pan_end: float      # base joint position when the hold ended (where it let go)
    released: bool      # True if the gripper was told to open; False if the object slipped or the run ended


@dataclass
class Episode:
    index: int
    fps: float
    action: np.ndarray  # frames x joints, commanded positions
    state: np.ndarray   # frames x joints, measured positions
    gripper: int        # column of the gripper joint
    pan: int            # column of the base joint


@dataclass
class Reference:
    """What a good pick looks like for one item, learned from its demonstrations."""

    episodes: int
    episodes_with_hold: int
    hold_s_median: float
    gap_median: float
    min_gap: float
    release_pan: float
    release_pan_std: float
    pick_pan: float
    pan_tolerance: float

    def save(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(asdict(self), indent=2) + "\n")

    @classmethod
    def load(cls, path):
        return cls(**json.loads(Path(path).read_text()))


@dataclass
class Verdict:
    outcome: str
    hold_s: float = 0.0
    gap: float = 0.0
    pan_end: float | None = None
    reason: str = ""


# ---------------------------------------------------------------------------
# Reading LeRobot folders


def load_episodes(folder) -> list[Episode]:
    """Read every episode in a LeRobot dataset or run folder."""
    import pandas as pd  # installed with LeRobot

    folder = Path(folder)
    info_path = folder / "meta" / "info.json"
    if not info_path.is_file():
        raise FileNotFoundError(f"{folder} is not a LeRobot folder (no meta/info.json)")
    info = json.loads(info_path.read_text())
    names = info["features"]["action"].get("names") or []
    if GRIPPER_NAME not in names or PAN_NAME not in names:
        raise ValueError(f"expected joints {GRIPPER_NAME} and {PAN_NAME} in {info_path}, found {names}")
    gripper, pan = names.index(GRIPPER_NAME), names.index(PAN_NAME)

    files = sorted((folder / "data").glob("chunk-*/file-*.parquet"))
    if not files:
        raise FileNotFoundError(f"no data files under {folder / 'data'}")
    table = pd.concat(
        [pd.read_parquet(f, columns=["action", "observation.state", "episode_index", "frame_index"]) for f in files],
        ignore_index=True,
    )
    episodes = []
    for index, frames in table.groupby("episode_index", sort=True):
        frames = frames.sort_values("frame_index")
        episodes.append(
            Episode(
                index=int(index),
                fps=float(info.get("fps", 30)),
                action=np.stack(frames["action"].to_numpy()).astype(float),
                state=np.stack(frames["observation.state"].to_numpy()).astype(float),
                gripper=gripper,
                pan=pan,
            )
        )
    return episodes


# ---------------------------------------------------------------------------
# Finding the hold


def _runs(mask):
    """Start and end (exclusive) of every run of True values."""
    runs, start = [], None
    for i, value in enumerate(mask):
        if value and start is None:
            start = i
        elif not value and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(mask)))
    return runs


def find_hold(episode: Episode, settings: Settings | None = None) -> Hold | None:
    """The longest stretch where the gripper was blocked from closing, or None."""
    settings = settings or Settings()
    commanded = episode.action[:, episode.gripper]
    measured = episode.state[:, episode.gripper]
    n = len(measured)
    if n == 0:
        return None

    gap = measured - commanded
    window = max(1, int(round(settings.still_window_s * episode.fps)))
    still = np.zeros(n, dtype=bool)
    still[window:] = np.abs(measured[window:] - measured[:-window]) <= settings.still_tolerance
    mask = (gap >= settings.min_gap) & still

    # Fill brief flickers so one noisy frame does not split a hold in two.
    bridge = int(round(settings.bridge_s * episode.fps))
    runs = _runs(mask)
    for (_, end), (next_start, _) in zip(runs, runs[1:]):
        if next_start - end <= bridge:
            mask[end:next_start] = True

    runs = _runs(mask)
    if not runs:
        return None
    start, end = max(runs, key=lambda run: run[1] - run[0])
    seconds = (end - start) / episode.fps
    if seconds < settings.min_hold_s:
        return None
    pan = episode.state[:, episode.pan]
    # Did the hold end because the gripper was told to open? Either the command
    # went clearly past where the object blocked it, or it rose well above the
    # squeeze it held during the hold: an operator (or a model copying one) who
    # opens in two stages first eases off to about the object's width, which ends
    # the hold before the gripper fully opens. In a slip the command stays closed.
    blocked_at = float(np.median(measured[start:end]))
    squeeze = float(np.median(commanded[start:end]))
    hold_gap = float(np.median(gap[start:end]))
    ahead = commanded[end : end + max(1, int(round(settings.release_window_s * episode.fps)))]
    released = bool(len(ahead)) and (
        float(ahead.max()) >= blocked_at + settings.release_margin
        or float(ahead.max()) >= squeeze + max(settings.release_margin, 0.5 * hold_gap)
    )
    return Hold(
        start=start,
        end=end,
        seconds=seconds,
        gap=float(np.median(gap[start:end])),
        pan_start=float(pan[start]),
        pan_end=float(pan[end - 1]),
        released=released,
    )


# ---------------------------------------------------------------------------
# Learning what a good pick looks like, and judging a run against it


def learn(episodes: list[Episode], settings: Settings | None = None) -> Reference:
    """Summarize the demonstrations of one item."""
    holds = [hold for hold in (find_hold(ep, settings) for ep in episodes) if hold and hold.released]
    if not holds:
        raise ValueError(
            "no demonstration shows the gripper holding an object. "
            "Grasp sensing will not work with this item or grip; see docs/history/06-check.md."
        )
    gap_median = statistics.median(hold.gap for hold in holds)
    release = [hold.pan_end for hold in holds]
    release_std = statistics.pstdev(release) if len(release) > 1 else 0.0
    return Reference(
        episodes=len(episodes),
        episodes_with_hold=len(holds),
        hold_s_median=statistics.median(hold.seconds for hold in holds),
        gap_median=gap_median,
        # Well below the gap seen while holding, well above the near-zero gap of an empty gripper.
        min_gap=float(min(8.0, max(2.0, 0.4 * gap_median))),
        release_pan=statistics.mean(release),
        release_pan_std=release_std,
        pick_pan=statistics.mean(hold.pan_start for hold in holds),
        # Generous: four standard deviations, and never tighter than 6 units.
        pan_tolerance=float(max(6.0, 4.0 * release_std)),
    )


def judge(episode: Episode, reference: Reference | None = None, settings: Settings | None = None) -> Verdict:
    """Decide what happened in one run."""
    settings = settings or Settings()
    if reference is not None:
        settings = Settings(**{**asdict(settings), "min_gap": reference.min_gap})
    hold = find_hold(episode, settings)
    if hold is None:
        return Verdict(MISSED, reason="the gripper never closed on anything")
    if not hold.released:
        if hold.end >= len(episode.state):
            why = "was still holding the object when the run ended"
        else:
            why = "the object slipped out of the gripper"
        return Verdict(DROPPED, hold.seconds, hold.gap, hold.pan_end, why)
    if reference is None:
        return Verdict(HELD, hold.seconds, hold.gap, hold.pan_end, "held an object and let go; no reference to check where")
    off = abs(hold.pan_end - reference.release_pan)
    if off <= reference.pan_tolerance:
        return Verdict(PLACED, hold.seconds, hold.gap, hold.pan_end, "held the object and let go at its bin")
    return Verdict(
        DROPPED,
        hold.seconds,
        hold.gap,
        hold.pan_end,
        f"let go {off:.0f} units away from its bin",
    )


def judge_folder(folder, reference: Reference | None = None, settings: Settings | None = None) -> Verdict:
    """Judge a run folder written by lerobot-record (one episode; the last one is used)."""
    return judge(load_episodes(folder)[-1], reference, settings)


# ---------------------------------------------------------------------------
# Command line


def _inspect(folder, settings):
    episodes = load_episodes(folder)
    print(f"{len(episodes)} episodes in {folder}")
    print(f"{'episode':>7}  {'held':>6}  {'gap':>5}  {'picked at':>9}  {'let go at':>9}  ended by")
    holds = []
    for ep in episodes:
        hold = find_hold(ep, settings)
        if hold:
            holds.append(hold)
            ending = "opening the gripper" if hold.released else "slipping or running out of time"
            print(f"{ep.index:>7}  {hold.seconds:>5.1f}s  {hold.gap:>5.1f}  {hold.pan_start:>9.1f}  {hold.pan_end:>9.1f}  {ending}")
        else:
            print(f"{ep.index:>7}  {'none':>6}")
    print()
    if not holds:
        print("No episode shows a hold. Grasp sensing cannot be used with this item or grip.")
        return 1
    share = len(holds) / len(episodes)
    gap = statistics.median(hold.gap for hold in holds)
    print(f"held in {len(holds)} of {len(episodes)} episodes; median gap while holding {gap:.1f} (an empty gripper reads near 0)")
    if share >= 0.9 and gap >= settings.min_gap:
        print("Usable: the hold shows up clearly.")
        return 0
    print("Weak signal: use a firmer or larger item, or close the gripper fully when grasping.")
    return 1


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m kitcheck.grasp", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("inspect", help="show the hold found in every episode of a folder")
    p.add_argument("folder")
    p = sub.add_parser("learn", help="learn what a good pick looks like from an item's demonstrations")
    p.add_argument("folder")
    p.add_argument("--out", required=True, help="where to write the reference, e.g. data/grasp_sensor.json")
    p = sub.add_parser("check", help="judge one run")
    p.add_argument("folder")
    p.add_argument("--ref", help="reference written by 'learn'")
    p.add_argument("--json", action="store_true", help="print the verdict as JSON")
    args = parser.parse_args(argv)
    settings = Settings()

    try:
        if args.command == "inspect":
            return _inspect(args.folder, settings)
        if args.command == "learn":
            reference = learn(load_episodes(args.folder), settings)
            reference.save(args.out)
            print(
                f"learned from {reference.episodes_with_hold} of {reference.episodes} demonstrations: "
                f"holds for about {reference.hold_s_median:.1f} s with a gap of {reference.gap_median:.1f}; "
                f"picks at {reference.pick_pan:.0f} and lets go at {reference.release_pan:.0f} "
                f"(accepted within {reference.pan_tolerance:.0f})"
            )
            if abs(reference.release_pan - reference.pick_pan) < 2 * reference.pan_tolerance:
                print(
                    "warning: the pickup and tray directions are close together, so a drop on the way "
                    "may be read as placed. Move the pickup square further from the tray if you can."
                )
            print(f"wrote {args.out}")
            return 0
        reference = Reference.load(args.ref) if args.ref else None
        verdict = judge_folder(args.folder, reference, settings)
        if args.json:
            print(json.dumps(asdict(verdict)))
        else:
            print(f"{verdict.outcome}: {verdict.reason} (held {verdict.hold_s:.1f} s, gap {verdict.gap:.1f})")
        return 0 if verdict.outcome in (PLACED, HELD) else 2
    except (FileNotFoundError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
