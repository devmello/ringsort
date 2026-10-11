# Examples

## A whole work order

[`full_run_20261011_1108.mp4`](full_run_20261011_1108.mp4): one dashboard order of all three colors, one attempt each, on day 2 at 11:08. Red (ACT, step 40,000) and purple (ACT, step 50,000) were placed; teal (ACT, step 20,000) missed, and the gripper check caught it. Made with `python -m kitcheck.clips reel <run folders> --out <video>`.

## Example runs

Two real picks by the purple ACT model (step 10,000) on day 1, recorded by the cell exactly as it records every pick (LeRobot dataset format: joint data in `data/`, both cameras in `videos/`).

| Folder | What happened | Gripper check |
|---|---|---|
| `runs/purple_placed` | Picked the ring and dropped it in the purple bin (day 1, 21:02) | placed |
| `runs/purple_missed` | Closed on nothing (day 1, 21:01) | missed |

Use them to try RingSort without an arm. Every pick copies the run instead of moving the arm:

```bash
KITCHECK_FAKE_RUN=examples/runs/purple_placed scripts/dashboard.sh
```

```bash
python -m kitcheck.grasp check examples/runs/purple_missed --ref data/grasp_purple.json
```
