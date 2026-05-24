"""Verify the local conference submission package.

This script checks the repository-side invariants that should hold immediately before
filling the review form. It does not perform any external submission action.
"""

from __future__ import annotations

import csv
import hashlib
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

PDF = ROOT / "paper/rave_intent_compiled_verified_execution_arr.pdf"
PDF_LOG = ROOT / "paper/rave_intent_compiled_verified_execution_arr.log"
SUPPLEMENT = ROOT / "artifacts/rave2_emnlp2026_arr_anonymous_supplement.tar.gz"
SUPPLEMENT_DIR = ROOT / "artifacts/rave2_emnlp2026_arr_anonymous_supplement"
MANIFEST = ROOT / "paper/arr_upload_manifest_20260507.md"
PACKET = ROOT / "paper/arr_openreview_submission_packet_20260507.md"
CHECKLIST = ROOT / "paper/arr_author_action_checklist_20260507.md"
METADATA = ROOT / "paper/arr_openreview_metadata_draft.md"
RESPONSIBLE = ROOT / "paper/arr_responsible_nlp_checklist_draft.md"
RESPONSIBLE_FORM = ROOT / "paper/arr_responsible_nlp_form_answers_20260507.md"
GITHUB_RELEASE = ROOT / ".tmp/github_release"

HASHED_FILES = [
    PDF,
    SUPPLEMENT,
    METADATA,
    RESPONSIBLE,
    RESPONSIBLE_FORM,
    CHECKLIST,
    PACKET,
]

SUPPLEMENT_BAD_PATTERNS = [
    "Neu" + "rIPS",
    "EM" + "NLP",
    "A" + "RR",
    "Open" + "Review",
    "second_" + "benchmark_" + "feasibility",
    "neu" + "rips2026",
    "/" + "home" + "/",
    "/" + "ylw" + "/",
    "ana" + "conda3",
    "mini" + "conda3",
    "121" + "--180",
    "121" + "-180",
]

SENSITIVE_TEXT_ROOTS = [
    ROOT / "src",
    ROOT / "docs",
    ROOT / "experiments",
    ROOT / "paper",
    ROOT / "README.md",
]

