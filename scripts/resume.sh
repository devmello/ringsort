#!/usr/bin/env bash
# Run an existing training run for longer, on the same data.
# Runs on the cloud machine.
#
#   scripts/resume.sh <item> <new total steps> [version]
#
#   scripts/resume.sh sensor 100000        -> kitcheck_act_sensor continues to 100,000 steps
#   scripts/resume.sh sensor 60000 v2      -> kitcheck_act_sensor_v2 continues to 60,000 steps
#
# The number is the new total, not the number of steps to add.

. "$(dirname "$0")/_lib.sh"

item="${1:-}"
total="${2:-}"
version="${3:-}"
[ -n "$item" ] && [ -n "$total" ] || die "usage: scripts/resume.sh <item> <new total steps> [version]     e.g. scripts/resume.sh sensor 100000"
check_item "$item"
check_label "$version"
case "$total" in *[!0-9]*) die "steps must be a whole number (got '$total')" ;; esac

job="$(job_name "$item" "$version")"
cfg="outputs/train/${job}/checkpoints/last/pretrained_model/train_config.json"
[ -f "$cfg" ] || die "no checkpoint to resume at ${cfg}"
check_not_running "$job"

log="logs/${job}.to_${total}.log"
start_run "$job" "$log" \
  --resume=true \
  --config_path="$cfg" \
  --steps="$total"
