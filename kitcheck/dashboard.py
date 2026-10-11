"""Station dashboard: the sorting cell as a factory screen, for the demo.

    scripts/dashboard.sh          then open http://127.0.0.1:8078

From the page you start a work order, watch each part go through the cell into
its bin, answer the cell when it flags the operator, and replay every pick from
the cell's own recording of it. The terminal runner (kitcheck/runner.py) does
the same work; this only puts a screen on it.

The cameras stream only while the arm is idle. During a pick the robot's own
process (lerobot-rollout) needs both cameras, and a second reader slows the
model down, so the page hands them over, stops all video work, and shows the
factory view instead. After the pick it plays that pick's recording next to
the verdict, then the live view comes back.

While the arm is idle, the stand camera also runs the parts view
(kitcheck/vision.py): which parts are on the table, whether each sits where it
was taught, which are already in a bin, and whether the camera itself has moved.

Without a robot, KITCHECK_FAKE_RUN=<a recorded run folder> makes every pick
copy that recording, as in scripts/try_model.sh.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import statistics
import threading
import time
import uuid
from collections import deque
from dataclasses import asdict
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import cv2
import numpy as np

from kitcheck import align, clips, grasp, replay, runner, vision
from kitcheck.skill import REPLAY, ROOT, load_config

EVAL = (ROOT / "data" / "eval").resolve()
GOOD = (grasp.PLACED, grasp.HELD)
W, H = 640, 480


def replay_items() -> set[str]:
    try:
        return {item for item, takes in replay.load()["items"].items() if takes}
    except (FileNotFoundError, ValueError):
        return set()


def model_labels(item: str) -> list[str]:
    """What can pick an item: camera replay if its takes are indexed, then downloaded models,
    best guess first: final, named versions (v3, v2), then the latest step."""
    folder = ROOT / "models" / item
    replayable = [REPLAY] if item in replay_items() else []
    if not folder.is_dir():
        return replayable
    labels = [p.name for p in folder.iterdir() if (p / "pretrained_model" / "model.safetensors").exists()]
    final = [label for label in labels if label == "final"]
    named = sorted((label for label in labels if label != "final" and not label.isdigit()), reverse=True)
    steps = sorted((label for label in labels if label.isdigit()), key=int, reverse=True)
    return replayable + final + named + steps


class Cameras:
    """Reads the cameras while the arm is idle and hands them over for each pick."""

    def __init__(self, devices: dict[str, str], fps: float = 10.0):
        self.devices = devices
        self.period = 1.0 / fps
        self.jpeg: dict[str, bytes | None] = {name: None for name in devices}
        self.frames: dict[str, tuple[float, object]] = {}  # name -> (time, BGR image), for the parts view
        self.errors: dict[str, str] = {}
        self.lock = threading.Lock()
        self.wanted = threading.Event()  # cleared while a pick runs or the operator paused the view
        self.free = threading.Event()    # set while no camera is open
        self.free.set()
        self.paused = False
        self.picking = False
        self.opened_at = 0.0
        self.wanted.set()

    @property
    def live(self) -> bool:
        return not self.free.is_set()

    def _update(self) -> None:
        with self.lock:
            if self.paused or self.picking:
                self.wanted.clear()
            else:
                self.wanted.set()

    def hand_over(self, timeout: float = 5.0) -> None:
        """Close every camera so the robot's process can open them."""
        self.picking = True
        self._update()
        self.free.wait(timeout)
        time.sleep(0.3)

    def take_back(self) -> None:
        self.picking = False
        self._update()

    def pause(self, paused: bool) -> None:
        """Free the cameras for scripts/record.sh or try_model.sh, or take them again."""
        self.paused = paused
        self._update()

    def _open(self) -> dict[str, cv2.VideoCapture]:
        caps = {}
        for name, device in self.devices.items():
            if Path(device).suffix.lower() in (".png", ".jpg", ".jpeg"):
                caps[name] = _StillCamera(device)  # rehearsal: a saved frame instead of a camera
                continue
            dev = os.path.realpath(device)
            index = int(dev.removeprefix("/dev/video")) if dev.startswith("/dev/video") else dev
            cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, W)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, H)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if cap.isOpened():
                caps[name] = cap
                self.errors.pop(name, None)
            else:
                cap.release()
                self.errors[name] = f"cannot open {device}: is another program using it?"
        return caps

    def loop(self) -> None:
        caps: dict[str, cv2.VideoCapture] = {}
        retry_at = 0.0
        while True:
            with self.lock:
                wanted = self.wanted.is_set()
                if wanted and not caps and time.monotonic() >= retry_at:
                    self.free.clear()  # under the lock, so hand_over() cannot miss an opening
                    opening = True
                else:
                    opening = False
            if not wanted:
                for cap in caps.values():
                    cap.release()
                caps = {}
                self.free.set()
                time.sleep(0.05)
                continue
            if opening:
                caps = self._open()
                self.opened_at = time.monotonic()
                if not caps:
                    self.free.set()
                    retry_at = time.monotonic() + 3.0
            if not caps:
                time.sleep(0.1)
                continue
            started = time.monotonic()
            for name, cap in caps.items():
                ok, img = cap.read()
                if ok:
                    if img.shape[:2] != (H, W):
                        img = cv2.resize(img, (W, H))
                    self.jpeg[name] = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 75])[1].tobytes()
                    self.frames[name] = (time.monotonic(), img)
            time.sleep(max(0.0, self.period - (time.monotonic() - started)))


