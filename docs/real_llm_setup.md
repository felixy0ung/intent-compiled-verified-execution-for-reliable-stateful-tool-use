# Real LLM Pilot Setup

The current main method is **RAVE / Intent-Compiled Verified Execution**. The real-LLM
runner uses an OpenAI-compatible HTTP adapter and expects one of these servers:

- LM Studio: usually `http://127.0.0.1:1234/v1`
- llama.cpp server: commonly `http://127.0.0.1:8080/v1`
- Ollama OpenAI-compatible API: commonly `http://127.0.0.1:11434/v1`
- vLLM: commonly `http://127.0.0.1:8000/v1`

Recommended local models:

- `Qwen2.5-7B-Instruct` or `Qwen2.5-7B-Instruct-GGUF`
- `Llama-3.1-8B-Instruct` or a GGUF quantization

For a 12GB RTX 3080 Ti, use a 4-bit quantized 7B/8B model first. The current local smoke
results used `Qwen/Qwen2.5-3B-Instruct` through
`experiments/local_openai_transformers_server.py`.

## Healthcheck

```bash
python experiments/run_real_llm_ministore.py \
  --base-url http://127.0.0.1:1234/v1 \
  --model your-loaded-model \
  --healthcheck-only
```

## Real MiniStore run

```bash
python experiments/run_real_llm_ministore.py \
  --base-url http://127.0.0.1:1234/v1 \
  --model your-loaded-model \
  --methods react rave \
  --tasks-per-category 2 \
  --max-steps 8 \
  --output results/real_llm_ministore.csv
```

Start with two tasks per category. If JSON compliance is poor, lower temperature to `0`, use
a stronger instruct model, or enable the server's JSON/schema mode if available.

## Interpretation

This runner compares real-LLM ReAct, the old PCTU ablation, and RAVE on the same
MiniStore environment. It is still not a public benchmark, but it is the necessary bridge
between the stochastic simulator and ToolSandbox/AppWorld.

Current reference result:

`results/real_llm_ministore_qwen25_3b_rave_tpc2_v2.csv`

RAVE reached 1.0 success, 0 invalid tool calls, and 0 unsafe state changes in the small
2-tasks-per-category MiniStore run, while using fewer LLM calls and token proxy than ReAct
or PCTU.
