#!/usr/bin/env bash
# Put the stand camera back where it was while recording. Runs on the PC.
#
#   scripts/align_camera.sh [item] [episode]
#
#   scripts/align_camera.sh              -> line up with the latest purple demonstration
#   scripts/align_camera.sh red          -> the latest red demonstration
#   scripts/align_camera.sh purple 40    -> purple demonstration 40
#
# Open http://127.0.0.1:${ALIGN_PORT:-8077} in the browser. It shows the live camera over
# the recorded view and says how many pixels it is off; move the stand until it
# says ALIGNED. Press "Done" on the page (or Ctrl+C here) when finished: until
# then recording and model runs cannot open the camera.

. "$(dirname "$0")/_lib.sh"

item="${1:-purple}"
episode="${2:-}"
check_item "$item"
case "$episode" in *[!0-9]*) die "episode must be a whole number (got '$episode')" ;; esac

PYTHONPATH="${SCRIPTS_DIR}/..${PYTHONPATH:+:$PYTHONPATH}" python -m kitcheck.align \
  --camera "$FRONT_CAM" \
  --data-dir "$DATA_DIR" \
  --item "$item" \
  ${episode:+--episode "$episode"} \
  --port "${ALIGN_PORT:-8077}"
