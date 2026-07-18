"""Check that the repository tree is safe to publish.

The check is intentionally conservative. It scans source-controlled and
untracked, non-ignored files, but skips files excluded by `.gitignore`.
"""

from __future__ import annotations

import csv
import hashlib
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from heatwave_definition.hwmid import HWMID_METHOD_ID

FORBIDDEN_PARTS = {
    ".idea",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "data",
    "outputs",
    "out",
}
FORBIDDEN_SUFFIXES = {
    ".nc",
    ".nc4",
    ".pkl",
    ".npz",
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".pyc",
}
ALLOWED_TEXT_SUFFIXES = {
    "",
    ".cff",
    ".csv",
    ".gitignore",
    ".md",
    ".py",
    ".toml",
    ".txt",
    ".yml",
    ".yaml",
}
LOCAL_PATH_PATTERNS = [
    re.compile(r"\b[A-Z]:\\(?:Users|Projects|endata|KIT|Data|Temp|tmp)\\", re.IGNORECASE),
    re.compile(r"\\\\[^\\\s]+\\[^\\\s]+"),
    re.compile(r"\b" + "js" + "2644" + r"\b", re.IGNORECASE),
    re.compile("DEN_" + "EMESA_RESUR", re.IGNORECASE),
    re.compile(r"(?:COPERNICUS_CDS_KEY|CDSAPI_KEY)\s*=\s*['\"][^'\"]+", re.IGNORECASE),
    re.compile(r"\b(?:github_pat_|ghp_)[A-Za-z0-9_]+"),
]

REQUIRED_FILES = {
    "CHANGELOG.md",
    "CITATION.cff",
    "LICENSE",
    "README.md",
    "requirements-lock.txt",
    ".github/workflows/tests.yml",
    "docs/data_download.md",
    "docs/reproducibility.md",
    "scripts/run_demo.py",
}
CANONICAL_TEXT_SUFFIXES = ALLOWED_TEXT_SUFFIXES - {""}

REQUIRED_RESULTS = {
    "results/provenance/raw_input_manifest.csv",
    "results/provenance/software_environment.csv",
    "results/rankings/ranked_years_e_obs.csv",
    "results/rankings/ranked_years_era5.csv",
    "results/ensemble/copernicus2100_de_fr_top_years.csv",
    "results/cmip6/cmip6_de_fr_file_inventory.csv",
    "results/cmip6/cmip6_de_fr_top_years.csv",
}


def main() -> int:
    problems: list[str] = []
    tracked = {path.relative_to(REPO).as_posix() for path in listed_files()}
    for required in sorted(REQUIRED_FILES - tracked):
        problems.append(f"missing release file: {required}")
    for required in sorted(REQUIRED_RESULTS - tracked):
        problems.append(f"missing versioned result: {required}")
    for path in listed_files():
        rel = path.relative_to(REPO)
        parts = set(rel.parts)

        if parts.intersection(FORBIDDEN_PARTS):
            problems.append(f"forbidden directory content: {rel}")
        if path.suffix.lower() in FORBIDDEN_SUFFIXES and not is_allowed_result_artifact(rel):
            problems.append(f"forbidden data/output file type: {rel}")
        if path.suffix.lower() == ".csv" and not is_allowed_csv(rel) and not is_allowed_result_artifact(rel):
            problems.append(f"CSV is only allowed as configs/*.example.csv: {rel}")
        if (
            path.suffix.lower() not in ALLOWED_TEXT_SUFFIXES
            and path.name not in {"LICENSE", "README.md"}
            and not is_allowed_result_artifact(rel)
        ):
            problems.append(f"unexpected file type for public source tree: {rel}")
        if is_text_file(path):
            problems.extend(scan_text_file(path, rel))
        if rel.parts and rel.parts[0] == "results" and path.suffix.lower() in {".csv", ".md"}:
            problems.extend(scan_result_provenance(path, rel))

    problems.extend(check_release_metadata())
    problems.extend(check_result_metadata())
    problems.extend(check_reachable_history())

    if problems:
        print("Public release check failed:")
        for problem in problems:
            print(f"- {problem}")
        return 1

    print("Public release check passed.")
    return 0


def check_release_metadata() -> list[str]:
    problems = []
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    citation = (REPO / "CITATION.cff").read_text(encoding="utf-8")
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    era5_config = (REPO / "configs" / "era5.example.toml").read_text(encoding="utf-8")

    version_match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
    citation_match = re.search(r'^version:\s*"([^"]+)"', citation, re.MULTILINE)
    if not version_match or not citation_match or version_match.group(1) != citation_match.group(1):
        problems.append("pyproject.toml and CITATION.cff versions do not match")
    elif f"## {version_match.group(1)} -" not in (REPO / "CHANGELOG.md").read_text(encoding="utf-8"):
        problems.append("CHANGELOG.md does not contain the current package version")
    if "github.com/johannesschuhmacher/heatwave_definition" not in citation:
        problems.append("CITATION.cff does not reference the public GitHub repository")
    if "10.5281/zenodo.20793872" not in readme or "10.5281/zenodo.20793872" not in citation:
        problems.append("README/CITATION do not use the Zenodo concept DOI")
    if "working paper" in citation.lower():
        problems.append("CITATION.cff still describes the associated output as a working paper")
    if "1950-2022" in era5_config:
        problems.append("ERA5 example still contains the obsolete 1950-2022 period")
    return problems


