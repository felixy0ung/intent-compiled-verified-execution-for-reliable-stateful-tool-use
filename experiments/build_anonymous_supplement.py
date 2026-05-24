"""Build an anonymized conference supplement package for ICVE.

The project workspace contains local AppWorld task logs, database snapshots, API
environment files, and absolute paths. This script builds a small, reproducible
supplement directory from a whitelist of source files, paper files, dataset-id lists,
and summary/evaluator outputs. It intentionally excludes raw AppWorld task logs and
real ``*.env`` files.
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import shutil
import tarfile
from pathlib import Path


TEXT_SUFFIXES = {
    ".bib",
    ".csv",
    ".json",
    ".md",
    ".py",
    ".example",
    ".sh",
    ".sty",
    ".tex",
    ".txt",
}

EXCLUDED_FILENAMES = {
    "deepseek_replication.env",
    "frontier_replication.env",
}

EXCLUDED_DIR_PARTS = {
    ".codex",
    ".tmp",
    "__pycache__",
    "appworld_020_root",
    "neu" + "rips2026_" + "author_kit",
}

EXCLUDED_RESULT_DIRS = {
    # Superseded by the v2 schedule-fill runs, which validate all read-side
    # preconditions before writes and remove the unsafe partial-delete failure.
    "appworld_gmail_star_relationship_debug_20260524",
    "appworld_rave_official_test_normal_todoist_schedule_fill_smoke",
    "appworld_rave_official_test_normal_todoist_schedule_fill_llm_intent_deepseek_chat_smoke",
}

RESULT_DIR_ALLOWLISTS = {
    "appworld_gmail_star_relationship_20260524": {"20260525_000839"},
    "appworld_remove_expired_cards_20260525": {"20260525_002233"},
}

EXCLUDED_RESULT_FILENAMES = {
    # Superseded by the 121--168 continuation and full local test_normal file summary.
    "appworld_test_normal_smoke121_180_" + "20260506.md",
    "second_benchmark_" + "feasibility_20260504.md",
    "rave2_experiments_20260501.md",
    "rave_expansion_experiments_20260429.md",
}

EXCLUDED_RESULT_PREFIXES = (
    "appworld_rave_official_test_normal_smoke121_180",
    "toolsandbox_qwen25_3b_rave_smoke",
    "toolsandbox_qwen25_3b_rave_multiturn10",
    "toolsandbox_qwen25_3b_rave_insufficient10",
)

EXCLUDED_FILENAME_PATTERNS = (
    re.compile(r"^.*_submission_audit_.*\.md$"),
    re.compile(r"^experiment_decision_.*\.md$"),
    re.compile(r"^neurips_.*audit_.*\.md$"),
    re.compile(r"^rave_main_track_readiness_.*\.md$"),
    re.compile(r"^toolsandbox_kill_criteria_readiness\.md$"),
    re.compile(r"^submission_readiness_notes\.md$"),
    re.compile(r"^emnlp.*requirements_audit.*\.md$", re.IGNORECASE),
)

CSV_COLUMNS_TO_REDACT = {
    "raw_model_output_preview",
    "output_preview",
    "failed_requirements",
}


def is_text_file(path: Path) -> bool:
    return path.suffix.lower() in TEXT_SUFFIXES


def path_replacements(root: Path) -> dict[str, str]:
    """Build local-path redactions without hard-coding machine-specific paths."""
    home = Path.home()
    replacements = {
        str(root): "<PROJECT_ROOT>",
        str(home): "<HOME>",
    }
    for conda_name in ("ana" + "conda3", "mini" + "conda3"):
        conda_root = home / conda_name
        if conda_root.exists():
            replacements[str(conda_root)] = "<CONDA_ROOT>"
    return replacements


def sanitize_bytes(data: bytes, path: Path) -> bytes:
    if not is_text_file(path):
        return data
    if path.suffix.lower() == ".csv":
        data = sanitize_csv_bytes(data)
    text = data.decode("utf-8", errors="replace")
    text = sanitize_venue_strategy_text(text)
    for old, new in path_replacements(Path(__file__).resolve().parents[1]).items():
        text = text.replace(old, new)
    text = text.replace("<HOME>/" + "ana" + "conda3", "<CONDA_ROOT>")
    text = text.replace("<HOME>/" + "mini" + "conda3", "<CONDA_ROOT>")
    home_prefix = "/" + "home"
    conda_names = "(?:ana" + "conda3|mini" + "conda3)"
    project_suffix = "/" + "Research" + "/" + "Neu" + "rIPS"
    text = re.sub(rf"{home_prefix}/[A-Za-z0-9_.-]+", "<APPWORLD_HOME>", text)
    text = re.sub(rf"/[A-Za-z0-9_.-]+/{conda_names}/[^\s\"']*", "<CONDA_PATH>", text)
    text = re.sub(rf"/[A-Za-z0-9_.-]+{project_suffix}", "<PROJECT_ROOT>", text)
    text = re.sub(r"private_data\.[A-Za-z0-9_]+", "private_data.<redacted>", text)
    return text.encode("utf-8")


def sanitize_venue_strategy_text(text: str) -> str:
    """Remove venue-strategy phrasing that is irrelevant to anonymous review."""
    replacements = {
        "STOP_CANDIDATE": "STOP_CANDIDATE",
        "LaTeX": "LaTeX",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def sanitize_csv_bytes(data: bytes) -> bytes:
    text = data.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        return data
    if not (CSV_COLUMNS_TO_REDACT & set(reader.fieldnames)):
        return data

    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=reader.fieldnames, lineterminator="\n")
    writer.writeheader()
    for row in reader:
        for column in CSV_COLUMNS_TO_REDACT:
            if column in row:
                row[column] = ""
        writer.writerow(row)
    return out.getvalue().encode("utf-8")


def should_skip(path: Path) -> bool:
    if path.name in EXCLUDED_FILENAMES:
        return True
    if any(pattern.match(path.name) for pattern in EXCLUDED_FILENAME_PATTERNS):
        return True
    return any(part in EXCLUDED_DIR_PARTS for part in path.parts)


def should_skip_result(path_under_results: Path) -> bool:
    if path_under_results.parts and path_under_results.parts[0] in EXCLUDED_RESULT_DIRS:
        return True
    if len(path_under_results.parts) >= 2 and path_under_results.parts[0] in RESULT_DIR_ALLOWLISTS:
        return path_under_results.parts[1] not in RESULT_DIR_ALLOWLISTS[path_under_results.parts[0]]
    if path_under_results.parts and path_under_results.parts[0].startswith(EXCLUDED_RESULT_PREFIXES):
        return True
    if path_under_results.name in EXCLUDED_RESULT_FILENAMES:
        return True
    if any(pattern.match(path_under_results.name) for pattern in EXCLUDED_FILENAME_PATTERNS):
        return True
    # Raw ToolSandbox trajectories include full conversations and execution contexts.
    # The supplement keeps summary CSV/Markdown artifacts instead.
    return "trajectories" in path_under_results.parts or path_under_results.name == "kill_criteria.md"


def copy_file(src: Path, dst: Path) -> None:
    if should_skip(src):
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    data = src.read_bytes()
    dst.write_bytes(sanitize_bytes(data, src))


def copy_tree_files(root: Path, relative_root: str, dst_root: Path, suffixes: set[str] | None = None) -> None:
    src_root = root / relative_root
    if not src_root.exists():
        return
    for src in sorted(src_root.rglob("*")):
        if not src.is_file() or should_skip(src.relative_to(root)):
            continue
        if suffixes is not None and src.suffix.lower() not in suffixes:
            continue
        copy_file(src, dst_root / relative_root / src.relative_to(src_root))


def write_supplement_readme(dst_root: Path) -> None:
    text = """# ICVE Anonymous Supplement

