#!/usr/bin/env bash
# Run one pick with a trained model, then say what the gripper felt and keep score.
# Runs on the PC, from the project folder.
#
#   scripts/try_model.sh <item> [label] [seconds]
#
#   scripts/try_model.sh red                 -> models/red/final, 15-second time limit
#   scripts/try_model.sh red 020000          -> the checkpoint from step 20,000
#   scripts/try_model.sh red v2 12           -> the v2 model with a 12-second time limit
#
# Before each run: ring on its spot, arm in the rest pose.
# Each run is recorded under data/eval/ and one line is added to data/trials.csv.
# If data/grasp_<item>.json exists (made by: python -m kitcheck.grasp learn ...),
# the verdict also checks that the arm let go at the tray.
# If voice is on in config.json and its clips exist, the verdict is spoken too.
#
# Without a robot: KITCHECK_FAKE_RUN=<a recorded LeRobot folder> uses that
# recording in place of a real run, to try the scoring.

. "$(dirname "$0")/_lib.sh"

item="${1:-}"
label="${2:-final}"
seconds="${3:-${RUN_TIME_S:-15}}"
[ -n "$item" ] || die "usage: scripts/try_model.sh <item> [label] [seconds]     e.g. scripts/try_model.sh sensor 020000"
check_item "$item"
check_label "$label"

model="models/${item}/${label}/pretrained_model"
# Scores are kept per model and per way of running it (POLICY_ARGS in settings.env).
mode="default"
case "$POLICY_ARGS" in
  *temporal_ensemble*) mode="ensemble" ;;
  *n_action_steps=*) mode="steps$(echo "$POLICY_ARGS" | sed -n 's/.*n_action_steps=\([0-9]*\).*/\1/p')" ;;
esac
# A slower playback rate (POLICY_ARGS="--fps=15 --dataset.fps=15") is labelled too.
run_fps="$(echo "$POLICY_ARGS" | sed -n 's/.*--fps=\([0-9.]*\).*/\1/p')"
if [ -n "$run_fps" ]; then [ "$mode" = "default" ] && mode="fps${run_fps}" || mode="${mode}_fps${run_fps}"; fi
# An offset is part of the label too: "pan-4" for ACTION_OFFSET="shoulder_pan.pos=-4".
if [ -n "$ACTION_OFFSET" ]; then
  offset_tag="$(echo "$ACTION_OFFSET" | sed 's/\.pos//g; s/shoulder_//g; s/[^A-Za-z0-9.=+-]//g; s/=//g')"
  [ "$mode" = "default" ] && mode="$offset_tag" || mode="${mode}_${offset_tag}"
fi
score_label="$label"
[ "$mode" = "default" ] || score_label="${label}_${mode}"
stamp="$(date +%Y%m%d_%H%M%S)"
run="data/eval/${item}_${label}_${stamp}"
mkdir -p data/eval

if [ -n "${KITCHECK_FAKE_RUN:-}" ]; then
  [ -d "$KITCHECK_FAKE_RUN" ] || die "KITCHECK_FAKE_RUN is not a folder: $KITCHECK_FAKE_RUN"
  cp -r "$KITCHECK_FAKE_RUN" "$run"
  echo "(fake run: using the recording in $KITCHECK_FAKE_RUN)"
