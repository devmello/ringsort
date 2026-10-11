# Data dump (branch `data-dump`)

Everything from the event PC that the `main` branch leaves out, saved before we lost access to the machine on 11 October 2026. `main` is the clean, documented project; this branch is the raw record.

## What's here

| Path | What |
|---|---|
| `data/eval/` | Every pick the cell recorded on the arm (222 runs, day 1 and day 2): LeRobot datasets with joint data and both cameras, plus each run's `.log` |
| `data/runs.jsonl` | Every attempt the runner and dashboard made: time, part, model, verdict |
| `data/trials.csv` | Day 1 model try-outs (`scripts/try_model.sh`) and their verdicts |
| `data/clips_archive/` | Clips taken out of `media/` (camera replay, early-checkpoint successes, an unfair red run) |
| `data/diagnostics/`, `data/*.png` | Camera checks, pick maps and overlays from day 1 and day 2 |
| `logs/` | Recording logs, camera alignment logs, dashboard logs |
| `DAY2-CHECKLIST.md` | The day 2 working checklist |
| `kitcheck_cloud.tar.gz` | The script bundle copied to the cloud GPU for training |
| `dump/deck/project/` | Source of the pitch slides (the "RingSort pitch" deck on claude.ai): one HTML file per slide plus `deck.json`. Images and videos in it point at the deck's own asset store; the same files are in `media/` and `examples/` |
| `dump/analysis/` | The scripts and data behind the charts in `media/charts/` (`collect.py`, `charts.py`, the palette check) |
| `dump/kitcheck_data/pick_purple_unfiltered/` | The purple dataset before 2 weak takes were removed (65 takes). Not on Hugging Face |

## Rejoining the split video

GitHub refuses files over 100 MB, so one video is in two parts:

```bash
cd dump/kitcheck_data/pick_purple_unfiltered/videos/observation.images.front/chunk-000
cat file-001.mp4.part00 file-001.mp4.part01 > file-001.mp4 && rm file-001.mp4.part0*
```

## Not here, because it's public on Hugging Face

Each model's `model.safetensors` is 207 MB and each dataset has videos over 100 MB, so they stay on Hugging Face:

| What | Where |
|---|---|
| Datasets | [purple](https://huggingface.co/datasets/varunsatish2017/kitcheck_pick_purple) (63 takes) · [teal](https://huggingface.co/datasets/varunsatish2017/kitcheck_pick_teal) (45) · [red](https://huggingface.co/datasets/varunsatish2017/kitcheck_pick_red) (47) |
| Models used in the demo | [teal 20k](https://huggingface.co/varunsatish2017/kitcheck_act_teal_020000) · [purple 50k](https://huggingface.co/varunsatish2017/kitcheck_act_purple_050000) · [red 40k](https://huggingface.co/varunsatish2017/kitcheck_act_red_040000) |
| Earlier checkpoints | purple [10k](https://huggingface.co/varunsatish2017/kitcheck_act_purple_010000), [20k](https://huggingface.co/varunsatish2017/kitcheck_act_purple_020000), [40k](https://huggingface.co/varunsatish2017/kitcheck_act_purple_040000) · red [10k](https://huggingface.co/varunsatish2017/kitcheck_act_red_010000), [20k](https://huggingface.co/varunsatish2017/kitcheck_act_red_020000) |
| Training logs | [Weights & Biases, devmello2/lerobot](https://wandb.ai/devmello2/lerobot) |

`scripts/get_model.sh <color> <step>` and `scripts/get_datasets.sh` download them back.

Also left out: a local copy of the red dataset under `scripts/datasets/` (the same as on Hugging Face), and rehearsal runs made without the arm (copies of other runs, not real picks).
