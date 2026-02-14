"""CLI commands for managing campaigns and analytics (Studio)."""

import argparse
import json
import sys
from pathlib import Path

from .config.runtime import get_settings
from .domain.sponsorship import Campaign, Creative
from .modules.analytics.store import AnalyticsStore
from .wiring import build_index_service

# Default path to demo ads JSON (project root / data / test_ads.json)
_DEFAULT_CAMPAIGNS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "test_ads.json"


def load_campaigns_from_file(path: Path) -> list[Campaign | Creative]:
    """Load campaigns/creatives from a JSON file. Raises on missing file or invalid JSON/schema."""
    if not path.exists():
        print(f"Error: campaigns file not found: {path}", file=sys.stderr)
        print("Create data/test_ads.json or pass --file <path>.", file=sys.stderr)
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, list):
        print("Error: JSON file must contain a list of campaign or creative objects.", file=sys.stderr)
        sys.exit(1)
    items: list[Campaign | Creative] = []
    for i, item in enumerate(raw):
        try:
            items.append(Campaign.model_validate(item))
            continue
        except Exception:
            pass
        try:
            items.append(Creative.model_validate(item))
        except Exception as e:
            print(f"Error: invalid campaign/creative at index {i}: {e}", file=sys.stderr)
            sys.exit(1)
    return items


def seed_campaigns(file_path: Path | None = None) -> None:
    """Load demo campaigns from a JSON file and upsert them via IndexService."""
    path = file_path if file_path is not None else _DEFAULT_CAMPAIGNS_PATH
    items = load_campaigns_from_file(path)
    print(f"Adding {len(items)} campaigns/creatives from {path}...")
    svc = build_index_service()
    count = svc.upsert_campaigns(items)
    print(f"Successfully added {count} creatives.")


def main():
    parser = argparse.ArgumentParser(description="Manage campaigns collection")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Create collection command
    create_parser = subparsers.add_parser("create", help="Create the campaigns collection")
    create_parser.add_argument(
        "--dimension",
        type=int,
        default=384,
        help="Embedding dimension (default: 384 for BAAI/bge-small-en-v1.5)",
    )

    # Delete collection command
    subparsers.add_parser("delete", help="Delete the campaigns collection")

    # Info command
    subparsers.add_parser("info", help="Show collection information")

    # Seed command
    seed_parser = subparsers.add_parser("seed", help="Load demo campaigns from a JSON file and add to the collection")
    seed_parser.add_argument(
        "--file",
        type=Path,
        default=None,
        help=f"Path to JSON file with campaigns (default: {_DEFAULT_CAMPAIGNS_PATH})",
    )

    report_parser = subparsers.add_parser("report", help="Show campaign analytics")
    report_parser.add_argument("--campaign-id", type=str, default=None, help="Campaign ID for detail report")
    report_parser.add_argument("--since-hours", type=int, default=24, help="Summary window in hours")

    args = parser.parse_args()
    svc = build_index_service()

    if args.command == "create":
        result = svc.ensure_collection(dimension=args.dimension)
        if result["created"]:
            print(f"Created collection: {result['name']}")
        else:
            print(f"Collection already exists: {result['name']}")
    elif args.command == "delete":
        svc.delete_collection()
        print("Deleted collection.")
    elif args.command == "info":
        info = svc.collection_info()
        print(f"Collection: {info['name']}")
        print(f"Status: {info['status']}")
        print(f"Points count: {info['points_count']}")
        print(f"Indexed vectors count: {info['indexed_vectors_count']}")
    elif args.command == "seed":
        seed_campaigns(args.file)
    elif args.command == "report":
        settings = get_settings()
        store = AnalyticsStore(settings.analytics_db_path)
        if args.campaign_id:
            report = store.campaign_report(args.campaign_id)
            print(json.dumps(report, indent=2))
        else:
            from datetime import datetime, timedelta, timezone

            since = datetime.now(timezone.utc) - timedelta(hours=max(1, args.since_hours))
            summary = store.summary(since=since)
            print(json.dumps({"since_hours": args.since_hours, "campaigns": summary}, indent=2))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
