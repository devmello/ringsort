"""Collect per-run and per-demonstration numbers for the deck's charts."""
import csv, json, sys
from pathlib import Path
import av, cv2, numpy as np
sys.path.insert(0, "/home/amd-genai1/kitcheck")
from kitcheck import align, grasp, vision

ROOT = Path("/home/amd-genai1/kitcheck"); DATA = Path.home() / "kitcheck_data"
OUT = Path(sys.argv[1])
conf = vision.settings(); RINGS = np.float32([[340, 330]])
CAM_REF = {"teal": ("teal", 20), "purple": ("purple", 30), "red": ("red", 0)}
cam_ref = {item: align.first_frame(DATA / f"pick_{c}", ep) for item, (c, ep) in CAM_REF.items()}
EXCLUDE = {"red_010000_20261010_192145"}  # not a fair run (team's call)

def frame_at(path, t):
    with av.open(str(path)) as c:
        s = c.streams.video[0]; c.seek(int(max(t - 1, 0) / s.time_base), stream=s)
        for f in c.decode(s):
            if f.time >= t: return cv2.resize(f.to_ndarray(format="bgr24"), (640, 480))
    return None

def close_time(ep):
    h = grasp.find_hold(ep)
    if h is not None: return h.start / ep.fps
    g = ep.action[:, ep.gripper]; opened = g > g.min() + 15
    if not opened.any(): return None
    a = int(opened.argmax()); closed = g[a:] < g.min() + 5
    return (a + int(closed.argmax())) / ep.fps if closed.any() else None

def ring_in_wrist(img, item):
    hsv = cv2.cvtColor(cv2.GaussianBlur(img, (5, 5), 0), cv2.COLOR_BGR2HSV)
    m = np.zeros(hsv.shape[:2], np.uint8)
    # The gripper camera renders teal greener than the stand camera does.
    ranges = [[[50, 55, 80], [85, 255, 255]]] if item == "teal" else conf["items"][item]["hsv"]
    for lo, hi in ranges: m |= cv2.inRange(hsv, np.array(lo), np.array(hi))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    n, lab, st, cen = cv2.connectedComponentsWithStats(m)
    if n < 2: return None
    i = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    return tuple(map(float, cen[i])) if st[i, cv2.CC_STAT_AREA] >= 300 else None

def camera_offset(img, item):
    w, cc = align.measure(cam_ref[item], img, None)
    if cc < 0.5: return None, None
    return float(np.linalg.norm(align.apply(w, RINGS) - RINGS)), float(np.degrees(np.arctan2(w[1, 0], w[0, 0])))

# --- demonstrations: grip gap, length, wrist ring position at the grasp
demos = {}
for item in ("purple", "teal", "red"):
    root = DATA / f"pick_{item}"; eps = grasp.load_episodes(root)
    import pandas as pd, glob
    meta = pd.concat(pd.read_parquet(f) for f in sorted(glob.glob(str(root / "meta/episodes/chunk-*/file-*.parquet"))))
    rows = []
    for ep in eps:
        h = grasp.find_hold(ep); r = meta[meta.episode_index == ep.index].iloc[0]
        t0 = float(r["videos/observation.images.wrist/from_timestamp"])
        path = root / f"videos/observation.images.wrist/chunk-{int(r['videos/observation.images.wrist/chunk_index']):03d}/file-{int(r['videos/observation.images.wrist/file_index']):03d}.mp4"
        pos = ring_in_wrist(frame_at(path, t0 + h.start / ep.fps), item) if h else None
        rows.append({"ep": ep.index, "len_s": len(ep.action) / ep.fps, "gap": h.gap if h else None,
                     "hold_s": h.seconds if h else None, "wrist": pos})
    demos[item] = rows
    print(item, "demos", len(rows), "wrist found", sum(r["wrist"] is not None for r in rows), flush=True)

# --- robot runs: day 1 trials.csv (default runs only) + day 2 runs.jsonl (ACT, first attempts)
runs = []
for t, item, label, out, *_ in csv.reader(open(ROOT / "data/trials.csv")):
    if t == "time" or not label.isdigit(): continue
    runs.append({"folder": f"{item}_{label}_{t}", "item": item, "step": int(label), "outcome": out, "day": 1})
for line in open(ROOT / "data/runs.jsonl"):
    r = json.loads(line)
    if r["attempt"] != 1 or "replay" in r["model"] or r["outcome"] == "error": continue
    runs.append({"folder": Path(r["run"]).name, "item": r["item"], "step": int(r["model"].split("/")[-2]),
                 "outcome": r["outcome"], "day": 2})
runs = [r for r in runs if r["folder"] not in EXCLUDE]
for r in runs:
    f = ROOT / "data/eval" / r["folder"]
    r["recorded"] = (f / "videos").exists()
    if not r["recorded"]: continue
    ep = grasp.load_episodes(f)[-1]; tc = close_time(ep)
    front0 = frame_at(f / "videos/observation.images.front/chunk-000/file-000.mp4", 0.05)
    r["cam_px"], r["cam_rot"] = camera_offset(front0, r["item"]) if front0 is not None else (None, None)
    r["wrist"] = ring_in_wrist(frame_at(f / "videos/observation.images.wrist/chunk-000/file-000.mp4", tc), r["item"]) if tc else None
print("runs", len(runs), "recorded", sum(r["recorded"] for r in runs), flush=True)
json.dump({"demos": demos, "runs": runs}, open(OUT, "w"), indent=1)
