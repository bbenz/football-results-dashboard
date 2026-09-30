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
#   guard         Run the no-data guard on the index and the full history.
#   install-hook  Optional: install a git pre-commit hook that runs the no-data guard.
#
# Azure commands (not run by local setup)
#   azure-foundation, azure-platform, upload-data, build-push, aks-deploy, aca-deploy,
#   ingest-aks, ingest-aca, smoke, allow-ip, switch-model <deployment>, teardown --dry-run
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
  up)
    compose build
    WEB_IMAGE_DIGEST="$(docker image inspect football-insights-web:local --format '{{.Id}}')"
    INSIGHTS_IMAGE_DIGEST="$(docker image inspect football-insights-insights:local --format '{{.Id}}')"
    export WEB_IMAGE_DIGEST INSIGHTS_IMAGE_DIGEST
    extra=()
    if [[ "${1:-}" == "--live-model" ]]; then
      [[ -n "${FOUNDRY_PROJECT_ENDPOINT:-}" ]] || { echo "demo up --live-model needs FOUNDRY_PROJECT_ENDPOINT in .env" >&2; exit 1; }
      update_token_file
      start_token_refresh
      extra=(-f "$ROOT/demo/docker/compose.live.yaml")
    fi
    compose "${extra[@]}" up -d
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
  guard)
    "$PYTHON" "$ROOT/demo/scripts/check_no_data.py"
    "$PYTHON" "$ROOT/demo/scripts/check_no_data.py" --history
    ;;
  install-hook)
    printf '#!/bin/sh\n# Installed by demo install-hook: refuse commits that would add data.\nexec python demo/scripts/check_no_data.py\n' > "$ROOT/.git/hooks/pre-commit"
    chmod +x "$ROOT/.git/hooks/pre-commit"
    echo "pre-commit hook installed: $ROOT/.git/hooks/pre-commit"
    ;;
  azure-foundation) azure_foundation ;;
  azure-platform) azure_platform ;;
  upload-data) upload_data ;;
  build-push) build_push ;;
  aks-deploy) aks_deploy ;;
  aca-deploy) aca_deploy ;;
  ingest-aks) ingest_aks ;;
  ingest-aca) ingest_aca ;;
  smoke) smoke ;;
  allow-ip) allow_ip ;;
  switch-model) switch_model "${1:-}" ;;
  teardown) teardown "${1:-}" ;;
  *) sed -n '2,22p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' ;;
esac
