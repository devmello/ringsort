"""Live camera alignment: put the stand camera back where the demonstrations saw it.

    python -m kitcheck.align --camera <device> [--item purple] [--episode N] [--port 8077]

scripts/align_camera.sh runs this; use that instead of calling it directly.

A model trained on demonstrations only works when the camera sees the table the
way it did while recording. This serves a page at http://127.0.0.1:<port> that
shows the live camera on top of the first frame of one recorded demonstration
(the arm is at rest there), and measures how far apart they are using only
things that never move: the cups along the top and the black pad bottom right.
Rings, the arm and anything else on the table are ignored.

The page shows the error in pixels and arrows for which way the picture has to
move. Nudge the stand until it says ALIGNED, then press "Done" on the page:
the camera stays busy (recording cannot open it) until this program stops.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import av
import cv2
import numpy as np
import pandas as pd

CAM = "observation.images.front"
W, H = 640, 480
ALIGNED_PX = 4.0   # worst pixel off by at most this much counts as aligned
CLOSE_PX = 12.0

# Areas that never move between takes: the cups along the top, the black pad
# bottom right. Everything else (arm, rings, stray objects) is ignored.
STATIC = np.zeros((H, W), np.uint8)
STATIC[:200, :] = 255
STATIC[330:, 430:] = 255


def datasets(data_dir: Path) -> dict[str, Path]:
    found = {}
    for info in sorted(data_dir.glob("pick_*/meta/info.json")):
        root = info.parent.parent
        found[root.name.removeprefix("pick_")] = root
    return found


def episode_count(root: Path) -> int:
    return json.loads((root / "meta/info.json").read_text()).get("total_episodes", 0)


def first_frame(root: Path, episode: int) -> np.ndarray:
    """The first frame of one demonstration from the stand camera, as BGR."""
    eps = pd.concat(pd.read_parquet(f) for f in sorted(glob.glob(str(root / "meta/episodes/chunk-*/file-*.parquet"))))
    row = eps[eps.episode_index == episode]
    if row.empty:
        raise ValueError(f"{root} has no episode {episode}")
    row = row.iloc[0]
    chunk, file = int(row[f"videos/{CAM}/chunk_index"]), int(row[f"videos/{CAM}/file_index"])
    t = float(row[f"videos/{CAM}/from_timestamp"]) + 0.05
    with av.open(str(root / f"videos/{CAM}/chunk-{chunk:03d}/file-{file:03d}.mp4")) as c:
        s = c.streams.video[0]
        c.seek(int(max(t - 1, 0) / s.time_base), stream=s)
        for f in c.decode(s):
            if f.time >= t:
                return cv2.resize(f.to_ndarray(format="bgr24"), (W, H))
    raise ValueError(f"could not read episode {episode} from {root}")


def gray(img: np.ndarray, scale: float) -> np.ndarray:
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return cv2.GaussianBlur(g, (5, 5), 0).astype(np.float32)


def measure(ref: np.ndarray, live: np.ndarray, start: np.ndarray | None) -> tuple[np.ndarray, float]:
    """Rotation + shift taking reference pixels to where they appear live.

    Coarse to fine (quarter, then half resolution), starting from the last
    answer when there is one. Returns the 2x3 matrix in full-resolution pixels
    and the correlation (1 = identical) over the static areas.
    """
    warp = np.eye(2, 3, dtype=np.float32) if start is None else start.copy()
    cc = 0.0
    for scale in (0.25, 0.5):
        w = warp.copy()
        w[:, 2] *= scale
        mask = cv2.resize(STATIC, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
        cc, w = cv2.findTransformECC(gray(ref, scale), gray(live, scale), w, cv2.MOTION_EUCLIDEAN,
                                     (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-5), mask, 1)
        warp = w.copy()
        warp[:, 2] /= scale
    return warp, cc


def apply(warp: np.ndarray, pts: np.ndarray) -> np.ndarray:
    return pts @ warp[:, :2].T + warp[:, 2]


# Points the error is judged at, and where the page draws arrows.
PROBES = np.float32([[100, 90], [540, 90], [320, 240], [100, 400], [540, 400]])
CORNERS = np.float32([[0, 0], [W, 0], [0, H], [W, H]])


def summary(warp: np.ndarray | None, cc: float) -> dict:
    if warp is None:
        return {"state": "NO LOCK", "text": "cannot match the cups and pad: is the camera covered or pointed far away?"}
    centre = np.float32([[W / 2, H / 2]])
    dx, dy = (apply(warp, centre) - centre)[0]
    rot = float(np.degrees(np.arctan2(warp[1, 0], warp[0, 0])))  # + = live is turned clockwise
    worst = float(np.linalg.norm(apply(warp, CORNERS) - CORNERS, axis=1).max())
    state = "ALIGNED" if worst <= ALIGNED_PX else "CLOSE" if worst <= CLOSE_PX else "OFF"
    moves = []
    if abs(dx) >= 1:
        moves.append(f"{'left' if dx > 0 else 'right'} {abs(dx):.0f} px")
    if abs(dy) >= 1:
        moves.append(f"{'up' if dy > 0 else 'down'} {abs(dy):.0f} px")
    if abs(rot) >= 0.2:
        moves.append(f"turn {'anticlockwise' if rot > 0 else 'clockwise'} {abs(rot):.1f}°")
    text = "picture must move " + ", ".join(moves) if moves else "nothing to move"
    return {"state": state, "worst_px": round(worst, 1), "dx": round(float(dx), 1), "dy": round(float(dy), 1),
            "rot_deg": round(rot, 2), "match": round(float(cc), 3), "text": text}


class Aligner:
    def __init__(self, camera: str, data_dir: Path, item: str, episode: int | None):
        self.camera = camera
        self.sets = datasets(data_dir)
        if not self.sets:
            raise SystemExit(f"no datasets in {data_dir}")
        self.lock = threading.Lock()
        self.live: np.ndarray | None = None
        self.warp: np.ndarray | None = None
        self.status: dict = {"state": "STARTING", "text": "opening the camera"}
        self.mode, self.alpha = "blend", 0.5
        self.running = True
        self.load(item, episode)

    def load(self, item: str, episode: int | None) -> None:
        if item not in self.sets:
            raise ValueError(f"no dataset for '{item}' (have: {', '.join(self.sets)})")
        root = self.sets[item]
        count = episode_count(root)
        episode = count - 1 if episode is None else episode
        if not 0 <= episode < count:
            raise ValueError(f"{item} has episodes 0 to {count - 1}")
        ref = first_frame(root, episode)
        with self.lock:
            self.item, self.episode, self.count, self.ref = item, episode, count, ref
            self.ref_edges = cv2.Canny(cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY), 60, 150)
            self.warp = None

    def capture(self) -> None:
        dev = os.path.realpath(self.camera)
        index = int(dev.removeprefix("/dev/video")) if dev.startswith("/dev/video") else dev
        cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, W)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, H)
        if not cap.isOpened():
            self.status = {"state": "NO CAMERA", "text": f"cannot open {self.camera}: is recording or a model run using it?"}
            return
        fails = 0
        while self.running:
            ok, img = cap.read()
            if not ok:
                fails += 1
                if fails > 30:
                    self.status = {"state": "NO CAMERA", "text": f"{self.camera} stopped sending frames"}
                time.sleep(0.03)
                continue
            fails = 0
            with self.lock:
                self.live = cv2.resize(img, (W, H)) if img.shape[:2] != (H, W) else img
        cap.release()

    def analyse(self) -> None:
        while self.running:
            with self.lock:
                live, ref, start = self.live, self.ref, self.warp
            if live is None:
                time.sleep(0.1)
                continue
            warp, cc = None, 0.0
            for s in ([start, None] if start is not None else [None]):
                try:
                    warp, cc = measure(ref, live, s)
                    if cc > 0.5:
                        break
                except cv2.error:
                    warp = None
            if warp is not None and cc <= 0.5:
                warp = None
            with self.lock:
                if ref is self.ref:  # the reference did not change meanwhile
                    self.warp = warp
                    self.status = summary(warp, cc)
            time.sleep(0.15)

    def frame(self) -> np.ndarray:
        with self.lock:
            live, ref, edges, warp, mode, alpha = self.live, self.ref, self.ref_edges, self.warp, self.mode, self.alpha
        if live is None:
            live = np.zeros_like(ref)
        if mode == "edges":
            out = np.zeros_like(live)
            out[..., 2] = cv2.dilate(edges, np.ones((2, 2), np.uint8))
            out[..., 1] = cv2.dilate(cv2.Canny(cv2.cvtColor(live, cv2.COLOR_BGR2GRAY), 60, 150), np.ones((2, 2), np.uint8))
        elif mode == "flicker":
            out = (ref if int(time.time() * 2) % 2 else live).copy()
        elif mode == "live":
            out = live.copy()
        elif mode == "ref":
            out = ref.copy()
        else:
            out = cv2.addWeighted(ref, alpha, live, 1 - alpha, 0)
        for x in range(0, W, 80):
            cv2.line(out, (x, 0), (x, H), (255, 255, 255), 1)
        for y in range(0, H, 80):
            cv2.line(out, (0, y), (W, y), (255, 255, 255), 1)
        if warp is not None:
            # Arrow from where each reference point is now to where it belongs.
            for (x0, y0), (x1, y1) in zip(apply(warp, PROBES), PROBES):
                cv2.circle(out, (int(x1), int(y1)), 6, (0, 0, 255), 2)
                if np.hypot(x1 - x0, y1 - y0) >= 2:
                    cv2.arrowedLine(out, (int(x0), int(y0)), (int(x1), int(y1)), (0, 255, 255), 2, tipLength=0.25)
        return out


PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Camera alignment</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{font:15px system-ui,sans-serif;margin:16px;background:#111;color:#eee}
.wrap{display:flex;gap:20px;flex-wrap:wrap}img{width:640px;max-width:100%;border:1px solid #444}
.panel{min-width:280px;max-width:420px}
#state{font-size:34px;font-weight:700;padding:8px 14px;border-radius:6px;display:inline-block}
.ALIGNED{background:#1b7f3a}.CLOSE{background:#b8860b}.OFF,.NO\\ LOCK,.NO\\ CAMERA{background:#a52a2a}.STARTING{background:#555}
#text{font-size:18px;margin:12px 0}table td{padding:2px 10px 2px 0}
button,select,input{font:inherit;margin:2px;padding:4px 8px}button.on{outline:2px solid #4af}
.small{color:#aaa;font-size:13px;line-height:1.4}#done{background:#633;color:#fff;margin-top:14px}
</style></head><body>
<div class="wrap"><img id="view" src="/stream" alt="camera">
<div class="panel">
<div id="state" class="STARTING">STARTING</div><div id="text"></div>
<table><tr><td>worst pixel off</td><td id="worst"></td></tr><tr><td>shift x / y</td><td id="shift"></td></tr>
<tr><td>rotation</td><td id="rot"></td></tr><tr><td>match</td><td id="match"></td></tr></table>
<p>View:
<button data-m="blend">blend</button><button data-m="edges">edges</button><button data-m="flicker">flicker</button>
<button data-m="live">live</button><button data-m="ref">recorded</button></p>
<p>Blend <input id="alpha" type="range" min="0" max="100" value="50"></p>
<p>Line up with: <select id="item"></select> episode <input id="ep" type="number" min="0" style="width:5em">
<button id="load">load</button> <span id="count" class="small"></span></p>
<p class="small">Yellow arrows run from where a recorded point is now to where it belongs (red circle).
Move the stand until the arrows vanish and the box says ALIGNED.
In <b>edges</b>, red is the recording and green is live. Only the cups and the black pad are measured;
rings, the arm and other objects are ignored. Keep things off the table that were not there while recording.</p>
<button id="done">Done: release the camera</button>
</div></div>
<script>
const $=id=>document.getElementById(id);
function set(q){return fetch('/set?'+new URLSearchParams(q)).then(r=>r.json()).then(s=>{if(s.error)alert(s.error);show(s)})}
document.querySelectorAll('button[data-m]').forEach(b=>b.onclick=()=>set({mode:b.dataset.m}));
$('alpha').oninput=e=>set({alpha:e.target.value/100});
$('load').onclick=()=>set({item:$('item').value,episode:$('ep').value});
$('item').onchange=()=>set({item:$('item').value});
$('done').onclick=()=>fetch('/quit').then(()=>{document.body.innerHTML='<h2>Camera released. You can record now.</h2>'});
let first=true;
function show(s){
  const st=s.status;$('state').textContent=st.state;$('state').className=st.state;$('text').textContent=st.text||'';
  $('worst').textContent=st.worst_px!=null?st.worst_px+' px':'';
  $('shift').textContent=st.dx!=null?st.dx+' / '+st.dy+' px':'';
  $('rot').textContent=st.rot_deg!=null?st.rot_deg+'°':'';$('match').textContent=st.match??'';
  document.querySelectorAll('button[data-m]').forEach(b=>b.classList.toggle('on',b.dataset.m==s.mode));
  if(first||document.activeElement!==$('ep')){$('ep').value=s.episode}
  if(first){$('item').innerHTML=s.items.map(i=>`<option>${i}</option>`).join('');$('alpha').value=s.alpha*100;first=false}
  $('item').value=s.item;$('count').textContent=`(0 to ${s.count-1})`;
}
setInterval(()=>fetch('/status').then(r=>r.json()).then(show).catch(()=>{}),300);
</script></body></html>"""


