#!/usr/bin/env bash
# Upload one checkpoint of a run to Hugging Face under its own name, so the PC
# can download and test it before the run finishes. Runs on the cloud machine.
#
#   scripts/push_checkpoint.sh <item> <step> [version]
#
#   scripts/push_checkpoint.sh sensor 20000       -> <you>/kitcheck_act_sensor_020000
#   scripts/push_checkpoint.sh sensor 10000 v2    -> <you>/kitcheck_act_sensor_v2_010000
#
# A finished run uploads its final model by itself; this is for the ones in between
# and for runs you stopped early.

. "$(dirname "$0")/_lib.sh"

item="${1:-}"
step="${2:-}"
version="${3:-}"
[ -n "$item" ] && [ -n "$step" ] || die "usage: scripts/push_checkpoint.sh <item> <step> [version]     e.g. scripts/push_checkpoint.sh sensor 20000"
check_item "$item"
check_label "$version"
case "$step" in *[!0-9]*) die "step must be a whole number (got '$step')" ;; esac
need_hf_user

job="$(job_name "$item" "$version")"
step6="$(six "$step")"
dir="outputs/train/${job}/checkpoints/${step6}/pretrained_model"
[ -d "$dir" ] || die "no checkpoint at ${dir}. Checkpoints present: $(ls "outputs/train/${job}/checkpoints" 2>/dev/null | tr '\n' ' ')"

repo="${HF_USER}/${job}_${step6}"
echo "uploading ${dir} to ${repo}"
hfcli upload "$repo" "$dir"

if [ -n "$version" ]; then label="${version}_${step6}"; else label="${step6}"; fi
echo
echo "on the PC:  scripts/get_model.sh ${item} ${label}"