SENSITIVE_TEXT_SUFFIXES = {
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

SENSITIVE_SKIP_PARTS = {
    ".git",
    "__pycache__",
    "acl_style",
    "Accepted",
    "history",
    "outputs",
    "Template",
}

SENSITIVE_PATTERNS = {
    "openai_style_key": re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    "github_token": re.compile(r"(?:ghp|github_pat)_[A-Za-z0-9_]{20,}"),
    "google_api_key": re.compile(r"AIza[0-9A-Za-z_-]{20,}"),
    "slack_token": re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    "absolute_home_path": re.compile(r"/(?:home|Users)/[A-Za-z0-9_.-]+"),
}


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_text(args: list[str]) -> str:
    proc = subprocess.run(args, cwd=ROOT, check=True, text=True, capture_output=True)
    return proc.stdout


def check_hashes() -> None:
    manifest = read_text(MANIFEST)
    packet = read_text(PACKET)
    for path in HASHED_FILES:
        if not path.exists():
            fail(f"missing expected file: {path.relative_to(ROOT)}")
        digest = sha256(path)
        if digest not in manifest:
            fail(f"manifest missing digest for {path.relative_to(ROOT)}: {digest}")
        if path in {PDF, SUPPLEMENT} and digest not in packet:
            fail(f"submission packet missing upload digest for {path.relative_to(ROOT)}")
    print("OK hashes")


def check_pdf() -> None:
    info = run_text(["pdfinfo", str(PDF)])
    pages_match = re.search(r"^Pages:\s+(\d+)$", info, flags=re.MULTILINE)
    if not pages_match:
        fail("pdfinfo did not report page count")
    page_count = int(pages_match.group(1))
    if page_count < 8:
        fail(f"expected at least 8-page long-paper PDF, found {page_count}")

    log = read_text(PDF_LOG)
    if re.search(r"Overfull|^!|LaTeX Error|Package .* Error", log, flags=re.MULTILINE):
        fail("TeX log contains overfull boxes or errors")

    content_boundary_text = run_text(["pdftotext", "-f", "8", "-l", "8", str(PDF), "-"])
    for marker in ["Conclusion"]:
        if marker not in content_boundary_text:
            fail(f"PDF page 8 missing content-boundary marker: {marker}")

    text = run_text(["pdftotext", "-f", "8", "-l", str(page_count), str(PDF), "-"])
    for marker in [
        "Conclusion",
        "Limitations",
        "Ethical Considerations",
        "References",
    ]:
        if marker not in text:
            fail(f"PDF pages 8-{page_count} missing marker: {marker}")
    print("OK pdf")


def check_supplement_text() -> None:
    if not SUPPLEMENT.exists():
        fail("missing supplement archive")
    if not SUPPLEMENT_DIR.exists():
        fail("missing unpacked supplement directory")

    text_suffixes = {".md", ".tex", ".py", ".sh", ".example", ".txt", ".csv", ".json"}
    for path in SUPPLEMENT_DIR.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in text_suffixes:
            continue
        text = read_text(path)
        for pattern in SUPPLEMENT_BAD_PATTERNS:
            if pattern in text:
                fail(f"supplement text marker {pattern!r} found in {path.relative_to(ROOT)}")

    trajectory_count = sum(1 for p in (SUPPLEMENT_DIR / "results").rglob("*trajectories*") if p.is_file())
    if trajectory_count:
        fail(f"supplement contains trajectory files: {trajectory_count}")
    kill_count = sum(1 for p in (SUPPLEMENT_DIR / "results").rglob("kill_criteria.md") if p.is_file())
    if kill_count:
        fail(f"supplement contains kill_criteria.md files: {kill_count}")
    print("OK supplement text")


def check_raw_preview_columns() -> None:
    result_root = SUPPLEMENT_DIR / "results"
    count = 0
    for path in result_root.rglob("episode_metrics.csv"):
        count += 1
        with path.open(newline="", encoding="utf-8", errors="replace") as handle:
            reader = csv.DictReader(handle)
            columns = [
                col
                for col in ("raw_model_output_preview", "output_preview", "failed_requirements")
                if col in (reader.fieldnames or [])
            ]
            for row_index, row in enumerate(reader, start=2):
                for column in columns:
                    if row.get(column):
                        rel = path.relative_to(ROOT)
                        fail(f"nonempty raw preview field {column} at {rel}:{row_index}")
    print(f"OK raw preview columns ({count} CSV files)")


def check_external_action_fields() -> None:
    text = "\n".join(
        read_text(path) for path in [PACKET, CHECKLIST, METADATA, RESPONSIBLE, RESPONSIBLE_FORM]
    )
    required = [
        "EM" + "NLP/AACL",
        "Consent to Share Data",
        "Reviewer registration",
        "Conflicts",
        "Preprint",
        "AI coding/writing assistance",
        "not simultaneously under review",
    ]
    for marker in required:
        if marker not in text:
            fail(f"external action marker missing: {marker}")
    print("OK external action fields")


def iter_sensitive_scan_files() -> list[Path]:
    files: list[Path] = []
    roots = list(SENSITIVE_TEXT_ROOTS)
    if GITHUB_RELEASE.exists():
        roots.append(GITHUB_RELEASE)
    for root in roots:
        if not root.exists():
            continue
        candidates = [root] if root.is_file() else sorted(root.rglob("*"))
        for path in candidates:
            if not path.is_file():
                continue
            rel = path.relative_to(ROOT)
            if any(part in SENSITIVE_SKIP_PARTS for part in rel.parts):
                continue
            if path.suffix.lower() not in SENSITIVE_TEXT_SUFFIXES:
                continue
            files.append(path)
    return files


def check_sensitive_info() -> None:
    for path in iter_sensitive_scan_files():
        text = read_text(path)
        for line_no, line in enumerate(text.splitlines(), start=1):
            for name, pattern in SENSITIVE_PATTERNS.items():
                if pattern.search(line):
                    fail(f"sensitive marker {name} at {path.relative_to(ROOT)}:{line_no}")
    print("OK sensitive info scan")


def check_transfer_sheet_freshness() -> None:
    metadata = read_text(METADATA)
    packet = read_text(PACKET)
    stale_markers = [
        "Current local check: 9 pages total",
        "Reproducibility Statement",
        "short artifact appendix",
    ]
    for marker in stale_markers:
        if marker in metadata or marker in packet:
            fail(f"stale transfer-sheet marker found: {marker}")
    required_markers = [
        "13 pages total",
        "regular boolean-setting",
        "previously unseen API signatures",
        "shadow-mode",
        "counterexample checks",
    ]
    combined = metadata + "\n" + packet
    for marker in required_markers:
        if marker not in combined:
            fail(f"fresh transfer-sheet marker missing: {marker}")
    print("OK transfer sheet freshness")


def main() -> int:
    check_hashes()
    check_pdf()
    check_supplement_text()
    check_raw_preview_columns()
    check_external_action_fields()
    check_transfer_sheet_freshness()
    check_sensitive_info()
    print("conference submission package checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
