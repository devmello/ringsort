#!/usr/bin/env bash
# Download a trained model from Hugging Face to the PC.
#
#   scripts/get_model.sh <item> [label]
#
#   scripts/get_model.sh sensor              -> final model of kitcheck_act_sensor
#   scripts/get_model.sh sensor 020000       -> its checkpoint at step 20,000
#   scripts/get_model.sh sensor v2           -> final model of kitcheck_act_sensor_v2
#   scripts/get_model.sh sensor v2_010000    -> that run's checkpoint at step 10,000
#
# The model lands in models/<item>/<label>/pretrained_model.
# Intermediate checkpoints must be uploaded first with scripts/push_checkpoint.sh.

. "$(dirname "$0")/_lib.sh"

item="${1:-}"
label="${2:-final}"
[ -n "$item" ] || die "usage: scripts/get_model.sh <item> [label]     e.g. scripts/get_model.sh sensor 020000"
check_item "$item"
check_label "$label"

if [ -n "${MODEL_REPO:-}" ]; then
  repo="$MODEL_REPO"
else
  need_hf_user
  if [ "$label" = "final" ]; then repo="${HF_USER}/kitcheck_act_${item}"; else repo="${HF_USER}/kitcheck_act_${item}_${label}"; fi
fi

dest="models/${item}/${label}/pretrained_model"
mkdir -p "$dest"
echo "downloading ${repo} to ${dest}"
hfcli download "$repo" --repo-type model --local-dir "$dest"

[ -f "${dest}/model.safetensors" ] || die "download finished but ${dest}/model.safetensors is missing"
echo
echo "model ready: ${dest}"
