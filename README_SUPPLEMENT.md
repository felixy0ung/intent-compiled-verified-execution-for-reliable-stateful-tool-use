# ICVE Summary Artifact

This directory was derived from the anonymized, summary-level artifact for the paper
"Intent-Compiled Verified Execution for Reliable Stateful Tool Use" and then cleaned for
public GitHub release.

Included:

- `src/`: ICVE runtime, DSL, ToolSandbox binding, and AppWorld binding.
- `experiments/`: public runners, summarizers, and environment templates.
- `paper/`: LaTeX source, references, artifact manifest, and compiled PDF.
- `results/`: markdown summaries, CSV summaries, statistical intervals, and packaged-evaluator reports.

Excluded:

- Real API-key environment files (`*.env` without `.example`).
- AppWorld protected data, raw AppWorld task logs, database snapshots, access tokens,
  downloaded data bundles, and dataset-id files copied from protected data releases.
- Local conda environments, model caches, and machine-specific temporary files.

Absolute local paths in copied text files are replaced with `<PROJECT_ROOT>`,
`<CONDA_ROOT>`, or `<HOME>`.