class _StillCamera:
    """A saved image that reads like a camera, for rehearsing the parts view without the table."""

    def __init__(self, path: str):
        self.img = cv2.imread(path)

    def isOpened(self) -> bool:
        return self.img is not None

    def read(self):
        time.sleep(1 / 30)
        return self.img is not None, None if self.img is None else self.img.copy()

    def release(self) -> None:
        pass


class Station:
    """One work order at a time, run on a worker thread, with everything the page shows."""

    def __init__(self, cameras: Cameras):
        self.cameras = cameras
        self.lock = threading.RLock()
        self.shift_start = datetime.now()
        self.events: deque[dict] = deque(maxlen=80)
        self.order: dict | None = None
        self.part: dict | None = None
        self.last_pick: dict | None = None
        self.question: dict | None = None
        self.answers: queue.Queue[str] = queue.Queue()
        self.stop_requested = False
        self.bins: dict[str, int] = {}
        self.shipped = 0
        self.operator_calls = 0
        self.picking_since: float | None = None
        self.config = load_config()
        self.seen: dict = {"time": None, "parts": [], "dark": False, "camera": None}
        self.parts_jpeg: tuple[float, bytes] | None = None
        self.warp = None  # where the stand camera points, from the parts view
        self.log("Cell started. Ready for a work order.")
        if "front" in cameras.devices:
            threading.Thread(target=self._watch, daemon=True).start()

    # ---- what the page sees ------------------------------------------------

    def log(self, text: str, level: str = "info") -> None:
        with self.lock:
            self.events.appendleft({"time": datetime.now().strftime("%H:%M:%S"), "text": text, "level": level})

    def label(self, item: str) -> str:
        return self.config["items"].get(item, {}).get("label", item)

    @property
    def running(self) -> bool:
        return self.order is not None and self.order["state"] == "running"

    def andon(self) -> dict:
        if self.question:
            return {"light": "red", "text": "Operator needed"}
        if self.running and self.part and self.part["status"] == "retrying":
            return {"light": "amber", "text": "Retrying a missed pick"}
        if self.running and self.part and self.part["attempt"] > 1:
            return {"light": "amber", "text": f"Picking, attempt {self.part['attempt']}"}
        if self.running:
            return {"light": "green", "text": "Sorting"}
        return {"light": "off", "text": "Ready"}

    def stats(self) -> dict:
        path = runner.RUN_LOG
        rows = []
        if path.exists():
            rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        since = self.shift_start.isoformat(timespec="seconds")
        shift = [row for row in rows if row.get("time", "") >= since]

        def figures(rows: list[dict]) -> dict:
            first = [row for row in rows if row["attempt"] == 1]
            parts = {(row["order"], row["item"]) for row in rows}
            done = {(row["order"], row["item"]) for row in rows if row["outcome"] in GOOD}
            times = [row["run_s"] for row in rows if row.get("run_s")]
            return {
                "picks": len(rows),
                "first_ok": sum(row["outcome"] in GOOD for row in first), "first": len(first),
                "parts_ok": len(done), "parts": len(parts),
                "cycle_s": round(statistics.mean(times)) if times else None,
            }

        return {"shift": figures(shift), "all": figures(rows), "operator_calls": self.operator_calls,
                "shift_start": self.shift_start.strftime("%H:%M")}

    def state(self) -> dict:
        with self.lock:
            items = {
                item: {"label": spec.get("label", item), "color": spec.get("color", "#888"), "models": model_labels(item),
                       "default": REPLAY if spec.get("mode") == REPLAY and item in replay_items() else None}
                for item, spec in self.config["items"].items()
            }
            return {
                "andon": self.andon(),
                "order": self.order,
                "part": self.part,
                "part_index": next((i for i, part in enumerate(self.order["parts"]) if part is self.part), None)
                if self.order and self.part else None,
                "picking_s": round(time.monotonic() - self.picking_since) if self.picking_since else None,
                "question": self.question,
                "last_pick": self.last_pick,
                "bins": self.bins,
                "shipped": self.shipped,
                "events": list(self.events)[:30],
                "stats": self.stats(),
                "stop_requested": self.stop_requested,
                "cameras": {"names": list(self.cameras.devices), "live": self.cameras.live,
                            "paused": self.cameras.paused, "picking": self.cameras.picking,
                            "errors": self.cameras.errors},
                "items": items,
                "kits": self.config["kits"],
                "fake": bool(os.environ.get("KITCHECK_FAKE_RUN")),
                "seen": {**self.seen, "fresh": self.seen_fresh()},
                "clips": clips.manifest(),
            }

    # ---- actions from the page -------------------------------------------

    def start(self, kit: str, labels: dict[str, str]) -> None:
        with self.lock:
            if self.running:
                raise ValueError("a work order is already running")
            self.config = load_config()
            if kit == SEEN_ORDER:
                items = self.seen_items()
                if not items:
                    raise ValueError("the camera sees no parts on the table")
            elif kit in self.config["kits"]:
                items = list(self.config["kits"][kit])
            elif kit in self.config["items"]:
                items = [kit]
            else:
                raise ValueError(f"unknown work order '{kit}'")
            fake = bool(os.environ.get("KITCHECK_FAKE_RUN"))
            missing = [item for item in items if not labels.get(item) and not fake]
            if missing:
                raise ValueError(f"no model chosen for {', '.join(missing)}; download one with scripts/get_model.sh")
            self.order = {
                "id": uuid.uuid4().hex[:8], "name": kit, "state": "running",
                "started": datetime.now().strftime("%H:%M:%S"),
                "parts": [{"item": item, "label": labels.get(item) or "final", "status": "queued", "attempt": 0}
                          for item in items],
            }
            self.stop_requested = False
            if self.seen_fresh():
                counts: dict[str, int] = {}
                for p in self.seen["parts"]:
                    if p["where"] == "table":
                        counts[p["item"]] = counts.get(p["item"], 0) + 1
                self.order["seen_on_table"] = {item: counts.get(item, 0) for item in self.config["items"]}
            names = ", ".join(self.label(item) for item in items)
            self.log(f"Work order {self.order['id']} \"{kit}\" started: {names}.")
            self._precheck(items)
        threading.Thread(target=self._work, args=(self.order,), daemon=True).start()

    def answer(self, choice: str) -> None:
        with self.lock:
            if not self.question or choice not in self.question["choices"]:
                raise ValueError("the cell is not waiting for that answer")
        self.answers.put(choice)

    def stop(self) -> None:
        with self.lock:
            if self.running:
                self.stop_requested = True
                self.log("Stopping after the current part.", "warn")

    def keep_clip(self, run: str) -> dict:
        """Save a run as a captioned clip in media/ (kitcheck/clips.py). Never while the arm works:
        encoding takes the CPU for a few seconds."""
        if self.running:
            raise ValueError("wait until the work order is finished: making a clip takes the CPU for a few seconds")
        folder = (ROOT / run).resolve()
        if not folder.is_relative_to(EVAL) or not folder.is_dir():
            raise ValueError("not a recorded run")
        entry = clips.add(folder, report=lambda *_: None)
        self.log(f"Kept a clip of this pick: {entry['video']}.", "good")
        return entry

    def ship(self) -> None:
        with self.lock:
            count = sum(self.bins.values())
            if count:
                self.shipped += count
                self.bins = {}
                self.log(f"Bins sent to packing: {count} part{'s' if count != 1 else ''}.", "good")

    # ---- the parts view: the stand camera while the arm is idle --------------

    def seen_fresh(self) -> bool:
        return self.seen["time"] is not None and time.monotonic() - self.seen["time"] < 2.0 and not self.seen["dark"]

    def seen_items(self) -> list[str]:
        """Parts on the table that have a model, in config order: the "what's on the table" order."""
        if not self.seen_fresh():
            return []
        fake = bool(os.environ.get("KITCHECK_FAKE_RUN"))
        on_table = [p["item"] for p in self.seen["parts"] if p["where"] == "table"]
        return [item for item in self.config["items"] for _ in range(on_table.count(item))
                if fake or model_labels(item)]

    def _precheck(self, items: list[str]) -> None:
        """Warn (never block) about parts the camera cannot see, or sees far from where they were taught."""
        if not self.seen_fresh():
            return
        table = [p for p in self.seen["parts"] if p["where"] == "table"]
        for item in dict.fromkeys(items):
            mine = [p for p in table if p["item"] == item]
            if not mine:
                self.log(f"Camera: no {self.label(item)} on the table. Restock it before the cell gets there.", "warn")
            elif all(p["spot"] == "outside" for p in mine):
                self.log(f"Camera: the {self.label(item)} is outside the area it was taught to pick from "
                         f"({mine[0]['off_px']} px off). Move it onto its mark.", "warn")

    def locate(self, item: str) -> tuple[float, float] | None:
        """Where the stand camera sees the item right now (locked camera view), for camera-guided replay.

        Called just before each replay pick, retries included, so a ring nudged by a miss is found
        where it is now. Waits for a frame taken after the camera's exposure has settled."""
        if "front" not in self.cameras.devices:
            return None
        frame = self._fresh_frame()
        if frame is None:
            self.log(f"Camera: no picture in time to find the {self.label(item)}.", "warn")
            return None
        conf = vision.settings(self.config)
        areas = vision.load_areas(conf["areas"])
        to_ref = cv2.invertAffineTransform(self.warp) if self.warp is not None else None
        target = vision.locate(vision.detect(frame, conf, areas, to_ref), item, areas, to_ref)
        if target is None:
            self.log(f"Camera: cannot find the {self.label(item)} on the table.", "bad")
            return None
        try:
            p = replay.plan(item, *target, replay.load())
            self.log(f"Camera: {self.label(item)} found; replaying {p.describe()}.", "warn" if p.far else "info")
        except (FileNotFoundError, ValueError) as error:
            self.log(f"Camera replay: {error}", "bad")
        return target

    def _fresh_frame(self, wait_s: float = 5.0):
        """A stand-camera frame taken after this call and after the camera's exposure settled, or None."""
        asked = time.monotonic()
        self.cameras.take_back()
        while time.monotonic() - asked < wait_s:
            frame = self.cameras.frames.get("front")
            if frame and frame[0] > max(asked, self.cameras.opened_at + 1.0):
                return frame[1]
            time.sleep(0.05)
        return None

    def _parts_now(self, frame) -> list:
        conf = vision.settings(self.config)
        to_ref = cv2.invertAffineTransform(self.warp) if self.warp is not None else None
        return vision.detect(frame, conf, vision.load_areas(conf["areas"]), to_ref)

    def confirm(self, item: str, outcome: str) -> None:
        """Cross-check a pick the gripper check called good, with the stand camera, as soon as it can
        see again: the part should have left the table, and be in its bin where the camera can see into
        it. Only ever adds a line to the log; it never overrides the gripper check."""
        if "front" not in self.cameras.devices or outcome not in GOOD:
            return
        frame = self._fresh_frame(4.0)
        if frame is None:
            return
        parts = [p for p in self._parts_now(frame) if p.item == item]
        name = self.label(item)
        before = (self.order or {}).get("seen_on_table", {}).get(item)
        on_table = sum(p.where == "table" for p in parts)
        if any(p.where == "bin" and p.bin == item for p in parts):
            self.log(f"Camera confirms: the {name} is in its bin.", "good")
        elif any(p.where == "bin" for p in parts):
            wrong = next(p.bin for p in parts if p.where == "bin")
            self.log(f"Camera: a {name} is in the {wrong} bin, not its own.", "bad")
        elif before is not None and on_table >= before > 0:
            self.log(f"Camera still sees the {name} on the table, though the gripper check said placed.", "bad")
        elif on_table == 0 or (before is not None and on_table < before):
            self.log(f"Camera confirms: the {name} has left the table.", "good")

    def _watch(self) -> None:
        conf = vision.settings(self.config)
        areas = vision.load_areas(conf["areas"])
        ref = cv2.imread(str(conf["reference"]))
        positions = {item: img for item, path in self.config.get("vision", {}).get("camera_positions", {}).items()
                     if (img := cv2.imread(str(ROOT / path))) is not None} or ({"locked": ref} if ref is not None else {})
        position_warps: dict = {}
        warp, measured_at, last_text, stable = None, 0.0, None, 0
        while True:
            time.sleep(0.15)
            frame = self.cameras.frames.get("front")
            if self.running or not self.cameras.live or not frame or time.monotonic() - frame[0] > 1.0:
                continue
            if frame[0] < self.cameras.opened_at + 1.0:  # a camera just handed back is still adjusting its exposure
                continue
            img = frame[1]
            if vision.too_dark(img):
                with self.lock:
                    self.seen = {"time": time.monotonic(), "parts": [], "dark": True, "camera": self.seen["camera"]}
                    self.parts_jpeg = None
                continue
            # Where the camera points, every few seconds: the taught areas are in the locked view (warp),
            # and the badge says how far it is from where each color was recorded.
            if ref is not None and time.monotonic() - measured_at > 3.0:
                measured_at = time.monotonic()
                try:
                    found, cc = align.measure(ref, img, warp)
                    warp = found if cc > 0.5 else None
                    camera = _camera_status(img, positions, position_warps)
                except cv2.error:
                    warp, camera = None, None
                with self.lock:
                    self.seen["camera"] = camera
            self.warp = warp
            to_ref = cv2.invertAffineTransform(warp) if warp is not None else None
            parts = vision.detect(img, conf, areas, to_ref)
            jpeg = cv2.imencode(".jpg", vision.draw(img, parts, conf, areas, warp), [cv2.IMWRITE_JPEG_QUALITY, 75])[1].tobytes()
            with self.lock:
                self.seen = {"time": time.monotonic(), "parts": [asdict(p) for p in parts], "dark": False,
                             "camera": self.seen["camera"]}
                self.parts_jpeg = (time.monotonic(), jpeg)
            # Log what the camera sees when it changes and holds for a moment.
            text = _seen_text(parts, self.label)
            stable = stable + 1 if text == getattr(self, "_seen_candidate", None) else 0
            self._seen_candidate = text
            if stable == 4 and text != last_text:
                last_text = text
                self.log(f"Camera: {text}.")

    # ---- the work order ----------------------------------------------------

    def _work(self, order: dict) -> None:
        results = {"verified": "sorted", "manual": "sorted by hand", "skipped": "skipped", "cancel": "cancelled"}
        try:
            for part in order["parts"]:
                if self.stop_requested:
                    part["status"] = "cancelled"
                    continue
                self.part = part
                outcome = runner.pack_item(part["item"], self.config, order["id"], part["label"],
                                           ask=self.ask, notify=self.notify, locate=self.locate)
                with self.lock:
                    part["status"] = results[outcome]
                    if outcome in ("verified", "manual"):
                        self.bins[part["item"]] = self.bins.get(part["item"], 0) + 1
                    if outcome == "cancel":
                        self.stop_requested = True
        except Exception as error:  # noqa: BLE001 - shown on the page instead of killing the thread
            self.log(f"Work order stopped by an error: {error}", "bad")
            for part in order["parts"]:
                if part["status"] in ("queued", "picking", "retrying"):
                    part["status"] = "cancelled"
        finally:
            self.cameras.take_back()
            with self.lock:
                self.picking_since = None
                self.part = None
                self.question = None
                order["state"] = "finished"
                order["finished"] = datetime.now().strftime("%H:%M:%S")
                sorted_ = sum(part["status"].startswith("sorted") for part in order["parts"])
                level = "good" if sorted_ == len(order["parts"]) else "warn"
                self.log(f"Work order {order['id']} finished: {sorted_} of {len(order['parts'])} parts in their bins.", level)
                self.stop_requested = False

    def notify(self, event: str, **data) -> None:
        item = data.get("item")
        name = self.label(item) if item else ""
        if event == "picking":
            with self.lock:
                self.part["status"] = "picking"
                self.part["attempt"] = data["attempt"]
                self.picking_since = time.monotonic()
            self.log(f"Picking {name}" + (f", attempt {data['attempt']}." if data["attempt"] > 1 else "."))
            self.cameras.hand_over()
        elif event == "checked":
            self.cameras.take_back()
            outcome = data["outcome"]
            run = Path(data["run"])
            with self.lock:
                self.picking_since = None
                self.part["status"] = "checking"
                self.last_pick = {
                    "item": item, "label": name, "attempt": data["attempt"], "outcome": outcome,
                    "reason": data["reason"], "seconds": data["seconds"], "model": data.get("model", ""),
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "run": str(run.relative_to(ROOT)) if run.is_relative_to(ROOT) else "",
                    "videos": [cam for cam in ("front", "wrist") if _video(run, cam)],
                }
            level = "good" if outcome in GOOD else "warn" if outcome == grasp.MISSED else "bad"
            self.log(f"{name}: {outcome.upper()}. {data['reason'][:1].upper()}{data['reason'][1:]}.", level)
            self.confirm(item, outcome)
            if outcome in GOOD and self.order and "seen_on_table" in self.order and item in self.order["seen_on_table"]:
                self.order["seen_on_table"][item] = max(0, self.order["seen_on_table"][item] - 1)
        elif event == "retrying":
            with self.lock:
                self.part["status"] = "retrying"
            self.log(f"{name} should still be in place. Retrying on its own.", "warn")
        elif event == "needs_operator":
            with self.lock:
                self.operator_calls += 1
                self.part["status"] = "operator"
                self._pending = {"item": item, "label": name, "outcome": data["outcome"], "reason": data["reason"]}
            self.log(f"{name}: operator needed ({data['outcome']}).", "bad")

    def ask(self, question: str, choices: dict[str, str]) -> str:
        """Called by the runner on the worker thread; waits for a button on the page."""
        while not self.answers.empty():
            self.answers.get_nowait()
        with self.lock:
            self.question = {**getattr(self, "_pending", {}), "choices": list(choices.values())}
        choice = self.answers.get()
        with self.lock:
            self.question = None
            if self.part:
                self.part["status"] = "queued" if choice == "retry" else self.part["status"]
        self.log(f"Operator chose: {choice}.")
        return choice


