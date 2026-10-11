#!/usr/bin/env bash
# Queue the long overnight runs, one after another. Runs on the cloud machine.
#
#   scripts/overnight.sh [--baseline <item>] <item> [<item> ...]
#
#   scripts/overnight.sh sensor motor
#       one long run per item:  kitcheck_act_sensor_long, kitcheck_act_motor_long
#
#   scripts/overnight.sh --baseline sensor sensor motor
#       the same, then the organizers' example recipe on the sensor data
#       (kitcheck_act_sensor_guide) so the two recipes can be compared in the morning
#
# Jobs run in the order given, so the ones the demo needs finish first.
# Progress is written to logs/overnight.log.

. "$(dirname "$0")/_lib.sh"

mkdir -p logs

# First call: restart this script in the background so it survives a closed tab.
if [ -z "${OVERNIGHT_CHILD:-}" ]; then
  [ $# -gt 0 ] || die "usage: scripts/overnight.sh [--baseline <item>] <item> [<item> ...]"
  [ -n "${DATASET_ROOT:-}" ] || need_hf_user
  OVERNIGHT_CHILD=1 nohup bash "$0" "$@" > logs/overnight.log 2>&1 &
  echo "overnight queue started (pid $!)"
  echo "  follow it:  tail -f logs/overnight.log"
  echo "  stop it:    kill $!   (then kill the lerobot-train it started, if one is running)"
  exit 0
fi

baseline=""
items=""
while [ $# -gt 0 ]; do
  case "$1" in
    --baseline) baseline="${2:-}"; [ -n "$baseline" ] || die "--baseline needs an item"; shift 2 ;;
    *) check_item "$1"; items="${items} $1"; shift ;;
  esac
done
[ -z "$baseline" ] || check_item "$baseline"

export RUN_FOREGROUND=1

run_job() {  # run_job <job> <item> <batch> <steps> <save_freq>
  local job="$1" item="$2" batch="$3" steps="$4" save_freq="$5"
  if [ -e "outputs/train/${job}" ]; then
    echo "$(date '+%H:%M:%S') skip ${job}: outputs/train/${job} already exists"
    return 0
  fi
  echo "$(date '+%H:%M:%S') start ${job} (batch ${batch}, ${steps} steps)"
  # shellcheck disable=SC2046
  if start_run "$job" "logs/${job}.log" \
      --dataset.repo_id="$(dataset_repo "$item")" \
      --dataset.root="$(dataset_root "$job")" \
      --policy.type=act \
      --batch_size="$batch" \
      --steps="$steps" \
      --save_freq="$save_freq" \
      --output_dir="outputs/train/${job}" \
      --job_name="$job" \
      --policy.device="$TRAIN_DEVICE" \
      $(push_args "$job") \
      --wandb.enable="$TRAIN_WANDB" \
      --wandb.disable_artifact=true; then
    echo "$(date '+%H:%M:%S') done  ${job}"
  else
    echo "$(date '+%H:%M:%S') FAILED ${job} (see logs/${job}.log)"
  fi
}

for item in $items; do
  run_job "$(job_name "$item" long)" "$item" "$TRAIN_BATCH_SIZE" "$LONG_STEPS" "$LONG_SAVE_FREQ"
done

if [ -n "$baseline" ]; then
  # The organizers' example: batch size 64, 20,000 steps, a checkpoint every 5,000.
  run_job "$(job_name "$baseline" guide)" "$baseline" "${GUIDE_BATCH_SIZE:-64}" "${GUIDE_STEPS:-20000}" "${GUIDE_SAVE_FREQ:-5000}"
fi

echo "$(date '+%H:%M:%S') queue finished"
