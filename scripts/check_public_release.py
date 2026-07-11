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
]


def main() -> int:
    problems: list[str] = []
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

    if problems:
        print("Public release check failed:")
        for problem in problems:
            print(f"- {problem}")
        return 1

    print("Public release check passed.")
    return 0


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