SEEN_ORDER = "What's on the table"
RINGS = np.float32([[340, 330]])  # where the parts sit in the stand camera's view


def _camera_status(img, positions: dict, warps: dict) -> dict | None:
    """How far the camera is from where each color's demonstrations were recorded, measured where the
    rings sit (a corner exaggerates a small turn). The closest one decides the badge."""
    found = {}
    for item, ref in positions.items():
        try:
            w, cc = align.measure(ref, img, warps.get(item))
        except cv2.error:
            continue
        if cc <= 0.5:
            warps.pop(item, None)
            continue
        warps[item] = w
        found[item] = {"ring_px": round(float(np.linalg.norm(align.apply(w, RINGS) - RINGS)), 1),
                       "rot_deg": round(float(np.degrees(np.arctan2(w[1, 0], w[0, 0]))), 2)}
    if not found:
        return {"state": "NO LOCK", "best": None, "by_item": {}}
    best = min(found, key=lambda item: found[item]["ring_px"] + 3 * abs(found[item]["rot_deg"]))
    px, rot = found[best]["ring_px"], abs(found[best]["rot_deg"])
    state = "ALIGNED" if px <= 5 and rot <= 0.6 else "CLOSE" if px <= 12 and rot <= 1.2 else "OFF"
    return {"state": state, "best": best, **found[best], "by_item": found}


