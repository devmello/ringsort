#!/usr/bin/env python3
"""Summarize one or more lerobot-train logs: speed, warm-up, checkpoints, loss, time left.

    python scripts/train_report.py logs/kitcheck_act_sensor.log
    python scripts/train_report.py logs/kitcheck_act_sensor_long.log logs/kitcheck_act_sensor_guide.log
    python scripts/train_report.py --md logs/kitcheck_act_sensor.log      # markdown, for notes or the README

With two or more logs it also prints how long each run took to reach the same
training-loss levels, which is the fair way to compare two recipes.

Works on the log file written by scripts/train.sh and on the output.log that
Weights & Biases saves inside a run folder. Needs only the Python standard library.
"""

import argparse
import re
import statistics
import sys
from datetime import datetime
from pathlib import Path

# LeRobot v0.4 writes "... lr:... updt_s:X data_s:Y"; v0.6 writes "... data_s:Y prep_s:... updt_s:X step_s:...".
# The two lookaheads read updt_s and data_s in either order.
LINE = re.compile(
    r"INFO (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) \S+ step:\S+ smpl:\S+ ep:\S+ epch:([\d.]+) "
    r"loss:([\d.]+)(?=[^\n]*? updt_s:([\d.]+))(?=[^\n]*? data_s:([\d.]+))"
)
STAMP = re.compile(r"INFO (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) ")
CHECKPOINT = re.compile(r"INFO (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) \S+ Checkpoint policy after step (\d+)")
LOSS_LEVELS = [1.0, 0.5, 0.2, 0.1, 0.07, 0.05, 0.04, 0.03]


def _time(text):
    return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")


def _top_level_int(text, key, default=None):
    """Read a top-level integer from the settings printed at the start of the log."""
    match = re.search(r"^(?:.*ot_train\.py:\d+ \{| )'" + re.escape(key) + r"': (\d+),?$", text, flags=re.M)
    return int(match.group(1)) if match else default


def _search_int(pattern, text, default=None):
    match = re.search(pattern, text)
    return int(match.group(1)) if match else default


def fmt_duration(seconds):
    if seconds is None:
        return "-"
    seconds = int(round(seconds))
    if seconds >= 600:  # ten minutes or more: the nearest minute is precise enough
        hours, minutes = divmod(int(round(seconds / 60)), 60)
        return f"{hours} h {minutes:02d} min" if hours else f"{minutes} min"
    minutes, secs = divmod(seconds, 60)
    return f"{minutes} min {secs:02d} s"


