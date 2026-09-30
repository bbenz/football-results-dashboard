# Local setup

Everything here runs on your machine with no Azure account: download the data, verify it, build the curated store, and run the three services with Docker Compose. Commands are shown for PowerShell 7 first and bash second; run them from the repository root.

## Prerequisites

| Tool | Version used to verify these steps | Notes |
| --- | --- | --- |
| Python | 3.12 | On `PATH`. `python --version` should print 3.12.x. |
| Docker Desktop | 4.93 (Engine 29.8, Compose v5.5) | Linux containers. |
| Git | 2.53 | |
| PowerShell | 7.6 | Or bash 5 (Git Bash on Windows works). |

If your network blocks `files.pythonhosted.org`, point pip at a mirror: the Dockerfile accepts `--build-arg PIP_INDEX_URL=...`.

## 1. Bootstrap

```powershell
./demo/scripts/demo.ps1 bootstrap
. ./demo/scripts/aliases.ps1        # optional: adds the short `demo` command to this terminal
```

```bash
./demo/scripts/demo.sh bootstrap
source ./demo/scripts/aliases.sh    # optional: adds the short `demo` command to this shell
```

`bootstrap` creates `.venv` and installs the pinned, hash-checked dependencies from `demo/requirements-dev.lock`. The rest of this guide writes `demo <command>`; without the alias, use `./demo/scripts/demo.ps1 <command>` or `./demo/scripts/demo.sh <command>`.

Settings are environment variables, optionally in a `.env` file at the repository root. Copy `.env.example` to `.env` and fill in only what you need; every setting has a safe default for local use.

## 2. Get and verify the data

Follow [data/README.md](../data/README.md), then:

```text
demo verify
```

The last line should read `verify-data PASSED: 0 failure(s), 0 warning(s).` A failure names the file and the problem. A warning means your dataset version differs from the one this demo was verified against.

## 3. Run with Docker Compose

```text
demo up
```

This builds three images (`web`, `insights`, `ingest`), runs `ingest` once against a read-only mount of `data/`, starts `insights` (internal only) and `web`, and waits until the app is ready at <http://127.0.0.1:8080>. The environment badge shows `Local`, the short image digests, the curated data version, and `AI narrative: off`. The narrative stays off even if `.env` has a Foundry endpoint, because the containers get no credential unless you use `-LiveModel` (section 4).

Every insight card works without a model. Each card's **View** selector shows the other views of its question, including the development-lens views that use World Bank data. Without a model, the question box still shows the evidence and says that the AI narrative is off.

- `demo logs` shows the latest log lines (structured JSON).
- `demo down` stops everything.
- Only `web` publishes a port, and only on `127.0.0.1`.
- The curated store lives in a Docker volume; the raw data is never copied into an image.
- If <http://127.0.0.1:8080> stops answering after Docker Desktop restarts its engine, even though `docker ps` shows the containers healthy, run `demo down` and then `demo up`. Docker Desktop can fail to restore a port published only on `127.0.0.1`; recreating the containers restores it.

## 4. Use the live models (optional, needs Azure)

The question box needs a Microsoft Foundry project with the model deployments. [DEPLOYMENT.md](DEPLOYMENT.md) creates one with `demo azure-foundation`, which also gives your own account the Foundry User role on it. Then:

```powershell
az login
./demo/scripts/demo.ps1 up -LiveModel
```

```bash
az login
./demo/scripts/demo.sh up --live-model
```

Set `FOUNDRY_PROJECT_ENDPOINT` in `.env` first (`demo azure-foundation` prints it). Containers can't use your Azure CLI sign-in, so `-LiveModel` writes a short-lived access token from your sign-in to `.local/secrets/tokens.json` (ignored by git) and refreshes it every 15 minutes in the background. No key is involved anywhere. `demo down` stops the refresh and deletes the file.

## 5. Build the curated store without Docker (optional)

```text
demo ingest
```

`ingest` verifies the raw files, then writes a versioned curated store to `.local/curated/` (ignored by git): Parquet tables, a manifest with checksums, and a data-quality report. Running it again on the same inputs reuses the same version with identical checksums, on any operating system.

To run the services on your machine instead of in containers, open two terminals and run `python -m football_insights.insights` and `python -m football_insights.web` with `PYTHONPATH=demo/src`, from the repository root, using the Python in `.venv`. They listen on `127.0.0.1` only, unless you set `BIND_HOST`. Code running on your machine uses your Azure CLI sign-in for the models when `FOUNDRY_PROJECT_ENDPOINT` is set.

## 6. Tests and checks

```text
demo test
```

This runs the no-data guard, `ruff`, `mypy`, and `pytest`. Unit tests use small synthetic fixtures with fictional teams. Tests marked `realdata` also run when the downloaded data is present and are skipped otherwise.

- `demo pytest tests/test_q3_trends.py` runs only the named tests, without the other checks.
- Tests marked `live` call the model deployments with your own sign-in. They run only when `FOUNDRY_PROJECT_ENDPOINT` is set and the data is downloaded, and each run costs a little. They check that every question gets a live, grounded answer from each allowed deployment, and that repeated answers cite identical numbers.
- `demo guard` checks the index and the full git history for data files.
- `demo install-hook` adds a git pre-commit hook that runs the guard before every commit.

## Traces on your machine

Each page shows a copyable trace ID in the footer. Open `http://127.0.0.1:8080/trace/<trace ID>` to see the spans that `web` and `insights` recorded for that request, including every analytics tool call with its evidence IDs. Local runs also append spans to `.local/traces/*.jsonl`.
