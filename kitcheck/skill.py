"""Launch one skill: run an item's trained model on the arm once and record it.

This is scripts/try_model.sh as a function the runner can call. It builds the
lerobot-rollout command from config.json and scripts/settings.env, runs it with
a fresh output folder, and returns that folder for the grasp check to read.

    from kitcheck.skill import run_skill
    result = run_skill("red")            # the model named in config.json
    result = run_skill("red", "020000")  # models/red/020000/pretrained_model
    result = run_skill("red", "replay")  # camera-guided replay of the nearest take (kitcheck/replay.py)

Without a robot, set KITCHECK_FAKE_RUN=<a recorded LeRobot folder> (or
"fake_robot": "<folder>" in config.json) and that recording is copied in place
of a real run.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = ROOT / "scripts" / "settings.env"


@dataclass
class RunResult:
    item: str
    folder: Path        # the run's recording (data/eval/<item>_<label>_<stamp>)
    ok: bool            # False if the command failed or left no recording
    seconds: float      # wall time from launch to exit, start-up included
    model: str
    error: str = ""     # last lines of the log when ok is False


def load_config(path=None) -> dict:
    return json.loads(Path(path or ROOT / "config.json").read_text())


def load_settings() -> dict:
    """The variables scripts/settings.env sets, as the shell would see them."""
    out = subprocess.run(
        ["bash", "-c", f"set -a; . {shlex.quote(str(SETTINGS))}; env -0"],
        capture_output=True, check=True,
    ).stdout.decode()
    return dict(line.split("=", 1) for line in out.split("\0") if "=" in line)


def model_path(item: str, label: str | None, config: dict) -> Path:
    if label:
        return ROOT / "models" / item / label / "pretrained_model"
    return ROOT / config["items"][item]["model"]


def build_command(item: str, model: Path, folder: Path, stamp: str, seconds: float, config: dict, env: dict) -> list[str]:
    # kitcheck.rollout is lerobot-rollout plus the optional ACTION_OFFSET from the environment.
    return [
        sys.executable, "-m", "kitcheck.rollout",
        "--strategy.type=episodic",
        "--robot.type=so101_follower",
        f"--robot.port={env['FOLLOWER_PORT']}",
        f"--robot.id={env['FOLLOWER_ID']}",
        f"--robot.cameras={env['CAMERAS']}",
        *shlex.split(env.get("ROBOT_EXTRA_ARGS", "")),
        f"--dataset.single_task={config['items'][item]['task']}",
        f"--dataset.repo_id=local/rollout_kitcheck_{item}_{stamp}",
        f"--dataset.root={folder}",
        f"--dataset.episode_time_s={seconds:g}",
        "--dataset.num_episodes=1",
        "--dataset.push_to_hub=false",
        f"--policy.path={model}",
        *shlex.split(env.get("POLICY_ARGS", "")),
        "--play_sounds=false",
    ]


REPLAY = "replay"


def uses_replay(item: str, label: str | None, config: dict) -> bool:
    return label == REPLAY or (label is None and config["items"][item].get("mode") == REPLAY)


def run_skill(item: str, label: str | None = None, seconds: float | None = None, config: dict | None = None,
              target: tuple[float, float] | None = None) -> RunResult:
    """target is where the stand camera saw the ring (locked camera view); camera-guided replay
    needs it, and looks for itself when it is not given."""
    config = config or load_config()
    if item not in config["items"]:
        raise KeyError(f"unknown item '{item}'; config.json has {', '.join(config['items'])}")
    if uses_replay(item, label, config):
        return _run_replay(item, config, target)
    seconds = float(seconds or config["items"][item].get("run_time_s", 15))
    model = model_path(item, label, config)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = ROOT / "data" / "eval" / f"{item}_{label or 'final'}_{stamp}"
    n = 1
    while folder.exists() or folder.with_suffix(".log").exists():  # two runs in the same second
        n += 1
        folder = folder.with_name(f"{item}_{label or 'final'}_{stamp}_{n}")
    folder.parent.mkdir(parents=True, exist_ok=True)
    log = folder.with_suffix(".log")
    started = time.monotonic()

    fake = os.environ.get("KITCHECK_FAKE_RUN") or (config.get("fake_robot") if isinstance(config.get("fake_robot"), str) else "")
    if fake:
        shutil.copytree(fake, folder)
        log.write_text(f"fake run: copied {fake}\n")
        return RunResult(item, folder, True, time.monotonic() - started, str(model))

    if not (model / "model.safetensors").exists():
        return RunResult(item, folder, False, 0.0, str(model), f"no model at {model}; download it with scripts/get_model.sh")

    env = {**os.environ, **load_settings()}
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    command = build_command(item, model, folder, stamp, seconds, config, env)
    # One missed or garbled motor reply while connecting aborts a run before the
    # arm moves; try again (up to 3 times) when that is why and nothing was recorded.
    for attempt in range(3):
        shutil.rmtree(folder, ignore_errors=True)
        code = _launch(command, log, env, seconds)
        if code == 0 or _arm_moved(folder) or attempt == 2:
            break
        if not CONNECT_GLITCH.search(log.read_text(errors="replace")):
            break
        time.sleep(2.0)
    took = time.monotonic() - started
    time.sleep(1.0)  # let the cameras and serial port close before anything else opens them

    ok = code == 0 and (folder / "meta" / "info.json").exists()
    error = ""
    if not ok:
        lines = [line for line in log.read_text(errors="replace").splitlines() if line.strip()]
        error = "\n".join(lines[-4:])
    return RunResult(item, folder, ok, took, str(model), error)


def _run_replay(item: str, config: dict, target: tuple[float, float] | None) -> RunResult:
    from kitcheck import replay, vision

    started = time.monotonic()
    env = {**os.environ, **load_settings()}
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = ROOT / "data" / "eval" / f"{item}_replay_{stamp}"
    while folder.exists() or folder.with_suffix(".log").exists():
        stamp += "_2"
        folder = ROOT / "data" / "eval" / f"{item}_replay_{stamp}"
    folder.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = replay.load()
    except FileNotFoundError as error:
        return RunResult(item, folder, False, 0.0, "camera replay", str(error))
    if target is None and not os.environ.get("KITCHECK_FAKE_RUN"):
        img = vision.snapshot(env["FRONT_CAM"])
        target = vision.where_is(item, img) if img is not None else None
    if target is None:
        taught = vision.load_areas(vision.settings(config)["areas"]).get(item)
        if os.environ.get("KITCHECK_FAKE_RUN") and taught:
            target = (taught["x"], taught["y"])  # rehearsal: pretend the ring is on its mark
        else:
            return RunResult(item, folder, False, 0.0, "camera replay",
                             f"the stand camera cannot find the {item} ring on the table")
    p = replay.plan(item, *target, data)
    take = next(t for t in data["items"][item] if t["episode"] == p.episode)
    model = f"camera replay of {p.describe()}"

    fake = os.environ.get("KITCHECK_FAKE_RUN") or (config.get("fake_robot") if isinstance(config.get("fake_robot"), str) else "")
    log = folder.with_suffix(".log")
    if fake:
        shutil.copytree(fake, folder)
        log.write_text(f"fake run: copied {fake}\n{model}\n")
        return RunResult(item, folder, True, time.monotonic() - started, model)

    command = [
        sys.executable, "-m", "kitcheck.replay_run",
        "--robot.type=so101_follower",
        f"--robot.port={env['FOLLOWER_PORT']}",
        f"--robot.id={env['FOLLOWER_ID']}",
        f"--robot.cameras={env['CAMERAS']}",
        *shlex.split(env.get("ROBOT_EXTRA_ARGS", "")),
        f"--source={Path(env['DATA_DIR']) / f'pick_{item}'}",
        f"--episode={p.episode}",
        f"--grasp={take['grasp']}",
        f"--release={take['release']}",
        f"--pan_offset={p.pan_offset}",
        f"--out={folder}",
        f"--task={config['items'][item]['task']}",
    ]
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    seconds = take["frames"] / 30.0 + 2.0
    for attempt in range(3):
        shutil.rmtree(folder, ignore_errors=True)
        code = _launch(command, log, env, seconds)
        if code == 0 or _arm_moved(folder) or attempt == 2:
            break
        if not CONNECT_GLITCH.search(log.read_text(errors="replace")):
            break
        time.sleep(2.0)
    took = time.monotonic() - started
    time.sleep(1.0)  # let the cameras and serial port close before anything else opens them
    ok = code == 0 and (folder / "meta" / "info.json").exists()
    error = ""
    if not ok:
        lines = [line for line in log.read_text(errors="replace").splitlines() if line.strip()]
        error = "\n".join(lines[-4:])
    return RunResult(item, folder, ok, took, model, error)


def _arm_moved(folder: Path) -> bool:
    """True once a run recorded anything: camera frames are written while the arm moves, the data at the
    end. A run that got that far is never retried, whatever failed afterwards."""
    return (folder / "data").exists() or any((folder / "images").glob("*/*/*.png"))


CONNECT_GLITCH = re.compile(r"motor check failed|There is no status packet|Incorrect status packet|Failed to (write|read|sync_read|sync_write)")


def _launch(command: list[str], log: Path, env: dict, seconds: float) -> int:
    with log.open("w") as handle:
        handle.write(shlex.join(command) + "\n\n")
        handle.flush()
        try:
            # stdin is closed so a stray key press cannot end the run early.
            # The limit is generous: start-up (model load, arm and cameras) comes on top.
            code = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=handle, stderr=subprocess.STDOUT,
                                  env=env, cwd=ROOT, timeout=seconds + 90).returncode
        except subprocess.TimeoutExpired:
            code = -1
            handle.write("\nkitcheck: the run went far past its time limit and was stopped\n")
    return code
