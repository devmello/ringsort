#!/usr/bin/env bash
# Continue training from a model you already have, on the dataset as it is now.
# Use it after adding demonstrations. Runs on the cloud machine.
#
#   scripts/retrain.sh <item> <new version> [from version] [from step]
#
#   scripts/retrain.sh sensor v2             -> starts from kitcheck_act_sensor (latest checkpoint)
#   scripts/retrain.sh sensor v3 v2          -> starts from kitcheck_act_sensor_v2
#   scripts/retrain.sh sensor v2 "" 40000    -> starts from kitcheck_act_sensor at step 40,000
#
# It downloads a fresh copy of the dataset, so the new demonstrations are used,
# and starts from the trained weights, so it needs far fewer steps.

. "$(dirname "$0")/_lib.sh"

item="${1:-}"
version="${2:-}"
from_version="${3:-}"
from_step="${4:-}"
[ -n "$item" ] && [ -n "$version" ] || die "usage: scripts/retrain.sh <item> <new version> [from version] [from step]     e.g. scripts/retrain.sh sensor v2"
check_item "$item"
check_label "$version"
check_label "$from_version"
[ -n "${DATASET_ROOT:-}" ] || need_hf_user

from_job="$(job_name "$item" "$from_version")"
if [ -n "$from_step" ]; then
  from="outputs/train/${from_job}/checkpoints/$(six "$from_step")/pretrained_model"
else
  from="outputs/train/${from_job}/checkpoints/last/pretrained_model"
fi
[ -d "$from" ] || die "no model at ${from}. Checkpoints present: $(ls "outputs/train/${from_job}/checkpoints" 2>/dev/null | tr '\n' ' ')"

job="$(job_name "$item" "$version")"
log="logs/${job}.log"
[ "$job" != "$from_job" ] || die "the new version must differ from the one you start from"
check_not_running "$job"
[ ! -e "outputs/train/${job}" ] || die "outputs/train/${job} already exists. Choose another version label."

save_freq="$TRAIN_SAVE_FREQ"
[ "$save_freq" -le "$RETRAIN_STEPS" ] || save_freq="$RETRAIN_STEPS"

echo "continuing from ${from}"
# shellcheck disable=SC2046
start_run "$job" "$log" \
  --dataset.repo_id="$(dataset_repo "$item")" \
  --dataset.root="$(dataset_root "$job")" \
  --policy.path="$from" \
  --policy.device="$TRAIN_DEVICE" \
  --batch_size="$TRAIN_BATCH_SIZE" \
  --steps="$RETRAIN_STEPS" \
  --save_freq="$save_freq" \
  --output_dir="outputs/train/${job}" \
  --job_name="$job" \
  $(push_args "$job") \
  --wandb.enable="$TRAIN_WANDB" \
  --wandb.disable_artifact=true

show_episode_count "$log" "$job"
