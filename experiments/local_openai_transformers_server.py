from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig


class OpenAICompatHandler(BaseHTTPRequestHandler):
    server: "OpenAICompatServer"

    def do_GET(self) -> None:
        if self.path.rstrip("/") == "/v1/models":
            self._write_json(
                {
                    "object": "list",
                    "data": [
                        {
                            "id": self.server.model_id,
                            "object": "model",
                            "created": int(time.time()),
                            "owned_by": "local",
                        }
                    ],
                }
            )
            return
        self._write_json({"error": "not found"}, status=404)

    def do_POST(self) -> None:
        if self.path.rstrip("/") != "/v1/chat/completions":
            self._write_json({"error": "not found"}, status=404)
            return

        try:
            request = self._read_json()
            messages = request.get("messages")
            if not isinstance(messages, list):
                raise ValueError("messages must be a list")
            max_tokens = int(request.get("max_tokens") or self.server.default_max_new_tokens)
            temperature = float(request.get("temperature") or 0.0)
            content, prompt_tokens, completion_tokens = self.server.generate(
                messages=messages,
                max_new_tokens=max_tokens,
                temperature=temperature,
            )
            self._write_json(
                {
                    "id": f"chatcmpl-local-{int(time.time() * 1000)}",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": self.server.model_id,
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": content},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": prompt_tokens + completion_tokens,
                    },
                }
            )
        except Exception as exc:  # noqa: BLE001
            self._write_json({"error": str(exc)}, status=500)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        if self.server.verbose:
            super().log_message(format, *args)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        data = self.rfile.read(length)
        parsed = json.loads(data.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("request body must be a JSON object")
        return parsed

    def _write_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class OpenAICompatServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        model_id: str,
        tokenizer: Any,
        model: Any,
        device: str,
        max_input_tokens: int,
        default_max_new_tokens: int,
        verbose: bool,
    ) -> None:
        super().__init__(server_address, OpenAICompatHandler)
        self.model_id = model_id
        self.tokenizer = tokenizer
        self.model = model
        self.device = device
        self.max_input_tokens = max_input_tokens
        self.default_max_new_tokens = default_max_new_tokens
        self.verbose = verbose

    def generate(
        self,
        messages: list[dict[str, Any]],
        max_new_tokens: int,
        temperature: float,
    ) -> tuple[str, int, int]:
        chat_messages = [
            {"role": str(message.get("role") or "user"), "content": str(message.get("content") or "")}
            for message in messages
        ]
        prompt = self.tokenizer.apply_chat_template(
            chat_messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        inputs = self.tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=self.max_input_tokens,
        ).to(self.device)
        prompt_tokens = int(inputs["input_ids"].shape[-1])
        do_sample = temperature > 0
        generate_kwargs: dict[str, Any] = {
            "max_new_tokens": max_new_tokens,
            "do_sample": do_sample,
            "pad_token_id": self.tokenizer.eos_token_id,
        }
        if do_sample:
            generate_kwargs["temperature"] = temperature
            generate_kwargs["top_p"] = 0.95

        with torch.inference_mode():
            output = self.model.generate(**inputs, **generate_kwargs)
        generated = output[0, prompt_tokens:]
        content = self.tokenizer.decode(generated, skip_special_tokens=True).strip()
        return content, prompt_tokens, int(generated.shape[-1])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="Qwen/Qwen2.5-3B-Instruct")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--load-in-4bit", action="store_true")
    parser.add_argument("--max-input-tokens", type=int, default=12000)
    parser.add_argument("--default-max-new-tokens", type=int, default=700)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    device = args.device
    if device == "cuda" and not torch.cuda.is_available():
        raise SystemExit("CUDA was requested but torch.cuda.is_available() is false.")
    dtype = torch.float16 if device == "cuda" else torch.float32

    quantization_config = None
    model_kwargs: dict[str, Any] = {"torch_dtype": dtype}
    if args.load_in_4bit:
        if device != "cuda":
            raise SystemExit("--load-in-4bit requires --device cuda.")
        quantization_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            llm_int8_enable_fp32_cpu_offload=True,
        )
        model_kwargs = {
            "torch_dtype": dtype,
            "quantization_config": quantization_config,
            # Accelerate calls `.to(cuda)` for single-device maps, which
            # bitsandbytes 4-bit modules reject. Keeping one tiny module on CPU
            # forces hook-based dispatch while leaving the model body on GPU.
            "device_map": {"": 0, "model.norm": "cpu"},
        }

    print(
        f"Loading {args.model} on {device} with dtype={dtype} load_in_4bit={args.load_in_4bit}...",
        flush=True,
    )
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForCausalLM.from_pretrained(args.model, **model_kwargs)
    if not args.load_in_4bit:
        model.to(device)
    model.eval()
    if device == "cuda":
        allocated = torch.cuda.memory_allocated() / (1024**3)
        reserved = torch.cuda.memory_reserved() / (1024**3)
        print(f"CUDA memory allocated={allocated:.2f}GB reserved={reserved:.2f}GB", flush=True)

    server = OpenAICompatServer(
        server_address=(args.host, args.port),
        model_id=args.model,
        tokenizer=tokenizer,
        model=model,
        device=device,
        max_input_tokens=args.max_input_tokens,
        default_max_new_tokens=args.default_max_new_tokens,
        verbose=args.verbose,
    )
    print(f"Serving OpenAI-compatible API at http://{args.host}:{args.port}/v1", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
