"""Command line: python -m football_insights <command>.

Commands:
  download-data Optional: fetch the two Kaggle datasets into the data folder.
  verify-data   Check the raw downloads against the data contract.
  ingest        Verify, build, and publish a curated version.
  dq-report     Print the data-quality report of the active curated version.
  tool          Run one deterministic analytics tool and print its result.
  tools         List the tools the insights agent can call.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

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
    print("Next: python -m football_insights verify-data")
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
        print(f"{spec.name:22} Q{spec.question}  {spec.description.splitlines()[0]}")
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

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
