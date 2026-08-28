from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .case_evaluator import evaluate_case
from .constants import contract_root
from .entry import evaluate_entry, load_entry
from .fetch import fetch_dataset_split, fetch_support
from .jsonio import write_json
from .packaging import create_package, verify_package
from .report import render_case_report


def _positive(value: str) -> int:
    result = int(value)
    if result < 1:
        raise argparse.ArgumentTypeError("value must be positive")
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autocfd5-aiml",
        description="Evaluate and package AutoCFD5 AIML DrivAerML entries.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate-entry", help="Validate entry metadata.")
    validate.add_argument("entry_root", type=Path)

    one = commands.add_parser("evaluate-case", help="Evaluate one case.")
    one.add_argument("--case-id", required=True)
    one.add_argument("--dataset-root", type=Path, required=True)
    one.add_argument("--support-root", type=Path, required=True)
    one.add_argument("--surface-manifest", type=Path, required=True)
    one.add_argument("--volume-manifest", type=Path, required=True)
    one.add_argument(
        "--native-source-pin", type=Path, default=contract_root() / "native-source-pin.json"
    )
    one.add_argument("--monolithic-volume", type=Path)
    one.add_argument("--output", type=Path, required=True)
    one.add_argument("--maximum-chunk-rows", type=_positive, default=1_000_000)
    one.add_argument("--io-chunk-bytes", type=_positive, default=8 * 1024 * 1024)

    full = commands.add_parser("evaluate-entry", help="Evaluate every test case in an entry.")
    full.add_argument("entry_root", type=Path)
    full.add_argument("--dataset-root", type=Path, required=True)
    full.add_argument("--support-root", type=Path, required=True)
    full.add_argument("--output", type=Path, required=True)
    full.add_argument(
        "--native-source-pin", type=Path, default=contract_root() / "native-source-pin.json"
    )
    full.add_argument("--scoring", type=Path, default=contract_root() / "scoring.json")
    full.add_argument("--force-truth", type=Path)
    full.add_argument("--maximum-chunk-rows", type=_positive, default=1_000_000)
    full.add_argument("--io-chunk-bytes", type=_positive, default=8 * 1024 * 1024)
    full.add_argument("--resume", action="store_true")

    package = commands.add_parser("package", help="Create a deterministic confidential ZIP.")
    package.add_argument("result_root", type=Path)
    package.add_argument("--output", type=Path, required=True)

    verify = commands.add_parser("verify-package", help="Verify a result ZIP and every member.")
    verify.add_argument("package", type=Path)

    support = commands.add_parser("fetch-support", help="Fetch immutable profile support.")
    support.add_argument("--destination", type=Path, required=True)
    support.add_argument("--archive", type=Path)

    data = commands.add_parser("fetch-data", help="Fetch pinned native data for one test split.")
    data.add_argument("--split-id", required=True)
    data.add_argument("--destination", type=Path, required=True)
    data.add_argument(
        "--native-source-pin", type=Path, default=contract_root() / "native-source-pin.json"
    )
    data.add_argument("--dry-run", action="store_true")

    report = commands.add_parser("report", help="Render an individual case profile report.")
    report.add_argument("--result-root", type=Path, required=True)
    report.add_argument("--support-root", type=Path, required=True)
    report.add_argument("--case-id", required=True)
    report.add_argument("--output", type=Path, required=True)
    return parser


def _print(value: object) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, allow_nan=False))


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "validate-entry":
            entry_path = args.entry_root / "entry.json"
            _print({"status": "valid", "entry": load_entry(entry_path)})
        elif args.command == "evaluate-case":
            result = evaluate_case(
                case_id=args.case_id,
                native_source_pin=args.native_source_pin,
                dataset_root=args.dataset_root,
                support_root=args.support_root,
                surface_prediction_manifest=args.surface_manifest,
                volume_prediction_manifest=args.volume_manifest,
                monolithic_volume=args.monolithic_volume,
                maximum_prediction_chunk_rows=args.maximum_chunk_rows,
                io_chunk_bytes=args.io_chunk_bytes,
            )
            identity = write_json(args.output, result, exclusive=True)
            _print({"status": "complete", **identity})
        elif args.command == "evaluate-entry":
            entry = load_entry(args.entry_root / "entry.json")
            split_path = contract_root() / "splits" / f"{entry['split_id']}.json"
            force_truth = args.force_truth or args.dataset_root / "force_mom_constref_all.csv"
            result = evaluate_entry(
                entry_root=args.entry_root,
                output_root=args.output,
                dataset_root=args.dataset_root,
                support_root=args.support_root,
                native_source_pin=args.native_source_pin,
                split_path=split_path,
                scoring_path=args.scoring,
                force_truth_path=force_truth,
                maximum_prediction_chunk_rows=args.maximum_chunk_rows,
                io_chunk_bytes=args.io_chunk_bytes,
                resume=args.resume,
            )
            _print({"status": "complete", "metric_values": result["metric_values"]})
        elif args.command == "package":
            _print({"status": "complete", **create_package(args.result_root, args.output)})
        elif args.command == "verify-package":
            _print({"status": "valid", **verify_package(args.package)})
        elif args.command == "fetch-support":
            root = fetch_support(args.destination, archive=args.archive)
            _print({"status": "complete", "support_root": str(root)})
        elif args.command == "fetch-data":
            split_path = contract_root() / "splits" / f"{args.split_id}.json"
            fetch_dataset_split(
                split_path=split_path,
                native_source_pin=args.native_source_pin,
                destination=args.destination,
                dry_run=args.dry_run,
            )
            _print({"status": "complete", "dry_run": args.dry_run})
        elif args.command == "report":
            path = render_case_report(
                result_root=args.result_root,
                support_root=args.support_root,
                case_id=args.case_id,
                output=args.output,
            )
            _print({"status": "complete", "report": str(path)})
        else:
            raise AssertionError(args.command)
    except (OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 0


__all__ = ["main"]
