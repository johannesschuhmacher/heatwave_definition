"""Write provenance manifests for the historical E-OBS/ERA5 comparison."""

from __future__ import annotations

import argparse
import csv
import hashlib
from datetime import datetime, timezone
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
DEFAULT_LOCAL_OUTPUT = REPO / "outputs" / "provenance" / "historical_data_product_comparison_manifest.local.csv"
DEFAULT_PUBLIC_OUTPUT = REPO / "results" / "provenance" / "historical_data_product_comparison_manifest.csv"

FIELDS = [
    "timestamp_utc",
    "role",
    "dataset",
    "period",
    "file_name",
    "local_path",
    "size_bytes",
    "sha256",
    "note",
]

DERIVED_ARTIFACTS = [
    (
        "outputs/ranking_from_config/ranked_years_e_obs.csv",
        "Historical / E-OBS",
        "1950-2025",
        "Versioned historical main ranking.",
    ),
    (
        "outputs/ranking_from_config/ranked_years_era5.csv",
        "Historical / ERA5",
        "1950-2026",
        "Versioned reanalysis ranking; 2026 is an incomplete current-year file.",
    ),
    (
        "outputs/appendix/historical_data_product_top10_common_period.csv",
        "E-OBS and ERA5",
        "1950-2025",
        "Top-10 common-period comparison table.",
    ),
    (
        "outputs/appendix/historical_data_product_top2_comparison.csv",
        "E-OBS and ERA5",
        "1950-2025",
        "Top-2 value comparison table.",
    ),
    (
        "outputs/figures/historical_data_product_top10_comparison.png",
        "E-OBS and ERA5",
        "1950-2025",
        "Manuscript appendix comparison figure.",
    ),
    (
        "scripts/make_historical_data_product_comparison.py",
        "derived workflow",
        "1950-2025",
        "Script generating comparison tables and figure.",
    ),
]


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    records = []
    records.extend(raw_records(args))
    records.extend(derived_records())
    write_manifest(records, args.local_output, strip_local_path=False)
    write_manifest(records, args.public_output, strip_local_path=True)


def raw_records(args: argparse.Namespace) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    if args.eobs_raw_file is not None:
        eobs_size, eobs_hash = lookup_existing_eobs_hash(args.eobs_manifest)
        records.append(
            {
                "timestamp_utc": timestamp(),
                "role": "raw_input",
                "dataset": "E-OBS v33.0e tx",
                "period": "1950-2025",
                "file_name": args.eobs_raw_file.name,
                "local_path": str(args.eobs_raw_file),
                "size_bytes": eobs_size or file_size(args.eobs_raw_file),
                "sha256": eobs_hash or (sha256_file(args.eobs_raw_file) if args.hash_eobs_raw else ""),
                "note": "Historical main basis; raw data kept outside Git.",
            }
        )

    if args.era5_root is not None:
        era5_files = sorted(args.era5_root.glob(args.era5_pattern)) if args.era5_root.exists() else []
        era5_common = [path for path in era5_files if args.start_year <= year_from_name(path) <= args.end_year]
        records.append(
            {
                "timestamp_utc": timestamp(),
                "role": "raw_input_directory",
                "dataset": "ERA5 hourly t2m",
                "period": f"{args.start_year}-{args.end_year}",
                "file_name": args.era5_root.name,
                "local_path": str(args.era5_root),
                "size_bytes": sum(path.stat().st_size for path in era5_common),
                "sha256": sha256_directory(era5_common, args.era5_root) if args.hash_era5_raw else "",
                "note": (
                    f"Reanalysis comparison; {len(era5_common)} annual files in common-period local inventory. "
                    "Use --hash-era5-raw for a directory checksum."
                ),
            }
        )
    return records


def derived_records() -> list[dict[str, object]]:
    records = []
    for rel_path, dataset, period, note in DERIVED_ARTIFACTS:
        path = REPO / rel_path
        records.append(
            {
                "timestamp_utc": timestamp(),
                "role": "derived_artifact" if rel_path.startswith("outputs/") else "script",
                "dataset": dataset,
                "period": period,
                "file_name": path.name,
                "local_path": str(path),
                "size_bytes": file_size(path),
                "sha256": sha256_file(path) if path.exists() and path.is_file() else "",
                "note": note if path.exists() else f"missing; {note}",
            }
        )
    return records


def lookup_existing_eobs_hash(path: Path) -> tuple[str, str]:
    if not path.exists():
        return "", ""
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            label = row.get("dataset") or row.get("label")
            if row.get("role") == "raw_input" and label == "E-OBS v33.0e tx":
                return row.get("size_bytes", ""), row.get("sha256", "")
    return "", ""


def write_manifest(records: list[dict[str, object]], path: Path, strip_local_path: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for record in records:
            row = dict(record)
            if strip_local_path:
                row["local_path"] = ""
            writer.writerow(row)
    print(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_directory(files: list[Path], root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(files):
        file_hash = sha256_file(path)
        digest.update(f"{path.relative_to(root).as_posix()}\t{path.stat().st_size}\t{file_hash}\n".encode("utf-8"))
    return digest.hexdigest()


def file_size(path: Path) -> int | str:
    return path.stat().st_size if path.exists() and path.is_file() else ""


def year_from_name(path: Path) -> int:
    return int(path.stem[-4:])


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eobs-raw-file", type=Path)
    parser.add_argument("--era5-root", type=Path)
    parser.add_argument("--start-year", type=int, default=1950)
    parser.add_argument("--end-year", type=int, default=2022)
    parser.add_argument("--era5-pattern", default="t2m_era5_*.nc")
    parser.add_argument("--eobs-manifest", type=Path, default=REPO / "results" / "provenance" / "eobs_v33_historical_manifest.csv")
    parser.add_argument("--local-output", type=Path, default=DEFAULT_LOCAL_OUTPUT)
    parser.add_argument("--public-output", type=Path, default=DEFAULT_PUBLIC_OUTPUT)
    parser.add_argument("--hash-eobs-raw", action="store_true")
    parser.add_argument("--hash-era5-raw", action="store_true")
    return parser.parse_args(argv)


if __name__ == "__main__":
    main()
