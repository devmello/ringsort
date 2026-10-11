#!/usr/bin/env bash
# Record demonstrations for one item by teleoperating the follower with the leader.
# Runs on the PC, from the project folder, in a terminal you can type in.
#
#   scripts/record.sh <item> [most takes]
#
#   scripts/record.sh red        -> record red takes until you press Esc (at most 50)
#   scripts/record.sh red 5      -> stop by itself after 5 kept takes
#
# You decide when each take starts and stops (kitcheck/record.py). A take also
# stops by itself after REC_EPISODE_S seconds (20) and is kept; waiting between
# takes has no limit.
# The screen always says WAITING (not recording) or RECORDING.
#
#   WAITING    right arrow  start the next take (keeps the one before it)
#              left arrow   throw away the take you just finished
#              Esc          save and finish
#   RECORDING  right arrow  stop the take and keep it
#              left arrow   stop the take and throw it away
#              Esc          stop, keep this take, save and finish
#
# n, r and q work like right, left and Esc. Keep this terminal focused: on
# Wayland LeRobot reads the keys from it. Never Ctrl+C: it can corrupt a video.
#
# The first session for an item creates $DATA_DIR/pick_<item>; later sessions add
# to it. When the session ends, scripts/push_dataset.sh uploads it to Hugging Face
# as <you>/kitcheck_pick_<item> and checks it arrived. The task text comes from config.json.
#
# The camera view is in the browser at http://127.0.0.1:9090 (Rerun).
# docs/history/03-recording.md explains what a good demonstration looks like.

. "$(dirname "$0")/_lib.sh"

item="${1:-}"
episodes="${2:-50}"
[ -n "$item" ] || die "usage: scripts/record.sh <item> [most takes]     e.g. scripts/record.sh red"
check_item "$item"
case "$episodes" in ''|*[!0-9]*) die "episodes must be a whole number (got '$episodes')" ;; esac
need_hf_user

root="$(demo_root "$item")"
repo="${HF_USER}/kitcheck_pick_${item}"
task="$(task_text "$item")"
have="$(episode_count "$root")"

resume_args=""
# A first session that failed before recording anything (wrong port, camera
# busy) leaves a folder with only meta/ in it, which would block the next try.
if [ -d "$root" ] && [ "$have" -eq 0 ] && [ ! -d "$root/data" ] && [ ! -d "$root/videos" ]; then
  echo "removing ${root}: left empty by a session that never started"
  rm -rf "$root"
fi
if [ -d "$root" ]; then
  [ "$have" -gt 0 ] || die "${root} holds no finished demonstrations (an interrupted first session). Delete it and start again: rm -rf ${root}"
  resume_args="--resume=true"
  echo "adding up to ${episodes} takes to the ${have} demonstrations in ${root} (Esc finishes sooner)"
else
  mkdir -p "$(dirname "$root")"
  echo "new dataset ${root}: up to ${episodes} takes (Esc finishes sooner)"
fi
echo "task: ${task}"

# Camera view: reuse a running Rerun server, or start one for this session.
display_args="--display_data=true --display_ip=127.0.0.1 --display_port=${RERUN_PORT} --display_compressed_images=true"
if ! (exec 3<>"/dev/tcp/127.0.0.1/${RERUN_PORT}") 2>/dev/null; then
  if command -v rerun >/dev/null 2>&1; then
    mkdir -p logs
    nohup rerun --serve-web --bind 127.0.0.1 --port "$RERUN_PORT" --web-viewer-port "$RERUN_WEB_PORT" \
      --server-memory-limit 128MB > logs/rerun.log 2>&1 &
    sleep 2
    echo "started the camera view: http://127.0.0.1:${RERUN_WEB_PORT}"
  else
    echo "no Rerun server and no rerun command: recording without a camera view"
    display_args="--display_data=false"
  fi
else
  echo "camera view: http://127.0.0.1:${RERUN_WEB_PORT}"
fi
echo

record_once() {
  # kitcheck.record is lerobot-record with manual start and stop.
  # shellcheck disable=SC2086
  PYTHONPATH="${SCRIPTS_DIR}/..${PYTHONPATH:+:$PYTHONPATH}" python -m kitcheck.record \
    --robot.type=so101_follower \
    --robot.port="$FOLLOWER_PORT" \
    --robot.id="$FOLLOWER_ID" \
    --robot.cameras="$CAMERAS" \
    $ROBOT_EXTRA_ARGS \
    --teleop.type=so101_leader \
    --teleop.port="$LEADER_PORT" \
    --teleop.id="$LEADER_ID" \
    $display_args \
    --dataset.repo_id="$repo" \
    --dataset.root="$root" \
    --dataset.num_episodes="$episodes" \
    --dataset.episode_time_s="$REC_EPISODE_S" \
    --dataset.reset_time_s="$REC_RESET_S" \
    --dataset.single_task="$task" \
    --dataset.push_to_hub=false \
    $resume_args
}

# LeRobot checks for all six motors once when it connects, and one missed reply
# from a single motor aborts the session. If that happens before anything was
# recorded, try again (up to 3 times) instead of making you start over.
mkdir -p logs
log="logs/record_${item}_$(date +%Y%m%d_%H%M%S).log"
for try in 1 2 3; do
  status=0
  record_once 2>&1 | tee "$log" || status=$?
  [ "$status" -eq 0 ] && break
  if [ "$(episode_count "$root")" -eq "$have" ] && grep -qE "motor check failed|There is no status packet|Incorrect status packet" "$log"; then
    if [ "$have" -eq 0 ] && [ ! -d "$root/data" ] && [ ! -d "$root/videos" ]; then rm -rf "$root"; fi
    if [ "$try" -lt 3 ]; then
      echo
      echo "A motor did not answer while connecting (nothing was recorded). Trying again in 2 s (try $((try + 1)) of 3)."
      echo "If this keeps happening, power off and reseat the cables at the motors it names."
      sleep 2
      continue
    fi
  fi
  echo
  die "recording failed (log: ${log}). $(episode_count "$root") demonstrations are saved in ${root}."
done

echo
echo "${root} now holds $(episode_count "$root") demonstrations."
# Upload with scripts/push_dataset.sh rather than LeRobot's own upload: it removes
# stale files left on the Hub by earlier datasets and checks that the upload arrived.
if [ "$(episode_count "$root")" -gt 0 ]; then
  bash "${SCRIPTS_DIR}/push_dataset.sh" "$item" || echo "UPLOAD FAILED: the demonstrations are safe in ${root}. Retry with: bash scripts/push_dataset.sh ${item}"
fi
echo "check the grasp signal:  python -m kitcheck.grasp inspect ${root}"
echo "replay one on the arm:   bash scripts/replay.sh ${item} 0"
