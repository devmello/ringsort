"""Recorded picks: turn a run's recording into a captioned clip in media/, for the
dashboard, the README and the submission.

Each clip puts the stand camera and the gripper camera side by side under a
caption bar (part, how it was picked, the verdict), encoded as H.264 so any
browser and GitHub can play it. media/clips.json lists every clip; the
dashboard's "Recorded picks" panel reads it.

    python -m kitcheck.clips add data/eval/purple_010000_20261010_210212
    python -m kitcheck.clips add <run folder> --title "First placed purple ring" --gif
    python -m kitcheck.clips list
    python -m kitcheck.clips demo <clip id>...      mark clips as the project's demos (--off to unmark)
    python -m kitcheck.clips reel <run>... --out examples/x.mp4   one video of a whole order, misses included

The dashboard's "Keep this clip" button on the last pick does the same as `add`.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from kitcheck import grasp
from kitcheck.skill import ROOT, load_config

MEDIA = ROOT / "media"
PICKS = MEDIA / "picks"
MANIFEST = MEDIA / "clips.json"
FONT = "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"
W, H, BAR = 640, 480, 72
TAIL_S = 2.5  # how long a clip keeps running after the gripper lets go (or closes on nothing)
VERDICT_COLORS = {grasp.PLACED: (34, 197, 94), grasp.HELD: (34, 197, 94), grasp.MISSED: (245, 158, 11),
                  grasp.DROPPED: (239, 68, 68)}


def manifest() -> list[dict]:
    return json.loads(MANIFEST.read_text())["clips"] if MANIFEST.exists() else []


def _save(clips: list[dict]) -> None:
    MEDIA.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps({"clips": clips}, indent=1) + "\n")


def describe_run(folder: Path, config: dict) -> dict:
    """What a run folder name says: data/eval/<item>_<label>_<YYYYmmdd>_<HHMMSS>[_n]."""
    match = re.match(r"(?P<item>[a-z0-9]+)_(?P<label>[A-Za-z0-9]+)_(?P<date>\d{8})_(?P<time>\d{6})", folder.name)
    if not match:
        raise ValueError(f"{folder.name} is not a run folder name like purple_010000_20261010_210212")
    item, label = match["item"], match["label"]
    if label == "replay":
        method = "Camera-guided replay"
    elif label.isdigit():
        method = f"ACT model, step {int(label):,}"
    else:
        method = f"ACT model, {label}"
    when = datetime.strptime(match["date"] + match["time"], "%Y%m%d%H%M%S")
    return {"item": item, "label": config["items"].get(item, {}).get("label", item.title()), "method": method,
            "recorded": when.isoformat(timespec="minutes")}


def _video(folder: Path, cam: str) -> Path:
    path = folder / "videos" / f"observation.images.{cam}" / "chunk-000" / "file-000.mp4"
    if not path.exists():
        raise FileNotFoundError(f"{folder} has no {cam} camera video")
    return path


def _overlay(path: Path, title: str, sub: str, verdict: str) -> None:
    """The caption bar and camera labels, as a transparent PNG laid over the side-by-side video."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGBA", (2 * W, BAR + H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 2 * W, BAR], fill=(21, 25, 31, 255))
    for x in range(-BAR, 2 * W, 28):  # hazard stripe along the top
        d.polygon([(x, 0), (x + 14, 0), (x + 8, 6), (x - 6, 6)], fill=(242, 194, 48, 255))
    def font(path, size):  # Noto ships with Ubuntu; elsewhere fall back to Pillow's own font
        return ImageFont.truetype(path, size) if Path(path).exists() else ImageFont.load_default(size)

    bold, regular, small = font(FONT_BOLD, 26), font(FONT, 18), font(FONT_BOLD, 16)
    d.text((20, 12), title, font=bold, fill=(233, 235, 238, 255))
    d.text((20, 44), sub, font=regular, fill=(169, 178, 190, 255))
    color = VERDICT_COLORS.get(verdict, (169, 178, 190))
    text = verdict.upper()
    tw = d.textlength(text, font=bold)
    d.rounded_rectangle([2 * W - tw - 48, 16, 2 * W - 16, 56], radius=8, fill=color + (255,))
    d.text((2 * W - tw - 32, 17), text, font=bold, fill=(21, 25, 31, 255))
    for x, label in ((12, "STAND CAMERA"), (W + 12, "GRIPPER CAMERA")):
        lw = d.textlength(label, font=small)
        d.rounded_rectangle([x, BAR + H - 36, x + lw + 16, BAR + H - 10], radius=5, fill=(0, 0, 0, 160))
        d.text((x + 8, BAR + H - 34), label, font=small, fill=(255, 255, 255, 255))
    img.save(path)


