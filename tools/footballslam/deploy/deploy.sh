#!/usr/bin/env bash
# NOTES_FOR_C
# - ConfigMap keys cannot contain '/'. Files are stored as f000, f001, ...
#   with manifest.txt mapping each key back to its path. The pod mounts that
#   ConfigMap read-only at /src and copies onto an emptyDir at /code, so the
#   start script can create static/ and data/ before python main.py.
#   main.py resolves static next to itself (/code/static). /matches and the
#   local data route use ./data from the working directory (/code/data).
# - GET /matches reads ./data/index.json and does not consult DATA_URL.
#   index.json is always packed when it exists. Every data/<scene>/*.json
#   that exists is packed too, including track_alerts.json and map_sim.json.
#   When those files would push the ConfigMap over 900KB, per-scene JSON is
#   not packed: it is uploaded to
#   s3://$S3_CHUNKS_BUCKET/footballslam/data/ and DATA_URL is set to the
#   path-style prefix $S3_ENDPOINT/$S3_CHUNKS_BUCKET/footballslam/data
#   (server fetches $DATA_URL/<match>/<name>.json). Objects are uploaded
#   with ACL public-read because the server GETs them with no AWS signature.
#   If the bucket rejects ACLs, those GETs can 403 until anonymous read is
#   allowed on that prefix.
# - Humans open https://workshop.thecosmoslabs.com and click App.
#   Do not send them to INGRESS_URL. No second hostname. No docker build.
# - VSS_URL inside the pod is the in-cluster backend Service, not INGRESS_URL.
#   From this cluster the lab host does not accept connections from pods.
# - No edit outside this file is required for the path above.

set -euo pipefail

APP_NAME=footballslam
APP_PORT=8080
LIMIT=$((900 * 1024))
S3_PREFIX=footballslam/data

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
APP_DIR="$ROOT/tools/footballslam/app"
DATA_DIR="$ROOT/tools/footballslam/data"