class Run:
    def __init__(self, path):
        self.path = Path(path)
        text = self.path.read_text(errors="replace")
        self.batch = _search_int(r"Effective batch size: (\d+) x", text) or _top_level_int(text, "batch_size")
        self.total_steps = _search_int(r"cfg\.steps=(\d+)", text) or _top_level_int(text, "steps")
        self.frames = _search_int(r"dataset\.num_frames=(\d+)", text)
        self.episodes = _search_int(r"dataset\.num_episodes=(\d+)", text)
        self.log_freq = _top_level_int(text, "log_freq", 200)
        self.cameras = sorted(set(re.findall(r"observation\.images\.([A-Za-z0-9_]+)", text)))
        self.finished = "End of training" in text
        job = re.search(r"^ 'job_name': '([^']+)',?$", text, flags=re.M)
        wandb_run = re.search(r"wandb\.ai/\S+/runs/([A-Za-z0-9]+)", text)
        self.job = job.group(1) if job else (f"wandb run {wandb_run.group(1)}" if wandb_run else None)

        first = STAMP.search(text)
        self.start = _time(first.group(1)) if first else None

        # Each progress line covers the log_freq steps before it. The step number
        # printed in the line is rounded ("20K"), so steps are counted instead:
        # anchored on a checkpoint line when there is one (those print the exact
        # step), otherwise estimated from the epoch count of the first line.
        events = [(m.start(), "line", m.groups()) for m in LINE.finditer(text)]
        events += [(m.start(), "ckpt", m.groups()) for m in CHECKPOINT.finditer(text)]
        events.sort(key=lambda event: event[0])
        lines = [event[2] for event in events if event[1] == "line"]

        first_step = None
        seen = 0
        for _, kind, groups in events:
            if kind == "line":
                seen += 1
            elif seen and int(groups[1]) % self.log_freq == 0:
                first_step = int(groups[1]) - (seen - 1) * self.log_freq
                break
        if first_step is None and lines:
            first_step = self.log_freq
            if self.frames and self.batch:
                estimate = float(lines[0][1]) * self.frames / self.batch
                first_step = max(self.log_freq, int(round(estimate / self.log_freq)) * self.log_freq)

        self.rows = []  # (step, seconds since start, loss, updt_s, data_s)
        for index, (when, _epoch, loss, updt, data) in enumerate(lines):
            step = first_step + index * self.log_freq
            self.rows.append((step, (_time(when) - self.start).total_seconds(), float(loss), float(updt), float(data)))

        self.checkpoints = [
            (int(step_text), (_time(when) - self.start).total_seconds())
            for when, step_text in CHECKPOINT.findall(text)
        ]
        last = None
        for last in STAMP.finditer(text):
            pass
        self.end = _time(last.group(1)) if last else None

    # -- derived numbers ---------------------------------------------------
    @property
    def name(self):
        return self.job or self.path.stem

    def steady_rows(self):
        """Progress lines after the start-up phase (skip the first 1,000 steps when possible)."""
        if not self.rows:
            return []
        first_step = self.rows[0][0]
        later = [row for row in self.rows if row[0] >= first_step + 1000]
        return later if len(later) >= 3 else self.rows[len(self.rows) // 2:]

    def step_seconds(self):
        rows = self.steady_rows()
        if not rows:
            return None, None
        return statistics.median(row[3] for row in rows), statistics.median(row[4] for row in rows)

    def slow_patches(self):
        updt, _ = self.step_seconds()
        if updt is None:
            return []
        return [(row[0], row[3]) for row in self.rows if row[3] > 1.5 * updt]

    def warmup_extra_seconds(self):
        """Time lost to slow start-up patches, compared with running at steady speed."""
        updt, _ = self.step_seconds()
        if updt is None:
            return None
        return sum((row[3] - updt) * self.log_freq for row in self.rows if row[3] > 1.5 * updt)

    def current_step(self):
        return self.rows[-1][0] if self.rows else 0

    def elapsed(self):
        if not (self.start and self.end):
            return None
        return (self.end - self.start).total_seconds()

    def seconds_left(self):
        updt, data = self.step_seconds()
        if self.finished or updt is None or not self.total_steps:
            return None
        return max(0, self.total_steps - self.current_step()) * (updt + data)

    def time_to_loss(self, level):
        for step, seconds, loss, _, _ in self.rows:
            if loss <= level:
                return step, seconds
        return None


PROGRESS_BAR = re.compile(r"Training:\s+\d+%\|[^|]*\|\s*(\d+)/(\d+) \[([^<\]]+)<([^,\]]+),\s*([\d.]+)\s*s?t?e?p?/s")


def live_status(path):
    """From the progress bar LeRobot redraws on every step, and the run's pid file."""
    path = Path(path)
    text = path.read_text(errors="replace").replace("\r", "\n")
    lines = []
    bars = PROGRESS_BAR.findall(text)
    if bars:
        done, total, elapsed, left, rate = bars[-1]
        lines.append(f"progress bar: step {done} of {total}, {rate} steps/s, {elapsed.strip()} so far, about {left.strip()} left")
    else:
        lines.append("no progress bar yet: still loading the dataset or the model")
    if re.search(r"Traceback|Error:", text):
        last = [line for line in text.splitlines() if line.strip()][-3:]
        lines.append("the log has an error; last lines:")
        lines.extend("  " + line[:200] for line in last)
    pid_file = path.parent / f"{path.name.split('.')[0]}.pid"
    if pid_file.exists():
        pid = pid_file.read_text().strip()
        alive = Path(f"/proc/{pid}").exists()
        lines.append(f"process {pid}: {'running' if alive else 'NOT running'}")
    return lines


def describe(run, md=False):
    out = []
    bullet = "- " if md else "  "
    out.append((f"### {run.name}" if md else f"== {run.name}"))
    if not run.rows:
        out.append(f"{bullet}no training progress lines yet (LeRobot writes one every 200 steps)")
        out.extend(f"{bullet}{line}" for line in live_status(run.path))
        return "\n".join(out)

    updt, data = run.step_seconds()
    per_step = updt + data
    cams = f", cameras: {', '.join(run.cameras)}" if run.cameras else ""
    out.append(f"{bullet}data: {run.episodes} demonstrations, {run.frames} frames{cams}")
    out.append(f"{bullet}recipe: batch size {run.batch}, {run.total_steps} steps")
    if run.finished:
        out.append(f"{bullet}finished: {run.total_steps} steps in {fmt_duration(run.elapsed())}")
    else:
        out.append(
            f"{bullet}progress: step {run.current_step()} of {run.total_steps} "
            f"(running or stopped early), {fmt_duration(run.elapsed())} so far"
        )
    if not run.finished and run.seconds_left() is not None:
        out.append(f"{bullet}time left at this speed: about {fmt_duration(run.seconds_left())}")
    out.append(
        f"{bullet}speed once warmed up: {per_step:.3f} s per step "
        f"({updt:.3f} s on the GPU + {data:.3f} s waiting for data, {100 * data / per_step:.0f}% waiting)"
    )
    rate = run.batch / per_step
    rate_text = f"{rate:.0f}" if rate >= 10 else f"{rate:.1f}"
    out.append(f"{bullet}that is {rate_text} samples per second, {fmt_duration(10000 * per_step)} per 10,000 steps")
    extra = run.warmup_extra_seconds()
    if extra is not None:
        patches = ", ".join(f"around step {step}" for step, _ in run.slow_patches()[:4]) or "none"
        out.append(f"{bullet}start-up cost: about {fmt_duration(extra)} lost to slow patches ({patches})")
    if run.checkpoints:
        shown = ", ".join(f"{step} at {fmt_duration(seconds)}" for step, seconds in run.checkpoints[:8])
        more = " ..." if len(run.checkpoints) > 8 else ""
        out.append(f"{bullet}checkpoints: {shown}{more}")
    reached = []
    for level in LOSS_LEVELS:
        hit = run.time_to_loss(level)
        if hit:
            reached.append(f"{level:g} at {fmt_duration(hit[1])}")
    if reached:
        out.append(f"{bullet}training loss reached: {'; '.join(reached)}")
    out.append(f"{bullet}latest training loss: {run.rows[-1][2]:.3f}")
    return "\n".join(out)


def compare(runs, md=False):
    levels = [level for level in LOSS_LEVELS if any(run.time_to_loss(level) for run in runs)]
    if not levels:
        return ""
    header = ["Training loss reached"] + [f"{run.name} (batch {run.batch})" for run in runs]
    rows = []
    for level in levels:
        cells = [f"{level:g}"]
        for run in runs:
            hit = run.time_to_loss(level)
            cells.append(f"{fmt_duration(hit[1])} (step {hit[0]})" if hit else "not reached")
        rows.append(cells)
    if md:
        lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
        lines += ["| " + " | ".join(cells) + " |" for cells in rows]
    else:
        widths = [max(len(row[i]) for row in [header] + rows) for i in range(len(header))]
        lines = ["  ".join(cell.ljust(width) for cell, width in zip(row, widths)) for row in [header] + rows]
    title = "### Time to reach the same training loss" if md else "== time to reach the same training loss"
    note = "Training loss shows how fast a run learns its data. It is not the success rate on the robot."
    return "\n".join([title, ""] + lines + ["", note])


def main(argv=None):
    parser = argparse.ArgumentParser(description="Summarize lerobot-train logs.")
    parser.add_argument("logs", nargs="+", help="log files (or Weights & Biases output.log files)")
    parser.add_argument("--md", action="store_true", help="print markdown")
    args = parser.parse_args(argv)

    runs = []
    for path in args.logs:
        if not Path(path).is_file():
            print(f"error: {path} is not a file", file=sys.stderr)
            return 1
        runs.append(Run(path))

    blocks = [describe(run, args.md) for run in runs]
    usable = [run for run in runs if run.rows]
    if len(usable) >= 2:
        table = compare(usable, args.md)
        if table:
            blocks.append(table)
    print("\n\n".join(blocks))
    return 0


if __name__ == "__main__":
    sys.exit(main())
