"""lerobot-record with manual start and stop: no timers decide when a take begins or ends.

    python -m kitcheck.record <the usual lerobot-record options>

scripts/record.sh runs this; use that instead of calling it directly.

LeRobot already ends a take on the right arrow and discards it on the left, but
it starts the first take the moment the arms connect, and it ends takes and
resets on timers. This runs LeRobot's own recorder unchanged, with two additions:

* Before the first take it waits (the follower copies the leader, nothing is
  recorded) until you press the right arrow.
* It prints which state you are in, so you always know whether you are recording.

A take stops on your key press or when --dataset.episode_time_s runs out, and is
then kept. Give it a long --dataset.reset_time_s (record.sh does) so the time
between takes has no limit:

    WAITING    ->  start the next take (this also keeps the take before it)
               <-  throw away the take you just finished, then wait again
               Esc keep the take you just finished, save and finish
    RECORDING  ->  stop the take and keep it
               <-  stop the take and throw it away
               Esc stop, keep this take, save and finish

The letters n (next), r (re-record) and q (quit) work as well as the arrows.
"""

from __future__ import annotations

import sys
import time

from lerobot.scripts import lerobot_record as rec

_record_loop = rec.record_loop
_must_wait = True  # wait for the right arrow before the next take
_started = False   # a take has been recorded in this session
WAIT_S = 24 * 3600  # "until a key is pressed"


def _banner(text: str):
    print(f"\n{'=' * 76}\n  {text}\n{'=' * 76}", flush=True)


def _wait_kwargs(kwargs: dict) -> dict:
    """The arguments for an unrecorded phase: same robot and leader, no dataset."""
    keep = {k: v for k, v in kwargs.items() if k not in ("dataset", "timer", "display_compressed_images")}
    keep["control_time_s"] = WAIT_S
    return keep


def _wait_for_start(args, kwargs, why: str):
    """Teleoperate without recording until the right arrow (start) or Esc (quit)."""
    events = kwargs["events"]
    _banner(f"WAITING (not recording). {why}    ->  start recording    Esc  finish")
    while True:
        _record_loop(*args, **_wait_kwargs(kwargs))
        if events["stop_recording"]:
            raise SystemExit(0)  # LeRobot's cleanup saves what was kept, disconnects and uploads
        if events["rerecord_episode"]:  # left arrow here: nothing left to throw away
            events["rerecord_episode"] = False
            events["exit_early"] = False
            continue
        return


def record_loop(*args, **kwargs):
    global _must_wait, _started
    events = kwargs["events"]

    if kwargs.get("dataset") is None:  # LeRobot's reset phase, right after a take
        discarding = events["rerecord_episode"]  # the take was ended with the left arrow
        if discarding:
            _banner("WAITING (not recording). That take will be thrown away.    ->  start the next take    Esc  finish")
        else:
            _banner("WAITING (not recording)    ->  keep that take and start the next    <-  throw that take away    Esc  keep it and finish")
        result = _record_loop(*args, **kwargs)
        if events["rerecord_episode"] and not discarding:
            _must_wait = True  # thrown away from here: set up again, then start with the right arrow
        return result

    if _must_wait:
        _must_wait = False
        _wait_for_start(args, kwargs, "Take thrown away. Set up again." if _started else "Ring on its spot, both arms at rest.")

    _started = True
    take = kwargs["dataset"].num_episodes + 1
    limit = kwargs.get("control_time_s") or 0
    _banner(f"RECORDING take {take} (stops by itself after {limit:g} s)    ->  stop and keep    <-  stop and throw away    Esc  keep it and finish")
    started = time.monotonic()
    result = _record_loop(*args, **kwargs)
    if limit and time.monotonic() - started >= limit - 0.1 and not events["rerecord_episode"]:
        print(f"\n  {limit:g} s limit reached: take {take} stopped and kept (press <- next to throw it away)", flush=True)
    return result


def main():
    rec.record_loop = record_loop
    sys.argv = ["lerobot-record", *sys.argv[1:]]
    rec.main()


if __name__ == "__main__":
    main()
