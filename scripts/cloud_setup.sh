#!/usr/bin/env bash
# Set up the cloud GPU machine to train with the same LeRobot as the PC.
# Run once, in a Jupyter terminal, from the folder that holds `scripts`:
#
#   bash scripts/cloud_setup.sh
#
# The PC runs LeRobot 0.6.2 from Seeed's fork at the commit below. A model
# trained with another version may not load on the PC, so the cloud machine
# uses the same commit, not the v0.4.1 the organizers' notebook checks out.
#
# LeRobot 0.6.2 needs Python 3.12+ and PyTorch 2.7 to 2.11. The script keeps the
# machine's own ROCm build of PyTorch if it qualifies. Otherwise it makes a
# Python 3.12 environment (kc-venv) with the ROCm build of PyTorch, never the
# default (NVIDIA) build from PyPI. That build is large (budget about 20 GB), so
# the environment goes on whichever disk has the most free space, and pip keeps
# no cache. The script says where; activate it in every new terminal.

set -euo pipefail

LEROBOT_REPO="${LEROBOT_REPO:-https://github.com/Seeed-Projects/lerobot.git}"
LEROBOT_COMMIT="${LEROBOT_COMMIT:-4aaff99be4a1d81568c08c8f0296b41b40c99ec4}"
# PyTorch for a fresh environment. 2.7.1 for ROCm 6.3 is the organizers' choice
# and is inside LeRobot 0.6.2's range.
TORCH_SPEC="${TORCH_SPEC:-torch==2.7.1 torchvision==0.22.1}"
TORCH_INDEX="${TORCH_INDEX:-https://download.pytorch.org/whl/rocm6.3}"
NEED_GB="${NEED_GB:-20}"

say() { echo; echo "== $*"; }
die() { echo "error: $*" >&2; exit 1; }
free_gb() { df -Pk "$1" 2>/dev/null | awk 'NR==2 {print int($4 / 1048576)}'; }

py_why() {  # empty if this python has 3.12+ and a ROCm torch in 2.7..2.11, else the reason
  "$1" - <<'PY' 2>/dev/null || echo "cannot run it"
import sys
if sys.version_info < (3, 12):
    print(f"Python {sys.version.split()[0]} (needs 3.12+)"); sys.exit()
try:
    import torch
except Exception:
    print("no PyTorch"); sys.exit()
major, minor = (int(x) for x in torch.__version__.split("+")[0].split(".")[:2])
if not (2, 7) <= (major, minor) < (2, 12):
    print(f"PyTorch {torch.__version__} (needs 2.7 to 2.11)")
elif not torch.version.hip:
    print(f"PyTorch {torch.__version__} is not a ROCm build")
PY
}
py_ok() { [ -z "$(py_why "$1")" ]; }

# The writable disk with the most free space: the home folder's, or a larger mount.
BASE="$HOME"
best="$(free_gb "$HOME")"
for mount in $(df -P 2>/dev/null | awk 'NR > 1 {print $6}'); do
  case "$mount" in /dev*|/proc*|/sys*|/run*|/boot*|/etc*|/usr*|/snap*) continue ;; esac
  [ -d "$mount" ] && [ -w "$mount" ] || continue
  gb="$(free_gb "$mount")"
  if [ "${gb:-0}" -gt "${best:-0}" ]; then best="$gb"; BASE="${mount%/}/kc"; fi
done
VENV="${VENV:-$BASE/kc-venv}"
LEROBOT_DIR="${LEROBOT_DIR:-$BASE/lerobot_kc}"

say "GPU"
command -v rocm-smi >/dev/null 2>&1 && rocm-smi --showproductname 2>/dev/null | grep -iE "card|series" | head -3 || true

say "Disk"
df -h "$HOME" "${BASE%/kc}" 2>/dev/null | awk '!seen[$0]++'
echo "installing into ${BASE} (${best} GB free)"

