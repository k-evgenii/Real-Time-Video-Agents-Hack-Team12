"""Per-frame YOLO detections for one VSS segment (or a batch).

  python map/detect.py --source s3://…/x_segment_001_of_006.mp4 [--out data/raw/det/<seg_id>/] [--engine sidecar|hosted|auto]
  python map/detect.py --batch sources.txt            # one s3 uri per line; skips segments already done

Writes <out>/detections.jsonl  {"frame","t","cls","conf","box":[x1,y1,x2,y2]}  (t = seconds inside the segment)
       <out>/meta.json         {"fps","width","height","source","n_frames","engine"}
       <out>/seg.mp4           (kept for team colour / calibration frames)
Engines: sidecar = GET /api/v1/videos/detections (stored by the ingest detector, all frames, no compute);
         hosted  = POST $YOLO_URL/v1/infer on the downloaded clip. auto = sidecar, else hosted.
"""
import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vss import VSS, yolo_infer  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DET_ROOT = os.path.join(ROOT, "data", "raw", "det")
KEEP = {c: 0.35 for c in ("car", "truck", "bus", "motorcycle", "person", "bicycle")}


def seg_id_of(source):
    return os.path.splitext(os.path.basename(source))[0]


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,r_frame_rate,nb_frames", "-of", "json", path],
                         capture_output=True, text=True).stdout
    s = json.loads(out)["streams"][0]
    num, den = s["r_frame_rate"].split("/")
    return {"width": int(s["width"]), "height": int(s["height"]),
            "fps": float(num) / float(den), "n_frames": int(s.get("nb_frames") or 0)}


def rows_from_frames(frames, fps):
    rows = []
    for i, fr in enumerate(frames):
        idx = fr.get("frame_index", i)
        t = fr.get("time_sec")
        if t is None:
            t = idx / fps
        for d in fr.get("detections", []):
            cls = d.get("label") or d.get("class") or d.get("name")
            conf = float(d.get("confidence", d.get("conf", 0)))
            if cls not in KEEP or conf < KEEP[cls]:
                continue
            x1, y1, x2, y2 = (int(round(v)) for v in d["bbox"][:4])
            rows.append({"frame": int(idx), "t": round(float(t), 3), "cls": cls, "conf": round(conf, 3),
                         "box": [x1, y1, x2, y2]})
    return rows


def detect(vss, source, out, engine="auto", keep_video=True):
    os.makedirs(out, exist_ok=True)
    t0 = time.time()
    mp4 = os.path.join(out, "seg.mp4")
    if keep_video and not os.path.exists(mp4):
        vss.download(source, mp4)
    frames, fps, W, H, used = None, None, None, None, None
    if engine in ("auto", "sidecar"):
        r = vss.detections(source)
        if r.ok:
            d = r.json()
            frames = d.get("frames") or []
            fps = float(d.get("fps") or 0) or None
            shp = d.get("video_shape") or [None, None]
            H, W = shp[0], shp[1]
            used = "sidecar"
        elif engine == "sidecar":
            raise SystemExit(f"no sidecar for {source} (HTTP {r.status_code})")
    if frames is None or not frames:
        if not os.path.exists(mp4):
            vss.download(source, mp4)
        d = yolo_infer(mp4)
        frames = d.get("frames") or (d.get("perception_json") or {}).get("frames") or []
        used = "hosted"
    if os.path.exists(mp4):
        p = probe(mp4)
        W, H = W or p["width"], H or p["height"]
        fps = fps or p["fps"]
    fps = fps or 30.0
    rows = rows_from_frames(frames, fps)
    with open(os.path.join(out, "detections.jsonl"), "w") as f:
        for r_ in rows:
            f.write(json.dumps(r_) + "\n")
    meta = {"fps": fps, "width": W, "height": H, "source": source, "n_frames": len(frames), "engine": used,
            "seconds": round(time.time() - t0, 2)}
    json.dump(meta, open(os.path.join(out, "meta.json"), "w"))
    n_frames = max(1, len(frames))
    meta["objects_per_frame"] = round(len(rows) / n_frames, 2)
    return meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source")
    ap.add_argument("--batch")
    ap.add_argument("--out")
    ap.add_argument("--engine", default="auto", choices=["auto", "sidecar", "hosted"])
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    vss = VSS().login()
    sources = []
    if a.source:
        sources.append(a.source)
    if a.batch:
        sources += [l.strip() for l in open(a.batch) if l.strip() and not l.startswith("#")]
    if a.limit:
        sources = sources[:a.limit]
    stats = []
    for s in sources:
        out = a.out if (a.out and len(sources) == 1) else os.path.join(DET_ROOT, seg_id_of(s))
        if a.batch and os.path.exists(os.path.join(out, "meta.json")):
            m = json.load(open(os.path.join(out, "meta.json")))
            print(f"skip {seg_id_of(s)} (done)")
            stats.append(m)
            continue
        m = detect(vss, s, out, a.engine)
        stats.append(m)
        print(f"{seg_id_of(s)} engine={m['engine']} frames={m['n_frames']} fps={m['fps']:.2f} "
              f"{m['width']}x{m['height']} objects/frame={m.get('objects_per_frame')} {m['seconds']}s")
    opf = [m["objects_per_frame"] for m in stats if "objects_per_frame" in m]
    if opf:
        print(f"TOTAL segments={len(stats)} mean objects/frame={sum(opf)/len(opf):.2f}")


if __name__ == "__main__":
    main()
