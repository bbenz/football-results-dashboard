#!/usr/bin/env bash
# Shared helpers for demo/scripts/*.sh. Source it; it sets ROOT and PYTHON.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ -x "$ROOT/.venv/Scripts/python.exe" ]]; then PYTHON="$ROOT/.venv/Scripts/python.exe"; else PYTHON="$ROOT/.venv/bin/python"; fi
TOKEN_FILE="$ROOT/.local/secrets/tokens.json"
TOKEN_SCOPES=("https://ai.azure.com/.default")
REFRESH_PID_FILE="$ROOT/.local/secrets/refresh.pid"

# Load KEY=VALUE lines from .env without overriding variables that are already set. Values are never printed.
if [[ -f "$ROOT/.env" ]]; then
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    if [[ "$line" =~ ^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*=[[:space:]]*(.*)$ ]]; then
      name="${BASH_REMATCH[1]}"; value="${BASH_REMATCH[2]}"; value="${value%\"}"; value="${value#\"}"
      [[ -n "$value" && -z "${!name:-}" ]] && export "$name=$value"
    fi
  done < "$ROOT/.env"
fi
export PYTHONPATH="$ROOT/demo/src" PYTHONUTF8=1
cd "$ROOT"

system_python() {
  for candidate in python3 python py; do command -v "$candidate" >/dev/null 2>&1 && { echo "$candidate"; return; }; done
  echo "Python 3.12 is not on PATH" >&2; exit 1
}

run_cli() {
  [[ -x "$PYTHON" ]] || { echo "No .venv yet: run demo bootstrap first." >&2; exit 1; }
  "$PYTHON" -m football_insights "$@"
}

compose() {
  # Compose resolves relative paths against demo/docker, so hand it the data folder as an absolute path.
  local data="${FOOTBALL_DATA_DIR:-data}"
  [[ "$data" = /* || "$data" =~ ^[A-Za-z]: ]] || data="$ROOT/$data"
  export FOOTBALL_DATA_DIR_HOST="$data"
  local args=(-f "$ROOT/demo/docker/compose.yaml")
  [[ -f "$ROOT/.env" ]] && args=(--env-file "$ROOT/.env" "${args[@]}")
  docker compose "${args[@]}" "$@"
}

wait_http() {
  local url="$1" timeout="${2:-120}" start
  start=$(date +%s)
  until [[ "$(curl -s -o /dev/null -w '%{http_code}' "$url" || true)" == "200" ]]; do
    (( $(date +%s) - start > timeout )) && { echo "timed out waiting for $url" >&2; exit 1; }
    sleep 2
  done
}

update_token_file() {
  # Short-lived access tokens from the operator's own Azure CLI sign-in, one per scope; never printed.
  mkdir -p "$(dirname "$TOKEN_FILE")"
  local body="{" first=1 scope json
  for scope in "${TOKEN_SCOPES[@]}"; do
    json="$(az account get-access-token --scope "$scope" --query '{token: accessToken, expires_on: expires_on}' -o json)"
    [[ $first -eq 1 ]] || body+=","
    body+="\"$scope\": $json"; first=0
  done
  printf '%s}' "$body" > "$TOKEN_FILE.tmp" && mv -f "$TOKEN_FILE.tmp" "$TOKEN_FILE"
  echo "token file refreshed"
}

start_token_refresh() {
  stop_token_refresh
  # Detached from this command's output, so a caller that pipes it (for example into tee) isn't held open by the loop.
  ( while true; do sleep 900; update_token_file >/dev/null 2>&1; done ) </dev/null >/dev/null 2>&1 &
  echo $! > "$REFRESH_PID_FILE"
  echo "token refresh running every 15 minutes in the background (demo down stops it)"
}

stop_token_refresh() {
  if [[ -f "$REFRESH_PID_FILE" ]]; then kill "$(cat "$REFRESH_PID_FILE")" 2>/dev/null || true; rm -f "$REFRESH_PID_FILE"; fi
}
