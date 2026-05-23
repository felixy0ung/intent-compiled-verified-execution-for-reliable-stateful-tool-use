# Intent-Compiled Verified Execution for Reliable Stateful Tool Use

This repository contains the code and summary-level artifacts for the paper
**"Intent-Compiled Verified Execution for Reliable Stateful Tool Use"**.

The method is **Intent-Compiled Verified Execution (ICVE)**. Some module names,
class names, and historical result paths still use `RAVE`; those names refer to
the same runtime lineage used during development.

## What Is Included

- `src/pctu_pilot/`: ICVE runtime, typed intent DSL, ToolSandbox binding, AppWorld
  binding, MiniStore diagnostic environment, and LLM client utilities.
- `experiments/`: runners for MiniStore, ToolSandbox, AppWorld slices, hosted
  OpenAI-compatible replications, and result summarization.
- `results/`: summary CSV/Markdown outputs and evaluator summaries used to support
  the paper tables.
- `paper/`: paper source, references, compiled PDF, and artifact manifest.
- `docs/`: setup notes for local/hosted LLM runs and ToolSandbox diagnostics.

## What Is Not Included

This public repository intentionally excludes:

- real API keys and private `.env` files;
- raw AppWorld task logs, database snapshots, access tokens, downloaded bundles, and
  protected AppWorld data;
- model weights, local conda environments, and machine-specific caches;
- internal submission/checklist files and local upload manifests.

To reproduce AppWorld experiments, obtain AppWorld through its official release channel
and follow its license and redistribution terms. To reproduce ToolSandbox experiments,
install ToolSandbox separately; this repository contains the ICVE binding and runner, not
a vendored ToolSandbox checkout.

## Quick Local Smoke Test

The MiniStore diagnostic has no external benchmark dependency:

```bash
python -m venv .venv
source .venv/bin/activate
python experiments/run_pilot.py
```

This writes summary files under `results/`.

## ToolSandbox Runs

Install ToolSandbox and place or symlink it at `third_party/ToolSandbox-main`, then run
against a local OpenAI-compatible model server:

```bash
PYTHONPATH=src python experiments/run_toolsandbox_kill_criteria.py \
  --base-url http://127.0.0.1:8000/v1 \
  --model Qwen/Qwen2.5-3B-Instruct \
  --methods react rave \
  --max-scenarios 30
```

For hosted OpenAI-compatible endpoints, copy one of the example environment files,
fill in credentials privately, and do not commit the copied file:

```bash
cp experiments/frontier_replication.env.example experiments/frontier_replication.env
source experiments/frontier_replication.env
./experiments/run_frontier_toolsandbox_replication.sh
```

## AppWorld Runs

Install AppWorld and download its data through the official tooling. Then run the
deterministic public stateful slice:

```bash
PYTHONPATH=src python experiments/run_appworld_rave_slice.py \
  --appworld-root /path/to/appworld/root \
  --agent deterministic
```

Hosted LLM intent extraction uses the same runner with `--agent llm-intent` plus
`FRONTIER_BASE_URL`, `FRONTIER_MODEL`, and `FRONTIER_API_KEY` supplied through your
private shell environment.

## Reproducing Paper Tables

The high-level artifact map is in `paper/artifact_manifest_rave2.md`. The summary
statistics used by the paper can be regenerated from the packaged summary files with:

```bash
PYTHONPATH=src python experiments/summarize_rave2_statistics.py
```

Some full benchmark rows require external packages and data that are not redistributed
here. The repository keeps summary outputs for auditability and provides the runner code
needed to regenerate them in a properly licensed local setup.

## Privacy and Security

Before publishing, this repository was built from a whitelist and scanned for common
secret formats, local absolute paths, private `.env` files, raw logs, and protected data
bundles. You can rerun the lightweight scanner with:

```bash
python scripts/scan_for_sensitive_info.py .
```

The scanner is not a substitute for manual review, but it catches the most common
accidental leaks.