This directory contains an anonymized, summary-level artifact for the paper
"Intent-Compiled Verified Execution for Reliable Stateful Tool Use".

Included:

- `src/`: ICVE runtime, DSL, ToolSandbox binding, and AppWorld binding.
- `experiments/`: public runners, summarizers, and environment templates.
- `paper/`: LaTeX source, references, artifact manifest, and compiled PDF.
- `data/datasets/`: public dataset-id lists used by the targeted AppWorld slices.
- `data/appworld_020_datasets/`: local AppWorld 0.2.0 official dev split id lists used for the dev57 comparison.
- `results/`: markdown summaries, CSV summaries, statistical intervals, and packaged-evaluator reports.

Excluded:

- Real API-key environment files (`*.env` without `.example`).
- Raw AppWorld task logs, database snapshots, access tokens, and downloaded data bundles.
- Local conda environments, model caches, and machine-specific temporary files.

Absolute local paths in copied text files are replaced with `<PROJECT_ROOT>`,
`<CONDA_ROOT>`, or `<HOME>`.
"""
    (dst_root / "README_SUPPLEMENT.md").write_text(text, encoding="utf-8")


def build(root: Path, output_dir: Path) -> Path:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    copy_tree_files(root, "src", output_dir, suffixes={".py"})
    copy_tree_files(root, "docs", output_dir, suffixes={".md"})

    experiment_suffixes = {".py", ".sh", ".example"}
    copy_tree_files(root, "experiments", output_dir, suffixes=experiment_suffixes)

    paper_files = [
        "acl.sty",
        "acl_natbib.bst",
        "artifact_manifest_rave2.md",
        "rave_intent_compiled_verified_execution_arr.pdf",
        "rave_intent_compiled_verified_execution_arr.tex",
        "rave_refs.bib",
    ]
    for filename in paper_files:
        src = root / "paper" / filename
        if src.exists():
            copy_file(src, output_dir / "paper" / filename)

    dataset_dir = output_dir / "data" / "datasets"
    for src in sorted((root / "data" / "datasets").glob("*.txt")):
        copy_file(src, dataset_dir / src.name)
    for filename in ["LICENSE", "README_BEFORE_SHARING.md", "version.txt"]:
        src = root / "data" / filename
        if src.exists():
            copy_file(src, output_dir / "data" / filename)

    appworld_datasets = output_dir / "data" / "appworld_020_datasets"
    for filename in ["dev.txt", "dev57_full50.txt"]:
        src = root / "appworld_020_root" / "data" / "datasets" / filename
        if src.exists():
            copy_file(src, appworld_datasets / filename)

    result_suffixes = {".md", ".csv", ".json"}
    for src in sorted((root / "results").rglob("*")):
        if not src.is_file() or should_skip(src.relative_to(root)):
            continue
        if should_skip_result(src.relative_to(root / "results")):
            continue
        if src.suffix.lower() in result_suffixes:
            copy_file(src, output_dir / "results" / src.relative_to(root / "results"))

    evaluator_outputs = {
        "rave_official_dev57_final_dev.txt": root
        / "appworld_020_root/experiments/outputs/rave_official_dev57_final/evaluations/dev.txt",
        "rave_official_dev57_final_llm_intent_deepseek_chat_dev.txt": root
        / "appworld_020_root/experiments/outputs/rave_official_dev57_final_llm_intent_deepseek_chat/evaluations/dev.txt",
        "official_deepseek_react_code_dev57_full50.txt": root
        / "appworld_020_root/experiments/outputs/simplified_react_code_agent/deepseek/deepseek-v3.2-terminus-exp-without-reasoning/dev57_full50/evaluations/dev57_full50.txt",
    }
    for name, src in evaluator_outputs.items():
        if src.exists():
            copy_file(src, output_dir / "results" / "appworld_official_dev57_evaluations" / name)

    write_supplement_readme(output_dir)
    return output_dir


def make_archive(output_dir: Path) -> Path:
    archive_path = output_dir.with_suffix(".tar.gz")
    if archive_path.exists():
        archive_path.unlink()
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(output_dir, arcname=output_dir.name)
    return archive_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        default="artifacts/rave2_emnlp2026_arr_anonymous_supplement",
        help="Directory to create. A .tar.gz archive is created next to it.",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output_dir = (root / args.output_dir).resolve()
    built = build(root, output_dir)
    archive = make_archive(built)
    print(f"Wrote {built.relative_to(root)}")
    print(f"Wrote {archive.relative_to(root)}")


if __name__ == "__main__":
    main()