else
  [ -d "$model" ] || die "no model at ${model}. Download it first: scripts/get_model.sh ${item} ${label}"
  echo "running ${model} for ${seconds} s ..."
  # LeRobot 0.6 runs trained models with lerobot-rollout; lerobot-record refuses
  # a policy. The episodic strategy records the run, which the grasp check reads.
  # One missed or garbled motor reply while connecting (the motor check, or
  # switching torque off) aborts the run before the arm moves. Try again (up to 3
  # times) when that is the reason and nothing was recorded, instead of making
  # you start over. A failure after recording began is not retried.
  for try in 1 2 3; do
    rm -rf "$run"
    # kitcheck.rollout is lerobot-rollout plus the optional ACTION_OFFSET.
    # shellcheck disable=SC2086
    if PYTHONPATH="${SCRIPTS_DIR}/..${PYTHONPATH:+:$PYTHONPATH}" python -m kitcheck.rollout \
        --strategy.type=episodic \
        --robot.type=so101_follower \
        --robot.port="$FOLLOWER_PORT" \
        --robot.id="$FOLLOWER_ID" \
        --robot.cameras="$CAMERAS" \
        $ROBOT_EXTRA_ARGS \
        --dataset.single_task="$(task_text "$item")" \
        --dataset.repo_id="local/rollout_kitcheck_${item}_${stamp}" \
        --dataset.root="$run" \
        --dataset.episode_time_s="$seconds" \
        --dataset.num_episodes=1 \
        --dataset.push_to_hub=false \
        --policy.path="$model" \
        $POLICY_ARGS \
        --play_sounds=false > "${run}.log" 2>&1; then
      break
    fi
    # Retry only if the arm never moved: camera frames are written while it moves, the data at the end.
    if [ "$try" -lt 3 ] && [ ! -d "$run/data" ] && [ -z "$(find "$run/images" -name '*.png' -print -quit 2>/dev/null)" ] \
        && grep -qE "motor check failed|There is no status packet|Incorrect status packet|Failed to (write|read|sync_read|sync_write)" "${run}.log"; then
      echo "a motor reply was lost while connecting (the arm did not move); trying again (try $((try + 1)) of 3)"
      sleep 2
      continue
    fi
    echo "The run failed. Last lines of ${run}.log:" >&2
    grep -v '^[[:space:]]*$' "${run}.log" | tail -n 4 >&2
    exit 1
  done
fi

ref="data/grasp_${item}.json"
ref_args=""
[ -f "$ref" ] && ref_args="--ref $ref"

# shellcheck disable=SC2086
verdict="$(PYTHONPATH="${SCRIPTS_DIR}/..${PYTHONPATH:+:$PYTHONPATH}" python -m kitcheck.grasp check "$run" $ref_args --json || true)"
[ -n "$verdict" ] || die "could not read the recording in ${run}"

[ "$mode" = "default" ] || echo "run mode: ${mode} (${POLICY_ARGS}${POLICY_ARGS:+ }${ACTION_OFFSET:+offset $ACTION_OFFSET})"
PYTHONPATH="${SCRIPTS_DIR}/..${PYTHONPATH:+:$PYTHONPATH}" python - "$verdict" "$item" "$score_label" "$stamp" <<'PY'
import csv, json, os, sys

verdict = json.loads(sys.argv[1])
item, label, stamp = sys.argv[2:5]
path = "data/trials.csv"
new = not os.path.exists(path)
with open(path, "a", newline="") as handle:
    writer = csv.writer(handle)
    if new:
        writer.writerow(["time", "item", "model", "outcome", "hold_s", "gap", "reason"])
    writer.writerow([stamp, item, label, verdict["outcome"], f"{verdict['hold_s']:.1f}", f"{verdict['gap']:.1f}", verdict["reason"]])

with open(path, newline="") as handle:
    rows = [row for row in csv.DictReader(handle) if row["item"] == item and row["model"] == label]
good = sum(row["outcome"] in ("placed", "held") for row in rows)
print()
print(f"{verdict['outcome'].upper()}: {verdict['reason']} (held {verdict['hold_s']:.1f} s)")
print(f"score for {item} / {label}: {good} of {len(rows)} runs counted as good by the gripper")
print("The gripper cannot see where the ring landed. Count a run as good yourself only if it is in its cup.")

# Optional spoken verdict (docs/history/10-voice.md). Silent unless voice is on in config.json and the clips exist.
try:
    from kitcheck.voice import Voice, key_for_verdict

    Voice.from_config().say(key_for_verdict(verdict["outcome"], verdict["reason"]), item=item, wait=True)
except Exception:
    pass
PY