def serve(al: Aligner, port: int) -> None:
    def state() -> dict:
        return {"status": al.status, "mode": al.mode, "alpha": al.alpha, "item": al.item,
                "episode": al.episode, "count": al.count, "items": list(al.sets)}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, body: bytes, kind: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            url = urlparse(self.path)
            if url.path == "/":
                self.send(PAGE.encode(), "text/html; charset=utf-8")
            elif url.path == "/status":
                self.send(json.dumps(state()).encode(), "application/json")
            elif url.path == "/set":
                q = {k: v[0] for k, v in parse_qs(url.query).items()}
                out = {}
                try:
                    if q.get("mode") in ("blend", "edges", "flicker", "live", "ref"):
                        al.mode = q["mode"]
                    if "alpha" in q:
                        al.alpha = min(max(float(q["alpha"]), 0.0), 1.0)
                    if "item" in q:
                        ep = q.get("episode")
                        al.load(q["item"], int(ep) if ep not in (None, "") and q["item"] == al.item else None)
                except ValueError as e:
                    out["error"] = str(e)
                self.send(json.dumps({**state(), **out}).encode(), "application/json")
            elif url.path == "/stream":
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                try:
                    while al.running:
                        jpg = cv2.imencode(".jpg", al.frame(), [cv2.IMWRITE_JPEG_QUALITY, 80])[1].tobytes()
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n")
                        time.sleep(1 / 15)
                except (BrokenPipeError, ConnectionResetError):
                    pass
            elif url.path == "/quit":
                self.send(b"{}", "application/json")
                al.running = False
                threading.Thread(target=server.shutdown, daemon=True).start()
            else:
                self.send_error(404)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    print(f"camera alignment: http://127.0.0.1:{port}   (press Done on the page, or Ctrl+C here, to release the camera)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    al.running = False


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--camera", required=True, help="stand camera device, e.g. /dev/v4l/by-id/...-video-index0")
    p.add_argument("--data-dir", type=Path, default=Path(os.environ.get("DATA_DIR", Path.home() / "kitcheck_data")))
    p.add_argument("--item", default="purple")
    p.add_argument("--episode", type=int, default=None, help="demonstration to line up with (default: the latest)")
    p.add_argument("--port", type=int, default=8077)
    a = p.parse_args()
    try:
        al = Aligner(a.camera, a.data_dir, a.item, a.episode)
    except ValueError as e:
        raise SystemExit(str(e))
    print(f"lining up with {a.item} episode {al.episode} (of 0 to {al.count - 1})", flush=True)
    threading.Thread(target=al.capture, daemon=True).start()
    threading.Thread(target=al.analyse, daemon=True).start()
    serve(al, a.port)


if __name__ == "__main__":
    main()
