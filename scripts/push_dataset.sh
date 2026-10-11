#!/usr/bin/env bash
# Upload an item's demonstrations to Hugging Face so the Hub copy is exactly the
# one on this PC, then check that it arrived. Runs on the PC.
#
#   scripts/push_dataset.sh <item>
#
# scripts/record.sh runs this when a session ends. Run it by hand to retry a
# failed upload. Unlike LeRobot's own upload, it deletes files on the Hub that
# are no longer on this PC (left by an earlier, deleted dataset), which training
# would otherwise read as extra demonstrations.

. "$(dirname "$0")/_lib.sh"

item="${1:-}"
[ -n "$item" ] || die "usage: scripts/push_dataset.sh <item>     e.g. scripts/push_dataset.sh red"
check_item "$item"
need_hf_user

root="$(demo_root "$item")"
[ "$(episode_count "$root")" -gt 0 ] || die "no demonstrations in ${root}"
repo="${HF_USER}/kitcheck_pick_${item}"

python - "$root" "$repo" <<'PY'
import json
import sys
from pathlib import Path

import pandas as pd
from huggingface_hub import HfApi, hf_hub_download

from lerobot.datasets.dataset_metadata import CODEBASE_VERSION, LeRobotDatasetMetadata
from lerobot.datasets.utils import create_lerobot_dataset_card

root, repo = Path(sys.argv[1]), sys.argv[2]
api = HfApi()
info = json.loads((root / "meta" / "info.json").read_text())
tasks = sorted(pd.read_parquet(root / "meta" / "tasks.parquet").index)
print(f"uploading {info['total_episodes']} demonstrations from {root} to {repo} ...", flush=True)

api.create_repo(repo, repo_type="dataset", exist_ok=True)
api.upload_folder(
    repo_id=repo,
    repo_type="dataset",
    folder_path=root,
    ignore_patterns=["images/"],
    # Mirror: remove dataset files on the Hub that this folder no longer has.
    delete_patterns=["data/**", "meta/**", "videos/**"],
    commit_message=f"{info['total_episodes']} demonstrations",
)
meta = LeRobotDatasetMetadata(repo, root=root)
create_lerobot_dataset_card(dataset_info=meta.info, repo_id=repo).push_to_hub(repo_id=repo, repo_type="dataset")
try:
    api.delete_tag(repo, tag=CODEBASE_VERSION, repo_type="dataset")
except Exception:
    pass
api.create_tag(repo, tag=CODEBASE_VERSION, repo_type="dataset")

# Check what the Hub now serves.
hub_info = json.loads(Path(hf_hub_download(repo, "meta/info.json", repo_type="dataset", force_download=True)).read_text())
hub_tasks = sorted(pd.read_parquet(hf_hub_download(repo, "meta/tasks.parquet", repo_type="dataset", force_download=True)).index)
local_files = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and "images" not in p.parts}
hub_files = {f for f in api.list_repo_files(repo, repo_type="dataset") if f.split("/")[0] in ("data", "meta", "videos")}
problems = []
if hub_info["total_episodes"] != info["total_episodes"]:
    problems.append(f"the Hub has {hub_info['total_episodes']} demonstrations, this PC {info['total_episodes']}")
if hub_tasks != tasks:
    problems.append(f"task text differs: Hub {hub_tasks}, PC {tasks}")
if hub_files != local_files:
    problems.append(f"files differ: only on the Hub {sorted(hub_files - local_files)}, only here {sorted(local_files - hub_files)}")
if problems:
    sys.exit("upload check FAILED: " + "; ".join(problems))
print(f"on the Hub: {repo}, {hub_info['total_episodes']} demonstrations, task '{tasks[0]}' (matches this PC)")
PY
