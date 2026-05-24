# ICVE Anonymous Supplement

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
