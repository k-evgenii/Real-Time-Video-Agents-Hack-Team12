"""FootballSLAM server.

Ingress strips /app, so every route is mounted at /. Data files are read from
./data relative to the process working directory. Static files are the
directory next to this module (app/static in the repo, /code/static once
deploy materializes the ConfigMap beside main.py).
"""

import base64
import logging
import os
import re
import threading
from pathlib import Path

import requests
from flask import Flask, Response, jsonify, request, send_from_directory

log = logging.getLogger("footballslam")

VSS_URL = os.environ.get("VSS_URL", "").rstrip("/")
VSS_USERNAME = os.environ.get("VSS_USERNAME", "")
VSS_PASSWORD = os.environ.get("VSS_PASSWORD", "")
DATA_URL = os.environ.get("DATA_URL", "").rstrip("/")
PORT = int(os.environ.get("PORT", "8080"))

DATA_DIR = Path.cwd() / "data"
STATIC_DIR = Path(__file__).resolve().parent / "static"
ALLOWED_NAMES = frozenset(
    {"segments", "attacks", "anomalies", "map", "track_alerts", "map_sim"}
)
MATCH_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
PART_MAP = re.compile(r"^map(_sim)?_[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
STREAM_HEADERS = ("Content-Range", "Accept-Ranges", "Content-Type", "Content-Length")
CHUNK = 64 * 1024

app = Flask(__name__, static_folder=None)
_token = None
_token_lock = threading.Lock()
_thread_local = threading.local()


def _http():
    """One Session per thread so concurrent Range streams do not share a socket."""
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = requests.Session()
        _thread_local.session = session
    return session


def login():
    """Fetch a JWT and keep it in memory. Never log the token or password."""
    global _token
    if not VSS_URL or not VSS_USERNAME or not VSS_PASSWORD:
        raise RuntimeError("vss credentials are not configured")
    try:
        resp = _http().post(
            f"{VSS_URL}/api/v1/auth/login",
            json={"username": VSS_USERNAME, "password": VSS_PASSWORD},
            timeout=15,
        )
    except requests.RequestException:
        raise RuntimeError("login failed")
    try:
        if resp.status_code != 200:
            raise RuntimeError("login failed")
        try:
            body = resp.json()
        except ValueError:
            body = None
        token = body.get("access_token") if isinstance(body, dict) else None
        if not isinstance(token, str) or not token:
            raise RuntimeError("login failed")
    finally:
        resp.close()
    with _token_lock:
        _token = token


def _current_token():
    with _token_lock:
        return _token


def _json_error(message, status):
    return jsonify(error=message), status


def _valid_match(match):
    return bool(MATCH_ID.fullmatch(match))


def _decode_src(src):
    padded = src.strip()
    padded += "=" * ((-len(padded)) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        uri = raw.decode("utf-8").strip()
    except (ValueError, UnicodeDecodeError):
        return None
    if not uri.startswith("s3://") or not uri[5:]:
        return None
    return uri


def _iter_upstream(upstream):
    try:
        while True:
            chunk = upstream.raw.read(CHUNK)
            if not chunk:
                break
            yield chunk
    finally:
        upstream.close()


def _proxy_video(uri, allow_relogin):
    token = _current_token()
    if not token:
        try:
            login()
        except RuntimeError:
            log.warning("video proxy login failed")
            return _json_error("upstream auth failed", 502)
        token = _current_token()
        if not token:
            return _json_error("upstream auth failed", 502)

    headers = {}
    range_header = request.headers.get("Range")
    if range_header:
        headers["Range"] = range_header

    try:
        upstream = _http().get(
            f"{VSS_URL}/api/v1/videos/stream",
            params={"source": uri, "token": token},
            headers=headers,
            stream=True,
            timeout=(10, 300),
        )
    except requests.RequestException:
        log.warning("video upstream request failed")
        return _json_error("upstream unavailable", 502)

    # Do not log upstream.url: it carries the JWT.
    if upstream.status_code == 401 and allow_relogin:
        upstream.close()
        try:
            login()
        except RuntimeError:
            log.warning("video proxy re-login failed")
            return _json_error("upstream auth failed", 502)
        return _proxy_video(uri, allow_relogin=False)

    if upstream.status_code not in (200, 206):
        status = upstream.status_code
        upstream.close()
        if status == 404:
            return _json_error("not found", 404)
        return _json_error("upstream error", status)

    upstream.raw.decode_content = False
    passthrough = {}
    for name in STREAM_HEADERS:
        value = upstream.headers.get(name)
        if value:
            passthrough[name] = value
    ctype = passthrough.get("Content-Type", "")
    ctype_base = ctype.split(";")[0].strip().lower()
    if ctype_base in ("", "application/octet-stream", "binary/octet-stream"):
        if str(uri).lower().split("?", 1)[0].endswith(".mp4"):
            passthrough["Content-Type"] = "video/mp4"

    return Response(
        _iter_upstream(upstream),
        status=upstream.status_code,
        headers=passthrough,
        direct_passthrough=True,
    )


@app.get("/health")
def health():
    return jsonify(status="ok")


@app.get("/matches")
def matches():
    index_path = DATA_DIR / "index.json"
    if not index_path.is_file():
        return _json_error("index not found", 404)
    return send_from_directory(DATA_DIR, "index.json")


@app.get("/data/<match>/<name>.json")
def match_data(match, name):
    if (name not in ALLOWED_NAMES and not PART_MAP.fullmatch(name)) or not _valid_match(match):
        return _json_error("not found", 404)
    if DATA_URL:
        return _fetch_remote_json(match, name)
    filename = f"{name}.json"
    path = DATA_DIR / match / filename
    if not path.is_file():
        return _json_error("not found", 404)
    return send_from_directory(DATA_DIR / match, filename)


def _fetch_remote_json(match, name):
    url = f"{DATA_URL}/{match}/{name}.json"
    try:
        upstream = _http().get(url, stream=True, timeout=(10, 60))
    except requests.RequestException:
        log.warning("data fetch failed")
        return _json_error("upstream unavailable", 502)
    if upstream.status_code == 404:
        upstream.close()
        return _json_error("not found", 404)
    if upstream.status_code != 200:
        upstream.close()
        return _json_error("upstream error", 502)
    upstream.raw.decode_content = True
    return Response(
        _iter_upstream(upstream),
        status=200,
        mimetype="application/json",
    )


@app.get("/video")
def video():
    src = request.args.get("src", "")
    if not src:
        return _json_error("missing src", 400)
    uri = _decode_src(src)
    if uri is None:
        return _json_error("bad src", 400)
    if not VSS_URL:
        return _json_error("upstream unavailable", 502)
    return _proxy_video(uri, allow_relogin=True)


def _search(query, camera_id, allow_relogin):
    """POST /api/v1/search. Never put the JWT in the response body or logs."""
    token = _current_token()
    if not token:
        try:
            login()
        except RuntimeError:
            log.warning("search login failed")
            return _json_error("upstream auth failed", 502)
        token = _current_token()
        if not token:
            return _json_error("upstream auth failed", 502)

    body = {"query": query, "top_k": 6, "min_similarity": 0.3}
    if camera_id:
        body["metadata_filters"] = {"camera_id": camera_id}

    try:
        upstream = _http().post(
            f"{VSS_URL}/api/v1/search",
            json=body,
            headers={"Authorization": f"Bearer {token}"},
            timeout=(10, 60),
        )
    except requests.RequestException:
        log.warning("search upstream request failed")
        return _json_error("upstream unavailable", 502)

    try:
        if upstream.status_code == 401 and allow_relogin:
            upstream.close()
            try:
                login()
            except RuntimeError:
                log.warning("search re-login failed")
                return _json_error("upstream auth failed", 502)
            return _search(query, camera_id, allow_relogin=False)

        if upstream.status_code != 200:
            log.warning("search upstream status %s", upstream.status_code)
            return _json_error("upstream error", 502)

        try:
            payload = upstream.json()
        except ValueError:
            return _json_error("upstream error", 502)
        return jsonify(payload)
    finally:
        upstream.close()


@app.get("/similar")
def similar():
    query = request.args.get("q", "").strip()
    if not query:
        return _json_error("missing q", 400)
    camera_id = request.args.get("camera_id", "").strip()
    if not VSS_URL:
        return _json_error("upstream unavailable", 502)
    return _search(query, camera_id, allow_relogin=True)


@app.get("/")
def index_page():
    return send_from_directory(STATIC_DIR, "index.html")


@app.get("/<path:filename>")
def static_files(filename):
    return send_from_directory(STATIC_DIR, filename)


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    # Upstream URLs contain the JWT. Keep HTTP client logs off.
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    try:
        login()
        log.info("logged in to vss")
    except RuntimeError:
        log.warning("startup login failed; video will retry on request")
    app.run(host="0.0.0.0", port=PORT, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
