"""Check that the repository tree is safe to publish.

The check is intentionally conservative. It scans source-controlled and
untracked, non-ignored files, but skips files excluded by `.gitignore`.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]

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


def main() -> int:
    problems: list[str] = []
    tracked = {path.relative_to(REPO).as_posix() for path in listed_files()}
    for required in sorted(REQUIRED_FILES - tracked):
        problems.append(f"missing release file: {required}")
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
    if "github.com/johannesschuhmacher/heatwave_definition" not in citation:
        problems.append("CITATION.cff does not reference the public GitHub repository")
    if "10.5281/zenodo.20793872" not in readme or "10.5281/zenodo.20793872" not in citation:
        problems.append("README/CITATION do not use the Zenodo concept DOI")
    if "1950-2022" in era5_config:
        problems.append("ERA5 example still contains the obsolete 1950-2022 period")
    return problems


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