say "Python and PyTorch"
PY="$(command -v python3 || command -v python)"
if py_ok "$PY"; then
  echo "using $PY ($("$PY" -c 'import sys,torch; print(sys.version.split()[0], torch.__version__)'))"
else
  echo "$PY does not qualify: $(py_why "$PY")"
  for old in "$VENV" "$HOME/kc-venv"; do
    if [ -x "$old/bin/python" ] && py_ok "$old/bin/python"; then VENV="$old"; break; fi
    # A half-built environment from an attempt that ran out of space: ours, remove it.
    if [ -d "$old" ] && [ "$(basename "$old")" = "kc-venv" ]; then echo "removing the unfinished $old"; rm -rf "$old"; fi
  done
  if [ -x "$VENV/bin/python" ] && py_ok "$VENV/bin/python"; then
    echo "using the existing $VENV"
  else
    [ "${best:-0}" -ge "$NEED_GB" ] || die "the roomiest disk has ${best} GB free; PyTorch for ROCm needs about ${NEED_GB} GB. Free space (rm -rf ~/.cache/pip ~/.cache/uv) or ask the organizers for more disk."
    mkdir -p "$BASE/tmp"
    # Keep pip's and uv's temporary files and caches off a small home disk.
    export TMPDIR="$BASE/tmp" UV_CACHE_DIR="$BASE/uv-cache" PIP_NO_CACHE_DIR=1
    echo "making $VENV"
    "$PY" -m pip install -q --no-cache-dir --user uv 2>/dev/null || "$PY" -m pip install -q --no-cache-dir uv
    UV="$("$PY" -m uv --version >/dev/null 2>&1 && echo "$PY -m uv" || echo uv)"
    $UV venv --seed --python 3.12 "$VENV"
    echo "installing PyTorch for ROCm (a large download; several minutes)"
    # shellcheck disable=SC2086
    "$VENV/bin/python" -m pip install -q --no-cache-dir $TORCH_SPEC --index-url "$TORCH_INDEX"
    rm -rf "$BASE/uv-cache"
    py_ok "$VENV/bin/python" || die "PyTorch in $VENV is not a working ROCm build: $(py_why "$VENV/bin/python")"
  fi
  PY="$VENV/bin/python"
fi
# Run real work on the GPU: a PyTorch build without kernels for this GPU model
# still reports it as available, then crashes once training starts.
"$PY" - <<'PY' || die "PyTorch at $PY cannot run on this GPU (see above). Paste this output to whoever is helping."
import torch
assert torch.cuda.is_available(), "PyTorch cannot see the GPU"
p = torch.cuda.get_device_properties(0)
print(f"GPU: {p.name}, {getattr(p, 'gcnArchName', '?')}, {p.total_memory / 1e9:.0f} GB; PyTorch {torch.__version__}")
x = torch.randn(8, 3, 224, 224, device="cuda")
conv = torch.nn.Conv2d(3, 64, 7, stride=2).cuda()
y = torch.nn.functional.relu(conv(x)).mean()
y.backward()
a = torch.randn(1024, 1024, device="cuda")
torch.cuda.synchronize()
print(f"GPU test passed: convolution, backward pass and matmul ({(a @ a).abs().mean().item():.1f})")
PY

say "LeRobot at ${LEROBOT_COMMIT:0:8}"
if [ ! -d "$LEROBOT_DIR/.git" ]; then
  git clone -q "$LEROBOT_REPO" "$LEROBOT_DIR" || die "could not download LeRobot from GitHub (network or proxy). Try again in a minute."
fi
# Only go to GitHub when the commit is missing: the network here can refuse it.
if ! git -C "$LEROBOT_DIR" cat-file -e "${LEROBOT_COMMIT}^{commit}" 2>/dev/null; then
  git -C "$LEROBOT_DIR" fetch -q origin || die "could not update LeRobot from GitHub (network or proxy). Try again in a minute."
