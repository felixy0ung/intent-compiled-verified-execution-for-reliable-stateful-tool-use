# AppWorld Official Agent Runner Attempt, 2026-05-05

This note records the attempt to run the official AppWorld repository agents as an
additional leaderboard-style baseline for the RAVE-2 AppWorld slice.

## Isolated Environment

- Environment: `<CONDA_ROOT>/envs/pctu-appworld-agents`
- Purpose: keep the latest AppWorld/appworld-agents stack separate from the working
  AppWorld 0.1.x evaluator environment.
- Main evaluator environment health after the attempt:
  `<CONDA_ROOT>/envs/pctu-appworld/bin/pip check` reports no broken
  requirements.
- Isolated official-agent environment health:
  `<CONDA_ROOT>/envs/pctu-appworld-agents/bin/pip check` reports no broken
  requirements.

## Repository And Package Stack

- Official repository clone: `third_party/appworld-latest`
- Commit: `a072b7a86e7c1d5b1d7175659d750ebb9b79f10a`
- Installed in the isolated environment:
  - `appworld 0.2.0.dev0`
  - `appworld-agents 0.1.0.dev0`
  - `pydantic 2.13.3`
- The first `pip install` attempt against `files.pythonhosted.org` failed while
  downloading `fastapi-0.136.1` metadata. Retrying with the Tsinghua PyPI mirror
  completed successfully.
- Import smoke passed:
  `from appworld_agents.code.simplified.run import run_experiment`.

## Historical Blocking Issue

The latest AppWorld package requires running:

```bash
<CONDA_ROOT>/envs/pctu-appworld-agents/bin/python -m appworld.cli install
```

to unpack the encrypted app/test bundles. This failed because the cloned bundle files are
Git LFS pointers, not real bundle files:

```text
Exception: File .../site-packages/appworld/.source/apps.bundle is a Git LFS pointer and not a bundle file.
```

Observed LFS pointers:

- `apps.bundle`: `sha256:88d21fc526c1655bb3eee4adfca78ccac793921e4506f28f734ecdb19af77a62`,
  expected size `193950`.
- `tests.bundle`: `sha256:04aa898cb015c53468c355d5ded662757c5234835a4de5cf4f7d7947bef159ec`,
  expected size `204426`.

`git-lfs 3.7.1` was installed only into the isolated official-agent environment, but:

```bash
timeout 180 env PATH=<CONDA_ROOT>/envs/pctu-appworld-agents/bin:$PATH \
  git -C third_party/appworld-latest lfs pull
```

timed out without downloading the LFS objects. Direct `curl` probes to GitHub raw/media
URLs also timed out after 30 seconds. PyPI does not publish `appworld-agents`; the latest
published `appworld` package visible on the mirror is `0.1.3.post1`, while the official
agent code lives in the GitHub repository and targets the newer development stack.

## Follow-up Resolution

The Git LFS blocker was later resolved by installing the LFS filters locally and pulling
the four bundle files explicitly with the `git-lfs` binary from
`<CONDA_ROOT>/envs/pctu-appworld-agents`. The latest AppWorld runner also requires
data version 0.2.0, so an isolated root was created at
`<PROJECT_ROOT>/appworld_020_root` without overwriting the 0.1.0 data used by
the active RAVE slice.

The follow-up records are `results/appworld_official_runner_smoke_20260506.md`,
`results/appworld_official_runner_dev10_20260506.md`, and
`results/appworld_official_runner_dev10_full50_20260506.md`. They verify:

- real LFS bundle files are available and unpackable,
- `appworld install --repo` and package-level `appworld install` complete,
- AppWorld 0.2.0 data downloads into the isolated root,
- `appworld verify tasks --include-only-first-n-tasks 1` passes,
- the official `simplified_react_code_agent` with DeepSeek-chat runs on one dev task and
  AppWorld's packaged evaluator reports 0.0 task completion,
- the same official runner executes a constrained AppWorld 0.2.0 `dev10` smoke and
  scores 0/10 under `max_steps=3`,
- the default-50-step official DeepSeek ReAct-code baseline reaches 90.0 task-goal /
  75.0 scenario-goal completion on `dev10_full50`, while deterministic RAVE and RAVE +
  DeepSeek-chat intent extraction reach 100.0 / 100.0 on the same small slice after four
  additional intent machines are registered.

## Result

The official repository agent runner is now executable in a 10-task setting, but no full
official AppWorld repository-agent or leaderboard-agent baseline has been completed. Do
not claim full official benchmark coverage from the small `dev10_full50` run alone.

The current AppWorld evidence remains:

- AppWorld's packaged evaluator verifies the active 72-task targeted slice outputs; see
  `results/appworld_expanded72_20260506.md`.
- Local and hosted direct-code, typed-intent-only, code-repair, and multi-step
  code-observation baselines cover the same 72-task targeted slice.
- This is stronger than a hand-rolled summary, but still not a full AppWorld
  leaderboard-agent comparison.
