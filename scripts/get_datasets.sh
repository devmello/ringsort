#!/usr/bin/env bash
# Download the demonstration datasets from Hugging Face. Runs on the PC.
#
#   scripts/get_datasets.sh                 -> purple, teal and red into $DATA_DIR/pick_<color>
#   scripts/get_datasets.sh teal            -> just teal
#
# Camera-guided replay plays these demonstrations back, so a fresh clone needs them
# before it can pick that way. A dataset already on disk is left alone (it may hold
# takes not uploaded yet); delete its folder first to download it again.

. "$(dirname "$0")/_lib.sh"
need_hf_user

items=("$@")
[ "${#items[@]}" -gt 0 ] || items=(purple teal red)
for item in "${items[@]}"; do
  check_item "$item"
  root="${DATA_DIR}/pick_${item}"
  if [ -f "${root}/meta/info.json" ]; then
    echo "${item}: already at ${root}; left alone"
    continue
  fi
  echo "${item}: downloading ${HF_USER}/kitcheck_pick_${item} into ${root}"
  hf download --repo-type dataset "${HF_USER}/kitcheck_pick_${item}" --local-dir "${root}"
done