def check_result_metadata() -> list[str]:
    problems = []
    raw_manifest = REPO / "results" / "provenance" / "raw_input_manifest.csv"
    if raw_manifest.exists():
        with raw_manifest.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if not rows:
            problems.append("raw input manifest is empty")
        for row in rows:
            file_name = row.get("file_name", "<unknown>")
            if row.get("role") != "raw_climate":
                problems.append(f"public raw input manifest contains non-input row: {file_name}")
            if row.get("local_path"):
                problems.append(f"public raw input manifest contains a local path: {file_name}")
            if row.get("exists", "").lower() != "true":
                problems.append(f"raw input was missing when manifest was written: {file_name}")
            if not re.fullmatch(r"[0-9a-f]{64}", row.get("sha256", "").lower()):
                problems.append(f"raw input has no valid SHA-256 checksum: {file_name}")

    method_result_files = (
        "results/rankings/ranked_years_e_obs.csv",
        "results/rankings/ranked_years_era5.csv",
        "results/rankings/ranked_years_copernicus_rcp45.csv",
        "results/rankings/ranked_years_copernicus_rcp85.csv",
        "results/rankings/scenario_selection_summary.csv",
        "results/ensemble/copernicus2100_de_fr_top_years.csv",
        "results/ensemble/copernicus2100_de_fr_top2_summary.csv",
        "results/cmip6/cmip6_de_fr_top_years.csv",
        "results/sensitivity/country_set_top_years.csv",
        "results/sensitivity/country_set_top2_summary.csv",
        "results/sensitivity/country_weighted_top_years.csv",
        "results/sensitivity/country_weighted_top2_summary.csv",
        "results/sensitivity/ranking_criteria_top_years.csv",
        "results/sensitivity/ranking_criteria_top2_summary.csv",
        "results/sensitivity/population_weighting_top_years.csv",
        "results/sensitivity/population_weighting_top2_summary.csv",
        "results/tables/primary_top10.csv",
        "results/tables/country_mask_top2.csv",
        "results/tables/country_weighted_top2.csv",
        "results/tables/ranking_criteria_top2.csv",
        "results/tables/historical_data_product_top10_common_period.csv",
        "results/tables/historical_data_product_top2_comparison.csv",
        "results/tables/climate_data_top10_with_cmip6.csv",
        "results/tables/climate_data_timing_top2_with_cmip6.csv",
        "results/tables/era5_event_period_summary.csv",
    )
    for relative in method_result_files:
        path = REPO / relative
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        methods = {row.get("hwmid_method", "") for row in rows}
        if methods != {HWMID_METHOD_ID}:
            problems.append(f"versioned ranking does not use {HWMID_METHOD_ID}: {relative}")

    historical_manifest = REPO / "results" / "provenance" / "historical_data_product_comparison_manifest.csv"
    if historical_manifest.exists():
        with historical_manifest.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        for row in rows:
            if row.get("role") != "derived_artifact":
                continue
            matches = list((REPO / "results").rglob(row.get("file_name", "")))
            if len(matches) != 1:
                problems.append(f"derived manifest target is not unique: {row.get('file_name', '')}")
                continue
            path = matches[0]
            content = artifact_bytes(path)
            expected_size = row.get("size_bytes", "")
            if expected_size and int(expected_size) != len(content):
                problems.append(f"derived manifest size mismatch: {path.relative_to(REPO)}")
            expected_hash = row.get("sha256", "")
            if expected_hash and expected_hash.lower() != hashlib.sha256(content).hexdigest():
                problems.append(f"derived manifest checksum mismatch: {path.relative_to(REPO)}")

    return problems


def check_reachable_history() -> list[str]:
    result = subprocess.run(
        ["git", "rev-list", "--objects", "HEAD"],
        cwd=REPO,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    problems = []
    for line in result.stdout.splitlines():
        parts = line.split(" ", 1)
        if len(parts) != 2:
            continue
        path = parts[1].lower()
        if Path(path).suffix in {".nc", ".nc4", ".pkl", ".pdf"}:
            problems.append(f"forbidden provider/intermediate file remains in reachable Git history: {parts[1]}")
    return problems


def artifact_bytes(path: Path) -> bytes:
    """Return platform-independent bytes for a versioned artifact."""

    content = path.read_bytes()
    if path.suffix.lower() in CANONICAL_TEXT_SUFFIXES:
        return content.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return content


def listed_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=REPO,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    paths = [REPO / line.strip() for line in result.stdout.splitlines() if line.strip()]
    return [path for path in paths if path.exists()]


def is_allowed_csv(rel: Path) -> bool:
    return len(rel.parts) == 2 and rel.parts[0] == "configs" and rel.name.endswith(".example.csv")


def is_allowed_result_artifact(rel: Path) -> bool:
    return len(rel.parts) >= 2 and rel.parts[0] == "results" and rel.suffix.lower() in {".csv", ".md", ".png"}


def is_text_file(path: Path) -> bool:
    if path.name in {"LICENSE", "README.md"}:
        return True
    return path.suffix.lower() in ALLOWED_TEXT_SUFFIXES


def scan_text_file(path: Path, rel: Path) -> list[str]:
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [f"non-UTF-8 text file: {rel}"]

    problems = []
    for pattern in LOCAL_PATH_PATTERNS:
        if pattern.search(content):
            problems.append(f"local/private path or user marker in {rel}: {pattern.pattern}")
    return problems


def scan_result_provenance(path: Path, rel: Path) -> list[str]:
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []

    problems = []
    if "_from_metrics" in content:
        problems.append(f"versioned result still references legacy metric rerun: {rel}")
    if ".pkl" in content:
        problems.append(f"versioned result still references pickle input: {rel}")
    return problems


if __name__ == "__main__":
    sys.exit(main())
