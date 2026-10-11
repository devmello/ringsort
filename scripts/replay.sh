#!/usr/bin/env bash
# Replay one recorded demonstration on the follower. Runs on the PC.
#
#   scripts/replay.sh <item> [episode]
#
#   scripts/replay.sh red        -> demonstration 0 of the red dataset
#   scripts/replay.sh red 12     -> demonstration 12
#
# Put the ring exactly where it was in that demonstration and the arm in the
# rest pose first. Use it to check a new dataset (the arm should repeat your
# motion and pick the ring), and as the demo fallback when a model is unreliable.

. "$(dirname "$0")/_lib.sh"

item="${1:-}"
episode="${2:-0}"
[ -n "$item" ] || die "usage: scripts/replay.sh <item> [episode]     e.g. scripts/replay.sh red 0"
check_item "$item"
case "$episode" in *[!0-9]*) die "episode must be a whole number (got '$episode')" ;; esac

root="$(demo_root "$item")"
have="$(episode_count "$root")"
[ "$have" -gt 0 ] || die "no demonstrations in ${root}. Record some first: bash scripts/record.sh ${item} 5"
[ "$episode" -lt "$have" ] || die "${root} has demonstrations 0 to $((have - 1))"

# shellcheck disable=SC2086
lerobot-replay \
  --robot.type=so101_follower \
  --robot.port="$FOLLOWER_PORT" \
  --robot.id="$FOLLOWER_ID" \
  $ROBOT_EXTRA_ARGS \
  --dataset.repo_id="${HF_USER:-local}/kitcheck_pick_${item}" \
  --dataset.root="$root" \
  --dataset.episode="$episode" \
  --play_sounds=false
