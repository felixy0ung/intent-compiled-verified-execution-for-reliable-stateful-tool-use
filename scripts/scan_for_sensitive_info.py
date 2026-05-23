from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


TEXT_SUFFIXES = {
    ".bib",
    ".csv",
    ".env",
    ".example",
    ".json",
    ".md",
    ".py",
    ".sh",
    ".sty",
    ".tex",
    ".txt",
    ".yaml",
    ".yml",
}

SKIP_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    "artifacts",
    "third_party",
    "appworld_020_root",
}

PATTERNS = {
    "private_env_file": re.compile(r"(^|/)[^.][^/]*\.env$"),
    "openai_style_key": re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    "github_token": re.compile(r"(ghp|github_pat)_[A-Za-z0-9_]{20,}"),
    "google_api_key": re.compile(r"AIza[0-9A-Za-z_-]{20,}"),
    "slack_token": re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    "absolute_home_path": re.compile(r"/(?:home|Users)/[A-Za-z0-9_.-]+"),
    "private_bundle": re.compile(r"\.(?:bundle|db|sqlite|sqlite3|pkl|pt|pth|bin)$"),
}


def is_text(path: Path) -> bool:
    return path.suffix.lower() in TEXT_SUFFIXES


def should_skip(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.parts)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    findings: list[str] = []

    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if should_skip(rel):
            continue
        rel_text = rel.as_posix()
        if path.is_file():
            for name, pattern in PATTERNS.items():
                if name in {"private_env_file", "private_bundle"} and pattern.search(rel_text):
                    if rel_text.endswith(".env.example"):
                        continue
                    findings.append(f"{name}: {rel_text}")
            if not is_text(path):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for line_no, line in enumerate(text.splitlines(), start=1):
                for name, pattern in PATTERNS.items():
                    if name in {"private_env_file", "private_bundle"}:
                        continue
                    if pattern.search(line):
                        findings.append(f"{name}: {rel_text}:{line_no}")

    if findings:
        print("\n".join(findings))
        return 1
    print("No sensitive-info patterns found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
