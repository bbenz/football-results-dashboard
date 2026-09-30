"""Command line: python -m football_insights <command>.

Commands:
  download-data Optional: fetch the two Kaggle datasets into the data folder.
  verify-data   Check the raw downloads against the data contract.
  ingest        Verify, build, and publish a curated version.
  dq-report     Print the data-quality report of the active curated version.
  tool          Run one deterministic analytics tool and print its result.
  tools         List the tools the insights agent can call.
  eval          Run the evaluation suite against the live model deployments.
  capture-narratives  Save labeled narratives for the offline fallback tier.
  load-test     Bounded load on deterministic pages (never the model).
  parity        Compare deterministic card results across web endpoints (AKS and ACA).
  snapshot      Save a web endpoint's pages, openable offline, for the fallback tiers.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from .config import get_settings


def _download(args: argparse.Namespace) -> int:
    from .data.download import DownloadError, download

    settings = get_settings()
    root = Path(args.data_dir) if args.data_dir else settings.football_data_dir
    keys = ["football", "wdi"] if args.dataset == "all" else [args.dataset]
    for key in keys:
        try:
            written = download(key, root, latest=args.latest)
        except DownloadError as exc:
            print(f"download-data FAILED: {exc}", file=sys.stderr)
            return 1
        print(f"download-data: {key}: wrote {len(written)} files under {root}")
    print("Next: demo verify")
    return 0


def _verify(args: argparse.Namespace) -> int:
    from .data.verify import render, verify

    settings = get_settings()
    report = verify(Path(args.data_dir) if args.data_dir else settings.football_data_dir)
    if args.json:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        print(render(report))
    return 0 if report.ok else 1


def _ingest(args: argparse.Namespace) -> int:
    from .ingest.pipeline import IngestError, run
    from .ingest.storage import BlobRawSource, LocalRawSource, RawSource
    from .store import storage_for

    settings = get_settings()
    raw: RawSource
    if args.source == "blob":
        if not settings.storage_account_url:
            print("ingest --source blob needs STORAGE_ACCOUNT_URL", file=sys.stderr)
            return 2
        raw = BlobRawSource(settings.storage_account_url, settings.raw_container)
    else:
        raw = LocalRawSource(Path(args.data_dir) if args.data_dir else settings.football_data_dir)
    storage = storage_for(settings)
    print(f"ingest: raw from {raw.description}; curated to {storage.description}")
    try:
        result = run(raw, storage, platform=settings.platform_name)
    except IngestError as exc:
        print(f"ingest FAILED: {exc}", file=sys.stderr)
        return 1
    dq = result.data_quality
    action = "reused existing" if result.reused else "published new"
    label = result.manifest["dataset_label"]
    print(f"ingest OK in {result.duration_s:.1f}s: {action} version {result.version} ({label})")
    print(f"  matches {dq['matches']['rows']:,} ({dq['matches']['first_date']} to {dq['matches']['last_date']}), "
          f"teams {dq['matches']['teams']}, goals with timelines "
          f"{dq['goalscorers']['coverage_of_scoring_matches_pct']}% of scoring matches")
    print(f"  crosswalk: both teams mapped in {dq['crosswalk']['both_teams_mapped_pct']}% of matches; "
          f"unreviewed teams: {len(dq['crosswalk']['unreviewed_teams'])}")
    for name, info in sorted(result.manifest["outputs"].items()):
        print(f"  {name:22} {info['bytes']:>10,} bytes  sha256 {info['sha256'][:16]}...")
    return 0


def _dq(args: argparse.Namespace) -> int:
    from .store import load

    store = load(get_settings())
    print(json.dumps(store.data_quality, indent=2, sort_keys=True))
    return 0


def _tool(args: argparse.Namespace) -> int:
    from .analytics.context import ToolContext
    from .analytics.registry import run_tool
    from .store import load

    params: dict[str, object] = {}
    for item in args.param or []:
        key, _, value = item.partition("=")
        params[key] = int(value) if value.isdigit() else value
    ctx = ToolContext(load(get_settings()))
    result = run_tool(ctx, args.name, params)
    print(result.model_dump_json(indent=2))
    return 0


def _tools(args: argparse.Namespace) -> int:
    from .analytics.registry import TOOLS

    for spec in TOOLS.values():
        print(f"{spec.name:22} Q{spec.question}  {spec.description.splitlines()[0][:100]}")
    return 0


def _local_agent() -> tuple[Any, Any]:
    from .agent.loop import InsightsAgent
    from .analytics.context import ToolContext
    from .analytics.registry import run_tool
    from .store import load

    settings = get_settings()
    if not settings.foundry_project_endpoint:
        raise SystemExit("set FOUNDRY_PROJECT_ENDPOINT (and sign in with az login) to call the live model")
    ctx = ToolContext(load(settings))
    return InsightsAgent(settings, lambda name, a: (run_tool(ctx, name, a), 0.0)), ctx


def _url_asker(url: str) -> Any:
    import httpx

    from .schemas import Answer

    endpoint = url.rstrip("/") + "/api/ask"

    def ask(question: str, deployment: str) -> Answer:
        # The public API always uses the endpoint's configured deployment; this checks it is the one requested.
        for _ in range(4):
            response = httpx.post(endpoint, json={"question": question}, timeout=120)
            if response.status_code == 429:
                time.sleep(61)
                continue
            response.raise_for_status()
            answer = Answer.model_validate(response.json())
            if answer.model and answer.model.deployment != deployment:
                raise SystemExit(f"{url} serves {answer.model.deployment}, not {deployment}. Run "
                                 f"`demo switch-model {deployment}` first, or pass --deployments "
                                 f"{answer.model.deployment}.")
            return answer
        raise SystemExit(f"rate limited repeatedly by {endpoint}")

    return ask


def _eval(args: argparse.Namespace) -> int:
    from . import evaluation
    from .analytics.registry import run_tool

    settings = get_settings()
    cases = [c for c in evaluation.load_cases() if not args.category or c.category in args.category.split(",")]
    cases = cases[: args.limit] if args.limit else cases
    deployments = args.deployments.split(",") if args.deployments else settings.allowed_deployments
    if args.target == "url":
        from .analytics.context import ToolContext
        from .store import load

        ctx = ToolContext(load(settings))
        ask = _url_asker(args.url)
    else:
        agent, ctx = _local_agent()
        ask = agent.answer
    print(f"eval: {len(cases)} cases x {len(deployments)} deployments x {args.repeats} repeats against {args.target}")
    results = evaluation.run(cases, ask, deployments, args.repeats, run_tool=lambda n, a: run_tool(ctx, n, a),
                             on_result=lambda r: print(f"  {r.deployment:12} {r.case_id:22} tool={r.tool_ok!s:5} "
                                                       f"grounded={r.grounding_ok!s:5} {r.wall_seconds:6.1f}s"))
    summary = evaluation.summarize(results)
    path = evaluation.write_report(results, summary, Path(args.out) if args.out else settings.evidence_dir / "eval",
                                   f"{args.target}-{'-'.join(deployments)}")
    print(evaluation.render(summary))
    print(f"report: {path}")
    return 0


def _parity(args: argparse.Namespace) -> int:
    import httpx

    from . import parity

    try:
        report = parity.run(args.url)
    except (ValueError, httpx.HTTPError) as exc:
        print(f"parity could not run: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report.as_dict(), indent=2))
    print("parity OK: identical deterministic results" if report.identical
          else f"parity FAILED: {len(report.differences)} difference(s)", file=sys.stderr)
    return 0 if report.identical else 1


def _snapshot(args: argparse.Namespace) -> int:
    from . import snapshot

    settings = get_settings()
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    out = Path(args.out) if args.out else settings.evidence_dir / "replay" / f"{args.label}-{stamp}"
    snap = snapshot.run(args.url, out, include_answers=not args.no_answers)
    for failure in snap.failed:
        print(f"  NOT saved {failure}", file=sys.stderr)
    print(f"snapshot: saved {len(snap.saved)} pages from {snap.url} to {out} (open index.html offline)")
    return 1 if snap.failed else 0


def _load(args: argparse.Namespace) -> int:
    from . import loadtest

    try:
        result = loadtest.run(args.url, args.rps, args.seconds)
    except ValueError as exc:
        print(f"load-test refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result.summary(), indent=2))
    return 0


def _capture(args: argparse.Namespace) -> int:
    from datetime import UTC, datetime

    from . import evaluation
    from .agent import narratives

    settings = get_settings()
    agent, _ = _local_agent()
    saved = 0
    for case in (c for c in evaluation.load_cases() if c.capture):
        answer = agent.answer(case.question, args.deployment)
        if answer.narrative_status == "live" and answer.grounding.status in ("passed", "passed_after_retry"):
            narratives.save(settings.narrative_cache_dir, answer, datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"))
            saved += 1
            print(f"  captured {case.id}")
        else:
            print(f"  NOT captured {case.id}: {answer.narrative_status}, grounding {answer.grounding.status}")
    print(f"capture-narratives: saved {saved} labeled narratives to {settings.narrative_cache_dir}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m football_insights", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("download-data", help="optional: fetch the Kaggle datasets into the data folder")
    p.add_argument("--dataset", choices=("all", "football", "wdi"), default="all")
    p.add_argument("--latest", action="store_true", help="take Kaggle's current version, not the verified one")
    p.add_argument("--data-dir", help="target folder (default: FOOTBALL_DATA_DIR or data)")
    p.set_defaults(func=_download)

    p = sub.add_parser("verify-data", help="check the raw downloads")
    p.add_argument("--data-dir", help="raw data folder (default: FOOTBALL_DATA_DIR or data)")
    p.add_argument("--json", action="store_true", help="print the full report as JSON")
    p.set_defaults(func=_verify)

    p = sub.add_parser("ingest", help="build and publish a curated version")
    p.add_argument("--source", choices=("local", "blob"), default="local")
    p.add_argument("--data-dir", help="raw data folder for --source local")
    p.set_defaults(func=_ingest)

    p = sub.add_parser("dq-report", help="print the active version's data-quality report")
    p.set_defaults(func=_dq)

    p = sub.add_parser("tool", help="run one analytics tool")
    p.add_argument("name")
    p.add_argument("--param", action="append", help="key=value, repeatable")
    p.set_defaults(func=_tool)

    p = sub.add_parser("tools", help="list the analytics tools")
    p.set_defaults(func=_tools)

    p = sub.add_parser("eval", help="run the evaluation suite against the live model deployments")
    p.add_argument("--target", choices=("local", "url"), default="local",
                   help="local: in-process agent with your sign-in; url: a deployed web endpoint")
    p.add_argument("--url", help="base URL of a deployed web service for --target url")
    p.add_argument("--deployments", help="comma-separated deployments (default: AI_ALLOWED_DEPLOYMENTS)")
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--category", help="comma-separated categories, e.g. q1,q6,limitation")
    p.add_argument("--limit", type=int, help="run only the first N cases")
    p.add_argument("--out", help="output folder (default: EVIDENCE_DIR/eval)")
    p.set_defaults(func=_eval)

    p = sub.add_parser("capture-narratives", help="save labeled narratives for the offline fallback tier")
    p.add_argument("--deployment", help="deployment to use (default: AI_MODEL_DEPLOYMENT)")
    p.set_defaults(func=_capture)

    p = sub.add_parser("load-test", help="bounded load on deterministic pages only (never the model)")
    p.add_argument("--url", required=True, help="base URL of a web service")
    p.add_argument("--rps", type=int, default=10, help="requests per second (max 50)")
    p.add_argument("--seconds", type=int, default=60, help="duration (max 180)")
    p.set_defaults(func=_load)

    p = sub.add_parser("parity", help="compare deterministic card results across web endpoints")
    p.add_argument("--url", action="append", required=True, help="base URL of a web service (repeat)")
    p.set_defaults(func=_parity)

    p = sub.add_parser("snapshot", help="save a web endpoint's pages for offline fallback (replay artifacts)")
    p.add_argument("--url", required=True, help="base URL of a web service")
    p.add_argument("--label", default="web", help="folder label, for example aks or aca")
    p.add_argument("--out", help="output folder (default: EVIDENCE_DIR/replay/<label>-<UTC time>)")
    p.add_argument("--no-answers", action="store_true", help="skip the prepared questions (no model calls)")
    p.set_defaults(func=_snapshot)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
