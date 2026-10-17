#!/usr/bin/env python3
"""Traffic episode page for two I-24 chunks. The player shows chunk 0003."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "8080"))
VSS_URL = os.environ.get("VSS_URL", "").rstrip("/")
VSS_USERNAME = os.environ.get("VSS_USERNAME", "")
VSS_PASSWORD = os.environ.get("VSS_PASSWORD", "")

PARENT = "s3://team-12-vss-chunks/team-12/20261001_055405_scene1_p1c1_chunk_0003.mp4"
SEARCH_URL = "https://team-12-vss.thecosmoslabs.com/search"
ALLOWED_SOURCES = (
    "s3://team-12-vss-chunks/team-12/",
    "s3://team-12-vss-chunks-segments/segments/",
)

CLIPS = {
    "match_id": "i24",
    "title": "I-24 overhead, chunk 0003",
    "duration_s": 30.0,
    "search_url": SEARCH_URL,
    "banner": "Every indexed video is on the team search page. This player starts on I-24 chunk 0003. The first 5 seconds are the only moderate-flow episode. Nothing scored at or above 2.5, so nothing is flagged.",
    "unparsed": {"t0": 0.0, "t1": 5.0, "why": "Moderate flow, 30.0–35.0s in the two-chunk timeline."},
    "segments": [
        {"seg_id": "i24_c3_0000", "t0": 0.0, "t1": 5.0, "events": ["none"], "note": "Moderate flow. Flow code is 1.7σ above this camera's other episodes, under the 2.5 flag line."},
        {"seg_id": "i24_c3_0001", "t0": 5.0, "t1": 30.0, "events": ["none"], "note": "Free flow for the rest of this chunk. No risk events were stated in the captions."},
    ],
    "attack": {
        "attack_id": "i24_e003",
        "team": "A",
        "t0": 5.0,
        "t1": 30.0,
        "n_seg": 5,
        "zones": ["H"],
        "events": ["none"],
        "ended_by": "end",
        "why": "After the 5-second moderate spell, this chunk is free flow through 30 seconds. That is the usual state for this camera.",
    },
    "anomaly": {
        "s_emb": None,
        "flagged": False,
        "reason": "Closest episode scores 1.75, below 2.5. Visual embedding score is not loaded.",
        "moment_t": 0.0,
        "moment_why": "Moderate flow on an otherwise free highway. No braking or stop was stated.",
    },
}

_token = ""


def vss_token() -> str:
    global _token
    if _token:
        return _token
    body = json.dumps({"username": VSS_USERNAME, "password": VSS_PASSWORD}).encode()
    req = urllib.request.Request(
        f"{VSS_URL}/api/v1/auth/login",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        _token = json.load(resp)["access_token"]
    return _token


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        path = self.path.split("?", 1)[0]
        status = args[1] if len(args) > 1 else args
        print(f"{self.command} {path} -> {status}")

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        if path == "/health":
            self._send(200, b'{"ok":true,"service":"footballslam"}', "application/json")
            return
        if path == "/api/match":
            self._send(200, json.dumps(CLIPS).encode(), "application/json")
            return
        if path == "/api/videos":
            self._videos()
            return
        if path == "/media/match":
            self._stream()
            return
        if path in ("/", "/index.html"):
            root = os.path.dirname(__file__)
            html = os.path.join(root, "static", "index.html")
            if not os.path.exists(html):
                html = os.path.join(root, "index.html")
            self._send(200, open(html, "rb").read(), "text/html; charset=utf-8")
            return
        self._send(404, b'{"error":"not found"}', "application/json")

    def _videos(self) -> None:
        query = urllib.parse.urlencode({"scope": "all", "limit": "30", "offset": "0", "location": "nashville"})
        req = urllib.request.Request(
            f"{VSS_URL}/api/v1/videos/explore?{query}",
            headers={"Authorization": "Bearer " + vss_token()},
        )
        try:
            with urllib.request.urlopen(req, timeout=40) as resp:
                payload = json.load(resp)
        except urllib.error.HTTPError as exc:
            self._send(exc.code, b'{"error":"catalog failed"}', "application/json")
            return
        rows = []
        for chunk in payload.get("chunks") or []:
            source = chunk.get("original_video") or ""
            if not source.startswith(ALLOWED_SOURCES):
                continue
            rows.append({
                "filename": chunk.get("filename") or "",
                "camera_id": chunk.get("camera_id") or "",
                "duration_s": chunk.get("chunk_duration_sec"),
                "source": source,
            })
        body = json.dumps({"search_url": SEARCH_URL, "total": payload.get("total"), "videos": rows}).encode()
        self._send(200, body, "application/json")

    def _stream(self) -> None:
        global _token
        parsed = urllib.parse.urlparse(self.path)
        asked = urllib.parse.parse_qs(parsed.query).get("source", [PARENT])[0]
        source = asked if asked.startswith(ALLOWED_SOURCES) else PARENT
        for attempt in (1, 2):
            token = vss_token()
            query = urllib.parse.urlencode({"source": source, "token": token})
            req = urllib.request.Request(f"{VSS_URL}/api/v1/videos/stream?{query}")
            if self.headers.get("Range"):
                req.add_header("Range", self.headers["Range"])
            try:
                upstream = urllib.request.urlopen(req, timeout=60)
                status = upstream.status
                break
            except urllib.error.HTTPError as exc:
                if exc.code == 401 and attempt == 1:
                    _token = ""
                    continue
                self._send(exc.code, b'{"error":"playback failed"}', "application/json")
                return
        else:
            self._send(502, b'{"error":"playback failed"}', "application/json")
            return
        self.send_response(status)
        content_type = upstream.headers.get("Content-Type") or ""
        if not content_type or "octet-stream" in content_type:
            content_type = "video/mp4"
        self.send_header("Content-Type", content_type)
        for header in ("Content-Length", "Content-Range", "Accept-Ranges"):
            value = upstream.headers.get(header)
            if value:
                self.send_header(header, value)
        self.end_headers()
        if self.command == "HEAD":
            upstream.close()
            return
        try:
            while True:
                chunk = upstream.read(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            upstream.close()


def main() -> None:
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
