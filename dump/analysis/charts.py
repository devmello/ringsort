import json, sys
from collections import defaultdict
from pathlib import Path
import numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
A = Path(sys.argv[1])
for f in ("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf", "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"): fm.fontManager.addfont(f)
plt.rcParams.update({"font.family": "Noto Sans", "font.size": 11, "axes.edgecolor": "#B9B4A8", "axes.labelcolor": "#4F5966",
                     "xtick.color": "#4F5966", "ytick.color": "#4F5966", "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.color": "#E2DED4", "grid.linewidth": 0.6, "axes.axisbelow": True})
BG, INK, MUTED = "#F3F1EA", "#1A1F26", "#4F5966"
COL = {"purple": "#6B46C1", "teal": "#008B80", "red": "#B83236"}
NAME = {"purple": "Purple", "teal": "Teal", "red": "Red"}
d = json.load(open(A / "data2.json")); ref = {k: np.array(v) for k, v in json.load(open(A / "ref.json"))["ref"].items()}
loss = json.load(open(A / "loss.json"))
by = defaultdict(list)
for r in d["runs"]:
    if r["recorded"]:
        r["err"] = float(np.hypot(*(np.array(r["wrist"]) - ref[r["item"]]))) if r["wrist"] else None
        by[(r["item"], r["step"])].append(r)
placed = lambda rs: sum(r["outcome"] in ("placed", "held") for r in rs)

def fig(w=8, h=3.6):
    f, ax = plt.subplots(figsize=(w, h), dpi=220); f.patch.set_facecolor(BG); ax.set_facecolor(BG); return f, ax

# 1. loss curves (log scale), direct-labeled, with the robot-tested checkpoints marked
f, ax = fig()
for item in ("purple", "red", "teal"):
    s, l = np.array(loss[item]["step"]), np.array(loss[item]["loss"])
    k = 5; ls = np.convolve(l, np.ones(k) / k, mode="valid"); ss = s[k - 1:]
    ax.plot(ss / 1000, ls, color=COL[item], lw=1.4, solid_capstyle="round")
    ax.text(ss[-1] / 1000 + 0.8, ls[-1] * (0.86 if item == "teal" else 1), f"{NAME[item]}  {ls[-1]:.2f}", color=INK, va="center", fontsize=10)
    for step in sorted({st for (it, st) in by if it == item}):
        y = np.interp(step, ss, ls)
        ax.plot(step / 1000, y, "o", ms=6.5, mfc=COL[item], mec=BG, mew=1.4, zorder=5)
ax.set_yscale("log"); ax.set_xlim(0, 62); ax.set_ylim(0.05, 6)
ax.set_xlabel("Training steps (thousands)"); ax.set_ylabel("Training loss (log scale)")
ax.set_yticks([0.05, 0.1, 0.2, 0.5, 1, 2, 5]); ax.set_yticklabels(["0.05", "0.1", "0.2", "0.5", "1", "2", "5"])
ax.text(0.99, 0.97, "dots: checkpoints tested on the arm", transform=ax.transAxes, ha="right", va="top", color=MUTED, fontsize=9.5)
f.tight_layout(); f.savefig(A / "chart_loss.png", facecolor=BG); plt.close(f)

# 2. robot results by checkpoint: one small panel per color, first-try placement rate, counts on the bars
f, axes = plt.subplots(1, 3, figsize=(8, 3.2), dpi=220, sharey=True, gridspec_kw={"width_ratios": [3, 3, 1.4]})
f.patch.set_facecolor(BG)
for ax, item in zip(axes, ("purple", "red", "teal")):
    ax.set_facecolor(BG); steps = sorted(st for (it, st) in by if it == item)
    rates = [placed(by[(item, s)]) / len(by[(item, s)]) * 100 for s in steps]
    xs = range(len(steps))
    ax.bar(xs, [max(r, 0.8) for r in rates], width=0.62, color=COL[item], edgecolor=BG, linewidth=2)
    for x, s, r in zip(xs, steps, rates):
        ax.text(x, r + 3, f"{placed(by[(item, s)])} of {len(by[(item, s)])}", ha="center", color=INK, fontsize=9.5)
    ax.set_xticks(list(xs)); ax.set_xticklabels([f"{s // 1000}k" for s in steps])
    ax.set_title(NAME[item], color=INK, fontsize=11, fontweight="bold", loc="left")
    ax.grid(axis="x", visible=False); ax.set_xlim(-0.6, len(steps) - 0.4)
axes[0].set_ylabel("Placed on the first try (%)"); axes[0].set_ylim(0, 80)
f.text(0.5, 0.01, "Training steps", ha="center", color=MUTED, fontsize=11)
f.tight_layout(rect=(0, 0.05, 1, 1)); f.savefig(A / "chart_results.png", facecolor=BG); plt.close(f)

