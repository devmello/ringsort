#!/usr/bin/env bash
# Shared helpers for the KitCheck scripts. Loaded by the other scripts; not run directly.
#
# Run the scripts from one working folder every time (on the cloud machine, the
# folder you start training from). They create these sub-folders there:
#   outputs/train/<job>/   checkpoints written by lerobot-train
#   datasets/<job>/        a fresh copy of the dataset for that run
#   logs/<job>.log         the training log
#   models/<item>/<label>/ models downloaded to the PC

set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
. "$SCRIPTS_DIR/settings.env"

die() { echo "error: $*" >&2; exit 1; }

# On the cloud machine, cloud_setup.sh may install into its own environment and
# records where in ~/.kitcheck_venv. Use it even if this terminal did not
# activate it, so lerobot-train is always the version the PC runs.
if [ -f "$HOME/.kitcheck_venv" ]; then
  _venv="$(cat "$HOME/.kitcheck_venv")"
  if [ -x "$_venv/bin/python" ] && [ "${VIRTUAL_ENV:-}" != "$_venv" ]; then
    # shellcheck disable=SC1091
    . "$_venv/bin/activate"
  fi
fi

# lerobot-train must be the LeRobot the PC runs (0.6.2), or models may not load there.
need_lerobot_train() {
  command -v lerobot-train >/dev/null 2>&1 || die "lerobot-train not found. Run: bash scripts/cloud_setup.sh"
  local bin version
  bin="$(command -v lerobot-train)"
  version="$("$(dirname "$bin")/python" -c 'import importlib.metadata as m; print(m.version("lerobot"))' 2>/dev/null || echo unknown)"
  [ "$version" = "${LEROBOT_VERSION:-0.6.2}" ] || die "lerobot-train at ${bin} is LeRobot ${version}, not ${LEROBOT_VERSION:-0.6.2}. Run: bash scripts/cloud_setup.sh"
}

# Item names become part of file and repository names.
check_item() {
  case "${1:-}" in
    ''|*[!a-z0-9_]*) die "item must use lowercase letters, digits or _ (got '${1:-}')" ;;
  esac
}

check_label() {
  case "${1:-}" in
    *[!A-Za-z0-9_]*) die "version must use letters, digits or _ (got '${1:-}')" ;;
  esac
}

need_hf_user() {
  [ -n "${HF_USER:-}" ] || die "HF_USER is not set. Run: export HF_USER=<your Hugging Face username>"
}

# kitcheck_act_<item> or kitcheck_act_<item>_<version>
job_name() {
  if [ -n "${2:-}" ]; then echo "kitcheck_act_${1}_${2}"; else echo "kitcheck_act_${1}"; fi
}

# Dataset on Hugging Face for an item. DATASET_REPO overrides it for every item.
dataset_repo() { echo "${DATASET_REPO:-${HF_USER}/kitcheck_pick_${1}}"; }

# Each run downloads its own copy of the dataset into datasets/<job>.
# LeRobot reuses a local copy without checking Hugging Face for new
# demonstrations, so a fresh folder per run is what guarantees fresh data.
# DATASET_ROOT points at an existing local dataset instead (no download).
dataset_root() { echo "${DATASET_ROOT:-datasets/${1}}"; }

# Demonstrations for an item, on the PC.
demo_root() { echo "${DATA_DIR}/pick_${1}"; }

# The item's task text from config.json, the same in recording and at run time.
task_text() {
  local cfg="${SCRIPTS_DIR}/../config.json"
  if [ -f "$cfg" ]; then
    python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["items"][sys.argv[2]]["task"])' "$cfg" "$1" 2>/dev/null && return 0
  fi
  echo "Pick the ${1} ring and drop it in the ${1} cup"
}

# Number of demonstrations in a dataset folder (0 if there is none).
episode_count() {
  local info="${1}/meta/info.json"
  [ -f "$info" ] || { echo 0; return 0; }
  python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("total_episodes", 0))' "$info"
}

# 20000 -> 020000 (checkpoint folder names have six digits)
six() { printf '%06d' "$((10#${1}))"; }

# Hugging Face command-line tool: newer installs call it hf.
hfcli() {
  if command -v hf >/dev/null 2>&1; then hf "$@"; else huggingface-cli "$@"; fi
}

# Arguments that decide where the finished model is uploaded.
push_args() {
  if [ "${TRAIN_PUSH}" = "true" ]; then
    echo "--policy.push_to_hub=true --policy.repo_id=${HF_USER}/${1}"
  else
    echo "--policy.push_to_hub=false"
  fi
}

# Refuse to start a second run with the same name while the first is alive.
check_not_running() {
  local pidfile="logs/${1}.pid"
  if [ -f "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    die "${1} is still running (pid $(cat "$pidfile")). Stop it first: kill $(cat "$pidfile")"
  fi
}

# start_run <job> <log file> <lerobot-train arguments...>
# Runs in the background and survives a closed browser tab, unless
# RUN_FOREGROUND=1 (used by overnight.sh to run jobs one after another).
start_run() {
  local job="$1" log="$2"
  shift 2
  mkdir -p logs
  # shellcheck disable=SC2086
  set -- "$@" ${TRAIN_EXTRA_ARGS:-}
  need_lerobot_train
  echo "lerobot-train $*"
  echo "  (using $(command -v lerobot-train))"
  if [ "${RUN_FOREGROUND:-0}" = "1" ]; then
    lerobot-train "$@" > "$log" 2>&1
  else
    nohup lerobot-train "$@" > "$log" 2>&1 &
    echo "$!" > "logs/${job}.pid"
    echo
    echo "started ${job} (pid $!)"
    echo "  follow it:  tail -f ${log}"
    echo "  summary:    python ${SCRIPTS_DIR}/train_report.py ${log}"
    echo "  stop it:    kill $!"
  fi
}

# After a background start, wait until the run reports its dataset, and say
# so plainly if it died while starting (not logged in, wrong name, ...).
show_episode_count() {
  local log="$1" job="${2:-}" line="" pid="" i
  [ "${RUN_FOREGROUND:-0}" = "1" ] && return 0
  [ -n "$job" ] && [ -f "logs/${job}.pid" ] && pid="$(cat "logs/${job}.pid")"
  for i in $(seq 1 90); do
    line="$(grep -m1 -o 'dataset.num_episodes=[0-9]*' "$log" 2>/dev/null || true)"
    [ -n "$line" ] && break
    if [ -n "$pid" ] && ! kill -0 "$pid" 2>/dev/null; then
      echo
      echo "The run stopped while starting. Last lines of ${log}:" >&2
      grep -v '^[[:space:]]*$' "$log" | tail -n 25 >&2
      exit 1
    fi
    sleep 2
  done
  if [ -n "$line" ]; then
    echo "  loaded:     ${line#dataset.num_episodes=} demonstrations (check this matches what you recorded)"
  else
    echo "  the run has not reported its dataset yet; look at ${log}"
  fi
}