cfg_get() {
  local key=$1 line val
  line=$(grep -m1 "^${key}=" "$TEAM_CONFIG" || true)
  if [[ -z "$line" ]]; then
    printf ''
    return 0
  fi
  val=${line#*=}
  val=${val//$'\r'/}
  if [[ ${#val} -ge 2 && ${val:0:1} == '"' && ${val: -1} == '"' ]]; then
    val=${val:1:${#val}-2}
  fi
  printf '%s' "$val"
}

load_cfg() {
  local val
  val=$(cfg_get "$1")
  if [[ -z "$val" ]]; then
    echo "missing ${1} in team config" >&2
    exit 1
  fi
  printf -v "$2" '%s' "$val"
}

file_bytes() {
  stat -c%s "$1"
}

stage_as() {
  local src=$1 rel=$2 key
  case "$rel" in
    /*|../*|*/../*|*/..)
      echo "refusing to pack path ${rel}" >&2
      exit 1
      ;;
  esac
  printf -v key 'f%03d' "$STAGE_N"
  cp -L "$src" "$STAGE/$key"
  printf '%s\t%s\n' "$key" "$rel" >> "$STAGE/manifest.txt"
  STAGE_N=$((STAGE_N + 1))
}

upload_offload() {
  if ! python3 -c 'import boto3' >/dev/null 2>&1; then
    python3 -m pip install --quiet --disable-pip-version-check --target "$WORKDIR/py" boto3
    export PYTHONPATH="$WORKDIR/py${PYTHONPATH:+:$PYTHONPATH}"
  fi
  python3 - <<'PY'
import os
import sys

import boto3
from botocore.config import Config

endpoint = os.environ["S3_ENDPOINT"].rstrip("/")
bucket = os.environ["S3_CHUNKS_BUCKET"]
prefix = os.environ["S3_PREFIX"].strip("/")
items = []
with open(os.environ["S3_FILE_LIST"], encoding="utf-8") as handle:
    for line in handle:
        line = line.rstrip("\n")
        if not line:
            continue
        rel, path = line.split("\t", 1)
        items.append((rel, path))

client = boto3.client(
    "s3",
    endpoint_url=endpoint,
    aws_access_key_id=os.environ["ACCESS_KEY"],
    aws_secret_access_key=os.environ["SECRET_KEY"],
    region_name="us-east-1",
    config=Config(
        signature_version="s3v4",
        s3={"addressing_style": "path"},
        retries={"max_attempts": 3, "mode": "standard"},
    ),
)


def put_all(use_acl):
    for rel, path in items:
        extra = {"ContentType": "application/json"}
        if use_acl:
            extra["ACL"] = "public-read"
        client.upload_file(path, bucket, f"{prefix}/{rel}", ExtraArgs=extra)


try:
    put_all(True)
except Exception:
    try:
        put_all(False)
    except Exception as exc:
        # Class name only. str(exc) can contain the access key.
        print("s3 upload failed", type(exc).__name__, file=sys.stderr)
        sys.exit(1)
    print(
        "warning: public-read ACL was rejected; anonymous GET may fail",
        file=sys.stderr,
    )

print(f"uploaded {len(items)} objects", file=sys.stderr)
PY
}

write_start_script() {
  cat > "$WORKDIR/start.sh" <<'EOS'
set -euo pipefail
while IFS=$'\t' read -r key rel || [[ -n "${key:-}" ]]; do
  [[ -n "${key:-}" ]] || continue
  dest="/code/${rel}"
  mkdir -p "$(dirname "$dest")"
  cp -L "/src/${key}" "$dest"
done < /src/manifest.txt
cd /code
if [[ -f requirements.txt ]]; then
  pip install --no-cache-dir -q -r requirements.txt
fi
exec python main.py
EOS
}

write_workload() {
  local data_env=""
  if [[ "$OFFLOAD" -eq 1 ]]; then
    data_env="        - name: DATA_URL
          valueFrom:
            secretKeyRef:
              name: ${APP_NAME}-vss-creds
              key: DATA_URL"
  fi

  cat > "$WORKDIR/workload.yaml" <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ${APP_NAME}
  namespace: ${NS}
  labels:
    app: ${APP_NAME}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: ${APP_NAME}
  template:
    metadata:
      labels:
        app: ${APP_NAME}
    spec:
      containers:
      - name: app
        image: python:3.12-slim
        imagePullPolicy: IfNotPresent
        ports:
        - containerPort: ${APP_PORT}
        env:
        - name: PORT
          value: "${APP_PORT}"
        - name: VSS_URL
          valueFrom:
            secretKeyRef:
              name: ${APP_NAME}-vss-creds
              key: VSS_URL
        - name: VSS_USERNAME
          valueFrom:
            secretKeyRef:
              name: ${APP_NAME}-vss-creds
              key: VSS_USERNAME
        - name: VSS_PASSWORD
          valueFrom:
            secretKeyRef:
              name: ${APP_NAME}-vss-creds
              key: VSS_PASSWORD
${data_env}
        volumeMounts:
        - name: src
          mountPath: /src
          readOnly: true
        - name: work
          mountPath: /code
        workingDir: /code
        command: ["bash", "-c"]
        args:
        - |
EOF
  sed 's/^/          /' "$WORKDIR/start.sh" >> "$WORKDIR/workload.yaml"
  cat >> "$WORKDIR/workload.yaml" <<EOF
        readinessProbe:
          httpGet:
            path: /health
            port: ${APP_PORT}
          initialDelaySeconds: 10
          periodSeconds: 10
      volumes:
      - name: src
        configMap:
          name: ${APP_NAME}-code
      - name: work
        emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: ${APP_NAME}
  namespace: ${NS}
  labels:
    app: ${APP_NAME}
spec:
  selector:
    app: ${APP_NAME}
  ports:
  - name: http
    port: 80
    targetPort: ${APP_PORT}
  type: ClusterIP
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: ${APP_NAME}
  namespace: ${NS}
  labels:
    app: ${APP_NAME}
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /\$2
spec:
  ingressClassName: nginx
  rules:
  - host: ${APP_HOST}
    http:
      paths:
      - path: /app(/|$)(.*)
        pathType: ImplementationSpecific
        backend:
          service:
            name: ${APP_NAME}
            port:
              number: 80
EOF
}

mapfile -t TEAM_CONFIGS < <(find /config -maxdepth 1 -type f -name '*.config' | sort)
(( ${#TEAM_CONFIGS[@]} == 1 )) || { echo "expected exactly one /config/*.config" >&2; exit 1; }
TEAM_CONFIG="${TEAM_CONFIGS[0]}"

load_cfg USERNAME USERNAME
load_cfg PASSWORD PASSWORD
load_cfg INGRESS_URL INGRESS_URL

[[ "$USERNAME" == team-* ]] || { echo "USERNAME does not start with team-" >&2; exit 1; }
NS="$USERNAME"
TEAM_N="${USERNAME#team-}"
APP_HOST="video-lab-team-${TEAM_N}.cosmos.vastdata.com"
export KUBECONFIG="/config/${NS}-k8s.yaml"
[[ -f "$KUBECONFIG" ]] || { echo "missing kubeconfig /config/${NS}-k8s.yaml" >&2; exit 1; }

[[ -f "$APP_DIR/main.py" ]] || { echo "missing tools/footballslam/app/main.py" >&2; exit 1; }

WORKDIR=$(mktemp -d)
STAGE="$WORKDIR/stage"
mkdir -p "$STAGE"
trap 'rm -rf "$WORKDIR"' EXIT
: > "$STAGE/manifest.txt"
STAGE_N=0

code_bytes=$(file_bytes "$APP_DIR/main.py")
stage_as "$APP_DIR/main.py" "main.py"
if [[ -f "$APP_DIR/requirements.txt" ]]; then
  code_bytes=$((code_bytes + $(file_bytes "$APP_DIR/requirements.txt")))
  stage_as "$APP_DIR/requirements.txt" "requirements.txt"
fi

static_n=0
if [[ -d "$APP_DIR/static" ]]; then
  while IFS= read -r -d '' src; do
    rel=${src#"$APP_DIR/static/"}
    if [[ "$(basename "$rel")" == "NOTES_FOR_C.md" ]]; then
      continue
    fi
    code_bytes=$((code_bytes + $(file_bytes "$src")))
    stage_as "$src" "static/${rel}"
    static_n=$((static_n + 1))
  done < <(find "$APP_DIR/static" -type f -print0 | sort -z)
fi
if (( static_n == 0 )); then
  echo "warning: no static files packed" >&2
fi
if (( code_bytes > LIMIT )); then
  echo "app code is ${code_bytes} bytes and exceeds the 900KB ConfigMap budget" >&2
  exit 1
fi

declare -a JSON_ABS=()
declare -a JSON_REL=()
json_bytes=0
add_json() {
  JSON_ABS+=("$1")
  JSON_REL+=("$2")
  json_bytes=$((json_bytes + $(file_bytes "$1")))
}
if [[ -f "$DATA_DIR/index.json" ]]; then
  add_json "$DATA_DIR/index.json" "index.json"
fi
# Every scene file, not an allowlist. track_alerts.json and map_sim.json
# are packed or offloaded with the rest when they exist.
if [[ -d "$DATA_DIR" ]]; then
  while IFS= read -r -d '' src; do
    add_json "$src" "${src#"$DATA_DIR/"}"
  done < <(find "$DATA_DIR" -mindepth 2 -maxdepth 2 -type f \( -name '*.json' -o -name 'track_alerts.json' -o -name 'map_sim.json' \) -print0 | sort -z)
fi

OFFLOAD=0
DATA_URL=""
if (( json_bytes > 0 && code_bytes + json_bytes > LIMIT )); then
  OFFLOAD=1
fi

if (( OFFLOAD == 0 )); then
  if ((${#JSON_ABS[@]} > 0)); then
    for i in "${!JSON_ABS[@]}"; do
      stage_as "${JSON_ABS[$i]}" "data/${JSON_REL[$i]}"
    done
  fi
  echo "data: packed in the ConfigMap" >&2
else
  index_bytes=0
  if ((${#JSON_ABS[@]} > 0)); then
    for i in "${!JSON_ABS[@]}"; do
      if [[ "${JSON_REL[$i]}" == "index.json" ]]; then
        index_bytes=$(file_bytes "${JSON_ABS[$i]}")
        stage_as "${JSON_ABS[$i]}" "data/index.json"
      fi
    done
  fi
  if (( code_bytes + index_bytes > LIMIT )); then
    echo "index.json does not fit in the ConfigMap with the app code" >&2
    exit 1
  fi

  load_cfg S3_ENDPOINT S3_ENDPOINT
  load_cfg ACCESS_KEY ACCESS_KEY
  load_cfg SECRET_KEY SECRET_KEY
  load_cfg S3_CHUNKS_BUCKET S3_CHUNKS_BUCKET
  case "$S3_ENDPOINT" in
    http://*|https://*) ;;
    *)
      echo "S3_ENDPOINT must start with http:// or https://" >&2
      exit 1
      ;;
  esac
  DATA_URL="${S3_ENDPOINT%/}/${S3_CHUNKS_BUCKET}/${S3_PREFIX}"

  : > "$WORKDIR/s3-files.txt"
  if ((${#JSON_ABS[@]} > 0)); then
    for i in "${!JSON_ABS[@]}"; do
      printf '%s\t%s\n' "${JSON_REL[$i]}" "${JSON_ABS[$i]}" >> "$WORKDIR/s3-files.txt"
    done
  fi
  export S3_ENDPOINT ACCESS_KEY SECRET_KEY S3_CHUNKS_BUCKET S3_PREFIX
  export S3_FILE_LIST="$WORKDIR/s3-files.txt"
  upload_offload
  unset ACCESS_KEY SECRET_KEY
  echo "data: s3 offload; index.json packed in the ConfigMap" >&2
fi

umask 077
{
  printf 'VSS_URL=%s\n' "http://video-backend-service.${NS}.svc.cluster.local:8000"
  printf 'VSS_USERNAME=%s\n' "$USERNAME"
  printf 'VSS_PASSWORD=%s\n' "$PASSWORD"
  if [[ "$OFFLOAD" -eq 1 ]]; then
    printf 'DATA_URL=%s\n' "$DATA_URL"
  fi
} > "$WORKDIR/secret.env"

kubectl -n "$NS" create configmap "${APP_NAME}-code" \
  --from-file="$STAGE" \
  --dry-run=client -o yaml > "$WORKDIR/configmap.yaml"
kubectl -n "$NS" create secret generic "${APP_NAME}-vss-creds" \
  --from-env-file="$WORKDIR/secret.env" \
  --dry-run=client -o yaml > "$WORKDIR/secret.yaml"

write_start_script
write_workload

{
  cat "$WORKDIR/configmap.yaml"
  printf '\n---\n'
  cat "$WORKDIR/secret.yaml"
  printf '\n---\n'
  cat "$WORKDIR/workload.yaml"
} > "$WORKDIR/all.yaml"

if ! kubectl apply --server-side --force-conflicts --field-manager=footballslam-deploy -f "$WORKDIR/all.yaml"; then
  echo "server-side apply failed; recreating objects" >&2
  kubectl -n "$NS" delete \
    "configmap/${APP_NAME}-code" \
    "secret/${APP_NAME}-vss-creds" \
    "deploy/${APP_NAME}" \
    "service/${APP_NAME}" \
    "ingress/${APP_NAME}" \
    --ignore-not-found
  kubectl apply -f "$WORKDIR/all.yaml"
fi

kubectl -n "$NS" rollout restart "deploy/${APP_NAME}"
set +e
kubectl -n "$NS" rollout status "deploy/${APP_NAME}"
status=$?
set -e

printf 'namespace: %s\n' "$NS"
printf 'app host: %s\n' "$APP_HOST"
printf 'rollout: KUBECONFIG=/config/%s-k8s.yaml kubectl -n %s rollout status deploy/%s\n' \
  "$NS" "$NS" "$APP_NAME"
exit "$status"
