#!/usr/bin/env bash
# Start a training run for one item, from scratch, with the fast recipe.
# Runs on the cloud machine.
#
#   scripts/train.sh <item> [version]
#
#   scripts/train.sh sensor          -> job kitcheck_act_sensor
#   scripts/train.sh sensor v2       -> job kitcheck_act_sensor_v2
#
# The recipe (batch size, steps, checkpoint spacing) comes from
# scripts/settings.env. docs/history/04-training.md explains it.

. "$(dirname "$0")/_lib.sh"

item="${1:-}"
version="${2:-}"
[ -n "$item" ] || die "usage: scripts/train.sh <item> [version]     e.g. scripts/train.sh sensor"
check_item "$item"
check_label "$version"
[ -n "${DATASET_ROOT:-}" ] || need_hf_user

job="$(job_name "$item" "$version")"
log="logs/${job}.log"
check_not_running "$job"
[ ! -e "outputs/train/${job}" ] || die "outputs/train/${job} already exists. Add a version label (scripts/train.sh ${item} v2), or use scripts/resume.sh to run it for longer."

# shellcheck disable=SC2046
start_run "$job" "$log" \
  --dataset.repo_id="$(dataset_repo "$item")" \
  --dataset.root="$(dataset_root "$job")" \
  --policy.type=act \
  --batch_size="$TRAIN_BATCH_SIZE" \
  --steps="$TRAIN_STEPS" \
  --save_freq="$TRAIN_SAVE_FREQ" \
  --output_dir="outputs/train/${job}" \
  --job_name="$job" \
  --policy.device="$TRAIN_DEVICE" \
  $(push_args "$job") \
  --wandb.enable="$TRAIN_WANDB" \
  --wandb.disable_artifact=true

show_episode_count "$log" "$job"
