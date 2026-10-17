"""Minimal VSS + GPU client for role B (map). Never prints credentials.

Credentials come from the environment, falling back to the single /config/*.config file.
"""
import base64
import glob
import json
import os
import time

import requests

GPU_HOST = "166.19.38.112"
YOLO_URL = os.environ.get("YOLO_URL", f"http://{GPU_HOST}:8002")


def _cfg():
    cfg = {}
    files = sorted(glob.glob("/config/*.config"))
    if len(files) == 1:
        for line in open(files[0]):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            cfg[k.replace("export ", "").strip()] = v.strip().strip('"').strip("'")
    return cfg


def env(name):
    v = os.environ.get(name)
    if v:
        return v
    return _cfg().get(name)


class VSS:
    def __init__(self):
        self.base = env("INGRESS_URL").rstrip("/")
        self.token = None

    def login(self):
        r = requests.post(f"{self.base}/api/v1/auth/login",
                          json={"username": env("USERNAME"), "password": env("PASSWORD")}, timeout=30)
        r.raise_for_status()
        self.token = r.json()["access_token"]
        return self

    def get(self, path, **params):
        if not self.token:
            self.login()
        for _ in range(2):
            r = requests.get(f"{self.base}{path}", params=params,
                             headers={"Authorization": f"Bearer {self.token}"}, timeout=60)
            if r.status_code == 401:
                self.login()
                continue
            return r
        return r

    def explore(self, scope="all", limit=48, offset=0, **kw):
        r = self.get("/api/v1/videos/explore", scope=scope, limit=limit, offset=offset, **kw)
        r.raise_for_status()
        return r.json()

    def detections(self, source):
        return self.get("/api/v1/videos/detections", source=source)

    def download(self, source, out_path):
        if not self.token:
            self.login()
        r = requests.get(f"{self.base}/api/v1/videos/stream",
                         params={"source": source, "token": self.token}, stream=True, timeout=120)
        if r.status_code == 401:
            self.login()
            r = requests.get(f"{self.base}/api/v1/videos/stream",
                             params={"source": source, "token": self.token}, stream=True, timeout=120)
        r.raise_for_status()
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)
        return out_path


def yolo_infer(path, include_frames=True, timeout=300, **extra):
    b64 = base64.b64encode(open(path, "rb").read()).decode()
    body = {"video_base64": b64, "filename": os.path.basename(path), "include_frames": include_frames}
    body.update(extra)
    t = time.time()
    r = requests.post(f"{YOLO_URL}/v1/infer", json=body,
                      headers={"Authorization": f"Bearer {env('GPU_BEARER_TOKEN')}"}, timeout=timeout)
    r.raise_for_status()
    d = r.json()
    d["_elapsed_s"] = round(time.time() - t, 2)
    return d


def dump(obj, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f)