fi
git -C "$LEROBOT_DIR" checkout -q "$LEROBOT_COMMIT"
# Pin the PyTorch already installed so pip cannot swap it for the NVIDIA build.
constraints="$(mktemp)"
"$PY" -c 'import torch, torchvision; print(f"torch=={torch.__version__}\ntorchvision=={torchvision.__version__}")' > "$constraints"
"$PY" -m pip install -q --no-cache-dir -c "$constraints" -e "${LEROBOT_DIR}[training]"
rm -f "$constraints"

say "Check"
"$PY" - <<'PY'
import importlib.metadata as m, torch
print("lerobot", m.version("lerobot"), "| torch", torch.__version__, "| GPU", torch.cuda.is_available())
assert m.version("lerobot") == "0.6.2", "expected lerobot 0.6.2 to match the PC"
PY
BIN="$(dirname "$PY")"
[ -x "$BIN/lerobot-train" ] || die "lerobot-train was not installed in $BIN"

say "Video decoder"
# torchcodec needs FFmpeg's shared libraries and a build matching this PyTorch.
# When it cannot load, LeRobot falls back to PyAV (which ships its own FFmpeg and
# decodes these AV1 videos fine) but prints a long warning in every log. Remove it.
if "$PY" -c 'import torchcodec.decoders' >/dev/null 2>&1; then
  echo "torchcodec works"
else
  "$PY" -m pip uninstall -y -q torchcodec >/dev/null 2>&1 || true
  echo "torchcodec cannot load here (no FFmpeg libraries or a PyTorch mismatch); removed it, PyAV decodes instead"
fi

say "Reading a recorded dataset the way training will"
# Downloads the first item's demonstrations (public, no login needed) and decodes
# one video frame from each camera. Catches video-decoder problems before a run.
HF_USER_DEFAULT="$(bash -c '. "$1/settings.env" >/dev/null 2>&1; echo "${HF_USER:-}"' _ "$(dirname "$0")")"
check_repo="${CHECK_DATASET:-${HF_USER_DEFAULT}/kitcheck_pick_red}"
check_dir="$(mktemp -d)"
if "$PY" - "$check_repo" "$check_dir/ds" <<'PY'
import sys
from lerobot.datasets.lerobot_dataset import LeRobotDataset
try:
    ds = LeRobotDataset(sys.argv[1], root=sys.argv[2])
except Exception as e:  # not recorded yet, or no network
    print(f"skipped: could not load {sys.argv[1]} ({type(e).__name__})")
    sys.exit(0)
frame = ds[ds.num_frames - 1]
cams = [k for k in frame if k.startswith("observation.images.")]
print(f"{sys.argv[1]}: {ds.num_episodes} demonstrations; decoded {', '.join(c.split('.')[-1] for c in cams)} "
      f"with {getattr(ds, '_video_backend', 'the default decoder')}")
PY
then :; else
  rm -rf "$check_dir"
  die "the dataset could not be decoded; send the lines above to whoever is helping"
fi
rm -rf "$check_dir"

# Let the other scripts find this environment even when a terminal did not activate it.
if [ "$PY" = "$VENV/bin/python" ]; then echo "$VENV" > "$HOME/.kitcheck_venv"; else rm -f "$HOME/.kitcheck_venv"; fi

say "Done"
work_gb="$(free_gb "$PWD")"
if [ "${work_gb:-0}" -lt 30 ] && [ "$BASE" != "$HOME" ]; then
  echo "NOTE: training writes several GB of checkpoints per run into this folder, which has"
  echo "only ${work_gb} GB free. Move it to the bigger disk and work from there:"
  echo "  mv \"$PWD\" \"$BASE/\" && cd \"$BASE/$(basename "$PWD")\""
  echo
fi
if [ "$PY" = "$VENV/bin/python" ]; then
  echo "In every new terminal first:   source $VENV/bin/activate"
fi
cat <<EOF
Then log in once (tokens from huggingface.co/settings/tokens and wandb.ai/authorize):
  hf auth login
  wandb login
and start a run (HF_USER comes from scripts/settings.env):
  bash scripts/train.sh red
EOF