def _ffmpeg(*args: str) -> None:
    result = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.strip()[-400:]}")


def _render(folder: Path, video: Path, title: str | None = None, method: str | None = None) -> dict:
    """Encode one run as a captioned side-by-side clip at video; returns what it found."""
    config = load_config()
    info = describe_run(folder, config)
    ref_path = ROOT / config["items"].get(info["item"], {}).get("grasp_reference", f"data/grasp_{info['item']}.json")
    reference = grasp.Reference.load(ref_path) if ref_path.exists() else None
    verdict = grasp.judge_folder(folder, reference)
    episode = grasp.load_episodes(folder)[-1]
    end_s = _end_s(episode)
    method = method or info["method"]
    title = title or f"{info['label']} · {method}"
    when = datetime.fromisoformat(info["recorded"])
    sub = f"{verdict.reason[:1].upper()}{verdict.reason[1:]}" + (f" · held {verdict.hold_s:.1f} s" if verdict.hold_s else "") \
        + f" · {when:%a %d %b, %H:%M}"
    with tempfile.TemporaryDirectory() as tmp:
        overlay = Path(tmp) / "overlay.png"
        _overlay(overlay, title, sub, verdict.outcome)
        _ffmpeg("-t", f"{end_s:.2f}", "-i", str(_video(folder, "front")), "-t", f"{end_s:.2f}", "-i", str(_video(folder, "wrist")),
                "-i", str(overlay),
                "-filter_complex",
                f"[0:v]scale={W}:{H},setsar=1[a];[1:v]scale={W}:{H},setsar=1[b];"
                f"[a][b]hstack=inputs=2,pad={2 * W}:{H + BAR}:0:{BAR}:color=0x15191F[v];[v][2:v]overlay=0:0,format=yuv420p[out]",
                "-map", "[out]", "-c:v", "libx264", "-crf", "23", "-preset", "medium", "-r", "30",
                "-movflags", "+faststart", str(video))
    return {"info": info, "verdict": verdict, "episode": episode, "hold": grasp.find_hold(episode),
            "title": title, "method": method, "end_s": end_s}


def _end_s(episode) -> float:
    """Where a clip ends: TAIL_S after the gripper lets go, or after it first closes when it held nothing.
    The rest of a run is the arm going back to rest, which only makes the clip longer."""
    length = len(episode.action) / episode.fps
    hold = grasp.find_hold(episode)
    if hold is not None:
        return min(length, hold.end / episode.fps + TAIL_S)
    commanded = episode.action[:, episode.gripper]
    opened = commanded > commanded.min() + 15.0
    if not opened.any():
        return length
    after = int(opened.argmax())  # the gripper rests closed, so look for the first close after it opened
    closed = commanded[after:] < commanded.min() + 5.0
    return min(length, (after + float(closed.argmax())) / episode.fps + TAIL_S) if closed.any() else length