# 3. the gripper learns where to close: ring offset in the gripper camera at the moment it closed
f, ax = fig(8, 3.8)
rng = np.random.default_rng(3)
order = [("purple", 10000), ("purple", 20000), ("purple", 50000), ("red", 10000), ("red", 20000), ("red", 40000), ("teal", 20000)]
xs = {k: i + (0.6 if k[0] == "red" else 1.2 if k[0] == "teal" else 0) for i, k in enumerate(order)}
ax.axhspan(0, 20, color="#E2DED4", zorder=0, lw=0)
for k in order:
    rs = [r for r in by[k] if r["err"] is not None]; x = xs[k]
    for r in rs:
        ok = r["outcome"] in ("placed", "held")
        ax.plot(x + rng.uniform(-0.18, 0.18), min(r["err"], 195), "o", ms=6 if ok else 4.5, mfc=COL[k[0]] if ok else BG,
                mec=COL[k[0]], mew=1.3, alpha=1 if ok else 0.75, zorder=4)
    med = np.median([r["err"] for r in rs]); ax.plot([x - 0.3, x + 0.3], [med, med], color=INK, lw=2, zorder=5)
    ax.text(x, -24, f"{NAME[k[0]]}\n{k[1] // 1000}k", ha="center", va="top", color=INK, fontsize=9.5)
ax.set_xlim(-0.6, max(xs.values()) + 0.6); ax.set_ylim(0, 245); ax.set_yticks([0, 50, 100, 150, 200]); ax.set_xticks([])
ax.set_ylabel("Ring offset at the close (px)")
ax.text(0.99, 0.97, "black bar: median · filled: placed · hollow: missed", transform=ax.transAxes, ha="right", va="top", color=MUTED, fontsize=9.5)
ax.text(0.99, 0.89, "shaded: within 20 px, where every placed pick closed · above 195 px drawn at the top", transform=ax.transAxes, ha="right", va="top", color=MUTED, fontsize=9.5)
f.tight_layout(); f.subplots_adjust(bottom=0.18); f.savefig(A / "chart_grasp.png", facecolor=BG); plt.close(f)

# 4. camera drift vs outcome, red and purple: camera offset from where that color was recorded
f, ax = fig(8, 3.2)
rows = [("red", 10000), ("red", 20000), ("red", 40000), ("purple", 10000), ("purple", 20000), ("purple", 50000), ("teal", 20000)]
for y, k in enumerate(rows):
    for r in by[k]:
        if r["cam_px"] is None: continue
        ok = r["outcome"] in ("placed", "held")
        ax.plot(r["cam_px"] + rng.uniform(-0.15, 0.15), y + rng.uniform(-0.15, 0.15), "o", ms=7 if ok else 5,
                mfc=COL[k[0]] if ok else BG, mec=COL[k[0]], mew=1.3, zorder=4)
    ax.text(-0.6, y, f"{NAME[k[0]]} {k[1] // 1000}k", ha="right", va="center", color=INK, fontsize=10)
ax.annotate("placed with the camera\n11 px off and turned 5.6°", xy=(11.0, 2), xytext=(12.6, 2.6), color=INK, fontsize=9.5,
            arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8))
ax.set_yticks([]); ax.set_ylim(len(rows) - 0.4, -0.6); ax.set_xlim(0, 20)
ax.set_xlabel("Stand camera's distance from where that color was recorded (px, at the rings)")
ax.text(0.99, 0.04, "filled: placed · hollow: missed", transform=ax.transAxes, ha="right", color=MUTED, fontsize=9.5)
f.tight_layout(); f.subplots_adjust(left=0.14); f.savefig(A / "chart_camera.png", facecolor=BG); plt.close(f)
print("ok")

# 5. where each color's ring started in every demonstration, on the stand camera's view
import cv2
vis = json.load(open("/home/amd-genai1/kitcheck/data/vision.json"))["items"]
img = cv2.cvtColor(cv2.imread("/home/amd-genai1/kitcheck/data/camera_ref_purple_30.png"), cv2.COLOR_BGR2RGB)[150:450, 150:550]
f, ax = plt.subplots(figsize=(4.4, 3.3), dpi=220); f.patch.set_facecolor(BG)
ax.imshow((img * 0.55 + 255 * 0.45).astype("uint8"), extent=(150, 550, 450, 150))
for item in ("purple", "red", "teal"):
    p = np.array(vis[item]["points"]); ax.plot(p[:, 0], p[:, 1], "o", ms=5, mfc=COL[item], mec="white", mew=0.8, alpha=0.95, label=NAME[item])
ax.set_xlim(150, 550); ax.set_ylim(450, 150); ax.axis("off")
leg = ax.legend(loc="upper right", frameon=True, fontsize=9, facecolor=BG, edgecolor="#DAD6CB", handletextpad=0.3, borderpad=0.4)
for t in leg.get_texts(): t.set_color(INK)
f.tight_layout(pad=0.2); f.savefig(A / "chart_starts.png", facecolor=BG); plt.close(f)
print("ok2")