def _seen_text(parts: list, label) -> str:
    table = [f"{label(p.item)} ({vision.SPOT_TEXT[p.spot]})" for p in parts if p.where == "table"]
    bins = [f"{label(p.item)} in the {p.bin} bin" + ("" if p.bin == p.item else " (wrong bin)")
            for p in parts if p.where == "bin"]
    if not table and not bins:
        return "nothing on the table"
    return "; ".join(filter(None, ["on the table: " + ", ".join(table) if table else "",
                                   "in bins: " + ", ".join(bins) if bins else ""]))


def _video(run: Path, cam: str) -> Path | None:
    path = run / "videos" / f"observation.images.{cam}" / "chunk-000" / "file-000.mp4"
    return path if path.exists() else None


PAGE = (Path(__file__).with_name("dashboard.html")).read_text


def serve(station: Station, host: str, port: int) -> None:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, body: bytes, kind: str, code: int = 200) -> None:
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def send_json(self, data, code: int = 200) -> None:
            self.send(json.dumps(data).encode(), "application/json", code)

        def send_video(self, path: Path) -> None:
            # Browsers ask for byte ranges to play and seek video.
            size = path.stat().st_size
            start, end = 0, size - 1
            ranged = self.headers.get("Range", "")
            if ranged.startswith("bytes="):
                first, _, last = ranged[6:].split(",")[0].partition("-")
                if first:
                    start, end = int(first), int(last) if last else size - 1
                else:
                    start = max(0, size - int(last))
                end = min(end, size - 1)
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            else:
                self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            self.end_headers()
            with path.open("rb") as handle:
                handle.seek(start)
                left = end - start + 1
                while left > 0:
                    chunk = handle.read(min(left, 1 << 16))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)

        def do_GET(self):
            url = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            try:
                if url.path == "/":
                    self.send(PAGE().encode(), "text/html; charset=utf-8")
                elif url.path == "/state":
                    self.send_json(station.state())
                elif url.path == "/cam":
                    jpg = station.cameras.jpeg.get(q.get("name", ""))
                    drawn = station.parts_jpeg
                    if q.get("parts") == "1" and q.get("name") == "front" and drawn and time.monotonic() - drawn[0] < 1.0:
                        jpg = drawn[1]
                    if jpg and station.cameras.live:
                        self.send(jpg, "image/jpeg")
                    else:
                        self.send(b"", "image/jpeg", 503)
                elif url.path.startswith("/media/"):
                    path = (ROOT / url.path.lstrip("/")).resolve()
                    kinds = {".mp4": "video/mp4", ".jpg": "image/jpeg", ".gif": "image/gif", ".png": "image/png"}
                    if not path.is_relative_to((ROOT / "media").resolve()) or not path.is_file() or path.suffix not in kinds:
                        self.send_error(404)
                    elif path.suffix == ".mp4":
                        self.send_video(path)
                    else:
                        self.send(path.read_bytes(), kinds[path.suffix])
                elif url.path == "/video":
                    run = (ROOT / q.get("run", "")).resolve()
                    path = _video(run, q.get("cam", "")) if run.is_relative_to(EVAL) else None
                    if path:
                        self.send_video(path)
                    else:
                        self.send_error(404)
                else:
                    self.send_error(404)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_POST(self):
            url = urlparse(self.path)
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}") if length else {}
            try:
                if url.path == "/order":
                    station.start(str(body.get("kit", "")), {k: str(v) for k, v in (body.get("labels") or {}).items() if v})
                elif url.path == "/answer":
                    station.answer(str(body.get("choice", "")))
                elif url.path == "/stop":
                    station.stop()
                elif url.path == "/ship":
                    station.ship()
                elif url.path == "/clips":
                    station.keep_clip(str(body.get("run", "")))
                elif url.path == "/cameras":
                    station.cameras.pause(bool(body.get("paused")))
                    station.log("Live view paused: the cameras are free for other programs." if body.get("paused")
                                else "Live view resumed.")
                else:
                    self.send_error(404)
                    return
                self.send_json({"ok": True})
            except ValueError as error:
                self.send_json({"error": str(error)}, 400)

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    shown = "127.0.0.1" if host in ("0.0.0.0", "") else host
    print(f"station dashboard: http://{shown}:{port}   (Ctrl+C here stops it and frees the cameras)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--front", help="stand camera device (scripts/settings.env FRONT_CAM)")
    parser.add_argument("--wrist", help="gripper camera device (scripts/settings.env WRIST_CAM)")
    parser.add_argument("--host", default="127.0.0.1", help="0.0.0.0 to reach the page from other machines")
    parser.add_argument("--port", type=int, default=8078)
    args = parser.parse_args(argv)
    devices = {name: device for name, device in (("front", args.front), ("wrist", args.wrist)) if device}
    cameras = Cameras(devices)
    threading.Thread(target=cameras.loop, daemon=True).start()
    serve(Station(cameras), args.host, args.port)


if __name__ == "__main__":
    main()