def add(folder: Path, title: str | None = None, method: str | None = None, gif: bool = False, report=print) -> dict:
    folder = Path(folder).resolve()
    clip_id = folder.name
    PICKS.mkdir(parents=True, exist_ok=True)
    video, poster = PICKS / f"{clip_id}.mp4", PICKS / f"{clip_id}.jpg"
    made = _render(folder, video, title, method)
    info, verdict, episode, hold, title, method = (made[k] for k in ("info", "verdict", "episode", "hold", "title", "method"))
    # Poster: the moment the gripper closed on the part; for a drop, just after it slipped (halfway if it never held).
    # A miss: the moment it closed on nothing (TAIL_S before the clip ends).
    if hold and verdict.outcome == grasp.DROPPED and hold.end < len(episode.action):
        at = hold.end / episode.fps + 0.4
    else:
        at = hold.start / episode.fps + 0.3 if hold else max(0.0, made["end_s"] - TAIL_S + 0.3)
    at = min(at, made["end_s"] - 0.1)
    _ffmpeg("-ss", f"{at:.2f}", "-i", str(video), "-frames:v", "1", "-q:v", "3", str(poster))
    entry = {
        "id": clip_id, "title": title, "item": info["item"], "method": method, "verdict": verdict.outcome,
        "reason": verdict.reason, "hold_s": round(verdict.hold_s, 1), "recorded": info["recorded"],
        "duration_s": round(made["end_s"], 1), "source": str(folder.relative_to(ROOT)),
        "video": str(video.relative_to(ROOT)), "poster": str(poster.relative_to(ROOT)),
    }
    if gif:
        path = PICKS / f"{clip_id}.gif"
        _ffmpeg("-i", str(video), "-vf", "fps=8,scale=640:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=64:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3:diff_mode=rectangle",
                str(path))
        entry["gif"] = str(path.relative_to(ROOT))
    old = next((clip for clip in manifest() if clip["id"] == clip_id), {})
    if old.get("demo"):
        entry["demo"] = True  # remaking a clip keeps it a demo
    clips = [clip for clip in manifest() if clip["id"] != clip_id] + [entry]
    clips.sort(key=lambda clip: clip["recorded"])
    _save(clips)
    report(f"{clip_id}: {verdict.outcome}; wrote {entry['video']} ({video.stat().st_size / 1e6:.1f} MB)")
    return entry


def _card(path: Path, heading: str, lines: list[tuple[str, tuple | None]], footer: str) -> None:
    """A title or result card the size of a clip: heading, lines (each with an optional badge color), footer."""
    from PIL import Image, ImageDraw, ImageFont

    def font(p, size):
        return ImageFont.truetype(p, size) if Path(p).exists() else ImageFont.load_default(size)

    img = Image.new("RGB", (2 * W, H + BAR), (21, 25, 31))
    d = ImageDraw.Draw(img)
    for x in range(-BAR, 2 * W, 28):
        d.polygon([(x, 0), (x + 14, 0), (x + 8, 6), (x - 6, 6)], fill=(242, 194, 48))
    d.text((64, 48), "RINGSORT", font=font(FONT_BOLD, 22), fill=(242, 194, 48))
    d.text((64, 84), heading, font=font(FONT_BOLD, 44), fill=(233, 235, 238))
    y = 176
    for text, color in lines:
        if color:
            d.ellipse([64, y + 8, 88, y + 32], fill=color)
        d.text((104 if color else 64, y), text, font=font(FONT, 28), fill=(233, 235, 238))
        y += 52
    d.text((64, H + BAR - 64), footer, font=font(FONT, 22), fill=(169, 178, 190))
    img.save(path)


