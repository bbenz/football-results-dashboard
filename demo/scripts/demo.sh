#!/usr/bin/env bash
# Operator commands for the football insights demo (bash equivalent of demo.ps1).
#
#   ./demo/scripts/demo.sh <command> [options]      or   source ./demo/scripts/aliases.sh; demo <command>
#
# Local commands
#   bootstrap     Create .venv and install the pinned development dependencies.
#   download      Optional: fetch the Kaggle datasets into data/ (see data/README.md).
#   verify        Check the raw data under FOOTBALL_DATA_DIR (default data/) against the contract.
#   ingest        Build and publish a curated version into CURATED_DIR (default .local/curated).
#   up            Build the three images and start Docker Compose (web on http://127.0.0.1:8080).
#                 --live-model: also give insights a short-lived Foundry token from your own sign-in.
#   down          Stop Docker Compose and delete any local token file.
#   logs          Show the last Compose log lines.
#   test          Run the no-data guard, ruff, mypy, and the tests.
#   pytest        Run only the named tests, for example: demo pytest tests/test_q3_trends.py
#   guard         Run the no-data guard on the index and the full history.
#   install-hook  Optional: install a git pre-commit hook that runs the no-data guard.
#
# Model commands (need a Foundry project; see docs/METHODS.md)
#   eval          Run the evaluation suite against the model deployments.
#   capture       Save labeled narratives of the prepared questions for the offline fallback.
#
# Azure commands (not run by local setup)
#   azure-foundation, azure-platform, upload-data, build-push, aks-deploy, aca-deploy,
#   ingest-aks, ingest-aca, smoke, parity, snapshot [aks|aca|both|local], load-test [aks|aca|both], rollout-v2,
#   rollback [aks|aca|both], trace <id>, preflight, reset, allow-ip, switch-model <deployment>, teardown --dry-run
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
source "$(dirname "${BASH_SOURCE[0]}")/azure.sh"

command="${1:-help}"
shift || true

case "$command" in
  bootstrap)
    [[ -x "$PYTHON" ]] || "$(system_python)" -m venv "$ROOT/.venv"
    "$PYTHON" -m pip install --quiet --upgrade pip
    "$PYTHON" -m pip install --quiet --require-hashes -r "$ROOT/demo/requirements-dev.lock"
    echo "bootstrap OK: .venv ready. Next: demo verify"
    ;;
  download) run_cli download-data "$@" ;;
  verify) run_cli verify-data "$@" ;;
  ingest) run_cli ingest "$@" ;;
  eval) run_cli eval "$@" ;;
  capture) run_cli capture-narratives "$@" ;;
  up)
    from_registry=0
    live_model=0
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --from-registry) from_registry=1; shift ;;
        --live-model) live_model=1; shift ;;
        *) shift ;;
      esac
    done
    if [[ $from_registry -eq 1 ]]; then
      set_demo_subscription
      import_digests
      az_checked acr login --name "$(required_env ACR_NAME)"
      registry="$("$PYTHON" -c 'import json; print(json.load(open(".local/deploy/digests.json"))["registry"])')"
      export WEB_IMAGE="${registry}/football-insights-web@${WEB_IMAGE_DIGEST}"
      export INSIGHTS_IMAGE="${registry}/football-insights-insights@${INSIGHTS_IMAGE_DIGEST}"
      export INGEST_IMAGE="${registry}/football-insights-ingest@${INGEST_IMAGE_DIGEST}"
      up_args=(up -d --no-build --pull always)
    else
      compose build
      WEB_IMAGE_DIGEST="$(docker image inspect football-insights-web:local --format '{{.Id}}')"
      INSIGHTS_IMAGE_DIGEST="$(docker image inspect football-insights-insights:local --format '{{.Id}}')"
      export WEB_IMAGE_DIGEST INSIGHTS_IMAGE_DIGEST
      up_args=(up -d)
    fi
    extra=()
    if [[ $live_model -eq 1 ]]; then
      [[ -n "${FOUNDRY_PROJECT_ENDPOINT:-}" ]] || { echo "demo up --live-model needs FOUNDRY_PROJECT_ENDPOINT in .env" >&2; exit 1; }
      update_token_file
      start_token_refresh
      extra=(-f "$ROOT/demo/docker/compose.live.yaml")
    fi
    compose "${extra[@]}" "${up_args[@]}"
    wait_http "http://127.0.0.1:8080/readyz" 180
    echo "up OK: http://127.0.0.1:8080  (web ${WEB_IMAGE_DIGEST:7:12}, insights ${INSIGHTS_IMAGE_DIGEST:7:12})"
    ;;
  down)
    stop_token_refresh
    compose -f "$ROOT/demo/docker/compose.live.yaml" down
    rm -f "$TOKEN_FILE"
    echo "down OK"
    ;;
  logs) compose logs --tail 40 "$@" ;;
  test)
    "$PYTHON" "$ROOT/demo/scripts/check_no_data.py"
    (cd "$ROOT/demo" && "$PYTHON" -m ruff check src tests scripts && "$PYTHON" -m mypy && "$PYTHON" -m pytest -q "$@")
    ;;
  pytest)
    # Only the named tests, without lint and type checks: for a quick check on stage.
    (cd "$ROOT/demo" && "$PYTHON" -m pytest -q "$@")
    ;;
  guard)
    "$PYTHON" "$ROOT/demo/scripts/check_no_data.py"
    "$PYTHON" "$ROOT/demo/scripts/check_no_data.py" --history
    ;;
  install-hook)
    cat > "$ROOT/.git/hooks/pre-commit" <<'HOOK'
#!/bin/sh
# Installed by demo install-hook: refuse commits that would add data.
for py in .venv/Scripts/python.exe .venv/bin/python python3 python; do
  if command -v "$py" >/dev/null 2>&1; then exec "$py" demo/scripts/check_no_data.py; fi
done
echo "no-data guard: no Python found; run demo bootstrap" >&2
exit 1
HOOK
    chmod +x "$ROOT/.git/hooks/pre-commit"
    echo "pre-commit hook installed: $ROOT/.git/hooks/pre-commit"
    ;;
  azure-foundation) azure_foundation ;;
  azure-platform) azure_platform ;;
  upload-data) upload_data ;;
  build-push)
    output=""
    while [[ $# -gt 0 ]]; do case "$1" in --output|-Output) output="${2:-}"; shift 2 ;; *) shift ;; esac; done
    build_push "$output"
    ;;
  aks-deploy) aks_deploy ;;
  aca-deploy) aca_deploy ;;
  ingest-aks) ingest_aks ;;
  ingest-aca) ingest_aca ;;
  smoke) smoke ;;
  parity) parity ;;
  snapshot) snapshot "${1:-both}" ;;
  load-test)
    platform="${1:-both}"; shift || true; rps=20; seconds=60
    while [[ $# -gt 0 ]]; do case "$1" in --rps|-Rps) rps="${2:-20}"; shift 2 ;; --seconds|-Seconds) seconds="${2:-60}"; shift 2 ;; *) shift ;; esac; done
    load_test "$platform" "$rps" "$seconds"
    ;;
  rollout-v2) rollout_v2 ;;
  rollback) rollback "${1:-both}" ;;
  trace) trace_cmd "${1:-}" ;;
  preflight) preflight ;;
  reset) reset_demo ;;
  allow-ip) allow_ip ;;
  switch-model) switch_model "${1:-}" ;;
  teardown) teardown "${1:-}" ;;
  *) awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print } /^set -euo/ { exit }' "${BASH_SOURCE[0]}" ;;
esac
