"""Write local and sanitized manifests for publication-workflow inputs."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import pandas as pd

from heatwave_definition.raw_copernicus import discover_tasadjust_runs


REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO / "outputs" / "provenance" / "data_manifest.local.csv"
DEFAULT_PUBLIC_OUTPUT = REPO / "results" / "provenance" / "raw_input_manifest.csv"


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    rows = []

    if args.copernicus_root:
        for run in discover_tasadjust_runs(args.copernicus_root):
            rows.append(
                file_record(
                    path=run.path,
                    role="raw_climate",
                    dataset_family="Copernicus/CORDEX tasAdjust",
                    scenario=run.scenario,
                    model_chain=f"{run.driving_model} / {run.regional_model}",
                    variable="tasAdjust",
                    source_note="CORDEX-CMIP5 provider input retained outside Git",
                    include_hash=args.hash_files,
                )
            )

    if args.eobs_file:
        rows.append(
            file_record(
                path=args.eobs_file,
                role="raw_climate",
                dataset_family="E-OBS",
                scenario="historical",
                model_chain="observational gridded dataset",
                variable="tx",
                source_note="E-OBS provider input retained outside Git",
                include_hash=args.hash_files,
            )
        )

    manifest = pd.DataFrame(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    manifest.to_csv(args.output, index=False)
    print(args.output)
    if args.public_output is not None:
        public = manifest[manifest["role"] == "raw_climate"].copy()
        if "local_path" in public.columns:
            public["local_path"] = ""
        args.public_output.parent.mkdir(parents=True, exist_ok=True)
        public.to_csv(args.public_output, index=False)
        print(args.public_output)


def file_record(
    path: Path,
    role: str,
    dataset_family: str,
    scenario: str,
    model_chain: str,
    variable: str,
    source_note: str,
    include_hash: bool,
) -> dict[str, object]:
    path = Path(path)
    exists = path.exists()
    return {
        "role": role,
        "dataset_family": dataset_family,
        "scenario": scenario,
        "model_chain": model_chain,
        "variable": variable,
        "file_name": path.name,
        "local_path": str(path),
        "exists": exists,
        "size_bytes": path.stat().st_size if exists and path.is_file() else "",
        "sha256": sha256(path) if include_hash and exists and path.is_file() else "",
        "source_note": source_note,
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--public-output", type=Path, default=DEFAULT_PUBLIC_OUTPUT)
    parser.add_argument("--copernicus-root", type=Path)
    parser.add_argument("--eobs-file", type=Path)
    parser.add_argument(
        "--hash-files",
        action="store_true",
        help="Calculate SHA-256 hashes. This can be slow for large NetCDF files.",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    main()