def reel(runs: list[Path], out: Path, title: str, report=print) -> Path:
    """One video of a whole work order: a title card, every pick in order (misses included), a result card."""
    runs = [Path(run).resolve() for run in runs]
    config = load_config()
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        parts, results = [], []
        for i, run in enumerate(runs, 1):
            info = describe_run(run, config)
            made = _render(run, tmp / f"{i}.mp4", f"{i} of {len(runs)} · {info['label']} · {info['method']}")
            parts.append(tmp / f"{i}.mp4")
            results.append((info, made["verdict"]))
        first = datetime.fromisoformat(results[0][0]["recorded"])
        _card(tmp / "title.png", title,
              [(f"{info['label']}: {info['method']}", None) for info, _ in results]
              + [("", None), ("One attempt per part. Every pick checked by the gripper's own position record.", None)],
              f"{first:%a %d %b %Y, %H:%M} · the cell's own cameras: stand camera left, gripper camera right")
        good = sum(v.outcome in (grasp.PLACED, grasp.HELD) for _, v in results)
        _card(tmp / "result.png", f"{good} of {len(results)} sorted on the first try",
              [(f"{info['label']}: {v.outcome.upper()}, {v.reason}", VERDICT_COLORS.get(v.outcome)) for info, v in results]
              + [("", None), ("Every miss was caught by the gripper check, not by a person watching.", None)],
              "RingSort: a factory sorting cell that knows when it got a pick wrong")
        segments = []
        for name in ("title", "result"):
            _ffmpeg("-loop", "1", "-t", "4", "-i", str(tmp / f"{name}.png"), "-c:v", "libx264", "-crf", "23",
                    "-preset", "medium", "-r", "30", "-pix_fmt", "yuv420p", str(tmp / f"{name}.mp4"))
        segments = [tmp / "title.mp4", *parts, tmp / "result.mp4"]
        inputs = [arg for seg in segments for arg in ("-i", str(seg))]
        chain = "".join(f"[{k}:v]setsar=1[v{k}];" for k in range(len(segments)))
        chain += "".join(f"[v{k}]" for k in range(len(segments))) + f"concat=n={len(segments)}:v=1:a=0,format=yuv420p[out]"
        _ffmpeg(*inputs, "-filter_complex", chain, "-map", "[out]", "-c:v", "libx264", "-crf", "23",
                "-preset", "medium", "-r", "30", "-movflags", "+faststart", str(out))
    report(f"wrote {out} ({out.stat().st_size / 1e6:.1f} MB): {good} of {len(results)} placed")
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    add_p = sub.add_parser("add", help="make a captioned clip of a run and list it in media/clips.json")
    add_p.add_argument("run", type=Path, nargs="+", help="run folder(s) under data/eval/")
    add_p.add_argument("--title", help="caption title (default: part and method)")
    add_p.add_argument("--method", help='how it picked, e.g. "ACT model, step 10,000" (default: from the folder name)')
    add_p.add_argument("--gif", action="store_true", help="also write a GIF, for showing inline in the README")
    sub.add_parser("list", help="the clips in media/clips.json")
    reel_p = sub.add_parser("reel", help="one video of a whole work order, misses included")
    reel_p.add_argument("run", type=Path, nargs="+", help="the order's run folders, in order")
    reel_p.add_argument("--out", type=Path, required=True, help="the video to write, e.g. examples/full_run.mp4")
    reel_p.add_argument("--title", default="One work order, start to finish")
    demo_p = sub.add_parser("demo", help="mark clips as the project's demos (shown first on the dashboard)")
    demo_p.add_argument("ids", nargs="+", help="clip ids, as `list` prints them")
    demo_p.add_argument("--off", action="store_true", help="unmark them instead")
    args = parser.parse_args(argv)
    if args.command == "list":
        for clip in manifest():
            print(f"{clip['id']}: {clip['title']} · {clip['verdict']}{' · DEMO' if clip.get('demo') else ''} · {clip['video']}")
        return 0
    if args.command == "reel":
        reel(args.run, args.out, args.title)
        return 0
    if args.command == "demo":
        clips = manifest()
        unknown = set(args.ids) - {clip["id"] for clip in clips}
        if unknown:
            parser.error(f"no clip {', '.join(sorted(unknown))}; see: python -m kitcheck.clips list")
        for clip in clips:
            if clip["id"] in args.ids:
                clip["demo"] = not args.off
        _save(clips)
        print(f"{'unmarked' if args.off else 'marked'} {len(args.ids)} clip(s)")
        return 0
    for run in args.run:
        add(run, args.title, args.method, args.gif)
    return 0


if __name__ == "__main__":
    sys.exit(main())
