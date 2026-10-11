#!/usr/bin/env bash
# The station dashboard for the demo: the sorting cell as a factory screen. Runs on the PC.
#
#   scripts/dashboard.sh                          -> open http://127.0.0.1:8078
#   DASHBOARD_HOST=0.0.0.0 scripts/dashboard.sh   -> also reachable from a laptop or phone on the same network
#
# Start work orders, answer the cell when it flags the operator, and replay each
# pick from its own recording. The cameras stream only while the arm is idle and
# are handed to the robot for every pick. While the page is open, the cameras
# are busy: press "Pause live view" before using record.sh or try_model.sh.
#
# Rehearse without the robot: every pick copies a recorded run instead, e.g.
#   KITCHECK_FAKE_RUN=examples/runs/purple_placed scripts/dashboard.sh
# and to rehearse the parts view with a saved stand-camera frame instead of the camera:
#   KITCHECK_FAKE_RUN=... python -m kitcheck.dashboard --front <frame.png>
#
# The parts view needs data/vision.json; make it once with: python -m kitcheck.vision learn

. "$(dirname "$0")/_lib.sh"

PYTHONPATH="${SCRIPTS_DIR}/..${PYTHONPATH:+:$PYTHONPATH}" python -m kitcheck.dashboard \
  --front "$FRONT_CAM" \
  --wrist "$WRIST_CAM" \
  --host "${DASHBOARD_HOST:-127.0.0.1}" \
  --port "${DASHBOARD_PORT:-8078}"
