"""CLI for the Phase 3 dataset pipeline.

Usage
-----

Prepare a dataset from a JSON config file::

    python -m virgo_slm.dataset.cli prepare --config path/to/dataset_config.json

Prepare a dataset from a single directory with default settings (quick,
single-source convenience mode -- for anything more than one source, or
non-default settings, write a config file instead)::

    python -m virgo_slm.dataset.cli prepare --input-dir path/to/corpus \\
        --output-dir path/to/output --format auto

Inspect a manifest already on disk::

    python -m virgo_slm.dataset.cli stats --manifest path/to/dataset_manifest.json

The JSON config file shape mirrors ``DatasetPipelineConfig``/
``DatasetSourceConfig`` field names exactly, e.g.::

    {
      "sources": [
        {"path": "data/en", "format": "txt", "domain": "general",
         "language": "en", "license": "CC-BY-4.0", "provenance": "my-corpus-v1"}
      ],
      "output_dir": "output/dataset_v1",
      "seed": 42
    }
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from virgo_slm.dataset.config import DatasetPipelineConfig, DatasetSourceConfig
from virgo_slm.dataset.manifest import DatasetManifest
from virgo_slm.dataset.pipeline import run_pipeline


def _load_config(path: str) -> DatasetPipelineConfig:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    sources = tuple(DatasetSourceConfig(**s) for s in data["sources"])
    kwargs = {k: v for k, v in data.items() if k != "sources"}
    return DatasetPipelineConfig(sources=sources, **kwargs)


def _cmd_prepare(args: argparse.Namespace) -> int:
    if args.config:
        config = _load_config(args.config)
    else:
        if not args.input_dir or not args.output_dir:
            print(
                "error: prepare requires either --config, or both "
                "--input-dir and --output-dir",
                file=sys.stderr,
            )
            return 2
        source = DatasetSourceConfig(path=args.input_dir, format=args.format)
        config = DatasetPipelineConfig(
            sources=(source,), output_dir=args.output_dir, seed=args.seed
        )

    result = run_pipeline(config)

    print(f"Accepted:  {len(result.accepted_records)}")
    print(f"Rejected:  {len(result.rejected_records)}")
    print(f"Ingest errors: {len(result.ingest_errors)}")
    print(f"Train file:      {result.split_files['train']}")
    print(f"Validation file: {result.split_files['validation']}")
    print(f"Test file:       {result.split_files['test']}")
    if result.manifest_path:
        print(f"Manifest:        {result.manifest_path}")
    return 0


def _cmd_stats(args: argparse.Namespace) -> int:
    manifest = DatasetManifest.load(args.manifest)
    print(json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="virgo_slm.dataset", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="Run the dataset pipeline")
    prepare.add_argument("--config", help="Path to a JSON pipeline config file")
    prepare.add_argument("--input-dir", help="Quick mode: single source directory")
    prepare.add_argument("--output-dir", help="Quick mode: output directory")
    prepare.add_argument("--format", default="auto", choices=["auto", "txt", "json", "jsonl"])
    prepare.add_argument("--seed", type=int, default=42)
    prepare.set_defaults(func=_cmd_prepare)

    stats = subparsers.add_parser("stats", help="Print a manifest already on disk")
    stats.add_argument("--manifest", required=True, help="Path to dataset_manifest.json")
    stats.set_defaults(func=_cmd_stats)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
